"""Script 1: every manifest source_pdf must exist, be non-empty, and not be a
byte-for-byte duplicate of a document claimed by a *different* combo (a smell
for copy-pasted/placeholder sourcing). Read-only."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

from _common import BASE_DIR, Finding, all_phase2_reports, print_findings


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run() -> list[Finding]:
    findings: list[Finding] = []
    hash_to_combos: dict[str, list[str]] = defaultdict(list)
    checked = 0
    missing = 0
    empty = 0

    for report in all_phase2_reports():
        combo = f"{report.get('issuer')}/{report.get('document_id')}"
        for doc in report.get("documents", []):
            src = doc.get("source_pdf")
            if not src:
                findings.append(Finding("HIGH", "manifest-schema", f"{combo}: document entry missing source_pdf ({doc})"))
                continue
            path = Path(src)
            if not path.is_absolute():
                path = (BASE_DIR / path).resolve()
            checked += 1
            if not path.exists():
                missing += 1
                findings.append(Finding("CRITICAL", "missing-file", f"{combo}: {doc.get('doc_type')} source_pdf does not exist: {src}"))
                continue
            size = path.stat().st_size
            if size == 0:
                empty += 1
                findings.append(Finding("CRITICAL", "empty-file", f"{combo}: {doc.get('doc_type')} source_pdf is 0 bytes: {src}"))
                continue
            digest = _hash_file(path)
            hash_to_combos[digest].append(f"{combo} [{doc.get('doc_type')}] {src}")

    for digest, combos in hash_to_combos.items():
        distinct_combos = {c.split(" [", 1)[0] for c in combos}
        if len(distinct_combos) > 1:
            findings.append(Finding(
                "HIGH", "duplicate-content",
                f"{len(distinct_combos)} different combos share byte-identical document content (hash {digest[:12]}): "
                + " | ".join(combos),
            ))

    findings.append(Finding("INFO", "summary", f"checked {checked} document references, {missing} missing, {empty} empty-file"))
    return findings


if __name__ == "__main__":
    print_findings("Script 1: manifest/doc existence + duplicate-content check", run())
