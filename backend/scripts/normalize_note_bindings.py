#!/usr/bin/env python3
"""规范化 note_template_bindings.json 的国企键 legacy_aliases 标注.

背景（gap-analysis §四 / requirement 10.2、10.15）：
- 国企「财务报表主要项目注释」章 canonical key = ``八、N``。
- 历史 ``五、N``（国企）已由 ``note_section_catalog.resolve_binding_key`` 在
  **查表时**归一为 ``八、N``（``note_template_bindings_loader.get_binding_for_section``
  内已接入）。
- 因此本步骤**不物理 re-key**（bindings 字典同时含 listed 的 ``五、N`` 键，
  re-key 会与 listed 绑定冲突/覆盖），仅为国企 ``八、N`` 绑定项**追加**
  ``legacy_aliases`` 字段，镜像 ``section_code_index.json`` 的别名映射。

数据安全：
- 写前备份到 ``data/note_template_bindings_backup/``。
- 纯追加字段，**不增删 binding 键**（前后键数量必须相等）。
- 别名来源 = section_code_index（国企变体节的 ``legacy_aliases``），不发明映射。

Usage:
    python scripts/normalize_note_bindings.py            # dry-run
    python scripts/normalize_note_bindings.py --write    # 备份 + 写回
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
DATA = _BACKEND / "data"
INDEX_PATH = DATA / "audit_report_templates" / "section_code_index.json"
BINDINGS_PATH = DATA / "note_template_bindings.json"
BACKUP_DIR = DATA / "note_template_bindings_backup"

SOE_VARIANTS = ("soe_standalone", "soe_consolidated")


def load_index_soe_aliases() -> dict[str, list[str]]:
    """从 section_code_index 收集国企 canonical(八、N) → legacy(五、N) 别名."""
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    aliases: dict[str, list[str]] = {}
    for vk in SOE_VARIANTS:
        variant = index.get("variants", {}).get(vk) or {}
        for s in variant.get("sections", []):
            la = s.get("legacy_aliases") or []
            if la:
                code = s.get("section_code", "")
                # union across variants (standalone/consolidated identical here)
                merged = aliases.setdefault(code, [])
                for a in la:
                    if a not in merged:
                        merged.append(a)
    return aliases


def annotate_bindings(payload: dict[str, Any], soe_aliases: dict[str, list[str]]) -> int:
    """为含 legacy 别名的国企 canonical 绑定项追加 legacy_aliases；返回标注数."""
    bindings = payload.get("bindings", {})
    annotated = 0
    for canonical, legacy in soe_aliases.items():
        entry = bindings.get(canonical)
        if not isinstance(entry, dict):
            continue  # canonical 不在 bindings（如 八、3 衍生金融资产）→ 跳过
        existing = entry.get("legacy_aliases")
        if isinstance(existing, list):
            merged = list(existing)
            for a in legacy:
                if a not in merged:
                    merged.append(a)
            if merged != existing:
                entry["legacy_aliases"] = merged
                annotated += 1
        else:
            entry["legacy_aliases"] = list(legacy)
            annotated += 1
    return annotated


def main() -> None:
    parser = argparse.ArgumentParser(description="Annotate SOE bindings with legacy_aliases (no re-key)")
    parser.add_argument("--write", action="store_true", help="Backup + write changes")
    args = parser.parse_args()

    soe_aliases = load_index_soe_aliases()
    print(f"Index SOE canonical→legacy aliases: {soe_aliases}")

    payload = json.loads(BINDINGS_PATH.read_text(encoding="utf-8"))
    keys_before = list(payload.get("bindings", {}).keys())

    annotated = annotate_bindings(payload, soe_aliases)
    keys_after = list(payload.get("bindings", {}).keys())

    print(f"Binding keys before: {len(keys_before)}  after: {len(keys_after)}")
    print(f"Entries annotated with legacy_aliases: {annotated}")
    assert keys_before == keys_after, "Binding keys changed — annotation must not re-key!"

    if args.write:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"note_template_bindings_{stamp}.json"
        shutil.copy2(BINDINGS_PATH, backup_path)
        print(f"Backed up to {backup_path}")
        BINDINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {BINDINGS_PATH}")
    else:
        print("(dry-run; pass --write to save)")


if __name__ == "__main__":
    main()
