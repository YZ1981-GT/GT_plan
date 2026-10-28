"""按准则分列 note_section：为 wp_account_mapping.json 加 note_section_soe / note_section_listed。

用 account_name 在两套附注模板种子里按标题精确匹配章节号。
匹配不到的留 null（不猜）。旧 note_section 字段保留不改（向下兼容）。

用法：
    python scripts/fix/fix_note_section_by_standard.py --check   # 只报告差异
    python scripts/fix/fix_note_section_by_standard.py --apply   # 写入
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
DATA = ROOT / "data"
WP_MAPPING = DATA / "wp_account_mapping.json"

# 手工裁定：account_name 在模板标题里找不到的条目（用科目名不完全匹配或章节名不同）
MANUAL_OVERRIDES: dict[str, dict[str, str | None]] = {
    # 营业收入在模板里叫不同名字
    "营业收入":    {"soe": "八、64", "listed": "五、62"},
    # 营业成本
    "营业成本":    {"soe": "八、64", "listed": "五、62"},  # 与营业收入同章
    # 应付股利在国企模板里的位置
    "应付股利":    {"soe": "八、43", "listed": "五、44"},
    # 递延所得税在模板里是合并章节
    "递延所得税资产": {"soe": "八、31", "listed": "五、30"},
    "递延所得税负债": {"soe": "八、31", "listed": "五、30"},
    # 应收利息/股利在新准则里并入其他应收款/其他流动资产
    "应收利息":    {"soe": None, "listed": None},  # 已归入其他流动资产
    "应收股利":    {"soe": None, "listed": None},  # 已归入其他流动资产
    # 资产处置损益
    "资产处置损益":  {"soe": "八、75", "listed": "五、78"},
}


def _load_title_index(template_path: Path) -> dict[str, str]:
    """标题 → section_number（精确匹配）。"""
    data = json.loads(template_path.read_text("utf-8"))
    out: dict[str, str] = {}
    for s in data.get("sections", []):
        code = (s.get("section_number") or "").strip()
        title = (s.get("section_title") or "").strip()
        if code and title:
            out[title] = code
    return out


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode not in ("--check", "--apply"):
        print(f"用法: {sys.argv[0]} --check|--apply")
        return 1

    soe_index = _load_title_index(DATA / "note_template_soe.json")
    listed_index = _load_title_index(DATA / "note_template_listed.json")

    payload = json.loads(WP_MAPPING.read_text("utf-8"))
    mappings = payload.get("mappings", [])

    changes = 0
    for m in mappings:
        if not m.get("note_section"):
            continue

        name = (m.get("account_name") or "").strip()
        wp_code = m.get("wp_code", "?")

        # 按科目名查找
        override = MANUAL_OVERRIDES.get(name)
        if override:
            soe_code = override["soe"]
            listed_code = override["listed"]
        else:
            soe_code = soe_index.get(name)
            listed_code = listed_index.get(name)

        old_soe = m.get("note_section_soe")
        old_listed = m.get("note_section_listed")

        if old_soe != soe_code or old_listed != listed_code:
            changes += 1
            if mode == "--check":
                print(f"  {wp_code:8s} [{name}]: soe {old_soe} -> {soe_code}, listed {old_listed} -> {listed_code}")

        m["note_section_soe"] = soe_code
        m["note_section_listed"] = listed_code

    if mode == "--apply":
        WP_MAPPING.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[ok] 已更新 {changes} 条映射的 note_section_soe / note_section_listed")
    else:
        print(f"[check] {changes} 条待更新（--apply 写入）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
