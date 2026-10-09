# -*- coding: utf-8 -*-
"""权威模板目录的两张**具名登记表**（`test_template_override_resolution` 的伴生数据模块）。

spec: d1-sync-row-table-engine-and-d1-coverage · X2（2026-09-28 升级为账本形态 · X5-j）

═══ 为什么是具名清单而不是标量计数 ═══

这两张表替代的是原先的 `一致==451 && 漂移==23` 两个标量。问题不是标量「不够严」，
而是**激励反了**：任何 lane 改一份权威模板都会让判据翻红，而修红最省事的做法就是把
两个数字改成现算值 —— 那会把**别人**的漂移一起静默吸收，下一个人再也看不出哪些是
新增的。本仓库反复在批的正是这种「重设基线吞漂移」。

具名之后两个方向都可归因：
* 新出现的漂移会被**点名**（不是只让计数 +1）；
* 清单里的条目不再漂移 = **失效条目**，由反向断言点名要求移除。

═══ 2026-09-28 升级：从 frozenset 到账本（X5-j）═══

原先只有一个 frozenset + 注释里写死的 `索引 KB / 磁盘 KB`。两个问题：

1. 注释里的数字**会过期** —— 模板再改一次，注释还停在旧值，而判据只看「在不在集合里」，
   过期完全不可见；
2. 没有归属字段 ⇒ 30 条欠账是一锅粥，没法按 lane 推动清理，实际上就躺着。

⇒ 改成 `INDEX_DRIFT_LEDGER`（dict，带归属循环 + 索引/磁盘声明值 + 性质），
  `INDEX_SIZE_DRIFTED_FILES` 由它**派生**（保持既有判据零改动，且两者不可能漂移）。
  配套查询/对账工具：`backend/scripts/check/check_template_index_drift_ledger.py`
  —— 按循环分组输出，并把账本里的声明值与**现算值**对账，过期即报。

🔴 归属按模板所在的**循环目录**记（A/B/D/G/H/L/M），不按 spec 名。理由：同一循环常有
多份 spec（A 轮就有 3 份），而模板漂移是循环级的历史遗留，按循环追责才落得下去。
这是**推定**归属 —— 未逐条向对应 lane 确认过，字段名 `cycle` 而不是 `owner` 就是为了
不假装它是确认过的责任人。

═══ 为什么单独一个模块 ═══

宿主判据文件在 HEAD 就已 889 行（超 800 上限且不在 whitelist）。把这两张纯数据表
连归因注释抽出来，宿主回落，且「登记表」本身有了独立落点 —— 后续哪条 lane 提交了
自己的模板改动，只改这里一行即可。
"""
from __future__ import annotations

from typing import NamedTuple

__all__ = [
    "INDEX_DRIFT_LEDGER",
    "INDEX_SIZE_DRIFTED_FILES",
    "KNOWN_DIRTY_AUTHORITATIVE_PATHS",
    "DriftEntry",
]


class DriftEntry(NamedTuple):
    """一条模板索引欠账。

    Attributes:
        cycle: 归属审计循环（推定，见模块 docstring）。
        index_kb: `_index.json` 声明的 size_kb（**记账时的值**，由对账工具校验是否过期）。
        disk_kb: 记账时磁盘实际 KB。
        nature: `committed`（已提交但索引从未重算）/ `worktree`（别 lane 未提交的临时态）。
    """

    cycle: str
    index_kb: float
    disk_kb: float
    nature: str


