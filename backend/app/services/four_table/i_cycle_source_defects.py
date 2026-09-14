"""I 类循环源模板缺陷登记（Requirement 10 / Task 19）。

## 为什么要这份登记

源模板（`backend/wp_templates/I/*.xlsx`，运行时权威）里有若干**笔误与形态异常**。
平台按源模板的**意图**实现、而不是照抄它的笔误 —— 但每一处偏离都必须留证，
否则下个会话看到「代码与源模板不一致」会把它「改回去」（平台已多次发生）。

## 铁律（AC 10.7）

**登记 + 守卫钉死，不得反改源 xlsx**。源 xlsx 是致同下发的运行时权威模板，
改它等于让平台与事务所的模板分叉；且 `wp_template_init_service` 生成底稿时直接复制它。

## 三种处置方式

- ``implement_intent``：按**意图**实现（源里是笔误 / 坏公式），代码与源模板刻意不一致
- ``keep_as_is``：**原样保留**（源里是有意设计或无害的形态差异），代码顺着它
- ``skip``：该 sheet / 区域**不进平台**（过时参考资料等），在 `wp_code_overrides.json` 标 skip

## source_ref 格式

``"<xlsx 文件名>!<sheet 名>!<单元格或区域>"``；守卫用 openpyxl 直读做 **stale 检测** ——
源模板一改动（缺陷被上游修掉、或行列漂移）即打红，提醒重新核对而不是继续按旧结论走。

spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/
      Requirements 10.1~10.7 / Task 19
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 源模板文件名（与 `backend/wp_templates/I/` 下逐字一致）
SRC_FILES: dict[str, str] = {
    "I1": "I1 无形资产、累计摊销及减值准备.xlsx",
    "I2": "I2 开发支出.xlsx",
    "I3": "I3 商誉.xlsx",
    "I4": "I4 长期待摊费用.xlsx",
    "I5": "I5 其他非流动资产.xlsx",
    "I6": "I6 研发费用.xlsx",
}

Disposition = Literal["implement_intent", "keep_as_is", "skip"]


@dataclass(frozen=True)
class ICycleSourceDefect:
    """一处源模板缺陷的登记。

    Attributes:
        defect_id: 稳定标识（英文，守卫与 Notes 引用它）。
        cycle: 所属循环 I1~I6。
        title: 一句话描述（中文）。
        source_ref: ``("<文件>!<sheet>!<单元格>", ...)``；守卫 openpyxl 直读做 stale 检测。
        evidence: **逐格实测**结论（含计数）。🔴 一律写实测值，不抄 spec 文本
            —— 本登记表落地时就实测出 spec 的两处计数与源模板不符（见各条注释）。
        disposition: 处置方式。
        rationale: 为什么这样处置（供下个会话判断能否改动）。
        expect_token: stale 检测用的期望文本；`source_ref` 指向的单元格必须仍含它。
            为 `None` 表示该条按「结构/计数」而非「文本」校验（守卫另写专条）。
    """

    defect_id: str
    cycle: str
    title: str
    source_ref: tuple[str, ...]
    evidence: str
    disposition: Disposition
    rationale: str
    expect_token: str | None = None


#: 🔴 唯一真源。新增缺陷只改这里；守卫会要求每条的 `source_ref` 仍能在源模板命中。
I_CYCLE_SOURCE_DEFECTS: tuple[ICycleSourceDefect, ...] = (
    # ── AC 10.1 ────────────────────────────────────────────────────────────
    ICycleSourceDefect(
        defect_id="i1_adjudication_tab_missing_suffix",
        cycle="I1",
        title="I1 审定表 tab 名为「审定表I1」，缺 `-1` 后缀（其余五个循环都是「审定表IX-1」）",
        source_ref=("I1 无形资产、累计摊销及减值准备.xlsx!审定表I1!A1",),
        evidence=(
            "openpyxl 直读六份源模板的 sheetnames："
            "I1=['审定表I1'] / I2=['审定表I2-1'] / I3=['审定表I3-1'] / "
            "I4=['审定表I4-1'] / I5=['审定表I5-1'] / I6=['审定表I6-1'] ⇒ 仅 I1 缺后缀"
        ),
        disposition="keep_as_is",
        rationale=(
            "sheet 名是底稿定位键（`wp_render_config` 按 sheet 名查 `_WP_CODE_OVERRIDE`、"
            "OnlyOffice 按 tab 名定位），改名会让既有项目的持久化数据失联。"
            "故**定位一律用 tab 名 `审定表I1`**，而**展示用底稿目录的索引号 `I1-1`**。"
            "前端 `I1TabAdjudication.vue` 的标题与 GtIndexChip 都写 `I1-1`，与源模板 tab 名不同"
            "—— 这是本条登记的偏离，不是 bug。"
        ),
    ),
    # ── AC 10.2 ────────────────────────────────────────────────────────────
    ICycleSourceDefect(
        defect_id="i2_listed_ref_error_continuation_table",
        cycle="I2",
        title="I2 上市披露表续表区 `A35:D39` 整片 `=#REF!` 坏公式",
        source_ref=(
            "I2 开发支出.xlsx!附注披露（上市公司）!A35",
            "I2 开发支出.xlsx!附注披露（上市公司）!D39",
        ),
        evidence=(
            "🔴 实测 **20 格**（A~D 列 × 35~39 行），而 spec AC 10.2 与 tasks.md 写的是「15 格」。"
            "以逐格实测为准。上下文：A33='续：' / A34='项目' / A40='合计' / "
            "A41='说明：（披露上述项目的资本化开始时点、资本化的具体依据、截至期末的研发进度等。）' "
            "⇒ 该区确是「资本化情况续表」的项目行区。"
        ),
        disposition="implement_intent",
        rationale=(
            "`=#REF!` 是模板制作时删除了被引用 sheet 留下的断链，**不含任何可读语义**，"
            "照抄会让附注出现 5 行 `#REF!`。按意图实现 = 该续表的项目行做成**可扩行**"
            "（由审计师按实际研发项目填），列结构取 A34/A40 的「项目 / 合计」骨架。"
            "对应实现：`i2DisclosureModel` 的可扩行 + `i2DisclosureSyncPayload` 的续表列。"
        ),
        expect_token="#REF!",
    ),
    # ── AC 10.3 ────────────────────────────────────────────────────────────
    ICycleSourceDefect(
        defect_id="i1_listed_disposal_typo_in_formula",
        cycle="I1",
        title="I1 上市披露表「（1）处置」行的 `D20:L20` 公式把判定值写成「购置」",
        source_ref=(
            "I1 无形资产、累计摊销及减值准备.xlsx!附注披露信息（上市公司）!D20",
            "I1 无形资产、累计摊销及减值准备.xlsx!附注披露信息（上市公司）!L20",
        ),
        evidence=(
            "逐格实测 row20（A20='（1）处置'，隶属 A19='3.本期减少金额'）："
            "**B20/C20 正确**写 `IF('明细表I1-2'!$G$20=\"处置\",...)`，"
            "**D20~L20 共 9 格误写 \"购置\"**。"
            "对照 row14（A14='（1）购置'，隶属 A13='2.本期增加金额'）的 B14:L14 全用「购置」——"
            "那 11 格是**正确的**。故真笔误 = D20:L20 的 9 格，"
            "形态是从 row14 横向复制粘贴后漏改判定值（前两格改了、后九格没改）。"
        ),
        disposition="implement_intent",
        rationale=(
            "按「处置」实现：本期减少行的取数判据必须是「处置」，否则该行恒取到 0"
            "（明细表 G 列不会同时出现「购置」在减少段）。平台不照抄该公式 ——"
            "取数走后端叶子聚合与 `adjudication_prefill`，不复刻 Excel 的 IF 链。"
        ),
        expect_token="购置",
    ),
    # ── AC 10.4 ────────────────────────────────────────────────────────────
    ICycleSourceDefect(
        defect_id="i6_index_cross_workbook_by_design",
        cycle="I6",
        title="I6 底稿目录第 7~14 项索引号指向 I2 底稿（`I2-4`~`I2-11`）",
        source_ref=(
            "I6 研发费用.xlsx!底稿目录!D10",
            "I6 研发费用.xlsx!底稿目录!E10",
            "I6 研发费用.xlsx!底稿目录!D17",
        ),
        evidence=(
            "实测 I6 底稿目录 row10~row17 的索引号列（D 列）= "
            "I2-4 / I2-5 / I2-6 / I2-7 / I2-8 / I2-9 / I2-10 / I2-11（第 7~14 项），"
            "且 **E10（备注列）有完整提示原文**：「提示：该部分底稿模板在开发支出底稿中，"
            "如果被审计单位既有开发支出又有研发费用可在开发支出中综合完成研发相关的主要底稿，"
            "研发费用交叉索引；如果被审计单位研发活动全部计入研发费用可将该部分底稿"
            "从开发支出底稿模板中移至研发费用中完成。」"
        ),
        disposition="keep_as_is",
        rationale=(
            "🔴 **有意的跨 workbook 交叉索引，不是笔误** —— 源模板自己在 E10 写明了理由。"
            "研发相关的会计政策检查 / 实质性分析 / 资本化时点判断 / 项目构成 / 材料投入 / "
            "人员认定 / 工时 / 委外八张检查表**物理上在 I2 workbook 里**，I6 只做交叉索引。"
            "下个会话若看到 I6 目录里出现 `I2-*` 索引号，**不得当笔误改成 `I6-*`** ——"
            "改了会让 I6 指向不存在的底稿。"
        ),
        expect_token="提示：该部分底稿模板在开发支出底稿中",
    ),
    # ── AC 10.5 ────────────────────────────────────────────────────────────
    ICycleSourceDefect(
        defect_id="i5_index_sequence_number_missing",
        cycle="I5",
        title="I5 底稿目录 `B4` 序号缺失（7 行内容只有 6 个序号）",
        source_ref=(
            "I5 其他非流动资产.xlsx!底稿目录!B4",
            "I5 其他非流动资产.xlsx!底稿目录!C4",
        ),
        evidence=(
            "实测 I5 底稿目录：C 列（内容）row4~row10 共 **7 行**"
            "（实质性程序 / 审定表 / 附注披露表（上市公司）/ 附注披露表（国有企业）/ "
            "明细表 / 调整分录汇总 / 检查表），"
            "B 列（序号）只有 row5~row10 的 **1~6 共 6 个** ⇒ "
            "`B4` 空（其内容行 C4='其他非流动资产实质性程序'、索引号 D4='I5A'）。"
        ),
        disposition="keep_as_is",
        rationale=(
            "序号是**源模板的展示编号**，不参与任何取数或定位（定位靠 D 列索引号 `I5A`）。"
            "平台的底稿目录按行序自然渲染，不读该列 ⇒ 无需修正，也不改源。"
            "登记它只为防下个会话看到「7 行内容 6 个序号」以为是解析漏了一行。"
        ),
    ),
    # ── AC 10.6 ────────────────────────────────────────────────────────────
    ICycleSourceDefect(
        defect_id="i3_hidden_sheet_stale_market_return",
        cycle="I3",
        title="I3 含 hidden sheet「市场平均收益率2017」（2017 年的过时参考数据）",
        source_ref=("I3 商誉.xlsx!市场平均收益率2017!A1",),
        evidence=(
            "openpyxl 实测 I3 的 hidden sheet = "
            "[('市场平均收益率2017', 'hidden'), ('GT_Custom', 'hidden')]；"
            "其余五个循环只有 `GT_Custom` 一个 hidden。"
            "🔴 库侧实测该 sheet **已被分类进 `workpaper_sheet_classification`**"
            "（`sheet_name='市场平均收益率2017'` / `wp_code='I3'` / `class_code='H-辅助说明'`）"
            "⇒ 分类链路**不读 `sheet_state`**（`GT_Custom` 是 `wp_classification_service` 里的"
            "硬编码特例），hidden 不会自动过滤，只认 `wp_code_overrides.json` 里的 `skip`。"
        ),
        disposition="skip",
        rationale=(
            "2017 年的市场平均收益率是**过时参考资料**，不该作为可编辑底稿 sheet 暴露给审计人员"
            "（会被误当本期折现率依据用）。处置 = 在 `backend/app/data/wp_code_overrides.json` "
            "登记 `\"市场平均收益率2017\": \"skip\"`，走 `wp_render_config` 既有的 "
            "`_WP_CODE_OVERRIDE.get(cls.sheet_name) == \"skip\"` 判据排除。"
            "商誉减值的折现率改由 I3-7 可收回金额测试按当期参数录入。"
        ),
    ),
)

#: `disposition` → 中文说明（UI / 报告用）
DISPOSITION_LABELS: dict[str, str] = {
    "implement_intent": "按意图实现（代码与源模板刻意不一致）",
    "keep_as_is": "原样保留（源模板是有意设计或无害差异）",
    "skip": "不进平台（在 wp_code_overrides.json 标 skip）",
}


def defects_of(cycle: str) -> tuple[ICycleSourceDefect, ...]:
    """某循环的缺陷登记；未知循环返空 tuple。"""
    key = str(cycle or "").upper()
    return tuple(d for d in I_CYCLE_SOURCE_DEFECTS if d.cycle == key)


def defect_by_id(defect_id: str) -> ICycleSourceDefect | None:
    """按 `defect_id` 取登记；未登记返 `None`。"""
    return next((d for d in I_CYCLE_SOURCE_DEFECTS if d.defect_id == defect_id), None)


def defects_payload() -> list[dict]:
    """供 render / 溯源面板下发的只读投影（不外泄 stale 检测细节）。"""
    return [
        {
            "defect_id": d.defect_id,
            "cycle": d.cycle,
            "title": d.title,
            "disposition": d.disposition,
            "disposition_label": DISPOSITION_LABELS[d.disposition],
            "source_ref": list(d.source_ref),
        }
        for d in I_CYCLE_SOURCE_DEFECTS
    ]


__all__ = [
    "DISPOSITION_LABELS",
    "Disposition",
    "ICycleSourceDefect",
    "I_CYCLE_SOURCE_DEFECTS",
    "SRC_FILES",
    "defect_by_id",
    "defects_of",
    "defects_payload",
]
