import json

import pytest

from app.rates.schedule import (
    LEGACY_SCHEDULE_VERSION,
    RateScheduleError,
    legacy_schedule,
    parse_schedule,
)


def period(start, end, tiers):
    return {"start_min": start, "end_min": end, "tiers": tiers}


def tier(width, rate):
    return {"width_min": width, "rate_cents": rate}


def schedule(periods, code="STAY_RATE", version="9.0.0"):
    return {"code": code, "version": version, "periods": periods}


def test_legacy_schedule_matches_historical_tiers():
    legacy = legacy_schedule()
    assert legacy["version"] == LEGACY_SCHEDULE_VERSION
    assert legacy["periods"][0]["start_min"] == 0
    assert legacy["periods"][0]["end_min"] is None
    assert [(t["width_min"], t["rate_cents"]) for t in legacy["periods"][0]["tiers"]] == [
        (60, 1),
        (60, 3),
        (None, 5),
    ]


def test_parse_accepts_bytes_with_bom():
    raw = ("﻿" + json.dumps(schedule([period(0, None, [tier(None, 1)])]))).encode()
    parsed = parse_schedule(raw)
    assert parsed["code"] == "STAY_RATE" and len(parsed["fingerprint"]) == 64


def test_parse_accepts_dict_and_string():
    payload = schedule([period(0, None, [tier(None, 2)])])
    assert parse_schedule(payload)["fingerprint"] == parse_schedule(json.dumps(payload))[
        "fingerprint"
    ]


def test_fingerprint_is_stable_and_order_independent_for_tiers():
    a = schedule([period(0, None, [tier(30, 1), tier(None, 2)])])
    b = json.loads(json.dumps(a))
    assert parse_schedule(a)["fingerprint"] == parse_schedule(b)["fingerprint"]


def test_fingerprint_changes_when_rate_changes():
    a = parse_schedule(schedule([period(0, None, [tier(None, 1)])]))
    b = parse_schedule(schedule([period(0, None, [tier(None, 2)])]))
    assert a["fingerprint"] != b["fingerprint"]


@pytest.mark.parametrize(
    "payload,code",
    [
        ([], "RATE_SHAPE"),
        (schedule([period(0, None, [tier(None, 1)])], code=" "), "RATE_CODE_INVALID"),
        (schedule([period(0, None, [tier(None, 1)])], version=""), "RATE_VERSION_INVALID"),
        ({"code": "x", "version": "1", "periods": []}, "RATE_PERIODS_EMPTY"),
        (schedule([period(-1, None, [tier(None, 1)])]), "RATE_PERIOD_START_INVALID"),
        (schedule([period(5, 5, [tier(None, 1)])]), "RATE_PERIOD_END_INVALID"),
        (
            schedule(
                [
                    period(0, 10, [tier(None, 1)]),
                    period(5, None, [tier(None, 1)]),
                ]
            ),
            "RATE_PERIOD_OVERLAP",
        ),
        (schedule([period(0, 10, [])]), "RATE_TIERS_EMPTY"),
        (schedule([period(0, None, [tier(0, 1)])]), "RATE_TIER_WIDTH_INVALID"),
        (schedule([period(0, None, [tier(None, -1)])]), "RATE_TIER_RATE_INVALID"),
        (
            schedule([period(0, None, [tier(None, 1), tier(None, 2)])]),
            "RATE_TIER_MULTIPLE_OPEN",
        ),
        (schedule([period(0, 10, [tier(5, 1)])]), "RATE_TIER_NO_OPEN"),
    ],
)
def test_invalid_schedules_are_rejected(payload, code):
    with pytest.raises(RateScheduleError, match=code):
        parse_schedule(payload)


def test_open_ended_period_must_be_last():
    payload = schedule(
        [period(0, None, [tier(None, 1)]), period(10, None, [tier(None, 1)])]
    )
    with pytest.raises(RateScheduleError, match="RATE_PERIOD_ORDER"):
        parse_schedule(payload)


def test_coverage_gap_is_allowed_at_parse_time():
    # 缺口不是结构错误，留待计费阶段挡签。
    payload = schedule(
        [period(0, 100, [tier(None, 1)]), period(130, None, [tier(None, 2)])]
    )
    parsed = parse_schedule(payload)
    assert parsed["periods"][1]["start_min"] == 130


@pytest.mark.parametrize("raw", [b"", "   ", b"\xef\xbb\xbf"])
def test_empty_inputs(raw):
    with pytest.raises(RateScheduleError, match="RATE_FILE_EMPTY"):
        parse_schedule(raw)


def test_malformed_json_and_encoding():
    with pytest.raises(RateScheduleError, match="RATE_JSON_MALFORMED"):
        parse_schedule("{not json")
    with pytest.raises(RateScheduleError, match="RATE_ENCODING_INVALID"):
        parse_schedule(b"\xff\xfe{")