#: `_index.json` 声明的 `size_kb` 与磁盘实际不符的模板（逐份具名 + 归属 + 数值）。
#:
#: 归因（2026-09-28 现算，逐份查 `git diff HEAD`）：**29 份是「已提交但索引从未重算」**
#: 的历史遗留（HEAD 字节 == 磁盘字节 ≠ 索引声明），**1 份是别的 lane 的工作树临时态**
#: （M10，nature=worktree）。
#:
#: 🔴 `D/D1 应收票据.xlsx` **刻意不在账本里**：它是 spec
#: `d1-sync-row-table-engine-and-d1-coverage` 改的（贴现息列数字格式修复），
#: 其 `_index.json` 条目已同步成改版后的 117.3KB —— **只改自己那一条，没有重算整份索引**。
#: 这就是本账本期望的处置范式。
INDEX_DRIFT_LEDGER: dict[str, DriftEntry] = {
    # ── A 循环（报表/调整、审计完成阶段）4 份 ────────────────────────────
    "A\\A17  重大事项概要程序表.xlsx": DriftEntry("A", 78.7, 66.3, "committed"),
    "A\\A17-1 重大事项概要汇总.docx": DriftEntry("A", 179.2, 68.9, "committed"),
    "A\\A17-5-1 审计工作完成核对表（适用于财报审计）.xlsx": DriftEntry(
        "A", 21.4, 15.9, "committed"
    ),
    "A\\A17-5-5  审计工作完成核对表（函证程序）.xlsx": DriftEntry(
        "A", 15.8, 11.2, "committed"
    ),
    # ── B 循环（审计计划/控制了解）10 份 ─────────────────────────────────
    "B\\B60 总体审计策略及具体审计计划.docx": DriftEntry("B", 237.4, 191.8, "committed"),
    "B\\B60-1 审计项目工时预算与控制表.xlsx": DriftEntry("B", 25.4, 16.2, "committed"),
    "B\\B60-2-1 IT复杂性判断表.docx": DriftEntry("B", 33.7, 28.2, "committed"),
    "B\\B60-2-2 IT审计进场前通知表.docx": DriftEntry("B", 40.9, 34.8, "committed"),
    "B\\B60-2-3 IT审计计划备忘录.docx": DriftEntry("B", 33.9, 28.3, "committed"),
    "B\\B60-3 评估专家工作计划.docx": DriftEntry("B", 46.1, 43.3, "committed"),
    "B\\B60A 对内控审计的特殊考虑.docx": DriftEntry("B", 135.2, 95.1, "committed"),
    "B\\B60B 对IPO申报财务报表审计的特殊考虑.docx": DriftEntry("B", 134.7, 90.4, "committed"),
    "B\\B60C 对国有企业年度财务报表审计的特殊考虑.docx": DriftEntry(
        "B", 129.9, 89.7, "committed"
    ),
    "B\\B60D 向监管机构报送总体审计策略和具体审计计划的函副本.docx": DriftEntry(
        "B", 27.4, 24.8, "committed"
    ),
    # ── D 循环（销售与收款）4 份 ─────────────────────────────────────────
    "D\\D3 预收账款.xlsx": DriftEntry("D", 130.0, 72.7, "committed"),
    "D\\D5 应收款项融资.xlsx": DriftEntry("D", 110.6, 52.5, "committed"),
    "D\\D6 合同资产.xlsx": DriftEntry("D", 411.8, 122.7, "committed"),
    "D\\D7 合同负债.xlsx": DriftEntry("D", 370.7, 86.7, "committed"),
    # ── G 循环（投资）4 份；G7 是唯一磁盘**更大**的一份 ──────────────────
    "G\\G4 债权投资.xlsx": DriftEntry("G", 1022.9, 976.4, "committed"),
    "G\\G5 长期应收款.xlsx": DriftEntry("G", 409.4, 389.6, "committed"),
    "G\\G6 其他债权投资.xlsx": DriftEntry("G", 1011.4, 958.0, "committed"),
    "G\\G7 长期股权投资.xlsx": DriftEntry("G", 244.4, 257.2, "committed"),
    # ── H 循环（固定资产及相关）5 份；H3 最极端（-80%）───────────────────
    "H\\H1 固定资产.xlsx": DriftEntry("H", 244.2, 194.7, "committed"),
    "H\\H10 资产处置损益.xlsx": DriftEntry("H", 58.3, 41.3, "committed"),
    "H\\H2 在建工程.xlsx": DriftEntry("H", 174.7, 158.8, "committed"),
    "H\\H3 投资性房地产.xlsx": DriftEntry("H", 712.3, 142.7, "committed"),
    "H\\H8 使用权资产.xlsx": DriftEntry("H", 491.0, 454.6, "committed"),
    # ── L 循环（筹资/债务）2 份 ──────────────────────────────────────────
    "L\\L5 长期应付款.xlsx": DriftEntry("L", 91.1, 65.9, "committed"),
    "L\\L6 专项应付款.xlsx": DriftEntry("L", 54.2, 36.9, "committed"),
    # ── M 循环（股东权益）1 份 ───────────────────────────────────────────
    # 🔴 唯一一份**工作树临时态**（别的 lane 未提交的模板改动），不是已提交漂移。
    #    那条 lane 提交或回滚之后本条会变成失效条目并被反向断言点名。
    "M\\M10 其他权益工具.xlsx": DriftEntry("M", 136.0, 113.0, "worktree"),
}

#: 由账本**派生** —— 既有判据用集合语义（`drifted_names - INDEX_SIZE_DRIFTED_FILES`），
#: 派生保证两者永不漂移（单源）。
INDEX_SIZE_DRIFTED_FILES = frozenset(INDEX_DRIFT_LEDGER)

#: 权威模板目录里**已知有归因**的未提交改动。空集是目标状态。
#:
#: 🔴 这不是豁免而是记账：每一条都必须写明是哪条 lane 的、为什么还没提交。
#: 反向断言会在它们提交/回滚后点名要求移除本登记。
KNOWN_DIRTY_AUTHORITATIVE_PATHS = frozenset(
    {
        # 别的 lane（M 循环）在工作树里改了这份模板，尚未提交。
        # 它同时是 `INDEX_DRIFT_LEDGER` 里唯一 `nature="worktree"` 的那一条。
        "backend/wp_templates/M/M10 其他权益工具.xlsx",
        #
        # 🔴 2026-09-30 移除 `backend/wp_templates/D/D4收入底稿.xlsx`：
        #    那份未提交的删除**已经提交**（D4 重复本清理 —— 它与
        #    `D/D4 收入底稿.xlsx` 是同一底稿的重复入库，352,950 B 未净化那份删掉，
        #    留 199,176 B 已净化那份）。登记表的反向断言 `stale` 本就会点名要求
        #    移除失效条目，这里按它的要求删。
    }
)
