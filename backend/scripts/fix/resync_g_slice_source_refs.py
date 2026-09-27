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
    # C-8：G8 的列模型整体重写（23 列 A..W，FVOCI）⇒ 同样只有行号移位。
    "xlsx/gt-g8-other-equity-instruments": (
        "useG8Detail.ts",
        "remark",
        re.compile(r"^\s*return `(g8d)-\$\{Date\.now\(\)"),
    ),
    # 🔴 C-9：G14 的行身份是 `rowKey`（`stable_template_row_key`）—— **没有生成器**，
    #    行集由 `G14_LINE_ITEMS` 固定。因此铸造点正则不适用，走 `mint_pat=None` 分支
    #    （只重算 payload 写入点行号）。
    "xlsx/gt-g14-credit-impairment-loss": ("useG14Detail.ts", "remark", None),
    # 🔴 C-10：G11 的前端列模型**零改动**（13 列顺序本就对齐模板）⇒ 行号不变，
    #    加进来是为了让这条也纳入「行号现算」的守护面（将来改了会自动同步）。
    #    生成器随机后缀取 **4** 位 `slice(2, 6)`（G9/G10/G8 取 3 位）—— 正则按值写。
    "xlsx/gt-g11-investment-income": (
        "useG11DetailAnalysis.ts",
        "remark",
        re.compile(r"^\s*return `(g11d)-\$\{Date\.now\(\)"),
    ),
    # 🔴 C-11：G13 的**受管载体换成了分类骨架** `G13-detail-skeleton`（Task 12 裁决），
    #    但 slice 冻结的是**工具明细**形态（`G13-detail-rows` + `g13d-` 生成器）——
    #    那是别人的裁决取证，**字节不改**，这里只重算被本轮改动移位的行号：
    #    `useG13Detail.ts` 加了 ITEM_ID_SKELETON / skeletonStore watch / persistSkeleton /
    #    setSkeletonCell 等 ⇒ 写入点与铸造点都下移。
    #    ⚠️ `find_write_site` 取**第一个**命中的 `debouncedSave` ⇒ 仍是 `ITEM_ID_ROWS` 那处
    #    （`persist()` 在 `persistSkeleton()` 之前），与 slice 的 `transport_key_shape` 一致。
    "xlsx/gt-g13-fair-value-changes": (
        "useG13Detail.ts",
        "remark",
        re.compile(r"^\s*return `(g13d)-\$\{Date\.now\(\)"),
    ),
    # 🔴 C-12：G12 的 `G`/`I` 两列改为落库（新增 `fvCheck`/`netHedgePnl` 字段 + 注释）
    #    ⇒ 写入点与铸造点都下移。生成器后缀取 **3** 位（`slice(2, 5)`），与 G11/G13 的 4 位
    #    不同 —— 正则按值写，不照抄。
    "xlsx/gt-g12-net-hedge-gains": (
        "useG12HedgeDetail.ts",
        "remark",
        re.compile(r"^\s*return `(g12h)-\$\{Date\.now\(\)"),
    ),
}
#: `dynamic_row_identity.tables[].table_key` → entry_id。
#:
#: 🔴 **只放口径已验证一致的两条**（G11 / G13），不是七条全放。实测依据：
#:   该表的 `row_identity.source_ref` 冻结值在六条 lane 里**口径不统一** ——
#:   G11 的 `#L71` 与 G13 改动前的 `#L65` 都是「生成器函数声明行」（与本脚本现算口径一致），
#:   而 G8 `#L76` / G9 `#L82` / G10 `#L109` / G14 `#L61` 都是小行号、指的不是生成器
#:   （更像行接口里 `rowId`/`rowKey` 字段的声明处）。把它们一并「同步」成生成器声明行
#:   会改掉别人的取证口径 ⇒ 排除，留给各自 lane 判定。
#:   G11 留在表里是**活证据**：它现算后逐字不变，证明本脚本的声明行口径没算错。
#: 🔴 G13 的键仍是 `G13-detail-rows`（受管载体虽已换成 `G13-detail-skeleton`，但这张表
#:   记的是「动态行身份」，骨架是固定行集、不属该表范围）。
TABLE_TO_ENTRY = {
    "G11-detail-rows": "xlsx/gt-g11-investment-income",
    "G13-detail-rows": "xlsx/gt-g13-fair-value-changes",
}

