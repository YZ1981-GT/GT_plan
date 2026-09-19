"""幂等修订 N3 / N4 / N5 的公式预设（`prefill_formula_mapping.json`）。

spec: `.kiro/specs/n345-four-table-extraction-alignment/` R8

为什么需要本脚本
----------------
`prefill_formula_mapping.json` 的 N3 / N4 / N5 段存在多类**科目与口径错误**，
且它经 `preset_library.convert_prefill_presets()` 直接进底稿页的「公式管理」，
用户看到的就是这些表达式。逐条依据（全部 DB / 活体只读实证）：

1. **`1812` 是不存在的科目码** —— 活体 `tb_balance` 全库 0 命中；递延所得税负债是 **`2901`**
   （`report_config` 四准则一致 `BS-067 递延所得税负债 = TB('2901','期末余额')`）。
   N3「明细表N3-2」块与 N5「N5-8递延所得税费用核对表」块都在用它 → 取数恒空。
   N3-2 块的描述甚至自认「1812 无数据，占位」。

2. **N3 审定表块整块是从 N5 复制来的** —— `wp_name` 写「所得税费用审定表」、
   `account_codes` 写 `['6801']`（所得税费用），而该块的 sheet 是
   「递延所得税负债审定表N3-1」→ N3 页的公式管理里全是所得税费用的取数。

3. **损益类用了 `期末余额`** —— N4（`6403`）/ N5（`6801`）都是损益类，
   `report_config` 实证口径是 `本期发生额`（`IS-003` / `IS-023`），
   平台铁律亦为「损益取发生额」。

4. **N5-4「利润总额」用 `TB('6001',...)`** —— `6001` 活体是「主营业务收入 / 营业收入」，
   不是利润总额；`IS-022 三、利润总额 = ROW('IS-019')+ROW('IS-020')-ROW('IS-021')`
   是**派生行**。prefill 引擎无 `ROW`/`REPORT` 解析器 → 只能降级 `PLACEHOLDER`
   并在描述写明正确来源（同 N1-1「税会差异汇总」范式）。

5. **N5-4「法定税率」用 `WP('N5','所得税费用审定表N5-1','审定数')`** —— 税率不等于
   审定金额，取回来是个金额 → 降级 `PLACEHOLDER`。

6. **N4「城建税_期末余额」用 `TB('6403.01',...)`** —— 活体实测 `6403.01` 在某客户是
   「印花税」，`6403.02` 既是「税金及附加_城市维护建设税」也是「车船税」→
   **子科目编码语义在客户间冲突**，不可作税种判据（按税种取数已由后端
   `_classify_n4_subaccount` 按**名称**实现）→ 删该 cell，宁缺勿造。

7. **补 N5 `6801.01 当期` / `6801.02 递延` 叶子预设** —— 活体这两个子科目语义清晰稳定。

另：`convert_prefill_presets` 的 `page_key = f"workpaper:{wp_code}"` **忽略 sheet**，
故同一 wp_code 内 `cell_ref` 必须唯一（同名会互相遮蔽，`seed_formula_presets --check`
的 `Skipped (duplicate page_key+target_cell)` 就是被吞掉的条数）→ 本脚本顺带把
N3 / N4 / N5 内重复的 `上年审定数` 按 sheet 加后缀去重。

用法::

    python -m scripts.fix.fix_n345_prefill_presets --dry-run   # 只打印差异
    python -m scripts.fix.fix_n345_prefill_presets             # 就地修订
    python -m scripts.fix.fix_n345_prefill_presets --check      # 不一致则 exit 1（CI）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "prefill_formula_mapping.json"

# 科目真源（DB 只读实证）
DTL_CODE = "2901"        # 递延所得税负债（BS-067）
TAX_CODE = "6403"        # 税金及附加（IS-003，本期发生额）
ITE_CODE = "6801"        # 所得税费用（IS-023，本期发生额）
BAD_CODE = "1812"        # 活体 0 命中的不存在科目码
REVENUE_CODE = "6001"    # 营业收入（曾被误当利润总额）

_PERIOD = "本期发生额"
_OPENING = "期初余额"
_CLOSING = "期末余额"


def _cell(ref: str, formula: str | None, ftype: str, desc: str) -> dict[str, Any]:
    return {
        "cell_ref": ref,
        "formula": formula,
        "formula_type": ftype,
        "description": desc,
    }


# ═══════════════════════════ 目标块定义 ═══════════════════════════
# key = (wp_code, sheet)；值 = 完整替换后的块（不存在则追加）

TARGETS: dict[tuple[str, str], dict[str, Any]] = {
    # ── N3 递延所得税负债审定表 ───────────────────────────────────────────────
    ("N3", "递延所得税负债审定表N3-1"): {
        "wp_code": "N3",
        "wp_name": "递延所得税负债审定表",
        "sheet": "递延所得税负债审定表N3-1",
        "account_codes": [DTL_CODE],
        "cells": [
            _cell("期初余额", f"=TB('{DTL_CODE}','{_OPENING}')", "TB",
                  f"从试算表取递延所得税负债期初余额（科目 {DTL_CODE}；报表行 BS-067 同口径）"),
            _cell("未审数", f"=TB('{DTL_CODE}','{_CLOSING}')", "TB",
                  "从试算表取递延所得税负债期末余额（未审）"),
            _cell("AJE调整", f"=ADJ('{DTL_CODE}','aje_net')", "ADJ",
                  "递延所得税负债审计调整分录净额"),
            _cell("RJE调整", f"=ADJ('{DTL_CODE}','rje_net')", "ADJ",
                  "递延所得税负债重分类调整分录净额"),
            _cell("审定表N3-1_上年审定数",
                  "=PREV('N3','递延所得税负债审定表N3-1','审定数')", "PREV",
                  "上年同底稿审定数（cell_ref 带 sheet 前缀：page_key 忽略 sheet，同名会遮蔽）"),
        ],
    },
    # ── N3 明细表 ────────────────────────────────────────────────────────────
    ("N3", "明细表N3-2"): {
        "wp_code": "N3",
        "wp_name": "递延所得税负债明细",
        "sheet": "明细表N3-2",
        "account_codes": [DTL_CODE],
        "cells": [
            _cell("递延负债_期末余额", f"=TB('{DTL_CODE}','{_CLOSING}')", "TB",
                  f"递延所得税负债期末余额（原写 {BAD_CODE}，该科目码在活体 tb_balance 全库 0 命中）"),
            _cell("递延负债_期初余额", f"=TB('{DTL_CODE}','{_OPENING}')", "TB",
                  "递延所得税负债期初余额"),
            _cell("明细表N3-2_上年审定数", "=PREV('N3','明细表N3-2','审定数')", "PREV",
                  "递延所得税负债明细上年审定数"),
            _cell("递延负债_本期变动", None, "PLACEHOLDER",
                  "本期变动额 = 期末余额 − 期初余额；由前端派生（余额类科目无「借方发生额」列口径，"
                  "原写 =TB('1812','借方发生额') 双重错误）"),
        ],
    },
    # ── N4 税金及附加审定表（损益类 → 本期发生额）──────────────────────────────
    ("N4", "税金及附加审定表N4-1"): {
        "wp_code": "N4",
        "wp_name": "税金及附加审定表",
        "sheet": "税金及附加审定表N4-1",
        "account_codes": [TAX_CODE],
        "cells": [
            _cell("未审数", f"=TB('{TAX_CODE}','{_PERIOD}')", "TB",
                  f"从试算表取税金及附加**本期发生额**（报表行 IS-003 = TB('{TAX_CODE}','{_PERIOD}')；"
                  "损益类不取期末余额）"),
            _cell("AJE调整", f"=ADJ('{TAX_CODE}','aje_net')", "ADJ", "税金及附加审计调整分录净额"),
            _cell("RJE调整", f"=ADJ('{TAX_CODE}','rje_net')", "ADJ", "税金及附加重分类调整分录净额"),
            _cell("审定表N4-1_上年审定数", "=PREV('N4','税金及附加审定表N4-1','审定数')", "PREV",
                  "上年同底稿审定数"),
        ],
    },
    # ── N4 明细表 ────────────────────────────────────────────────────────────
    ("N4", "明细表N4-2"): {
        "wp_code": "N4",
        "wp_name": "税金及附加明细",
        "sheet": "明细表N4-2",
        "account_codes": [TAX_CODE],
        "cells": [
            _cell("税金及附加_本期发生额", f"=TB('{TAX_CODE}','{_PERIOD}')", "TB",
                  "税金及附加本期发生额（损益类；原写 期末余额）"),
            _cell("明细表N4-2_上年审定数", "=PREV('N4','明细表N4-2','审定数')", "PREV",
                  "税金及附加明细上年审定数"),
            # 🔴 已删「城建税_期末余额 = TB('6403.01','期末余额')」：
            #    活体实测 6403.01 在某客户是「印花税」，6403.02 既是「城市维护建设税」
            #    也是「车船税」→ 子科目编码语义客户间冲突，不可作税种判据。
            #    按税种取数已由后端 `_classify_n4_subaccount` 按**名称**实现。
        ],
    },
    # ── N4 审计程序表（跨底稿引用，保留但纠正口径描述）─────────────────────────
    ("N4", "税金及附加审计程序表N4A "): {
        "wp_code": "N4",
        "wp_name": "税金及附加审计程序表",
        "sheet": "税金及附加审计程序表N4A ",
        "account_codes": [TAX_CODE],
        "cells": [
            _cell("税金及附加_审定数", "=WP('N4','税金及附加审定表N4-1','审定数')", "WP",
                  "从 N4-1 审定表取税金及附加审定数（本期发生额口径）"),
            _cell("增值税_应交数", "=WP('N2','应交税费审定表N2-1','审定数')", "WP",
                  "从 N2 审定表取应交税费审定数（各税种费用确认与 N2 计提对应核对）"),
        ],
    },
    # ── N5 所得税费用审定表（损益类 → 本期发生额）──────────────────────────────
    ("N5", "所得税费用审定表N5-1"): {
        "wp_code": "N5",
        "wp_name": "所得税费用审定表",
        "sheet": "所得税费用审定表N5-1",
        "account_codes": [ITE_CODE],
        "cells": [
            _cell("未审数", f"=TB('{ITE_CODE}','{_PERIOD}')", "TB",
                  f"从试算表取所得税费用**本期发生额**（报表行 IS-023 = TB('{ITE_CODE}','{_PERIOD}')；"
                  "损益类不取期末余额）"),
            _cell("当期所得税费用_本期发生额", f"=TB('{ITE_CODE}.01','{_PERIOD}')", "TB",
                  f"科目 {ITE_CODE}.01 当期所得税费用本期发生额（活体叶子语义稳定）"),
            _cell("递延所得税费用_本期发生额", f"=TB('{ITE_CODE}.02','{_PERIOD}')", "TB",
                  f"科目 {ITE_CODE}.02 递延所得税费用本期发生额（活体可为负，语义即贷方性质）"),
            _cell("AJE调整", f"=ADJ('{ITE_CODE}','aje_net')", "ADJ", "所得税费用审计调整分录净额"),
            _cell("RJE调整", f"=ADJ('{ITE_CODE}','rje_net')", "ADJ", "所得税费用重分类调整分录净额"),
            _cell("审定表N5-1_上年审定数", "=PREV('N5','所得税费用审定表N5-1','审定数')", "PREV",
                  "上年同底稿审定数"),
        ],
    },
    # ── N5 明细表 ────────────────────────────────────────────────────────────
    ("N5", "明细表N5-2"): {
        "wp_code": "N5",
        "wp_name": "所得税费用明细",
        "sheet": "明细表N5-2",
        "account_codes": [ITE_CODE],
        "cells": [
            _cell("所得税费用_本期发生额", f"=TB('{ITE_CODE}','{_PERIOD}')", "TB",
                  "所得税费用本期发生额（损益类；原写 期末余额）"),
            _cell("递延所得税资产变动", "=WP('N1','递延所得税资产审定表N1-1','审定数')", "WP",
                  "从 N1 审定表取递延所得税资产审定数（sheet 名补全为源模板 tab 名）"),
        ],
    },
    # ── N5-4 当期所得税费用计算表 ─────────────────────────────────────────────
    ("N5", "N5-4当期所得税费用计算表"): {
        "wp_code": "N5",
        "wp_name": "当期所得税费用计算表",
        "sheet": "N5-4当期所得税费用计算表",
        "account_codes": [ITE_CODE],
        "cells": [
            _cell("利润总额", None, "PLACEHOLDER",
                  f"利润总额取自报表行 IS-022（`ROW('IS-019')+ROW('IS-020')-ROW('IS-021')` 派生行），"
                  f"**不是科目**；prefill 引擎无 ROW/REPORT 解析器故暂为占位。"
                  f"原写 =TB('{REVENUE_CODE}','{_CLOSING}') 双重错误：{REVENUE_CODE} 是营业收入，"
                  f"且损益类不取期末余额"),
            _cell("法定税率", None, "PLACEHOLDER",
                  "法定税率是项目税务参数（见 N5-6 税收优惠明细表 / 项目基础信息），非公式取数；"
                  "原写 =WP('N5','所得税费用审定表N5-1','审定数') 取回来是金额而非税率"),
            _cell("当期所得税费用_计算表核对", f"=TB('{ITE_CODE}.01','{_PERIOD}')", "TB",
                  "科目 6801.01 当期所得税费用本期发生额，与本表计算结果核对"),
        ],
    },
    # ── N5-8 递延所得税费用核对表 ─────────────────────────────────────────────
    ("N5", "N5-8递延所得税费用核对表"): {
        "wp_code": "N5",
        "wp_name": "递延所得税费用核对表",
        "sheet": "N5-8递延所得税费用核对表",
        "account_codes": ["1811", DTL_CODE],
        "cells": [
            _cell("递延资产_期末", f"=TB('1811','{_CLOSING}')", "TB",
                  "递延所得税资产期末余额（核对用；报表行 BS-036 同口径）"),
            _cell("递延资产_期初", f"=TB('1811','{_OPENING}')", "TB", "递延所得税资产期初余额"),
            _cell("递延负债_期末", f"=TB('{DTL_CODE}','{_CLOSING}')", "TB",
                  f"递延所得税负债期末余额（原写 {BAD_CODE}，活体 0 命中；报表行 BS-067 同口径）"),
            _cell("递延负债_期初", f"=TB('{DTL_CODE}','{_OPENING}')", "TB", "递延所得税负债期初余额"),
        ],
    },
}

# 需整块删除的（wp_code, sheet）—— 当前无
DROPS: set[tuple[str, str]] = set()


# ═══════════════════════════ apply ═══════════════════════════


def _key(m: dict[str, Any]) -> tuple[str, str]:
    return (str(m.get("wp_code") or "").strip(), str(m.get("sheet") or ""))


def apply(*, check_only: bool = False, dry_run: bool = False) -> bool:
    """返回 True 表示存在待修订内容。"""
    doc = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    mappings: list[dict[str, Any]] = doc.get("mappings") or []

    changes: list[str] = []
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []

    for m in mappings:
        k = _key(m)
        if k in DROPS:
            changes.append(f"删除块 {k[0]} / {k[1]}")
            continue
        target = TARGETS.get(k)
        if target is None:
            out.append(m)
            continue
        seen.add(k)
        if m != target:
            old_refs = [c.get("cell_ref") for c in (m.get("cells") or [])]
            new_refs = [c.get("cell_ref") for c in target["cells"]]
            detail: list[str] = []
            if m.get("account_codes") != target["account_codes"]:
                detail.append(f"科目 {m.get('account_codes')} → {target['account_codes']}")
            if m.get("wp_name") != target["wp_name"]:
                detail.append(f"名称 {m.get('wp_name')!r} → {target['wp_name']!r}")
            dropped = [r for r in old_refs if r not in new_refs]
            added = [r for r in new_refs if r not in old_refs]
            if dropped:
                detail.append(f"删 cell {dropped}")
            if added:
                detail.append(f"增 cell {added}")
            changes.append(f"{k[0]} / {k[1]}：" + "；".join(detail or ["公式/描述更新"]))
        out.append(dict(target))

    # 目标块不存在 → 追加
    for k, target in TARGETS.items():
        if k in seen:
            continue
        changes.append(f"新增块 {k[0]} / {k[1]}")
        out.append(dict(target))

    if not changes:
        print("[n345-presets] 已对齐，无需修改")
        return False

    print(f"[n345-presets] {len(changes)} 处待修订：")
    for c in changes:
        print(f"    - {c}")

    if check_only or dry_run:
        return True

    doc["mappings"] = out
    DATA_PATH.write_bytes(
        json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
    )
    print(f"[n345-presets] 已写入 {DATA_PATH.name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只校验不写盘，不一致则 exit 1")
    parser.add_argument("--dry-run", action="store_true", help="只打印差异摘要，不写盘")
    args = parser.parse_args()
    changed = apply(check_only=args.check, dry_run=args.dry_run)
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
