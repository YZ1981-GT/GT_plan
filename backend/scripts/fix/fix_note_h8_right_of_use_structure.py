#!/usr/bin/env python
"""附注「使用权资产」章节补 columns/guidance + 展开 `……` 占位列头（幂等）。

**背景**（源模板 `backend/wp_templates/H/H8 使用权资产.xlsx`）：
两版**行集已与源模板逐行一致**（上市 sheet 行 7~45 四层 38 行 / 国企 sheet 行 7~31
五层 25 行），欠账在列元数据与提示：

1. 两版 `columns=0`（未表态）→ seed 路径走 `_infer_groups_from_headers` 前缀推断，
   国企 `本期增加`/`本期减少` 会被反猜出凭空「本期」父表头；金额列也无 `format`。
2. 两版无 `guidance` → 附注 TAB 无编制提示。
3. **🔴 上市 headers 第 5 列是 `……` 占位列头**，而底稿默认分类
   （`H8_LISTED_DEFAULT_CATEGORIES`）第 4 类是 **`其他`**，同步载荷
   （`buildH8ListedColumns` 用 `key: c.label`）推的也是 `其他`
   → seed 路径会渲染出一个**永远收不到数据**的 `……` 列（与 H1「`……` 占位列头
   必须展开成实际类别」同款）。本脚本把它展开为 `其他`。

🔴 **`……` 的两种语义必须分开**（本脚本最易踩错处）：
- `……` 作**列头** → 收不到数据，必须展开为实际类别（本脚本处理）；
- `……` 作**行** → 在 H8 底稿模型里是**真实可扩行**（`cost_inc_ellipsis` /
  `dep_inc_ellipsis` 等键参与各块 `sumOf` 小计），与「可无限量添加行」那类纯占位
  说明**不同**，**必须保留** —— 故本脚本 `rows=None` 不动行集，删掉会破坏
  载荷↔模板的行对齐。

国企 `text_sections=[]` 是**正确状态**（源 xlsx 国企 sheet 只有表格无说明段），不补。

Usage::

    python backend/scripts/fix/fix_note_h8_right_of_use_structure.py --dry-run
    python backend/scripts/fix/fix_note_h8_right_of_use_structure.py
    python backend/scripts/fix/fix_note_h8_right_of_use_structure.py --check

spec: .kiro/specs/h8-right-of-use-disclosure-alignment/ (Task 2)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _note_structure_kit import (  # noqa: E402
    AMOUNT,
    build_cli,
    flat_columns,
    rule,
    run_section,
)

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"
LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、25"
SOE_SECTION = "八、26"
ALIGNED_BY = "h8-right-of-use-disclosure-alignment"

T_MAIN = "使用权资产"

# 上市资产类别列 = 底稿默认分类 H8_LISTED_DEFAULT_CATEGORIES（第 4 类 `其他` 即原 `……`）
_LISTED_CATEGORIES = ("房屋及建筑物", "机器设备", "运输设备", "其他")

_LISTED_COLUMNS = flat_columns(
    [("label", "项目", None)]
    + [(c, c, AMOUNT) for c in _LISTED_CATEGORIES]
    + [("合计", "合计", AMOUNT)]
)

_SOE_COLUMNS = flat_columns([
    ("label", "项目", None),
    ("begin", "期初余额", AMOUNT),
    ("increase", "本期增加", AMOUNT),
    ("decrease", "本期减少", AMOUNT),
    ("end", "期末余额", AMOUNT),
])

_G_LISTED = (
    "使用权资产变动表（源模板 R6–R45）：列 = 资产类别（房屋及建筑物 / 机器设备 / 运输设备 / "
    "其他），行 = 四层结构 —— 一、账面原值 / 二、累计折旧 / 三、减值准备 / 四、账面价值。"
    "各层「本期增加金额」「本期减少金额」下的 `……` 行为可扩明细行，"
    "按被审计单位实际增减事项填列（该行参与本层小计）。"
    "勾稽：各层 期末余额 = 期初余额 + 本期增加金额 − 本期减少金额；"
    "四、账面价值 1.期末账面价值 = 一、账面原值4.期末余额 − 二、累计折旧4.期末余额"
    " − 三、减值准备4.期末余额，2.期初账面价值 同口径；合计列 = 各资产类别之和。"
    "本公司确认与短期租赁和低价值资产租赁相关的租赁费用见对应损益附注。"
    "【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去"
    "处置费用后的净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。"
    "可收回金额按预计未来现金流量的现值确定的，应披露预测期的年限、预测期及稳定期的关键参数"
    "及其确定依据。（15号文第十九条（十九））注意：本年执行减值测试的，即使未计提减值，"
    "也要参照上述要求披露；估计可收回金额时通常不应使用重置成本法。】"
    "数据来源：审定表 H8-1 / 明细表 H8-2 / 折旧测算表 H8-8 / 减值测算表 H8-10。"
)

_G_SOE = (
    "使用权资产变动表（源模板 R6–R31）：五层结构 —— 一、账面原值合计 / 二、累计折旧合计 / "
    "三、使用权资产账面净值合计 / 四、减值准备合计 / 五、使用权资产账面价值合计，"
    "各层下以「其中：」列示 土地 / 房屋、建筑物 / 机器、运输、办公设备 / 其他。"
    "勾稽：一、二、四层 期末余额 = 期初余额 + 本期增加 − 本期减少；"
    "账面净值 = 账面原值 − 累计折旧；账面价值 = 账面净值 − 减值准备；"
    "各层合计行 = 该层「其中：」四类别之和。"
    "源模板列示约定：「三、使用权资产账面净值合计」与「五、使用权资产账面价值合计」两层为"
    "推导层，其「本期增加」「本期减少」列填「——」（不作变动分析）。"
    "数据来源：审定表 H8-1 / 明细表 H8-2 / 折旧测算表 H8-8 / 减值测算表 H8-10。"
)


def _listed_plan() -> list[dict[str, Any]]:
    # rows=None：行集已与源模板一致，且上市 `……` 行是真实可扩行，必须保留
    return [rule(T_MAIN, _LISTED_COLUMNS, None, _G_LISTED)]


def _soe_plan() -> list[dict[str, Any]]:
    return [rule(T_MAIN, _SOE_COLUMNS, None, _G_SOE)]


EXPECTED = {"listed": [T_MAIN], "soe": [T_MAIN]}
_TARGETS = {
    "listed": (LISTED_PATH, LISTED_SECTION, _listed_plan),
    "soe": (SOE_PATH, SOE_SECTION, _soe_plan),
}
_LABELS = {
    "listed": "note_template_listed.json §五、25 使用权资产（上市）",
    "soe": "note_template_soe.json §八、26 使用权资产（国企）",
}


def _runner(key: str, dry_run: bool, check: bool):
    path, section_number, plan_fn = _TARGETS[key]
    return run_section(
        path,
        section_number,
        plan_fn(),
        EXPECTED[key],
        aligned_by=ALIGNED_BY,
        dry_run=dry_run,
        check=check,
    )


main = build_cli("附注使用权资产章节补 columns/guidance（幂等）", _runner, _LABELS)

if __name__ == "__main__":
    raise SystemExit(main())
