"""生成 canonical bytes 的跨语言 golden 用例。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
真源模块：`backend/app/services/workpaper_sync/canonical_interop.py`
产物：`backend/data/workpaper_sync_canonical_golden.json`

Python 与 TypeScript 两侧读同一份产物、各自计算 canonical bytes 再比对，
因此本文件的 `--check` 挂 CI 后，任一侧 canonicalizer 漂移都会被打红。

仓库根执行::

    python backend/scripts/gen/generate_workpaper_sync_canonical_golden.py --check
    python backend/scripts/gen/generate_workpaper_sync_canonical_golden.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / "backend"))

from app.services.workpaper_sync.canonical_interop import (  # noqa: E402
    CANONICAL_GOLDEN_PATH,
    render_golden_document,
)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the generated golden fixture")
    mode.add_argument("--apply", action="store_true", help="atomically regenerate the fixture")
    args = parser.parse_args(argv)

    content = render_golden_document()
    relative = CANONICAL_GOLDEN_PATH.relative_to(_REPO)
    if args.check:
        if not CANONICAL_GOLDEN_PATH.is_file():
            print(f"[FAIL] missing: {relative}")
            return 2
        if CANONICAL_GOLDEN_PATH.read_text(encoding="utf-8") != content:
            print(f"[FAIL] stale: {relative}")
            return 2
        print(f"[OK] {relative} matches the canonicalizer")
        return 0

    _atomic_write(CANONICAL_GOLDEN_PATH, content)
    print(f"[APPLIED] {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
