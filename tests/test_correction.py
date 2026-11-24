import pytest

from app.business import DomainIssue
from app.inputs import RATE_PROFILES
from app.modules.correction_pipeline import run_correction
from app.review.service import execute, execute_correction, review


def find(report, case_id):
    return next(case for case in report["cases"] if case["case"] == case_id)


def test_correction_preview_splits_clean_sample(clean):
    report = run_correction(clean, RATE_PROFILES["corrected"])
    case = find(report, "0001")
    assert case["status"] == "BLOCKED"  # 票据金额按旧费率开具，与更正额不符
    block_codes = [block["code"] for block in case["bill"]["blocks"]]
    assert block_codes == ["INVOICE_MISMATCH"]
    assert case["bill"]["amount_cents"] == 320
    assert case["invoice_cents"] == 240


def test_correction_carries_schedule_fingerprint(clean):
    report = run_correction(clean, RATE_PROFILES["corrected"])
    assert report["schedule"]["fingerprint"] == RATE_PROFILES["corrected"]["fingerprint"]
    assert "manifest" not in report  # 预览不入库，无运行清单


def test_gapped_schedule_blocks_release(clean):
    report = run_correction(clean, RATE_PROFILES["gapped"])
    assert report["balance"]["releasable"] is False
    assert report["balance"]["block_reasons"] == {"RATE_INTERVAL_MISSING": 1}


def test_invalid_stay_is_surfaced_as_case_status(dirty):
    report = run_correction(dirty, RATE_PROFILES["legacy"])
    assert find(report, "0003")["status"] == "INVALID_STAY"
    assert report["balance"]["releasable"] is False


def test_balance_conserves_rows(dirty):
    balance = run_correction(dirty, RATE_PROFILES["legacy"])["balance"]
    assert balance["input"] == balance["accepted"] + balance["isolated"] + balance["ignored"]


def test_legacy_and_correction_runs_coexist_without_overwrite(store, clean):
    legacy = execute(store, clean)
    corrected = execute_correction(store, clean, RATE_PROFILES["corrected"])
    assert legacy["id"] != corrected["id"]
    assert len(store.list()) == 2
    # 历史批次报告原样保留，仍是旧费率金额。
    assert find(legacy["report"], "0001")["measure"]["value"] == 240
    assert find(corrected["report"], "0001")["bill"]["amount_cents"] == 320


def test_same_source_and_schedule_rerun_is_idempotent(store, clean):
    first = execute_correction(store, clean, RATE_PROFILES["corrected"])
    second = execute_correction(store, clean, RATE_PROFILES["corrected"])
    assert first == second and len(store.list()) == 1


def test_same_source_different_schedule_creates_distinct_run(store, clean):
    a = execute_correction(store, clean, RATE_PROFILES["legacy"])
    b = execute_correction(store, clean, RATE_PROFILES["corrected"])
    c = execute_correction(store, clean, RATE_PROFILES["gapped"])
    assert len({a["id"], b["id"], c["id"]}) == 3
    assert len(store.list()) == 3


def test_lineage_records_prior_rate_and_traceable_delta(store, clean):
    legacy = execute(store, clean)
    review(
        store,
        legacy["id"],
        dict(revision=0, status="APPROVED", note="月初已签发批次"),
    )
    corrected = execute_correction(store, clean, RATE_PROFILES["corrected"])
    prior = corrected["report"]["lineage"]["prior_runs"]
    assert len(prior) == 1
    link = prior[0]
    assert link["run_id"] == legacy["id"] and link["status"] == "APPROVED"
    delta = link["deltas"]["0001"]
    assert delta == {"prior_cents": 240, "corrected_cents": 320, "delta_cents": 80}
    # 已签发的旧批次不受更正影响。
    assert store.load(legacy["id"])["status"] == "APPROVED"


def test_blocked_correction_cannot_be_approved(store, clean):
    run = execute_correction(store, clean, RATE_PROFILES["gapped"])
    with pytest.raises(DomainIssue, match="UNRESOLVED_ISSUES"):
        review(store, run["id"], dict(revision=0, status="APPROVED", note="试图挡签放行"))
    assert store.load(run["id"])["revision"] == 0


def test_releasable_correction_can_be_approved(store):
    # 构造票据金额与更正费率一致的数据源，验证可签发路径。
    from conftest import csv_data

    rows = [
        ["S1", "C1", "stay", "0", "100", "0", "0", "停时"],
        ["I1", "C1", "invoice", "0", "0", "0", "200", "票据"],
    ]
    data = csv_data(rows)
    schedule = RATE_PROFILES["legacy"]  # 100 分钟 = 60*1 + 40*3 = 180
    run = execute_correction(store, data, schedule)
    # 票据写 200 与计算 180 不符 -> 先挡签；改为 180 后可签发。
    assert run["report"]["balance"]["releasable"] is False
    rows[1][-2] = "180"
    good = csv_data(rows)
    run_ok = execute_correction(store, good, schedule)
    assert run_ok["report"]["balance"]["releasable"] is True
    approved = review(
        store, run_ok["id"], dict(revision=0, status="APPROVED", note="更正账单可签")
    )
    assert approved["status"] == "APPROVED"


def test_manifest_binds_source_and_schedule(store, clean):
    run = execute_correction(store, clean, RATE_PROFILES["corrected"])
    manifest = run["report"]["manifest"]
    assert manifest["kind"] == "CORRECTION"
    assert manifest["schedule_fingerprint"] == RATE_PROFILES["corrected"]["fingerprint"]
    assert manifest["run_id"] == run["id"]


def test_lineage_is_frozen_at_creation_and_accumulates_later(store, clean):
    first = execute_correction(store, clean, RATE_PROFILES["legacy"])
    # 重跑返回原批次，lineage 维持创建时快照。
    assert execute_correction(store, clean, RATE_PROFILES["legacy"]) == first
    second = execute_correction(store, clean, RATE_PROFILES["corrected"])
    third = execute_correction(store, clean, RATE_PROFILES["gapped"])
    assert len(first["report"]["lineage"]["prior_runs"]) == 0
    assert len(second["report"]["lineage"]["prior_runs"]) == 1
    # 第三个批次能追溯到同数据源的前两个（legacy 与 corrected）。
    prior_ids = {link["run_id"] for link in third["report"]["lineage"]["prior_runs"]}
    assert prior_ids == {first["id"], second["id"]}
