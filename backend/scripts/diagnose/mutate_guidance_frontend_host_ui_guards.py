"""Guidance Task 18 — frontend host/store/UI mutations must RED.

Covers:
  T18-M1  HTML initial emit (immediate watch)
  T18-M2  Univer switch / identity mapping fail-closed
  T18-M3  cache identity must exclude contextRevision
  T18-M4  sanitize must strip executable HTML
  T18-M5  incomplete location → adapter null (no mount)

Usage:
  python mutate_guidance_frontend_host_ui_guards.py --check-anchors
  python mutate_guidance_frontend_host_ui_guards.py --apply
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform" / "frontend"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
EVIDENCE = (
    ROOT
    / ".kiro"
    / "specs"
    / "workpaper-guidance-content-closure"
    / "basis"
    / "T18-frontend-mutation-report.json"
)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass


@dataclass(frozen=True)
class Case:
    id: str
    file: Path
    anchor: str
    replacement: str
    vitest: str
    wants: tuple[str, ...]


CASES = [
    Case(
        id="T18-M1-emit-not-immediate",
        file=FE / "src/components/workpaper/GtWpRenderer.vue",
        anchor=(
            "watch(currentSheetContext, emitSheetContext, "
            "{ immediate: true, flush: 'sync' })"
        ),
        replacement=(
            "watch(currentSheetContext, emitSheetContext, "
            "{ immediate: false, flush: 'sync' })"
        ),
        vitest="src/components/workpaper/GtWpRenderer.runtime-boundary.test.ts",
        wants=("同一结构化 emitter",),
    ),
    Case(
        id="T18-M2-univer-always-null",
        file=FE / "src/composables/useWpRenderer.ts",
        anchor="  if (!activeSheetId) return null\n",
        replacement="  if (true) return null // MUTATED: Univer switch no-op\n",
        vitest="src/composables/__tests__/useWpRendererSheetContext.spec.ts",
        wants=("custom nav/native tab/locate",),
    ),
    Case(
        id="T18-M3-cache-includes-revision",
        file=FE / "src/stores/guidancePanelStore.ts",
        anchor=(
            "  return [\n"
            "    GUIDANCE_CACHE_SCHEMA,\n"
            "    ctx.projectId,\n"
            "    ctx.wpId,\n"
            "    ctx.wpCode,\n"
            "    ctx.host,\n"
            "    sheetIdentity,\n"
            "  ].join('|')\n"
        ),
        replacement=(
            "  return [\n"
            "    GUIDANCE_CACHE_SCHEMA,\n"
            "    ctx.projectId,\n"
            "    ctx.wpId,\n"
            "    ctx.wpCode,\n"
            "    ctx.host,\n"
            "    sheetIdentity,\n"
            "    String(ctx.contextRevision ?? 0),\n"
            "  ].join('|')\n"
        ),
        vitest="src/stores/__tests__/guidancePanelStore.spec.ts",
        wants=("不含 revision",),
    ),
    Case(
        id="T18-M4-sanitize-bypass",
        file=FE / "src/components/workpaper/guidance/GuidanceTabContent.vue",
        anchor="    return sanitizeHtml(withChips)\n",
        replacement="    return withChips // MUTATED: skip sanitize\n",
        vitest="src/components/workpaper/guidance/__tests__/GuidanceTabContent.spec.ts",
        wants=("script、事件属性、javascript URL",),
    ),
    Case(
        id="T18-M5-rail-mounts-without-location",
        file=FE / "src/shell/guidance/guidanceRailAdapter.ts",
        anchor="  if (!input.location) return null\n",
        replacement=(
            "  if (!input.location) return {\n"
            "    contractVersion: GC0_CONTRACT_VERSION,\n"
            "    id: 'guidance',\n"
            "    visible: true,\n"
            "    disabledReason: null,\n"
            "    location: null as any,\n"
            "    guidanceVersion: null,\n"
            "    hasDraft: false,\n"
            "    open: () => undefined,\n"
            "    close: async () => undefined,\n"
            "  }\n"
        ),
        vitest="src/shell/formula/__tests__/rightRailArbiter.spec.ts",
        wants=("incomplete location / unknown major",),
    ),
]


def _normalize_newlines(text: str, file_text: str) -> str:
    nl = "\r\n" if "\r\n" in file_text else "\n"
    return text.replace("\r\n", "\n").replace("\n", nl)


def run_vitest(spec: str) -> tuple[int, str]:
    proc = subprocess.run(
        f"npx vitest run {spec}",
        cwd=str(FE),
        capture_output=True,
        env=ENV,
        shell=True,
    )
    out = (proc.stdout or b"").decode("utf-8", errors="replace") + (
        proc.stderr or b""
    ).decode("utf-8", errors="replace")
    return proc.returncode, out


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        anchor = _normalize_newlines(case.anchor, text)
        n = text.count(anchor)
        print(f"  [{'OK' if n == 1 else 'MISS'}] {case.id} (n={n}) {case.file.name}")
        if n != 1:
            bad += 1
    return 1 if bad else 0


def apply() -> int:
    import json
    from datetime import datetime, timezone

    # Baseline: all guard specs green
    baseline_specs = sorted({c.vitest for c in CASES})
    for spec in baseline_specs:
        rc, out = run_vitest(spec)
        if rc != 0:
            print(f"baseline not green: {spec}")
            print(out[-2500:])
            return 1
    print("OK baseline")

    results: list[dict] = []
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        anchor = _normalize_newlines(case.anchor, text)
        replacement = _normalize_newlines(case.replacement, text)
        n = text.count(anchor)
        if n != 1:
            print(f"  {case.id}: ANCHOR-MISS (n={n})")
            results.append({"id": case.id, "verdict": "ANCHOR-MISS", "anchorCount": n})
            bad += 1
            continue
        bak = case.file.with_suffix(case.file.suffix + ".bak")
        shutil.copy2(case.file, bak)
        try:
            case.file.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")
            rc, out = run_vitest(case.vitest)
            if rc == 0:
                print(f"  {case.id}: GREEN FAIL")
                results.append({"id": case.id, "verdict": "GREEN"})
                bad += 1
            elif not all(w in out for w in case.wants):
                print(f"  {case.id}: WRONG-TEST")
                print(out[-1500:])
                results.append({"id": case.id, "verdict": "WRONG-TEST"})
                bad += 1
            else:
                print(f"  {case.id}: RED OK")
                results.append({"id": case.id, "verdict": "RED"})
        finally:
            shutil.copy2(bak, case.file)
            bak.unlink(missing_ok=True)

    report = {
        "task": 18,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "allRed": bad == 0,
        "results": results,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"bad={bad}/{len(CASES)} evidence={EVIDENCE}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.check_anchors:
        return check_anchors()
    if args.apply:
        return apply()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
