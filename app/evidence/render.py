import json


def artifact(run):
    report = run["report"]
    kind = report.get("manifest", {}).get("kind", "LEGACY")
    packet = {
        "schema": "review-evidence/2" if kind == "CORRECTION" else "review-evidence/1",
        "manifest": report["manifest"],
        "balance": report["balance"],
        "cases": report["cases"],
        "intake": report["intake"],
        "review": {key: run[key] for key in ("status", "revision", "note", "reviewed")},
    }
    if "schedule" in report:
        packet["schedule"] = report["schedule"]
    if "lineage" in report:
        packet["lineage"] = report["lineage"]
    return (
        json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
