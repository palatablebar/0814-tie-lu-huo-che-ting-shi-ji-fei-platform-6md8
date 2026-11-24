import json

from flask import request

from app.business import DomainIssue
from app.config import MAX_FILE, ROOT
from app.rates.schedule import (
    LEGACY_SCHEDULE_CODE,
    LEGACY_SCHEDULE_VERSION,
    RateScheduleError,
    canonical_schedule,
    parse_schedule,
)

SAMPLES = {
    "dirty": "incoming.csv",
    "clean": "ready.csv",
    "corrected_ready": "corrected_ready.csv",
}

# 内置费率档案：legacy 与历史阶梯一致；corrected 演示回溯到月初的费率更正，
# 在分钟 120 处切换生效区间；gapped 在 100–130 分钟留下费率缺口用于挡签演示。
RATE_PROFILE_FILES = {
    "legacy": None,
    "corrected": "rate_corrected.json",
    "gapped": "rate_gap.json",
}


def _load_profiles():
    profiles = {
        "legacy": canonical_schedule(
            LEGACY_SCHEDULE_CODE, LEGACY_SCHEDULE_VERSION
        )
    }
    for name, filename in RATE_PROFILE_FILES.items():
        if filename is None:
            continue
        raw = (ROOT / "sample_data" / filename).read_text(encoding="utf-8")
        profiles[name] = parse_schedule(json.loads(raw))
    return profiles


RATE_PROFILES = _load_profiles()


def read_input():
    sample = request.form.get("sample")
    if sample is not None:
        if sample not in SAMPLES:
            raise DomainIssue("SAMPLE_UNKNOWN")
        return (ROOT / "sample_data" / SAMPLES[sample]).read_bytes()
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        raise DomainIssue("FILE_REQUIRED")
    value = uploaded.stream.read(MAX_FILE + 1)
    if len(value) > MAX_FILE:
        raise DomainIssue("FILE_TOO_LARGE")
    return value


def read_schedule():
    """读取费率表：rate_profile 内置档案或 rate_file 上传，二选一。"""
    profile = request.form.get("rate_profile")
    uploaded = request.files.get("rate_file")
    if uploaded is not None and uploaded.filename:
        raw = uploaded.stream.read(MAX_FILE + 1)
        if len(raw) > MAX_FILE:
            raise DomainIssue("RATE_FILE_TOO_LARGE")
        try:
            return parse_schedule(raw)
        except RateScheduleError as error:
            raise DomainIssue(error.code) from error
    if profile is not None:
        if profile not in RATE_PROFILES:
            raise DomainIssue("RATE_PROFILE_UNKNOWN")
        return RATE_PROFILES[profile]
    # 缺省沿用历史费率，保证不传费率表时行为可预期。
    return RATE_PROFILES["legacy"]
