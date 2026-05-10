"""F14 / Sprint 4.2 — pipeline 关键阶段 checkpoint 常量。

对齐 design §D6.2 中 ``ImportJobRunner.resume_from_checkpoint`` 的路由表：

| ImportJob.current_phase            | 恢复动作                                            |
|------------------------------------|-----------------------------------------------------|
| parse_write_streaming_done         | 从 activation_gate 开始重跑                         |
| activation_gate_done               | 从 activate_dataset 开始重跑（metadata 切换 <1s）   |
| activate_dataset_done              | 从 rebuild_aux_summary 开始重跑（幂等）             |
| rebuild_aux_summary_done           | 视为已完成，标 completed                            |
| 其他 / 中途（含 writing 阶段）     | 不在此表中的 phase 走 cleanup staged → 全量重跑     |

设计意图：
- pipeline 的 ``_mark(phase)`` 在每个关键 phase **结束后**写入 current_phase；
  resume 时查到的 phase 表示"已完成这个阶段"。
- 恢复表只覆盖三个幂等可恢复点：activation_gate / activate_dataset /
  rebuild_aux_summary；parse/write 中途崩溃必须清空 staged 数据后重跑，
  否则会出现半写入数据污染后续 activate。
- activate_dataset 本身是 metadata UPDATE 单行事务，幂等；重跑一次若发现
  ledger_datasets.status 已是 active 则走 no-op。
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Pipeline 生命周期 phases（与 pipeline.py _mark() 传入字符串对齐）
# ---------------------------------------------------------------------------

PHASE_START = "start"
PHASE_DETECT_IDENTIFY_DONE = "detect_identify_done"
PHASE_CREATE_STAGED_DONE = "create_staged_done"
PHASE_PARSE_WRITE_STREAMING_DONE = "parse_write_streaming_done"
PHASE_ACTIVATION_GATE_DONE = "activation_gate_done"
PHASE_ACTIVATE_DATASET_DONE = "activate_dataset_done"
PHASE_REBUILD_AUX_SUMMARY_DONE = "rebuild_aux_summary_done"


ALL_PHASES: tuple[str, ...] = (
    PHASE_START,
    PHASE_DETECT_IDENTIFY_DONE,
    PHASE_CREATE_STAGED_DONE,
    PHASE_PARSE_WRITE_STREAMING_DONE,
    PHASE_ACTIVATION_GATE_DONE,
    PHASE_ACTIVATE_DATASET_DONE,
    PHASE_REBUILD_AUX_SUMMARY_DONE,
)


# ---------------------------------------------------------------------------
# Resume 路由表：key=崩溃前最后完成的 phase，value=(继续动作 label, 是否可恢复)
# ---------------------------------------------------------------------------
# 动作 label 含义见模块 docstring 表格。
RESUME_FROM_PHASE: dict[str, tuple[str, bool]] = {
    PHASE_PARSE_WRITE_STREAMING_DONE: ("activation_gate", True),
    PHASE_ACTIVATION_GATE_DONE: ("activate_dataset", True),
    PHASE_ACTIVATE_DATASET_DONE: ("rebuild_aux_summary", True),
    PHASE_REBUILD_AUX_SUMMARY_DONE: ("complete", True),
}


__all__ = [
    "PHASE_START",
    "PHASE_DETECT_IDENTIFY_DONE",
    "PHASE_CREATE_STAGED_DONE",
    "PHASE_PARSE_WRITE_STREAMING_DONE",
    "PHASE_ACTIVATION_GATE_DONE",
    "PHASE_ACTIVATE_DATASET_DONE",
    "PHASE_REBUILD_AUX_SUMMARY_DONE",
    "ALL_PHASES",
    "RESUME_FROM_PHASE",
]
