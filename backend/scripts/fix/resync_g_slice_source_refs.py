"""把 G slice 里各 entry 的 `source_ref` 与行身份生成器形态**按值实测**重新同步。

spec: `g-cycle-single-region-detail-lanes`（逐 lane 复用：每改一条前端就跑一次 `--check`）

🔴 不是一次性脚本：本 spec 的九条 lane 每条都要改前端（列模型对齐权威模板），改完行号
必然移位、铸造形态可能变。手改 slice 的行号会漏、会错，而判据是按值回源的 ⇒ 这里把
「行号与形态从源码现取」固化成工具。新增 lane 时往 :data:`TARGETS` 加一行即可。

为什么需要：
* Task 7 的行身份收口把 G1/G3 的铸造点从 `` `row-${Date.now()}` `` 改成 `genRowId()`
  （前缀内联 + 随机后缀单点），形态与行号都变了；
* C-1 重写 `useG9Detail.ts`（列模型对齐权威模板）把写入点与 `genId` 行号整体移位。

判据（`test_task49_g_cycle_migration.py`）要求：
  ① `payload_column_source` 的「声明行起 4 行窗口」剔掉 `xxx: null` 占位后，
     remark_only ⇒ 见 `remark:` 不见 `conclusion:`；conclusion_only ⇒ 反之；
  ② `row_identity_generator_source` 指向**声明行模型**的文件（要在那里找
     `{row_identity_key}: string`）；
  ③ `row_identity_generator_form` 逐字出现在该文件（空白折叠后），且非 uuid 族要能提出
     `` `<前缀>-${ `` 并在源码里找到该前缀 —— 这正是「前缀必须内联在消费方」的由来。

本脚本只认**实测值**：行号一律 grep 出来，不写死。幂等；`--check` 只报不改。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
SLICE = ROOT / "backend/data/workpaper_sync_g_cycle_manifest_slice.json"
COMP_REL = "audit-platform/frontend/src/components/workpaper/composables"
COMP = ROOT / COMP_REL

#: entry_id → (composable 文件名, payload 权威列, 行身份铸造点正则)
TARGETS: dict[str, tuple[str, str, re.Pattern[str]]] = {
    "xlsx/gt-g1-trading-financial-assets": (
        "useG1Detail.ts",
        "conclusion",
        re.compile(r"^\s*return `(g1d)-\$\{mintRowIdSuffix\(\)\}`\s*$"),
    ),
    "xlsx/gt-g3-dividend-receivable": (
        "useG3Detail.ts",
        "conclusion",
        re.compile(r"^\s*return `(g3d)-\$\{mintRowIdSuffix\(\)\}`\s*$"),
    ),
    "xlsx/gt-g9-other-noncurrent-financial": (
        "useG9Detail.ts",
        "remark",
        re.compile(r"^\s*return `(g9d)-\$\{Date\.now\(\)"),
    ),
    # C-7：G10 的列模型整体重写（19 列 A..S）⇒ 写入点与 genId 行号都移位。
    # 铸造形态**未**改（仍是 `g10d-${Date.now()}…` 内联），故正则同 G9 形态。
    "xlsx/gt-g10-trading-financial-liabilities": (
        "useG10Detail.ts",
        "remark",
        re.compile(r"^\s*return `(g10d)-\$\{Date\.now\(\)"),
    ),
}
TABLE_TO_ENTRY = {
    "G1-detail-rows": "xlsx/gt-g1-trading-financial-assets",
    "G3-detail-rows": "xlsx/gt-g3-dividend-receivable",
    "G9-detail-rows": "xlsx/gt-g9-other-noncurrent-financial",
    "G10-detail-rows": "xlsx/gt-g10-trading-financial-liabilities",
}

_NULL_COL = re.compile(r"\b(remark|conclusion)\s*:\s*null\s*,?")


def _strip_comment_lines(text: str) -> list[str]:
    """与判据 `_strip_ts_comments` 同口径（按行首标记剔注释行，保留行号占位）。"""
    out: list[str] = []
    for line in text.splitlines():
        t = line.strip()
        out.append("" if (t.startswith("//") or t.startswith("*") or t.startswith("/*")) else line)
    return out


def find_write_site(lines: list[str], column: str) -> int:
    """找 `debouncedSave(...)` 写入点：4 行窗口剔空占位后只见权威列。返回 1-based 行号。"""
    other = "conclusion" if column == "remark" else "remark"
    hits: list[int] = []
    for idx, line in enumerate(lines):
        if "debouncedSave(" not in line:
            continue
        window = "\n".join(lines[idx : idx + 4])
        probe = _NULL_COL.sub("", window)
        if f"{column}:" in probe and f"{other}:" not in probe:
            hits.append(idx + 1)
    if not hits:
        raise SystemExit(f"找不到写 {column} 列的 debouncedSave 点")
    return hits[0]


def find_mint_site(lines: list[str], pattern: re.Pattern[str]) -> tuple[int, str]:
    for idx, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            return idx + 1, line.strip().removeprefix("return ").strip()
    raise SystemExit(f"找不到行身份铸造点 {pattern.pattern!r}")


FIXED_NOTE = (
    "🔴 2026-09-27 已修（spec `g-cycle-single-region-detail-lanes` Task 7）："
    "行身份铸造收口到 `g1g3RowIdentity.ts`，**但前缀留在消费方内联**。改造前两层病灶："
    "①载入路径 `id ?? String(i + 1)` 用**数组下标**当身份（比 BP-7 正文的 G6-sppi 更严重 —— "
    'G6-sppi 至少带时间戳前缀，G1/G3 是纯下标字符串，不同底稿的第 1 行 id 都是 "1"）；'
    "②新增行 `` `row-${Date.now()}` `` 无随机后缀，同毫秒连加两行撞 id。"
    "修法：载入走 `resolveStableRowIds(list, genRowId, stats)`（缺失/下标/同载荷重复才重铸，"
    "而 `row-<ts>` 形态**不无条件重铸** —— 无条件重铸会让每次载入身份都变，比原缺陷更糟）；"
    "新增行走消费方本文件的 `genRowId()`。铸造后由 `loadRowsAndPersistIfMinted()` 立即回写。"
    "判据：前端 `composables/__tests__/g1g3RowIdentityBp7.spec.ts`（17 tests）+ 后端 "
    "`tests/workpaper_sync/test_g_single_region_p1_p3_p5_p6.py::TestG1rP1RowIdentityThreeFamilies`。"
    "🔴 `row_identity_generator_source` 指消费方而非铸造模块：判据要在声明 `id: string` 行模型的"
    "那个文件里逐字回源行身份形态。这也是**前缀 `g1d`/`g3d` 不放共享常量表**的原因 —— 放了就只剩"
    "`newRowId(G_ROW_ID_PREFIX.g1Detail)`，形态回不了源；随机性单点仍在 `mintRowIdSuffix()`。"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not (args.apply or args.check):
        ap.error("需要 --apply 或 --check")

    data = json.loads(SLICE.read_text(encoding="utf-8"))
    resolved: dict[str, dict[str, str]] = {}
    for entry_id, (fname, column, mint_pat) in TARGETS.items():
        lines = _strip_comment_lines((COMP / fname).read_text(encoding="utf-8"))
        write_line = find_write_site(lines, column)
        mint_line, form = find_mint_site(lines, mint_pat)
        resolved[entry_id] = {
            "payload_column_source": f"{COMP_REL}/{fname}#L{write_line}",
            "row_identity_generator_source": f"{COMP_REL}/{fname}#L{mint_line}",
            "row_identity_generator_form": form,
        }
        print(f"{entry_id}\n    写入点 L{write_line}（{column}）\n    铸造点 L{mint_line} {form}")

    changed: list[str] = []
    for entry in data["independent_entries"]:
        patch = resolved.get(entry["entry_id"])
        if not patch:
            continue
        store = entry["html_counterpart"]
        for key, value in patch.items():
            if store.get(key) != value:
                changed.append(f"{entry['entry_id']}.{key}: {store.get(key)!r} -> {value!r}")
                store[key] = value

    for table in data.get("dynamic_row_identity", {}).get("tables", []):
        entry_id = TABLE_TO_ENTRY.get(table.get("store_key", ""))
        if not entry_id:
            continue
        ident = table.get("row_identity", {})
        patch = resolved[entry_id]
        for key, slice_key in (
            ("row_identity_generator_form", "generator_form"),
            ("row_identity_generator_source", "source_ref"),
        ):
            if slice_key in ident and ident[slice_key] != patch[key]:
                changed.append(f"{table['store_key']}.{slice_key}: {ident[slice_key]!r} -> {patch[key]!r}")
                ident[slice_key] = patch[key]

    for bp in data.get("blocking_practices", []):
        if bp.get("id") == "BP-7" and bp.get("fixed_note") != FIXED_NOTE:
            changed.append("BP-7.fixed_note 更新")
            bp["fixed_note"] = FIXED_NOTE

    if not changed:
        print("\n无需改动（已同步）")
        return 0
    print("\n待改 %d 处:" % len(changed))
    for c in changed:
        print("  -", c)
    if args.apply:
        SLICE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("已写回", SLICE.name)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
