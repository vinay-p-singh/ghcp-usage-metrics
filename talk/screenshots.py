"""Render a screenshot-safe copy of the dashboard for the talk deck.

The real report carries employer-internal project names and absolute paths
containing a username. This repository is public, so the images in `talk/img/`
are captured from an anonymised copy instead: every project is renamed, home
paths are masked, and everything that makes the point — credits, tokens,
requests, models, agents, skills, dates — is left exactly as recorded.

    python talk/screenshots.py        # writes talk/_shots/dashboard.html

Then open that file and capture the panels. `talk/_shots/` is gitignored.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ghcp.report import write_dashboard  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "out")
DST = os.path.join(ROOT, "talk", "_shots")

# The project this deck is about stays named; it is already public.
KEEP = {"vinay-p-singh/ghcp-usage-metrics"}

ORGS = ["contoso", "northwind", "fabrikam"]
LEAVES = [
    "support-agent-poc", "billing-service", "claims-triage", "data-pipeline",
    "docs-portal", "auth-gateway", "search-index", "report-builder",
    "chat-prototype", "ml-experiments", "infra-terraform", "design-system",
    "api-gateway", "etl-jobs", "notebook-lab", "web-portal", "event-router",
    "feature-store", "cost-explorer", "batch-runner", "voice-poc",
    "intake-forms", "rules-engine", "catalog-sync", "audit-trail",
    "onboarding-flow", "pricing-model", "risk-scoring", "telemetry-agent",
    "content-tagger", "shift-planner", "invoice-parser", "route-optimiser",
    "asset-tracker", "survey-tool", "kb-indexer", "alert-router",
    "ledger-export", "policy-checker", "sandbox-runner", "sku-mapper",
    "vision-poc", "queue-worker", "schema-registry", "trial-harness",
    "usage-probe", "doc-splitter", "tenant-admin", "seat-report", "log-shipper",
]


def name_map(projects: list[dict]) -> dict[str, str]:
    """Stable pseudonyms that preserve whether a name carried an org prefix."""
    mapping: dict[str, str] = {}
    leaf = 0
    for i, real in enumerate(sorted(p["name"] for p in projects)):
        if real in KEEP:
            mapping[real] = real
            continue
        stand_in = LEAVES[leaf % len(LEAVES)]
        leaf += 1
        mapping[real] = f"{ORGS[i % len(ORGS)]}/{stand_in}" if "/" in real else stand_in
    return mapping


def mask_paths(text: str) -> str:
    text = re.sub(r"[A-Za-z]:\\\\Users\\\\[^\\\\\"]+", r"C:\\\\Users\\\\you", text)
    return re.sub(r"/(?:home|Users)/[^/\"]+", "/home/you", text)


# Session names are free text a session store wrote to describe real work, so
# they are the most revealing field in the extract. Replaced wholesale rather
# than pattern-matched: a deny-list would only catch the phrasings I thought of.
TOPICS = [
    "Fix failing build", "Add retry to the client", "Review the migration",
    "Trace a flaky test", "Refactor the parser", "Wire up the dashboard",
    "Tidy the release notes", "Investigate a timeout", "Split a large module",
    "Rename a public field", "Update the fixtures", "Chase a memory leak",
]


def mask_session_names(projects: list[dict]) -> int:
    masked = 0
    for p in projects:
        for client in ("vscode", "cli", "claude"):
            names = p.get(client, {}).get("session_names") or {}
            for i, sid in enumerate(sorted(names)):
                names[sid] = TOPICS[(masked + i) % len(TOPICS)]
            masked += len(names)
    return masked


def main() -> None:
    with open(os.path.join(SRC, "projects.json"), encoding="utf-8") as f:
        projects = json.load(f)
    with open(os.path.join(SRC, "diagnostics.json"), encoding="utf-8") as f:
        diag = json.load(f)

    names = name_map(projects)
    for p in projects:
        p["name"] = names[p["name"]]
    for row in diag.get("no_token_rows", []):
        row["project"] = names.get(row["project"], row["project"])

    sessions_masked = mask_session_names(projects)
    diag = json.loads(mask_paths(json.dumps(diag)))

    write_dashboard(projects, DST, diag)
    print(f"{len(projects)} projects and {sessions_masked} session names "
          f"anonymised -> {os.path.join(DST, 'dashboard.html')}")


if __name__ == "__main__":
    main()
