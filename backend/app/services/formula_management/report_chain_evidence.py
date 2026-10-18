"""报表链「生产实证」口径澄清（Task 4.3 / 需求 15.1）。

本模块把报表链的证据量级口径固化为**单一真源**，供测试与诊断复用，避免
在各处用「项目克隆口径」夸大为「独立证据」。

口径定义
========

`financial_report` 存的是**各项目各年各报表类型的已生成报表数据行**，其
`formula_used` 列记录该行的取数公式。多个项目往往套用**同一套报表模板**
（`report_config` 为全局模板表，无 `project_id`，按 `applicable_standard`
四标准区分），因此同一条模板公式会在每个项目各物化出一行。

- **克隆口径（clone / 物化行数）**：`financial_report` 里 `formula_used`
  非空且未软删的**总行数**。这是「同一模板 × N 项目」的物化副本数，
  **不是独立证据数**——撰写期快照 ≈ 492（= 6 项目 × 82）。
- **distinct 口径（模板/标准证据数）**：对 `(row_code, formula_used)` 去重
  后的**对数**。这才是报表链的「生产实证」量级——撰写期快照 ≈ 82。

关键关系：若 N 个项目各套用同一套模板且跨项目公式无冲突，则
``clone_count ≈ distinct_pairs × distinct_project_count``。把 clone_count
当证据数即是「按项目数夸大」。

`formula_push` 的定位
=====================

`formula_push`（`formula_push_run/state`、E1/审定表/披露表的物化）是把
**权威定义**（report=`report_config`、附注=`disclosure_notes` 公式键、
底稿=`wp_formula`）执行后**自动写入目标载体的物化层**，它**不是权威定义源**：
`financial_report` 的行是物化产物，权威定义仍在 `report_config`。因此统计
「报表链证据量级」必须按 `report_config` 的 distinct 模板/标准口径，而非按
`financial_report` 的克隆行数。

本任务只澄清口径 + 固化测试断言，**不改模板范式**。

关联：design §5 步骤 4「report=report_config」/「formula_push 为自动物化层」、
§3 数据流表「报表链」、深化 12.3；requirements 需求 15.1。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# formula_push 的权威定位（单一真源文案，供文档/诊断引用）。
FORMULA_PUSH_ROLE = "automatic_materialization_layer"
FORMULA_PUSH_IS_AUTHORITATIVE_SOURCE = False
REPORT_AUTHORITATIVE_SOURCE = "report_config"


@dataclass(frozen=True)
class ReportChainEvidence:
    """报表链证据量级的两套口径现算结果。

    - ``clone_count``：物化行数（含跨项目克隆），**禁当独立证据数**。
    - ``distinct_pairs``：去重 ``(row_code, formula_used)`` 的对数，
      即报表链「生产实证」的真实量级。
    - ``project_count``：贡献了含公式行的 distinct 项目数。
    - ``cross_project_conflict``：同一 ``(report_type, row_code)`` 在不同
      项目取了**不同** ``formula_used`` 的组数（0 = 纯克隆，无独立变体）。
    """

    clone_count: int
    distinct_pairs: int
    project_count: int
    cross_project_conflict: int

    @property
    def inflation_ratio(self) -> float:
        """克隆口径相对 distinct 口径的夸大倍数（≈ project_count 即为纯克隆）。"""
        if self.distinct_pairs == 0:
            return 0.0
        return self.clone_count / self.distinct_pairs


def classify_report_chain_evidence(
    rows: Iterable[Sequence],
) -> ReportChainEvidence:
    """从 ``financial_report`` 含公式行现算两套口径。

    ``rows`` 中每行是 ``(project_id, report_type, row_code, formula_used)``
    四元组（仅传入 ``formula_used`` 非空且未软删的行）。

    **禁写死** 82/492/6 任何量级——全部由传入行现算得出。
    """
    clone_count = 0
    distinct_pairs: set[tuple] = set()
    projects: set = set()
    # (report_type, row_code) -> 该键下出现过的 distinct formula_used 集合
    by_logical_row: dict[tuple, set] = {}

    for row in rows:
        project_id, report_type, row_code, formula_used = row
        if formula_used is None or str(formula_used).strip() == "":
            continue
        clone_count += 1
        distinct_pairs.add((row_code, formula_used))
        projects.add(project_id)
        by_logical_row.setdefault((report_type, row_code), set()).add(formula_used)

    cross_project_conflict = sum(
        1 for formulas in by_logical_row.values() if len(formulas) > 1
    )

    return ReportChainEvidence(
        clone_count=clone_count,
        distinct_pairs=len(distinct_pairs),
        project_count=len(projects),
        cross_project_conflict=cross_project_conflict,
    )
