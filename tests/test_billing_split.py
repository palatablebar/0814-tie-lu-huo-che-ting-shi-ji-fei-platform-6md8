from app.rates.billing import guard_invoice, split_bill
from app.rates.schedule import canonical_schedule, legacy_schedule, parse_schedule


def pause(start, end):
    return {"start_min": start, "end_min": end}


def corrected_schedule():
    return parse_schedule(
        {
            "code": "STAY_RATE",
            "version": "2.0.0",
            "periods": [
                {
                    "start_min": 0,
                    "end_min": 120,
                    "tiers": [
                        {"width_min": 60, "rate_cents": 2},
                        {"width_min": None, "rate_cents": 4},
                    ],
                },
                {
                    "start_min": 120,
                    "end_min": None,
                    "tiers": [
                        {"width_min": 60, "rate_cents": 3},
                        {"width_min": None, "rate_cents": 6},
                    ],
                },
            ],
        }
    )


def gapped_schedule():
    return parse_schedule(
        {
            "code": "STAY_RATE",
            "version": "gap",
            "periods": [
                {"start_min": 0, "end_min": 100, "tiers": [{"width_min": None, "rate_cents": 1}]},
                {"start_min": 130, "end_min": None, "tiers": [{"width_min": None, "rate_cents": 2}]},
            ],
        }
    )


def test_overlapping_pauses_are_deducted_once():
    # 两段暂停交叠于 [15,25)，并集只有 30 分钟，不能扣两次。
    bill = split_bill((0, 160), [pause(5, 25), pause(15, 35)], 0, legacy_schedule())
    assert bill["paused_min"] == 30
    assert bill["billable_min"] == 130
    assert sum(segment["minutes"] for segment in bill["segments"]) == 130


def test_pause_outside_stay_is_clipped():
    bill = split_bill((100, 140), [pause(80, 115), pause(135, 150)], 0, legacy_schedule())
    assert bill["paused_min"] == 20
    assert bill["billable_min"] == 20


def test_free_minutes_used_once_across_rate_periods():
    # 免计 70 分钟跨生效区间只冲抵一次，不随费段重置。
    bill = split_bill((0, 160), [], 70, corrected_schedule())
    assert bill["free_used_min"] == 70
    assert bill["billable_min"] == 90
    assert sum(segment["minutes"] for segment in bill["segments"]) == 90
    # 第一个计费片段从第 70 分钟开始。
    assert bill["segments"][0]["start_min"] == 70


def test_free_minutes_never_exceed_billable_time():
    bill = split_bill((0, 50), [], 999, legacy_schedule())
    assert bill["free_used_min"] == 50
    assert bill["billable_min"] == 0
    assert bill["segments"] == []
    assert bill["amount_cents"] == 0


def test_segments_record_key_minutes_rate_and_amount():
    bill = split_bill((0, 160), [pause(5, 35)], 10, corrected_schedule())
    for segment in bill["segments"]:
        assert segment["key"]
        assert segment["minutes"] == segment["end_min"] - segment["start_min"]
        assert segment["amount_cents"] == segment["minutes"] * segment["rate_cents"]
    assert [s["rate_cents"] for s in bill["segments"]] == [2, 4, 3]
    # 分段金额之和等于总额。
    assert sum(s["amount_cents"] for s in bill["segments"]) == bill["amount_cents"]


def test_segment_sum_equals_total_under_legacy_tiers():
    bill = split_bill((0, 160), [pause(5, 35)], 10, legacy_schedule())
    assert bill["amount_cents"] == 240
    assert bill["segments"][0]["rate_cents"] == 1
    assert bill["segments"][1]["rate_cents"] == 3


def test_rate_interval_missing_blocks_and_is_listed():
    bill = split_bill((0, 160), [], 0, gapped_schedule())
    codes = [block["code"] for block in bill["blocks"]]
    assert codes == ["RATE_INTERVAL_MISSING"]
    assert bill["blocks"][0]["at_min"] == 100
    # 缺口前的分段仍可查，缺口后的分钟不计入金额。
    assert sum(s["minutes"] for s in bill["segments"]) == 100