#: 🔴 第二口径：`source_ref` 指 **`return` 那一行**（而不是函数声明行）的 entry。
#:
#: 实测 G12 的冻结值 `#L40` 恰是改造前 `genId()` 的 `return` 行（声明行是 L39）⇒ 它与
#: `TABLE_TO_ENTRY` 那组是**两种口径**，混在一起会把其中一组改错一行。
#: G8/G9/G10/G14 的冻结值（`#L76`/`#L82`/`#L109`/`#L61`）两种口径都对不上（差 40~120 行，
#: 指的不是生成器）⇒ 仍然排除，留给各自 lane 判定。
TABLE_TO_ENTRY_RETURN_LINE = {
    "G12-hedge-detail-rows": "xlsx/gt-g12-net-hedge-gains",
}

#: `html_counterpart_source_refs` 里有一项**镜像** `payload_column_source` 的 entry。
#:
#: 🔴 同样只列口径已验证一致的两条：G11 的该项冻结值 `#L233` 与 `payload_column_source`
#:   逐字相同（镜像成立），G13 改动前的 `#L185` 亦然。而 G8 `#L400` / G9 `#L322` /
#:   G10 `#L382` / G14 `#L199` 与各自写入点**不同值** ⇒ 那一项指的是别的取证点
#:   （不是写入点的镜像），跟着改会改掉原意 ⇒ 排除。
SOURCE_REFS_MIRROR_WRITE_SITE = frozenset(
    {"xlsx/gt-g11-investment-income", "xlsx/gt-g13-fair-value-changes"}
)

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


#: 🔴 固定行集（`stable_template_row_key`）没有铸造点 —— 行身份来自模板行集常量。
#:   身份源仍指**消费方 composable** 里的固定行集构造点 `createDefaultRows`：
#:   判据 `test_row_identity_key_and_generator_are_source_backed` 要在同一个文件里同时
#:   回源「`rowKey: string` 的行模型声明」与「createDefaultRows 的构造点」，指向
#:   `g14Constants.ts` 会让后者找不到（本轮实测踩过）。
_FIXED_ROW_SET_ANCHOR = re.compile(r"^function createDefaultRows\b")
_FIXED_ROW_SET_FORM = (
    "stable_template_row_key（行集由 G14_LINE_ITEMS 固定，rowKey 不生成也不派生自位置；"
    "合计行 rowKey='total'）"
)


#: 生成器**函数声明行**锚点（`dynamic_row_identity.source_ref` 用的是这一行，
#: 与 `html_counterpart.row_identity_generator_source` 指的 `return` 行差一行 ——
#: 🔴 两个字段口径不同，不能互相覆盖，见 `_resolve_decl_line` 的 docstring）。
_FUNC_DECL = re.compile(r"^\s*(?:export\s+)?function\s+\w+")


def _resolve_decl_line(lines: list[str], return_line: int) -> int:
    """从 `return` 行往上找最近的 `function ...` 声明行（1-based）。

    🔴 为什么要单独算：slice 里有两个指向生成器的引用，**口径不同**——
      * `html_counterpart.row_identity_generator_source` → `return` 那一行
        （逐字回源「身份形态」，判据要在这一行读到前缀与随机后缀）；
      * `dynamic_row_identity.tables[].row_identity.source_ref` → **函数声明行**
        （回源「哪个函数负责铸造」）。
    实证：G11 的两处冻结值是 `#L72`（return）与 `#L71`（声明）—— 差一行。
    早先 `dynamic_row_identity` 那段同步代码读的是 `table.get("store_key")`，而 slice
    里的字段名是 `table_key` ⇒ 该段**从未生效**（六条 lane 的 `source_ref` 全是旧值）。
    本轮修了字段名，同时按本函数现算声明行 —— 而不是把 `return` 行号灌进去改掉口径。
    """
    for idx in range(return_line - 1, 0, -1):
        if _FUNC_DECL.match(lines[idx - 1]):
            return idx
    return return_line


