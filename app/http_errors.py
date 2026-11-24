from flask import jsonify

LABELS = {
    "FILE_TOO_LARGE": "文件超过 256 KiB",
    "FILE_EMPTY": "文件没有内容",
    "FILE_BLANK": "文件只有空白",
    "HEADER_ONLY": "文件只有标题行",
    "HEADER_MISMATCH": "列名与字段字典不一致",
    "ENCODING_INVALID": "请使用 UTF-8 CSV",
    "CSV_MALFORMED": "CSV 引号或行格式异常",
    "ROW_LIMIT": "文件超过 2000 行",
    "FILE_REQUIRED": "请选择 CSV 文件",
    "RUN_NOT_FOUND": "批次不存在",
    "REVIEW_FIELDS": "请填写 3 至 200 字复核意见",
    "STALE_REVIEW": "批次已更新，请刷新",
    "RUN_FINALIZED": "批次已签发",
    "UNRESOLVED_ISSUES": "存在待处理差异",
    "SAMPLE_UNKNOWN": "样例不存在",
    "STAGE_UNKNOWN": "处理阶段不存在",
    "RATE_PROFILE_UNKNOWN": "费率档案不存在",
    "RATE_FILE_TOO_LARGE": "费率表超过 256 KiB",
    "RATE_FILE_EMPTY": "费率表没有内容",
    "RATE_ENCODING_INVALID": "费率表请使用 UTF-8 JSON",
    "RATE_JSON_MALFORMED": "费率表 JSON 格式异常",
    "RATE_SHAPE": "费率表结构应为对象",
    "RATE_CODE_INVALID": "费率表缺少有效的代码",
    "RATE_VERSION_INVALID": "费率表缺少有效的版本号",
    "RATE_PERIODS_EMPTY": "费率表至少需要一个生效区间",
    "RATE_PERIOD_START_INVALID": "费率生效区间起点无效",
    "RATE_PERIOD_END_INVALID": "费率生效区间终点无效",
    "RATE_PERIOD_OVERLAP": "费率生效区间重叠或顺序错误",
    "RATE_PERIOD_ORDER": "开放终点的生效区间必须位于末尾",
    "RATE_TIERS_EMPTY": "费率生效区间至少需要一个档位",
    "RATE_TIER_SHAPE": "费率档位结构无效",
    "RATE_TIER_WIDTH_INVALID": "费率档位宽度须为正整数或留空",
    "RATE_TIER_RATE_INVALID": "费率单价须为非负整数",
    "RATE_TIER_MULTIPLE_OPEN": "一个生效区间只能有一个开放档位",
    "RATE_TIER_NO_OPEN": "费率生效区间缺少开放档位，深处费率缺失",
}


def response(error):
    code = error.code
    status = (
        404
        if code in {"RUN_NOT_FOUND", "SAMPLE_UNKNOWN", "STAGE_UNKNOWN"}
        else (
            409
            if code in {"STALE_REVIEW", "RUN_FINALIZED", "UNRESOLVED_ISSUES"}
            else 413 if code == "FILE_TOO_LARGE" else 422
        )
    )
    return jsonify(code=code, message=LABELS.get(code, code)), status
