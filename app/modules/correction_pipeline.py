"""费率更正运行流水线。

与历史流水线并行存在：历史批次保持原费率与原报告，更正批次携带费率表
指纹、分段账单、阻断记录与对账结果，二者共用同一套批次存储但运行编号
不同，互不覆盖。
"""

from collections import Counter

from app.business import DomainIssue
from app.intake.service import inspect
from app.modules.grouping import case_groups
from app.rates.correction import build_case_bill, case_status


def evaluate(rows, schedule):
    case = {
        "case": rows[0]["case"],
        "records": [row["record"] for row in rows],
        "status": "READY",
    }
    try:
        bill, invoice_amount, stay_record = build_case_bill(rows, schedule)
        case["bill"] = bill
        case["invoice_cents"] = invoice_amount
        case["stay_record"] = stay_record
        case["status"] = case_status(bill)
    except DomainIssue as error:
        case["status"] = error.code
        case["bill"] = None
    return case


def correction_balance(intake, cases):
    accounted = (
        intake["accepted"] + intake["rejected"] + intake["blank"] + intake["repeated"]
    )
    statuses = Counter(case["status"] for case in cases)
    ready = statuses.pop("READY", 0)
    blocked = sum(count for status, count in statuses.items())
    observed = sum(len(case["records"]) for case in cases)
    block_codes = Counter()
    for case in cases:
        if case.get("bill"):
            block_codes.update(block["code"] for block in case["bill"]["blocks"])
    releasable = (
        bool(cases)
        and ready == len(cases)
        and not intake["rejected"]
        and not block_codes
        and accounted == intake["input"]
        and observed == intake["accepted"]
    )
    return dict(
        input=intake["input"],
        accepted=intake["accepted"],
        isolated=intake["rejected"],
        ignored=intake["blank"] + intake["repeated"],
        accounted=accounted,
        balanced=accounted == intake["input"] and observed == intake["accepted"],
        ready=ready,
        pending=len(cases) - ready,
        blocked=blocked,
        block_reasons=dict(sorted(block_codes.items())),
        issues=dict(sorted(statuses.items())),
        releasable=releasable,
    )


def run_correction(data, schedule):
    intake = inspect(data)
    output = {"intake": {k: v for k, v in intake.items() if k != "rows"}}
    cases = [evaluate(rows, schedule) for _, rows in case_groups(intake["rows"])]
    output["cases"] = cases
    output["schedule"] = {
        "code": schedule["code"],
        "version": schedule["version"],
        "fingerprint": schedule["fingerprint"],
        "periods": schedule["periods"],
    }
    output["balance"] = correction_balance(intake, cases)
    return output
