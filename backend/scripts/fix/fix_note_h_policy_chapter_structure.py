"""fix_note_h_policy_chapter_structure — H 类会计政策章表结构修正（幂等）

Spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 13
      (R7.1 ~ R7.7)

裁决真源 = `docs/模版/` 两份附注源 docx，按 `paragraph.style.name == 'Heading N'`
定位章节（**不能用 `^N、` 正则** —— docx 章号是 Word 自动编号，段落文本不含「三、」）。

## 四类处置（逐条带源 docx 依据）

listed 会计政策章（`三、xxx`）：
  1. `三、固定资产` t[0]  —— 表名是**整段红字说明文本泄漏**（md 重建产物）
     → 正名为源 docx 的 `Heading 3` 标题「各类固定资产的折旧方法」，
       红字说明移入 `guidance`，补 4 列 `flat` columns（源 docx 表头逐字）
  2. `三、生物资产【不适用` t[0] —— 同款泄漏
     → 正名「生产性生物资产」（源 docx `Heading 4`），补 4 列 + guidance
  3. `三、工程物资【不适用` t[0] —— **移除**（源 docx 该章 `tables_between=0`；
     该表与项目注释章 `五、23` 的 t[5]「工程物资」行标签同构：
     专用材料/专用设备/工器具/工程物资减值准备/合计）
  4. `三、使用权资产` t[0] —— **移除**（源 docx 该章及三个 `Heading 3` 子节全部
     `tables_between=0`；该表与 `五、25` t[0] **逐行同构**，39 行里仅 5 处
     「4. 期末余额」多一个空格的 md 空白差异，headers 亦同构且还残留 `……` 占位列头）

soe 会计政策章（`四、xxx`）：
  5. `四、固定资产` —— **补 1 表**「固定资产分类及折旧政策」（源 docx `Heading 4`，
     8 行 × 4 列，行 = 房屋、建筑物 / 机器设备 / 运输工具 / 电子设备 / 办公设备 /
     酒店业家具 / 其他）
  6. `四、生物资产` —— **补 1 表**「生产性生物资产」（源 docx `Heading 5`，13 行 × 4 列，
     四产业 × (①, ……) 可扩位）
  7. `四、投资性房地产` / `四、在建工程` / `四、油气资产` / `四、使用权资产`
     —— 源 docx 实证**确无政策表**（各章及其 `Heading 4` 子节 `tables_between` 全 0）
     ⇒ **不动**（宁缺勿造），由守卫显式登记 + 反向自检钉死

## 安全性

这些政策章**无 pusher**：`note_workpaper_sync_registry.json` 里全部不在册；
80 个 `*NoteSectionMap.ts` 对这些章节号的命中经逐条核实全是**别的语义**
（`h1` 在注释里 / `h3`·`h5` 命中的是**行标签**「四、投资性房地产减值准备累计金额合计」
「四、油气资产账面价值合计」/ `h8` 的 `isH8RouNoteSection` 只判章节号且只有测试消费方）
⇒ 移除重复表不打断任何同步链路。

用法：
    python backend/scripts/fix/fix_note_h_policy_chapter_structure.py --check
    python backend/scripts/fix/fix_note_h_policy_chapter_structure.py --dry-run
    python backend/scripts/fix/fix_note_h_policy_chapter_structure.py --apply

控制台输出禁 emoji（GBK 崩点在写盘之后，会让 exit code 与实际写入状态背离）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"

LISTED = DATA_DIR / "note_template_listed.json"
SOE = DATA_DIR / "note_template_soe.json"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# `row_type` 判据单一真源（理由见 ADD_TABLES 处注释）。
from app.services.note_expandable_markers import (  # noqa: E402
    row_type_for_label as _row_type_for_label,
)


# ───────────────────────── 源 docx 实证常量（逐字） ─────────────────────────

# listed `三、固定资产` / soe `四、固定资产` 的折旧政策表列头不同（源 docx 实证）
LISTED_FA_HEADERS = ["类  别", "使用年限（年）", "残值率%", "年折旧率%"]
SOE_FA_HEADERS = ["固定资产类别", "使用年限", "残值率%", "年折旧率%"]
BIO_HEADERS = ["生产性生物资产类别", "使用年限（年）", "残值率%", "年折旧率%"]

SOE_FA_ROWS = [
    "房屋、建筑物",
    "机器设备",
    "运输工具",
    "电子设备",
    "办公设备",
    "酒店业家具",
    "其他",
]

# 四产业 × (①, ……)：`①` 与 `……` 是源模板的**可扩位**，不是数据行标签
BIO_ROWS = [
    "种植业", "①", "……",
    "畜牧养殖业", "①", "……",
    "林业", "①", "……",
    "水产业", "①", "……",
]

LISTED_FA_GUIDANCE = (
    "本公司采用年限平均法计提折旧。固定资产自达到预定可使用状态时开始计提折旧，"
    "终止确认时或划分为持有待售非流动资产时停止计提折旧。"
    "提示：此处分类应与固定资产项目注释（五、22）的分类保持一致；"
    "年折旧率区间应当由大到小列示（如 19.00—9.50）。"
)
SOE_FA_GUIDANCE = (
    "按固定资产类别、预计使用寿命和预计净残值确定各类固定资产的年折旧率。"
    "提示：分类应与固定资产项目注释（八、22）保持一致；"
    "每年年度终了应对使用寿命、预计净残值和折旧方法进行复核。"
)
BIO_GUIDANCE = (
    "生产性生物资产折旧采用直线法计算，按各类生物资产估计的使用年限扣除残值后确定折旧率。"
    "提示：`①` 与 `……` 是源模板预留的可扩位，按实际生物资产类别逐条列示；"
    "不适用的产业整段删除。"
)

# 正名映射：md 重建把源 docx 的说明段落当成了表名（表名 = 整段红字）
RENAME_BY_SECTION: dict[tuple[str, str], str] = {
    ("listed", "三、固定资产"): "各类固定资产的折旧方法",
    ("listed", "三、生物资产【不适用"): "生产性生物资产",
}

# 移除重复表：(variant, section_number) -> 该章要移除的表在源 docx 的对应位置说明
DROP_TABLES: dict[tuple[str, str], str] = {
    ("listed", "三、工程物资【不适用"): "与项目注释章 五、23 的「工程物资」表同构（源 docx 政策章无表）",
    ("listed", "三、使用权资产"): "与项目注释章 五、25 的「使用权资产」表逐行同构（源 docx 政策章无表）",
}

# soe 待补表
ADD_TABLES: dict[tuple[str, str], dict[str, Any]] = {
    ("soe", "四、固定资产"): {
        "name": "固定资产分类及折旧政策",
        "headers": SOE_FA_HEADERS,
        "rows": SOE_FA_ROWS,
        "guidance": SOE_FA_GUIDANCE,
    },
    ("soe", "四、生物资产"): {
        "name": "生产性生物资产",
        "headers": BIO_HEADERS,
        "rows": BIO_ROWS,
        "guidance": BIO_GUIDANCE,
    },
}

# 源 docx 实证「确无政策表」的章节（守卫用；本脚本不动它们）
NO_TABLE_SECTIONS: dict[str, tuple[str, ...]] = {
    "listed": ("三、投资性房地产【不", "三、在建工程"),
    "soe": ("四、投资性房地产", "四、在建工程", "四、油气资产", "四、使用权资产"),
}


def build_columns(headers: list[str]) -> list[dict[str, Any]]:
    """政策表都是**单级表头** → 标签列必须标 `flat`，抑制 `_infer_groups_from_headers`
    按前缀反猜出凭空父表头（`使用年限`/`残值率%`/`年折旧率%` 无共同前缀，
    但 `flat` 是显式表态，比"恰好推不出"稳）。"""
    cols: list[dict[str, Any]] = []
    for i, h in enumerate(headers):
        col: dict[str, Any] = {"key": f"c{i}", "label": h}
        if i == 0:
            col["is_label"] = True
            col["flat"] = True
        cols.append(col)
    return cols


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def sections_of(tpl: dict[str, Any]) -> list[dict[str, Any]]:
    return tpl.get("sections") if isinstance(tpl.get("sections"), list) else tpl  # type: ignore[return-value]


def plan(variant: str, tpl: dict[str, Any]) -> list[str]:
    """返回待办清单（空 = 已收敛）。同时**就地修改** tpl。"""
    todo: list[str] = []
    by_num = {str(s.get("section_number") or ""): s for s in sections_of(tpl)}

    # 1) 正名 + 补 columns + guidance
    for (v, num), new_name in RENAME_BY_SECTION.items():
        if v != variant:
            continue
        sec = by_num.get(num)
        if sec is None:
            todo.append(f"[MISS] {variant} {num}: 章节不存在")
            continue
        tables = sec.get("tables") or []
        if not tables:
            todo.append(f"[MISS] {variant} {num}: 应有 1 张政策表但 tables=0")
            continue
        t = tables[0]
        headers = LISTED_FA_HEADERS if "固定资产" in num else BIO_HEADERS
        guidance = LISTED_FA_GUIDANCE if "固定资产" in num else BIO_GUIDANCE
        if t.get("name") != new_name:
            todo.append(f"[RENAME] {variant} {num} t[0]: -> {new_name!r}")
            t["name"] = new_name
        if list(t.get("headers") or []) != headers:
            todo.append(f"[HEADERS] {variant} {num} t[0]")
            t["headers"] = list(headers)
        want_cols = build_columns(headers)
        if t.get("columns") != want_cols:
            todo.append(f"[COLUMNS] {variant} {num} t[0]: {len(t.get('columns') or [])} -> {len(want_cols)}")
            t["columns"] = want_cols
        if (t.get("guidance") or "") != guidance:
            todo.append(f"[GUIDANCE] {variant} {num} t[0]")
            t["guidance"] = guidance
        sec["_aligned_by"] = "fix_note_h_policy_chapter_structure"

    # 2) 移除重复表
    for (v, num), reason in DROP_TABLES.items():
        if v != variant:
            continue
        sec = by_num.get(num)
        if sec is None:
            todo.append(f"[MISS] {variant} {num}: 章节不存在")
            continue
        if sec.get("tables"):
            todo.append(f"[DROP] {variant} {num}: 移除 {len(sec['tables'])} 张重复表 ({reason})")
            sec["tables"] = []
            sec["_aligned_by"] = "fix_note_h_policy_chapter_structure"

    # 3) soe 补表
    for (v, num), spec in ADD_TABLES.items():
        if v != variant:
            continue
        sec = by_num.get(num)
        if sec is None:
            todo.append(f"[MISS] {variant} {num}: 章节不存在")
            continue
        tables = sec.get("tables") or []
        want = {
            "name": spec["name"],
            "headers": list(spec["headers"]),
            "columns": build_columns(list(spec["headers"])),
            # 🔴 禁硬编码 "data"：`ADD_TABLES` 走 `tables[0] != want` **深比较整表**
            # 后整表重写 rows ⇒ 硬编码会把 `fix_note_expandable_rows.py` 标好的
            # `expandable` 翻回 `data`（实测 soe `四、生物资产` 4 行 `……`，2026-08-08）。
            # 判据单一真源 = app/services/note_expandable_markers.row_type_for_label。
            "rows": [
                {"label": r, "row_type": _row_type_for_label(r)} for r in spec["rows"]
            ],
            "guidance": spec["guidance"],
        }
        if len(tables) != 1 or tables[0] != want:
            todo.append(f"[ADD] {variant} {num}: 补政策表 {spec['name']!r} ({len(want['rows'])} 行)")
            sec["tables"] = [want]
            sec["_aligned_by"] = "fix_note_h_policy_chapter_structure"

    # 4) 反向核验：声明「无表」的章节确实无表（本脚本不改，只报）
    for num in NO_TABLE_SECTIONS.get(variant, ()):
        sec = by_num.get(num)
        if sec is None:
            todo.append(f"[MISS] {variant} {num}: 章节不存在（NO_TABLE 清单过期？）")
        elif sec.get("tables"):
            todo.append(
                f"[UNEXPECTED] {variant} {num}: 源 docx 实证无政策表但 JSON 有 "
                f"{len(sec['tables'])} 张 —— 请先核源 docx 再决定处置"
            )
    return todo


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total: list[str] = []
    writes: list[tuple[Path, dict[str, Any]]] = []
    for variant, path in (("listed", LISTED), ("soe", SOE)):
        if not path.exists():
            print(f"[ERR] 模板不存在: {path}")
            return 2
        raw = path.read_text(encoding="utf-8")
        tpl = json.loads(raw)
        # 🔴 round-trip 硬闸：`json.dumps(indent=2) + "\n"` 必须**逐字**复现原文，
        # 否则写回会重排整个文件（1 MB 级 diff）并与并发会话的改动互相回退。
        # 实证两份模板都满足（listed 1,026,449 B / soe 680,717 B 逐字相等）。
        if json.dumps(tpl, ensure_ascii=False, indent=2) + "\n" != raw:
            print(f"[ERR] {path.name} round-trip 自检失败：json.dumps(indent=2) 不能逐字复现原文，"
                  "写回会重排全文件 —— 拒绝写入")
            return 2
        todo = plan(variant, tpl)
        for line in todo:
            print("  " + line)
        total.extend(todo)
        if todo:
            writes.append((path, tpl))

    print(f"[INFO] pending={len(total)}")
    if args.check:
        if total:
            print(f"[ERR] {len(total)} 项欠账")
            return 1
        print("[OK] no pending")
        return 0
    if args.dry_run:
        print("[OK] dry-run only, nothing written")
        return 0

    for path, tpl in writes:
        path.write_text(
            json.dumps(tpl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"[OK] applied to {len(writes)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