def find_mint_site(
    lines: list[str], pattern: re.Pattern[str] | None, *, fname: str = ""
) -> tuple[int, str, int]:
    """定位行身份铸造点，返回 `(return 行, 形态串, 函数声明行)`。

    `pattern=None` ⇒ 该 entry 是**固定行集**（G14），没有生成器：回到 composable 里的
    固定行集构造点 `createDefaultRows`，形态串写死为 `_FIXED_ROW_SET_FORM`
    （与 slice 冻结值逐字一致）；此时两个口径重合（锚点本身就是声明行）。
    """
    if pattern is None:
        for idx, line in enumerate(lines):
            if _FIXED_ROW_SET_ANCHOR.match(line):
                return idx + 1, _FIXED_ROW_SET_FORM, idx + 1
        raise SystemExit(f"找不到固定行集构造点 createDefaultRows（{fname}）")
    for idx, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            return (
                idx + 1,
                line.strip().removeprefix("return ").strip(),
                _resolve_decl_line(lines, idx + 1),
            )
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
        mint_line, form, decl_line = find_mint_site(lines, mint_pat, fname=fname)
        resolved[entry_id] = {
            "payload_column_source": f"{COMP_REL}/{fname}#L{write_line}",
            "row_identity_generator_source": f"{COMP_REL}/{fname}#L{mint_line}",
            "row_identity_generator_form": form,
            #: 🔴 `dynamic_row_identity` 专用口径：函数**声明行**（见 `_resolve_decl_line`）
            "_decl_source": f"{COMP_REL}/{fname}#L{decl_line}",
        }
        print(
            f"{entry_id}\n    写入点 L{write_line}（{column}）"
            f"\n    铸造点 L{mint_line}（声明行 L{decl_line}） {form}"
        )

    changed: list[str] = []
    for entry in data["independent_entries"]:
        patch = resolved.get(entry["entry_id"])
        if not patch:
            continue
        store = entry["html_counterpart"]
        for key, value in patch.items():
            if key.startswith("_"):
                continue  # 内部口径（`_decl_source`）不写进 html_counterpart
            if store.get(key) != value:
                changed.append(f"{entry['entry_id']}.{key}: {store.get(key)!r} -> {value!r}")
                store[key] = value
        # 🔴 `html_counterpart_source_refs` 里**镜像写入点**的那一项也要跟着走。
        #    同样只对口径已验证一致的两条生效（见 `SOURCE_REFS_MIRROR_WRITE_SITE`）。
        if entry["entry_id"] in SOURCE_REFS_MIRROR_WRITE_SITE:
            fname = TARGETS[entry["entry_id"]][0]
            want = patch["payload_column_source"]
            refs = entry.get("html_counterpart_source_refs") or []
            for i, ref in enumerate(refs):
                if not str(ref).startswith(f"{COMP_REL}/{fname}#L"):
                    continue
                if ref != want:
                    changed.append(
                        f"{entry['entry_id']}.html_counterpart_source_refs[{i}]: "
                        f"{ref!r} -> {want!r}"
                    )
                    refs[i] = want

    # 🔴 修：早先这里读 `table.get("store_key")`，而 slice 的字段名是 **`table_key`**
    #    ⇒ 整段 for 从未命中、六条 lane 的 `source_ref` 一直是旧值（本轮实测发现）。
    #    同时 `source_ref` 用**声明行**口径（`_decl_source`）而不是 `return` 行 ——
    #    灌 return 行号会把这个字段的语义改掉（见 `_resolve_decl_line` docstring）。
    for table in data.get("dynamic_row_identity", {}).get("tables", []):
        table_key = str(table.get("table_key") or table.get("store_key") or "")
        entry_id = TABLE_TO_ENTRY.get(table_key)
        # 两种口径二选一：声明行（G11/G13）或 return 行（G12）
        ref_key = "_decl_source"
        if entry_id is None:
            entry_id = TABLE_TO_ENTRY_RETURN_LINE.get(table_key)
            ref_key = "row_identity_generator_source"
        if not entry_id:
            continue
        ident = table.get("row_identity", {})
        patch = resolved[entry_id]
        for slice_key, value in (
            ("generator_form", patch["row_identity_generator_form"]),
            ("source_ref", patch[ref_key]),
        ):
            if slice_key in ident and ident[slice_key] != value:
                changed.append(f"{table_key}.{slice_key}: {ident[slice_key]!r} -> {value!r}")
                ident[slice_key] = value

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
