from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic

from app.business import DomainIssue
from app.config import CORRECTION_RULE_VERSION, RULE_VERSION
from app.modules.correction_pipeline import run_correction
from app.modules.pipeline import run


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _source_fingerprint(data):
    return sha256(data).hexdigest()


def execute(store, data):
    start = monotonic()
    fingerprint = _source_fingerprint(data)
    run_id = sha256(f"{RULE_VERSION}:{fingerprint}".encode()).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != "RUN_NOT_FOUND":
            raise
    report = run(data)
    report["manifest"] = _manifest(
        run_id, fingerprint, RULE_VERSION, len(data), start, kind="LEGACY"
    )
    return store.register(run_id, report)


def execute_correction(store, data, schedule):
    """以指定费率表重算并登记一个更正批次。

    运行编号同时绑定数据源指纹与费率表指纹：同源不同费率表必然产生不同
    编号，已存在的批次原样返回，绝不覆盖旧版或丢失记录。
    """
    start = monotonic()
    fingerprint = _source_fingerprint(data)
    run_id = sha256(
        f"{CORRECTION_RULE_VERSION}:{fingerprint}:{schedule['fingerprint']}".encode()
    ).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != "RUN_NOT_FOUND":
            raise
    report = run_correction(data, schedule)
    report["lineage"] = _lineage(store, fingerprint, report)
    report["manifest"] = _manifest(
        run_id,
        fingerprint,
        CORRECTION_RULE_VERSION,
        len(data),
        start,
        kind="CORRECTION",
        schedule_code=schedule["code"],
        schedule_version=schedule["version"],
        schedule_fingerprint=schedule["fingerprint"],
    )
    return store.register(run_id, report)


def _manifest(run_id, fingerprint, version, size, start, *, kind, **extra):
    manifest = dict(
        sha256=fingerprint,
        version=version,
        created=now(),
        duration_ms=round((monotonic() - start) * 1000, 3),
        bytes=size,
        run_id=run_id,
        kind=kind,
    )
    manifest.update(extra)
    return manifest


def _amount_by_case(report):
    amounts = {}
    for case in report.get("cases", []):
        bill = case.get("bill")
        if bill is not None:
            amounts[case["case"]] = bill["amount_cents"]
        elif "measure" in case and case["measure"] is not None:
            amounts[case["case"]] = case["measure"]["value"]
    return amounts


def _lineage(store, fingerprint, correction_report):
    """找出同数据源的历史批次，按业务组保留原费率金额与差额，便于追责。"""
    links = []
    new_amounts = _amount_by_case(correction_report)
    for item in store.list():
        prior = store.load(item["id"])
        prior_report = prior["report"]
        if prior_report.get("manifest", {}).get("sha256") != fingerprint:
            continue
        prior_amounts = _amount_by_case(prior_report)
        deltas = {}
        for case_id, new_amount in sorted(new_amounts.items()):
            if case_id in prior_amounts and prior_amounts[case_id] is not None:
                deltas[case_id] = {
                    "prior_cents": prior_amounts[case_id],
                    "corrected_cents": new_amount,
                    "delta_cents": new_amount - prior_amounts[case_id],
                }
        links.append(
            {
                "run_id": item["id"],
                "kind": prior_report.get("manifest", {}).get("kind", "LEGACY"),
                "status": prior["status"],
                "revision": prior["revision"],
                "rule_version": prior_report.get("manifest", {}).get("version"),
                "deltas": deltas,
            }
        )
    return {"source_sha256": fingerprint, "prior_runs": links}


def review(store, run_id, values):
    if not isinstance(values, dict):
        raise DomainIssue("REVIEW_FIELDS")
    revision, status, note = (values.get(key) for key in ("revision", "status", "note"))
    if (
        type(revision) is not int
        or revision < 0
        or status not in ("APPROVED", "HELD")
        or not isinstance(note, str)
        or not (3 <= len(note.strip()) <= 200)
    ):
        raise DomainIssue("REVIEW_FIELDS")
    current = store.load(run_id)
    if revision != current["revision"]:
        raise DomainIssue("STALE_REVIEW")
    if current["status"] == "APPROVED":
        raise DomainIssue("RUN_FINALIZED")
    if status == "APPROVED" and not current["report"]["balance"]["releasable"]:
        raise DomainIssue("UNRESOLVED_ISSUES")
    return store.revise(run_id, revision, status, note.strip(), now())
