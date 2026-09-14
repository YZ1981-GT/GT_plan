"""H 类公式预设纠偏（第二阶段） —— 幂等脚本。

修订六类缺陷（判据全部来自 `backend/data/prefill_formula_mapping.json` 与
真实库实证，见 spec Requirements 2/3）：

===  =========================================  =====
 #   类别                                        处数
===  =========================================  =====
 ①   H3 审定表整块贴错（使用权资产口径 → 投资性房地产）   5
 ②   H8/H9 双族并取（1641/1651、2601/2651）          13
 ③   H10 审定表「期初余额」改 PREV（损益类无期初）        1
 ④   删 H2 明细表硬编码项目号（B510003/B510006）        4
 ⑤   补 `WP()` 底稿间联动（H1-1/H2-1/H8-1/H9-1）        6
 ⑥   H1 分析程序区间上界越界（1601~1604 → 1601~1603）    1
===  =========================================  =====

**为什么 ② 是「加和」不是「改码」**

`ROU_LEASE_DUAL_FAMILIES` 的 evidence 已实证：旧族 `1641`/`2601` 与新族
`1651`/`2651` 在**同一项目内互斥**（9 项目逐个查），唯一两族并存的项目双方
均为 0.00 ⇒ ``TB(a)+TB(b)`` 零双算；而改码会重演 V138「改对码反而暴雷」。

**为什么 ⑥ 是真缺陷**

``TB_SUM('1601~1604','期末余额')`` 把 `1604` 在建工程（BS-029，H2 循环）、
`1605` 工程物资（H4）、`1606` 固定资产清理（H6）全扫进「固定资产合计」。
固定资产族的正确区间是 ``1601~1603``（原值/累计折旧/减值准备）。

用法::

    python backend/scripts/fix/fix_h_cycle_prefill_presets_phase2.py            # dry-run
    python backend/scripts/fix/fix_h_cycle_prefill_presets_phase2.py --check    # 有欠账 exit 1
    python backend/scripts/fix/fix_h_cycle_prefill_presets_phase2.py --apply    # 写盘

🔴 **round-trip 自检**：写盘前先确认 ``json.dumps`` 能逐字复现原文，
不能则 exit 2（防全文件重排把并发会话的改动冲掉）。

🔴 控制台输出**禁 emoji** —— GBK 控制台 `print('✅')` 抛 UnicodeEncodeError，
而崩点在写盘**之后** ⇒ 退出码非零但改动已落盘，极易误判成「apply 失败」。

spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
      Requirements 2.1~2.7 / 3.1~3.7
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.four_table.dual_family_codes import (  # noqa: E402
    DUAL_FAMILY_BY_SLOT,
    tb_expression,
)

PRESET_PATH = _BACKEND / "data" / "prefill_formula_mapping.json"

# ── 双族码（从单一真源派生，禁写字面量）──
_ROU_GROSS = DUAL_FAMILY_BY_SLOT["gross"].codes            # ('1641', '1651')
_ROU_DEP = DUAL_FAMILY_BY_SLOT["accum_dep"].codes          # ('1642', '1652')
_LEASE = DUAL_FAMILY_BY_SLOT["lease_liability"].codes      # ('2601', '2651')


def _tb(codes: tuple[str, ...], col: str) -> str:
    return "=" + tb_expression(codes, col)


# ═══════════════════════════════════════════════════════════════════════════
# 变更计划：(wp_code, sheet) → {cell_ref: {字段: 新值}}
#
# `formula` / `formula_type` / `description` 三者一并给，
# 避免出现「公式改了但 description 还写着旧科目」的漂移。
# ═══════════════════════════════════════════════════════════════════════════

#: ① H3 审定表（成本模式）—— 整块从使用权资产口径改回投资性房地产
_H3_ADJ = {
    "期初余额": {
        "formula": "=TB('1521','期初余额')",
        "formula_type": "TB",
        "description": "投资性房地产原值期初余额（成本模式）",
    },
    "未审数": {
        "formula": "=TB('1521','期末余额')",
        "formula_type": "TB",
        "description": "投资性房地产原值期末余额（未审，成本模式）",
    },
    "累计折旧_期初": {
        "formula": "=TB('1525','期初余额')",
        "formula_type": "TB",
        "description": "投资性房地产累计折旧期初余额",
    },
    "累计折旧_未审数": {
        "formula": "=TB('1525','期末余额')",
        "formula_type": "TB",
        "description": "投资性房地产累计折旧期末余额（未审）",
    },
    "减值准备_未审数": {
        "formula": "=TB('1527','期末余额')",
        "formula_type": "TB",
        "description": "投资性房地产减值准备期末余额（未审）",
    },
    "AJE调整": {
        "formula": "=ADJ('1521','aje_net')",
        "formula_type": "ADJ",
        "description": "投资性房地产审计调整分录净额",
    },
    "RJE调整": {
        "formula": "=ADJ('1521','rje_net')",
        "formula_type": "ADJ",
        "description": "投资性房地产重分类调整分录净额",
    },
}

#: ② H8 审定表 —— 双族并取
_H8_ADJ = {
    "期初余额": {
        "formula": _tb(_ROU_GROSS, "期初余额"),
        "formula_type": "TB",
        "description": (
            "使用权资产原值期初余额（双族并取：旧族 1641 + 新族 1651；"
            "两族在同一项目内互斥故加和零双算，见 dual_family_codes）"
        ),
    },
    "未审数": {
        "formula": _tb(_ROU_GROSS, "期末余额"),
        "formula_type": "TB",
        "description": "使用权资产原值期末余额（未审，双族并取 1641+1651）",
    },
    "累计折旧_期初": {
        "formula": _tb(_ROU_DEP, "期初余额"),
        "formula_type": "TB",
        "description": "使用权资产累计折旧期初余额（双族并取 1642+1652）",
    },
    "累计折旧_未审数": {
        "formula": _tb(_ROU_DEP, "期末余额"),
        "formula_type": "TB",
        "description": "使用权资产累计折旧期末余额（未审，双族并取 1642+1652）",
    },
    "AJE调整": {
        "formula": "=ADJ('1641','aje_net')+ADJ('1651','aje_net')",
        "formula_type": "ADJ",
        "description": "使用权资产审计调整分录净额（双族并取）",
    },
    "RJE调整": {
        "formula": "=ADJ('1641','rje_net')+ADJ('1651','rje_net')",
        "formula_type": "ADJ",
        "description": "使用权资产重分类调整分录净额（双族并取）",
    },
}

#: ② H8 明细表 —— 双族并取
_H8_DETAIL = {
    "使用权资产_期初": {
        "formula": _tb(_ROU_GROSS, "期初余额"),
        "formula_type": "TB",
        "description": "使用权资产原值期初余额（双族并取 1641+1651）",
    },
    "使用权资产_期末": {
        "formula": _tb(_ROU_GROSS, "期末余额"),
        "formula_type": "TB",
        "description": "使用权资产原值期末余额（双族并取 1641+1651）",
    },
    "使用权资产_本期增加": {
        "formula": _tb(_ROU_GROSS, "本期借方"),
        "formula_type": "TB",
        "description": "使用权资产本期增加（新增租赁；借方发生额，双族并取）",
    },
    "使用权资产累计折旧_期初": {
        "formula": _tb(_ROU_DEP, "期初余额"),
        "formula_type": "TB",
        "description": "使用权资产累计折旧期初（双族并取 1642+1652）",
    },
    "使用权资产累计折旧_期末": {
        "formula": _tb(_ROU_DEP, "期末余额"),
        "formula_type": "TB",
        "description": "使用权资产累计折旧期末（双族并取 1642+1652）",
    },
    "使用权资产累计折旧_本期计提": {
        "formula": _tb(_ROU_DEP, "本期贷方"),
        "formula_type": "TB",
        "description": "使用权资产本期折旧计提（贷方发生额，双族并取）",
    },
}

#: ② H9 审定表 —— 双族并取
_H9_ADJ = {
    "期初余额": {
        "formula": _tb(_LEASE, "期初余额"),
        "formula_type": "TB",
        "description": (
            "租赁负债期初余额（双族并取 2601+2651）。"
            "🔴 新族把未确认融资费用做成 2651.02 子科目，已含在 2651 父额内，"
            "故此处**不再单独减 2602**（会双算）"
        ),
    },
    "未审数": {
        "formula": _tb(_LEASE, "期末余额"),
        "formula_type": "TB",
        "description": "租赁负债期末余额（未审，双族并取 2601+2651）",
    },
    "AJE调整": {
        "formula": "=ADJ('2601','aje_net')+ADJ('2651','aje_net')",
        "formula_type": "ADJ",
        "description": "租赁负债审计调整分录净额（双族并取）",
    },
    "RJE调整": {
        "formula": "=ADJ('2601','rje_net')+ADJ('2651','rje_net')",
        "formula_type": "ADJ",
        "description": "租赁负债重分类调整分录净额（双族并取）",
    },
}

#: ② H9 明细表 —— 双族并取
_H9_DETAIL = {
    "租赁负债_期初": {
        "formula": _tb(_LEASE, "期初余额"),
        "formula_type": "TB",
        "description": "租赁负债期初余额（双族并取 2601+2651）",
    },
    "租赁负债_期末": {
        "formula": _tb(_LEASE, "期末余额"),
        "formula_type": "TB",
        "description": "租赁负债期末余额（双族并取 2601+2651）",
    },
    "租赁负债_本期增加": {
        "formula": _tb(_LEASE, "本期贷方"),
        "formula_type": "TB",
        "description": "租赁负债本期增加（新增租赁确认；贷方发生额，双族并取）",
    },
    "租赁负债_本期偿还": {
        "formula": _tb(_LEASE, "本期借方"),
        "formula_type": "TB",
        "description": "租赁负债本期偿还（租金支付；借方发生额，双族并取）",
    },
    "租赁负债_利息费用": {
        "formula": "=LEDGER('2601','credit','全年')+LEDGER('2651','credit','全年')",
        "formula_type": "LEDGER",
        "description": "租赁负债全年利息费用（贷方发生额含利息确认，双族并取）",
    },
}

#: ③ H10 审定表 —— 损益类期初走 PREV
_H10_ADJ = {
    "期初余额": {
        "formula": "=PREV('H10','审定表H10-1','审定数')",
        "formula_type": "PREV",
        "description": (
            "🔴 损益类**无期初余额** —— 上年数只能取上年同底稿审定数。"
            "改造前此格与「未审数」逐字相同（都是 TB('6115','本期发生额')），"
            "让「期初」列显示本期数，是数字错"
        ),
    },
}

#: ⑥ H1 分析程序 —— 区间上界收回固定资产族
_H1_ANALYSIS = {
    "本年未审数": {
        "formula": "=TB_SUM('1601~1603','期末余额')",
        "formula_type": "TB_SUM",
        "description": (
            "固定资产族期末余额合计（未审）。"
            "🔴 上界由 1604 收回 1603 —— 1604 是在建工程（BS-029，H2 循环）、"
            "1605 工程物资（H4）、1606 固定资产清理（H6），区间不得跨循环"
        ),
    },
}

#: ⑤ 新增 `WP()` 联动（审定表←明细表；明细表禁反向引用防成环）
_WP_ADDITIONS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("H1", "审定表H1-1"): [
        {
            "cell_ref": "明细表合计_原值",
            "formula": "=WP('H1','明细表H1-2','固定资产原值_期末')",
            "formula_type": "WP",
            "description": "从 H1-2 固定资产明细表带入原值期末合计（与审定数核对）",
        },
        {
            "cell_ref": "折旧测算_全年折旧",
            "formula": "=WP('H1','折旧测算表（不含减值）-直线法H1-12','全年折旧合计')",
            "formula_type": "WP",
            "description": "从 H1-12 折旧测算表带入全年折旧合计（与累计折旧变动核对）",
        },
    ],
    ("H2", "审定表H2-1"): [
        {
            "cell_ref": "明细表合计_期末",
            "formula": "=WP('H2','明细表H2-2','在建工程_期末')",
            "formula_type": "WP",
            "description": "从 H2-2 在建工程明细表带入期末合计（与审定数核对）",
        },
    ],
    ("H8", "审定表H8-1"): [
        {
            "cell_ref": "明细表合计_原值",
            "formula": "=WP('H8','明细表H8-2','使用权资产_期末')",
            "formula_type": "WP",
            "description": "从 H8-2 使用权资产明细表带入原值期末合计",
        },
    ],
    ("H9", "审定表H9-1"): [
        {
            "cell_ref": "明细表合计_期末",
            "formula": "=WP('H9','租赁负债明细表H9-2','租赁负债_期末')",
            "formula_type": "WP",
            "description": "从 H9-2 租赁负债明细表带入期末合计",
        },
        {
            "cell_ref": "未确认融资费用_期末",
            "formula": "=WP('H9','未确认融资费用明细表H9-3','未确认融资费用_期末')",
            "formula_type": "WP",
            "description": "从 H9-3 未确认融资费用明细表带入期末余额",
        },
    ],
}

#: ④ 删除的 cell_ref（H2 明细表硬编码项目号）
_DROP_CELLS: dict[tuple[str, str], tuple[str, ...]] = {
    ("H2", "明细表H2-2"): (
        "项目B510003_期末",
        "项目B510006_期末",
        "项目B510003_期初",
        "项目B510006_期初",
    ),
}

#: cell 级公式改写计划
_CELL_UPDATES: dict[tuple[str, str], dict[str, dict[str, Any]]] = {
    ("H3", "审定表（成本模式）H3-1"): _H3_ADJ,
    ("H8", "审定表H8-1"): _H8_ADJ,
    ("H8", "明细表H8-2"): _H8_DETAIL,
    ("H9", "审定表H9-1"): _H9_ADJ,
    ("H9", "租赁负债明细表H9-2"): _H9_DETAIL,
    ("H10", "审定表H10-1"): _H10_ADJ,
    ("H1", "分析程序H1-3"): _H1_ANALYSIS,
}

#: `account_codes` 补码（双族 alternate）
_ACCOUNT_ADDITIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("H8", "审定表H8-1"): ("1651", "1652"),
    ("H8", "明细表H8-2"): ("1651", "1652"),
    ("H9", "审定表H9-1"): ("2651",),
    ("H9", "租赁负债明细表H9-2"): ("2651",),
    ("H0", "函证结果汇总表H0-1"): ("1651", "2651"),
}


# ═══════════════════════════════════════════════════════════════════════════
# 计划构建与应用
# ═══════════════════════════════════════════════════════════════════════════


def _key(block: dict) -> tuple[str, str]:
    return (str(block.get("wp_code") or ""), str(block.get("sheet") or ""))


def build_plan(data: dict) -> list[str]:
    """返回待办清单（人类可读）；空列表 = 无欠账。"""
    todo: list[str] = []
    seen: set[tuple[str, str]] = set()

    for block in data.get("mappings", []):
        k = _key(block)
        seen.add(k)
        cells = block.get("cells") or []
        by_ref = {c.get("cell_ref"): c for c in cells}

        for ref, spec in _CELL_UPDATES.get(k, {}).items():
            cur = by_ref.get(ref)
            if cur is None:
                todo.append(f"{k[0]} | {k[1]} | +{ref} (新增格)")
            elif cur.get("formula") != spec["formula"]:
                todo.append(
                    f"{k[0]} | {k[1]} | ~{ref}\n"
                    f"      old: {cur.get('formula')}\n"
                    f"      new: {spec['formula']}"
                )

        for ref in _DROP_CELLS.get(k, ()):
            if ref in by_ref:
                todo.append(f"{k[0]} | {k[1]} | -{ref} (删除硬编码项目号)")

        for spec in _WP_ADDITIONS.get(k, []):
            ref = spec["cell_ref"]
            if ref not in by_ref:
                todo.append(f"{k[0]} | {k[1]} | +{ref} = {spec['formula']}")

        add = _ACCOUNT_ADDITIONS.get(k, ())
        if add:
            cur_codes = [str(c) for c in (block.get("account_codes") or [])]
            missing = [c for c in add if c not in cur_codes]
            if missing:
                todo.append(f"{k[0]} | {k[1]} | account_codes += {missing}")

    for k in set(_CELL_UPDATES) | set(_WP_ADDITIONS) | set(_ACCOUNT_ADDITIONS):
        if k not in seen:
            todo.append(f"[MISS] 计划里的块不存在: {k[0]} | {k[1]}")

    return todo


def apply_plan(data: dict) -> int:
    """就地修改 ``data``，返回变更处数。"""
    n = 0
    for block in data.get("mappings", []):
        k = _key(block)
        cells: list[dict] = block.setdefault("cells", [])

        # ── 删除 ──
        drops = set(_DROP_CELLS.get(k, ()))
        if drops:
            before = len(cells)
            block["cells"] = cells = [
                c for c in cells if c.get("cell_ref") not in drops
            ]
            n += before - len(cells)

        # ── 改写 ──
        by_ref = {c.get("cell_ref"): c for c in cells}
        for ref, spec in _CELL_UPDATES.get(k, {}).items():
            cur = by_ref.get(ref)
            if cur is None:
                cells.append({"cell_ref": ref, **spec})
                n += 1
            elif cur.get("formula") != spec["formula"]:
                cur.update(spec)
                n += 1

        # ── 新增 WP() ──
        by_ref = {c.get("cell_ref"): c for c in cells}
        for spec in _WP_ADDITIONS.get(k, []):
            if spec["cell_ref"] not in by_ref:
                cells.append(dict(spec))
                n += 1

        # ── account_codes 补码 ──
        add = _ACCOUNT_ADDITIONS.get(k, ())
        if add:
            codes = [str(c) for c in (block.get("account_codes") or [])]
            missing = [c for c in add if c not in codes]
            if missing:
                block["account_codes"] = codes + missing
                n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="H 类公式预设纠偏（第二阶段）")
    ap.add_argument("--apply", action="store_true", help="写盘")
    ap.add_argument("--check", action="store_true", help="有欠账 exit 1")
    args = ap.parse_args()

    raw = PRESET_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)

    todo = build_plan(data)

    if args.check:
        if todo:
            print(f"[CHECK] {len(todo)} 项欠账:")
            for t in todo:
                print(f"  - {t}")
            return 1
        print("[CHECK] 0 项欠账")
        return 0

    if not args.apply:
        if not todo:
            print("[DRY-RUN] 0 项欠账，无需修改")
            return 0
        print(f"[DRY-RUN] {len(todo)} 项待修改:")
        for t in todo:
            print(f"  - {t}")
        return 0

    # ── round-trip 自检：确认 json.dumps 能逐字复现原文 ──
    roundtrip = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if roundtrip != raw:
        print(
            "[ERR] round-trip 自检失败 —— json.dumps 无法逐字复现原文，"
            "写盘会重排整个文件并可能冲掉并发会话的改动。"
        )
        print(f"      原文 {len(raw)} 字节 / 复现 {len(roundtrip)} 字节")
        return 2

    changed = apply_plan(data)
    if not changed:
        print("[APPLY] 0 处变更（已是目标状态）")
        return 0

    PRESET_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[APPLY] {changed} 处变更已写入 {PRESET_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
