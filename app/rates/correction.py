"""费率更正编排：把单个业务组拆成可签账单。"""

from app.business import DomainIssue, by_kind, single
from app.rates.billing import guard_invoice, split_bill


def build_case_bill(rows, schedule):
    """返回 (账单, 票据金额, 停时记录键)；领域约束不合法时抛 DomainIssue。"""
    stay = single(rows, "stay")
    invoice = single(rows, "invoice")
    left, right = stay["start_min"], stay["end_min"]
    if left >= right:
        raise DomainIssue("INVALID_STAY")
    pauses = by_kind(rows, "pause")
    if any(row["start_min"] >= row["end_min"] for row in pauses):
        raise DomainIssue("INVALID_PAUSE")
    bill = split_bill((left, right), pauses, stay["free_min"], schedule)
    guard_invoice(bill, invoice["amount_cents"], stay["record"])
    return bill, invoice["amount_cents"], stay["record"]


def case_status(bill):
    return "BLOCKED" if bill["blocks"] else "READY"
