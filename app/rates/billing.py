"""按实际计费区间拆分可签账单。

约定（与字段字典一致，分钟段左闭右开）：

1. 暂停段先剪裁到停时区间再合并；暂停与停时交叠的部分只扣一次，
   暂停段之间的重叠经合并后不会重复扣除。
2. 免计分钟是整笔停时的额度，跨费率区间只使用一次，不随费率段重置：
   从扣费起点开始按分钟顺序冲抵，扣完为止。
3. 剩余计费分钟按费率表的生效区间（period）与区间内档位（tier）切分，
   每个分段记录键、分钟、费率、金额，金额 = 分钟 × 费率。
4. 分段金额之和必须等于账单总额；若费率表无法覆盖整个停时（费率区间
   缺失），登记阻断原因，该分组不得签账。
"""

from app.business import intervals, subtract


def _merge_pauses(stay, pauses):
    left, right = stay
    clipped = (
        (max(left, row["start_min"]), min(right, row["end_min"])) for row in pauses
    )
    return [(a, b) for a, b in intervals(clipped) if b > a]


def _consume_free(pieces, free_min):
    """跨片段冲抵免计分钟，返回剩余计费片段与实际使用的免计分钟。"""
    remaining = max(0, free_min)
    used = 0
    kept = []
    for start, end in pieces:
        if remaining <= 0:
            kept.append((start, end))
            continue
        length = end - start
        if length <= remaining:
            remaining -= length
            used += length
        else:
            kept.append((start + remaining, end))
            used += remaining
            remaining = 0
    return kept, used


class RateCursor:
    """沿分钟轴推进，定位某一分钟所属的生效区间、档位与费率。

    档位按「生效区间内已计费分钟」推进，跨生效区间时归零；免计分钟不
    经过游标，因此不会消耗任何档位额度。
    """

    def __init__(self, schedule, stay_end):
        self.schedule = schedule
        self.stay_end = stay_end
        self.period_index = 0
        self.tier_index = 0
        self.tier_used = 0  # 当前档位已计费分钟。

    def _period(self):
        if self.period_index >= len(self.schedule["periods"]):
            return None
        return self.schedule["periods"][self.period_index]

    def locate(self, minute):
        period = self._period()
        if period is None or minute < period["start_min"]:
            return None
        # 顺移到覆盖 minute 的生效区间；若下一区间起点晚于 minute，
        # 说明中间存在费率缺口（费率区间缺失）。
        while (
            period is not None
            and period["end_min"] is not None
            and minute >= period["end_min"]
        ):
            self.period_index += 1
            self.tier_index = 0
            self.tier_used = 0
            period = self._period()
        if period is None or minute < period["start_min"]:
            return None
        # 顺移到覆盖当前已计费量的档位。
        tier = period["tiers"][self.tier_index]
        while tier["width_min"] is not None and self.tier_used >= tier["width_min"]:
            self.tier_index += 1
            self.tier_used = 0
            tier = period["tiers"][self.tier_index]
        period_end = self.stay_end if period["end_min"] is None else period["end_min"]
        if tier["width_min"] is None:
            tier_end = period_end
        else:
            tier_end = min(period_end, minute + (tier["width_min"] - self.tier_used))
        return {
            "period": period,
            "tier": tier,
            "rate_cents": tier["rate_cents"],
            "boundary": min(period_end, tier_end),
        }

    def advance(self, minutes):
        self.tier_used += minutes


def split_bill(stay, pauses, free_min, schedule):
    """生成可签账单的分段明细与汇总。

    返回字典包含暂停/免计扣减证据、``segments`` 分段列表以及阻断列表
    ``blocks``。``blocks`` 非空时调用方必须挡签。
    """
    left, right = stay
    duration = right - left
    pause_union = _merge_pauses(stay, pauses)
    paused_min = sum(b - a for a, b in pause_union)
    pieces, free_used = _consume_free(subtract([stay], pause_union), free_min)
    billable_min = sum(b - a for a, b in pieces)

    segments = []
    blocks = []
    cursor = RateCursor(schedule, right)
    missing_reported = None

    for piece_start, piece_end in pieces:
        at = piece_start
        while at < piece_end:
            located = cursor.locate(at)
            if located is None:
                # 费率区间缺失：登记一次并停止该笔后续切分。
                if missing_reported != at:
                    blocks.append(
                        {
                            "code": "RATE_INTERVAL_MISSING",
                            "at_min": at,
                            "detail": "费率区间未覆盖该计费分钟",
                        }
                    )
                    missing_reported = at
                at = piece_end
                break
            seg_end = min(piece_end, located["boundary"])
            minutes = seg_end - at
            period = located["period"]
            segments.append(
                {
                    "key": f"{period['start_min']}:{located['rate_cents']}:{len(segments) + 1}",
                    "period_start_min": period["start_min"],
                    "period_end_min": period["end_min"],
                    "start_min": at,
                    "end_min": seg_end,
                    "minutes": minutes,
                    "rate_cents": located["rate_cents"],
                    "amount_cents": minutes * located["rate_cents"],
                }
            )
            cursor.advance(minutes)
            at = seg_end

    total = sum(segment["amount_cents"] for segment in segments)
    summed_minutes = sum(segment["minutes"] for segment in segments)
    if not blocks and summed_minutes != billable_min:
        blocks.append(
            {
                "code": "SEGMENT_MINUTES_MISMATCH",
                "at_min": None,
                "detail": "分段分钟之和与计费分钟不符",
            }
        )
    return {
        "duration_min": duration,
        "paused_min": paused_min,
        "free_min": free_min,
        "free_used_min": free_used,
        "billable_min": billable_min,
        "segments": segments,
        "amount_cents": total,
        "blocks": blocks,
    }


def guard_invoice(bill, invoice_amount, record):
    """核对分段相加与票据金额，不符则追加一条阻断记录。"""
    if bill["blocks"]:
        return bill["blocks"]
    if bill["amount_cents"] != invoice_amount:
        bill["blocks"].append(
            {
                "code": "INVOICE_MISMATCH",
                "at_min": None,
                "record": record,
                "detail": "分段金额之和与票据金额不符",
                "expected_cents": invoice_amount,
                "actual_cents": bill["amount_cents"],
                "delta_cents": bill["amount_cents"] - invoice_amount,
            }
        )
    return bill["blocks"]
