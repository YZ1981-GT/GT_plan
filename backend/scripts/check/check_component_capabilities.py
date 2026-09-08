"""CI / CLI checker for the component capability manifest.

Wraps the generator ``--check`` path and prints the four-way drift report.
Does not invent componentType entries; rebuild must match disk exactly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.gen.generate_component_capability_manifest import (  # noqa: E402
    DEFAULT_SOURCE_PATHS,
    check_manifest,
    extract_observed_sources,
)


def four_way_report() -> dict[str, list[str]]:
    """Four-way drift without importing application modules."""
    import json

    observed = extract_observed_sources(DEFAULT_SOURCE_PATHS)
    backend = set(observed.backend_renderer_types)
    frontend = set(observed.frontend_registry_types)
    manifest_path = (
        BACKEND_ROOT / "app" / "data" / "component_capabilities.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = set(payload.get("components", {}))
    return {
        "backend_only": sorted(backend - frontend),
        "frontend_only": sorted(frontend - backend),
        "manifest_missing_backend": sorted(backend - manifest),
        "manifest_missing_frontend": sorted(frontend - manifest),
        "manifest_only": sorted(manifest - backend - frontend),
    }


def unadjudicated_asymmetries() -> list[str]:
    """Asymmetric componentTypes (backend/frontend/manifest-only) with no exemption.

    Req 1.4/1.5: an intentional asymmetry must be registered as an exemption
    (owner/reason/source_digest). Any asymmetry NOT covered by an on-disk
    exemption is undeclared drift and must fail the check — otherwise a new
    frontend-only/backend-only type could slip in silently.
    """
    import json

    report = four_way_report()
    asymmetric = set(report["backend_only"]) | set(report["frontend_only"]) | set(
        report["manifest_only"]
    )
    manifest_path = BACKEND_ROOT / "app" / "data" / "component_capabilities.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    exempted = {
        e["component_type"]
        for e in payload.get("exemptions", [])
        if isinstance(e, dict) and "component_type" in e
    }
    return sorted(asymmetric - exempted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print four-way diffs without failing on drift",
    )
    args = parser.parse_args(argv)

    ok, detail = check_manifest()
    report = four_way_report()
    print("== four-way ==")
    for key, values in report.items():
        preview = values[:12]
        suffix = " ..." if len(values) > 12 else ""
        print(f"  {key} ({len(values)}): {preview}{suffix}")

    unadjudicated = unadjudicated_asymmetries()
    print(f"  unadjudicated_asymmetry ({len(unadjudicated)}): {unadjudicated[:12]}")

    if args.report_only:
        print(detail)
        return 0
    if not ok:
        print(f"[FAIL] {detail}", file=sys.stderr)
        return 1
    if unadjudicated:
        print(
            "[FAIL] capability asymmetry not adjudicated as exemption "
            f"(Req 1.4/1.5): {unadjudicated}",
            file=sys.stderr,
        )
        return 1
    print(f"[OK] {detail} — {len(report['frontend_only']) + len(report['backend_only']) + len(report['manifest_only'])} asymmetries all adjudicated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
