"""费率表的解析、校验、规范化与指纹。

费率表描述若干个在分钟轴上首尾相接的生效区间（period）。每个生效区间
内部再按计费分钟的累计顺序划分档位（tier），费率单位为「分/分钟」。

更正费率时发布一张新版本费率表；费率表是不可变数据，解析后得到规范化
结构与稳定指纹，供运行批次引用，保证同源重跑金额一致、历史批次不被覆盖。
"""

import json
from hashlib import sha256

# 现行规则的初始费率表：前 60 分钟 1 分/分，接下来 60 分钟 3 分/分，
# 其余 5 分/分。与历史阶梯计费保持一致，保证旧样例结论不变。
LEGACY_TIERS = (
    {"width_min": 60, "rate_cents": 1},
    {"width_min": 60, "rate_cents": 3},
    {"width_min": None, "rate_cents": 5},
)
LEGACY_SCHEDULE_CODE = "STAY_RATE"
LEGACY_SCHEDULE_VERSION = "1.0.0"


class RateScheduleError(ValueError):
    """费率表结构不合法，``code`` 为可登记的原因码。"""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _is_int(value):
    # 拒绝 bool 与浮点，只接受非负整数。
    return type(value) is int and value >= 0


def canonical_schedule(code=LEGACY_SCHEDULE_CODE,
                       version=LEGACY_SCHEDULE_VERSION,
                       tiers=LEGACY_TIERS,
                       start_min=0):
    """由可信的内置参数构造规范化费率表（不做来源校验）。"""
    periods = (
        {
            "start_min": int(start_min),
            "end_min": None,
            "tiers": [
                {
                    "width_min": None if tier["width_min"] is None else int(tier["width_min"]),
                    "rate_cents": int(tier["rate_cents"]),
                }
                for tier in tiers
            ],
        },
    )
    schedule = {"code": code, "version": version, "periods": list(periods)}
    return _finalize(schedule)


def legacy_schedule():
    return canonical_schedule()


def parse_schedule(raw):
    """解析外部提交的费率表 JSON 字节/字符串/字典并规范化。

    任何结构问题都抛出 :class:`RateScheduleError`，原因码可直接登记。
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise RateScheduleError("RATE_ENCODING_INVALID") from error
    if isinstance(raw, str):
        if not raw.strip():
            raise RateScheduleError("RATE_FILE_EMPTY")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RateScheduleError("RATE_JSON_MALFORMED") from error
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise RateScheduleError("RATE_SHAPE")
    schedule = _validate(payload)
    return _finalize(schedule)


def _validate(payload):
    if not isinstance(payload, dict):
        raise RateScheduleError("RATE_SHAPE")
    code = payload.get("code")
    version = payload.get("version")
    if not isinstance(code, str) or not code.strip():
        raise RateScheduleError("RATE_CODE_INVALID")
    if not isinstance(version, str) or not version.strip():
        raise RateScheduleError("RATE_VERSION_INVALID")
    periods = payload.get("periods")
    if not isinstance(periods, list) or not periods:
        raise RateScheduleError("RATE_PERIODS_EMPTY")
    cleaned = []
    cursor = None
    for index, period in enumerate(periods):
        start = period.get("start_min") if isinstance(period, dict) else None
        end = period.get("end_min") if isinstance(period, dict) else None
        if not _is_int(start):
            raise RateScheduleError("RATE_PERIOD_START_INVALID")
        if end is not None and (not _is_int(end) or end <= start):
            raise RateScheduleError("RATE_PERIOD_END_INVALID")
        if cursor is not None and start < cursor:
            # 生效区间重叠或乱序属于费率表结构错误，解析即拒。
            raise RateScheduleError("RATE_PERIOD_OVERLAP")
        # start > cursor 的覆盖缺口允许登记，计费时按 RATE_INTERVAL_MISSING 挡签。
        tiers = period.get("tiers") if isinstance(period, dict) else None
        if not isinstance(tiers, list) or not tiers:
            raise RateScheduleError("RATE_TIERS_EMPTY")
        clean_tiers = []
        open_seen = False
        for tier in tiers:
            if not isinstance(tier, dict):
                raise RateScheduleError("RATE_TIER_SHAPE")
            width = tier.get("width_min")
            rate = tier.get("rate_cents")
            if width is not None and (not _is_int(width) or width == 0):
                raise RateScheduleError("RATE_TIER_WIDTH_INVALID")
            if not _is_int(rate):
                raise RateScheduleError("RATE_TIER_RATE_INVALID")
            if width is None:
                if open_seen:
                    raise RateScheduleError("RATE_TIER_MULTIPLE_OPEN")
                open_seen = True
            clean_tiers.append({"width_min": width, "rate_cents": rate})
        if not open_seen:
            # 每个生效区间必须有一个开放档，否则该区间深处会出现费率缺失。
            raise RateScheduleError("RATE_TIER_NO_OPEN")
        cleaned.append({"start_min": start, "end_min": end, "tiers": clean_tiers})
        cursor = end
        if cursor is None:
            if index != len(periods) - 1:
                raise RateScheduleError("RATE_PERIOD_ORDER")
            break
    return {"code": code.strip(), "version": version.strip(), "periods": cleaned}


def _finalize(schedule):
    schedule["fingerprint"] = fingerprint(schedule)
    return schedule


def fingerprint(schedule):
    """对规范化（去掉指纹自身）的费率表计算稳定指纹。"""
    body = {
        "code": schedule["code"],
        "version": schedule["version"],
        "periods": [
            {
                "start_min": period["start_min"],
                "end_min": period["end_min"],
                "tiers": [
                    {
                        "width_min": tier["width_min"],
                        "rate_cents": tier["rate_cents"],
                    }
                    for tier in period["tiers"]
                ],
            }
            for period in schedule["periods"]
        ],
    }
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()
