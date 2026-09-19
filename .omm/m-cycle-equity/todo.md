# 待办（M 循环）

## 需核实 / 需决策

- **两组同码回写口径**（M3/M4=4002、M6/M8=4104）：确认单一回写方，避免互相覆盖
- **M3 库存股 4002 与 M4 资本公积 4002 的取数隔离**（同码不同方向，如何区分明细）
- **M8 一般风险准备 4104 与 M6 未分配利润 4104**：金融企业专属，普通企业不适用（应可裁剪）

## 已知未做

- **M3-2 persistence 双路径修复**（`_syncFullData` 双写 + 降级读取）为历史修复，其余明细表 full-data 键覆盖度待持续核
- **M 循环附注结构化推送**：部分已有 buildM{n}SyncPayload + columns，
  生产环境 `sub_table_data` 为 0（全平台"披露同步未跑起来"问题）
- **M6 利润分配与损益结转的自动勾稽**（本年利润 4103本年利润 → M6）是否全自动待核
- M3 空洞 el-card 打磨（状态面板无 meta 时的紧凑单行 bar）—— 属 UI 打磨范式

## 已完成（本平台历史）

- M1~M10 全部完成（含 M6 未分配利润枢纽）
- 明细表 P0 数据丢失修复（read-full-data-write-per-row：M1/M2/M7/M9/M10 + M3 前轮）
- AI 全线接线（Runtime Boundary generateAiText）+ 双模式 P0+P1（useMxEntryDualMode 统一 + 删 tab 级冗余）
- 科目名按 ACCOUNT_CODE 纠偏（M5/M6/M7/M8/M9/M10/M3）
- M3 库存股增强（M3-5 注销冲减差额 AJE 建议 / M3-1 审计结论 / M3-2 勾稽 / persistence 双路径 / M3 目录进度）