def test_invoice_mismatch_is_recorded_as_block():
    bill = split_bill((0, 160), [], 0, legacy_schedule())
    blocks = guard_invoice(bill, invoice_amount=1, record="STAY-1")
    assert [b["code"] for b in blocks] == ["INVOICE_MISMATCH"]
    assert blocks[0]["record"] == "STAY-1"
    assert blocks[0]["expected_cents"] == 1
    assert blocks[0]["delta_cents"] == bill["amount_cents"] - 1


def test_matching_invoice_has_no_block():
    bill = split_bill((0, 160), [], 0, legacy_schedule())
    assert guard_invoice(bill, bill["amount_cents"], "STAY-1") == []


def test_flat_rate_schedule():
    schedule = canonical_schedule(
        code="FLAT", version="1", tiers=({"width_min": None, "rate_cents": 7},)
    )
    bill = split_bill((0, 30), [], 0, schedule)
    assert bill["amount_cents"] == 210
    assert len(bill["segments"]) == 1 and bill["segments"][0]["rate_cents"] == 7


def test_zero_rate_segments_are_kept_for_audit():
    schedule = canonical_schedule(
        code="ZERO", version="1", tiers=({"width_min": None, "rate_cents": 0},)
    )
    bill = split_bill((0, 20), [], 0, schedule)
    assert bill["amount_cents"] == 0
    assert bill["segments"][0]["minutes"] == 20


def test_pause_minutes_do_not_consume_tier_capacity():
    # 停时 0-100，暂停 30-90（60 分钟），实际计费为 [0,30) 与 [90,100) 共 40 分钟。
    # 全部落在第一档（60 分钟内，单价 1），暂停不占用档位额度，因此不会跳到第二档。
    bill = split_bill((0, 100), [pause(30, 90)], 0, legacy_schedule())
    assert bill["paused_min"] == 60 and bill["billable_min"] == 40
    assert [segment["rate_cents"] for segment in bill["segments"]] == [1, 1]
    assert bill["amount_cents"] == 40


def test_tier_advances_across_pause_gap():
    # 计费 70 分钟被暂停切成两段，档位仍应累计到第二档。
    # 停时 0-100，暂停 60-90：计费 [0,60)=60 分钟第一档，[90,100)=10 分钟第二档。
    bill = split_bill((0, 100), [pause(60, 90)], 0, legacy_schedule())
    assert [segment["rate_cents"] for segment in bill["segments"]] == [1, 3]
    assert bill["amount_cents"] == 60 + 30


def test_free_minutes_inside_paused_window_are_not_wasted():
    # 免计分钟只冲抵实际计费片段：暂停 0-90 后仅剩 [90,100) 10 分钟可冲抵。
    bill = split_bill((0, 100), [pause(0, 90)], 50, legacy_schedule())
    assert bill["free_used_min"] == 10
    assert bill["billable_min"] == 0 and bill["amount_cents"] == 0


def test_pause_covering_rate_gap_avoids_missing_block():
    # 缺口 100-130 恰好被暂停覆盖时没有计费分钟落入缺口，不应挡签。
    schedule = gapped_schedule()
    bill = split_bill((0, 200), [pause(100, 130)], 0, schedule)
    assert bill["blocks"] == []
    assert [(s["start_min"], s["end_min"], s["rate_cents"]) for s in bill["segments"]] == [
        (0, 100, 1),
        (130, 200, 2),
    ]
    assert bill["amount_cents"] == 100 + 140


def test_gap_inside_piece_reports_first_missing_minute_once():
    schedule = gapped_schedule()
    bill = split_bill((0, 200), [], 0, schedule)
    assert [block["code"] for block in bill["blocks"]] == ["RATE_INTERVAL_MISSING"]
    assert bill["blocks"][0]["at_min"] == 100
    # 缺口前的分段保留可查，缺口及其后分钟不产生金额。
    assert sum(s["minutes"] for s in bill["segments"]) == 100
