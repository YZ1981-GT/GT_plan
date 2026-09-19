"""One-shot probe for PAC Task 19/20 assembly integrity."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FE = ROOT / "audit-platform" / "frontend" / "src"


def count_component_types(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    return re.findall(r"componentType:\s*'([^']+)'", src)


def main() -> None:
    legacy = FE / "components/workpaper/htmlRendererRegistry.ts"
    barrel = FE / "components/workpaper/registry/index.ts"
    entries_dir = FE / "components/workpaper/registry/entries"
    legacy_types = count_component_types(legacy)
    barrel_types = count_component_types(barrel)
    entry_types: list[str] = []
    for p in sorted(entries_dir.glob("*.ts")):
        types = count_component_types(p)
        print(f"entries/{p.name}: {len(types)}")
        entry_types.extend(types)

    print("legacy entries", len(legacy_types), "unique", len(set(legacy_types)))
    print("barrel list literals", len(barrel_types), "unique", len(set(barrel_types)))
    print("entry arrays", len(entry_types), "unique", len(set(entry_types)))
    print("legacy - entries", sorted(set(legacy_types) - set(entry_types))[:20], "count", len(set(legacy_types) - set(entry_types)))
    print("entries - legacy", sorted(set(entry_types) - set(legacy_types))[:20], "count", len(set(entry_types) - set(legacy_types)))

    old = subprocess.check_output(
        ["git", "show", "HEAD:audit-platform/frontend/src/router/index.ts"],
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    # Find Dashboard block: path '' through next few siblings that belong to dashboard domain
    m = re.search(r"path:\s*''[\s\S]*?path:\s*'my-procedures'[\s\S]*?\},", old)
    print("--- HEAD dashboard-ish slice ---")
    print(m.group(0) if m else "NOT FOUND")


if __name__ == "__main__":
    main()
