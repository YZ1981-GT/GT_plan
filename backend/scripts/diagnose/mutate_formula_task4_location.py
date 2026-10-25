"""Formula Task 4 mutations: location epoch/revision + G-ID fail-closed."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOC = ROOT / "audit-platform/frontend/src/shell/formula/canonicalLocationState.ts"
GID = ROOT / "audit-platform/frontend/src/shell/formula/gidSheetIdentity.ts"
VITEST_CWD = ROOT / "audit-platform/frontend"
ENVPATCH = {**os.environ, "PYTHONIOENCODING": "utf-8"}
VITEST_CMD = (
    "npx vitest run src/shell/formula/__tests__/canonicalLocationState.spec.ts"
)


@dataclass(frozen=True)
class MutCase:
    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]


CASES = [
    MutCase(
        id="M1-epoch-not-bumped-on-owner-change",
        file=LOC,
        anchor="        ownerEpoch: prevEpoch + 1,\n",
        replacement="        ownerEpoch: prevEpoch,\n",
        wants=("ownerEpoch increases across owners",),
    ),
    MutCase(
        id="M2-allow-nodekey-as-identity",
        file=GID,
        anchor=(
            "  if (input.nodeKeyAsIdentity != null && String(input.nodeKeyAsIdentity).length > 0) {\n"
            "    return {\n"
            "      ok: false,\n"
            "      reasonCode: 'gid_nodekey_not_identity',\n"
            "      detail: 'nodeKey is migration metadata only — not location identity',\n"
            "    }\n"
            "  }\n"
        ),
        replacement="  // mutation: nodeKey accepted as identity\n",
        wants=("blocks capability-not-ready and G-ID identity violations",),
    ),
    MutCase(
        id="M3-async-ignore-revision",
        file=LOC,
        anchor=(
            "  if (args.state.contextRevision !== args.ticket.contextRevision) {\n"
            "    return { accept: false, reasonCode: 'revision_mismatch' }\n"
            "  }\n"
        ),
        replacement="  // mutation: revision gate disabled\n",
        wants=("async landing requires subject+epoch+revision+capability",),
    ),
]


def check_anchors() -> int:
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        n = text.count(case.anchor)
        print(f"  [{'OK' if n == 1 else 'ANCHOR-MISS'}] {case.id} (n={n})")
        if n != 1:
            bad += 1
    return 1 if bad else 0


def run_vitest() -> tuple[int, str]:
    proc = subprocess.run(
        VITEST_CMD, cwd=str(VITEST_CWD), capture_output=True, env=ENVPATCH, shell=True,
    )
    out = (proc.stdout or b"").decode("utf-8", errors="replace") + (
        proc.stderr or b""
    ).decode("utf-8", errors="replace")
    return proc.returncode, out


def apply_one(case: MutCase) -> str:
    text = case.file.read_text(encoding="utf-8")
    if text.count(case.anchor) != 1:
        return f"{case.id}: ANCHOR-MISS"
    new_text = text.replace(case.anchor, case.replacement, 1)
    backup = case.file.with_suffix(case.file.suffix + ".bak")
    shutil.copy2(case.file, backup)
    try:
        case.file.write_text(new_text, encoding="utf-8")
        rc, out = run_vitest()
        if rc == 0:
            return f"{case.id}: GREEN FAIL"
        hit = [w for w in case.wants if w in out]
        if len(hit) != len(case.wants):
            return f"{case.id}: WRONG-TEST FAIL\n{out[-1500:]}"
        return f"{case.id}: RED OK -- {hit}"
    finally:
        shutil.copy2(backup, case.file)
        backup.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.check_anchors:
        return check_anchors()
    if not args.apply:
        print(__doc__)
        return 0
    rc, out = run_vitest()
    if rc != 0:
        print("baseline not green")
        print(out[-2000:])
        return 1
    print("OK baseline green")
    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "RED OK" not in result:
            bad += 1
    print(f"\nbad={bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
