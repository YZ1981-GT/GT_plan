# 关注点 / 已知脆弱处（M 循环）

## 1. 🔴 两组同码

| 码 | 用它的科目 | 说明 |
|---|---|---|
| 4002 | M3 库存股（备抵借方）+ M4 资本公积（贷方）| 两者方向相反且都用 4002 → 取数/回写会撞 |
| 4104 | M6 未分配利润 + M8 一般风险准备（金融专属）| 两底稿都回写 4104 会互相覆盖 |

**未核实**是否刻意（4002 下确有库存股与资本公积两个明细、4104 下确有一般风险准备明细），
但审定合计关系必须显式核对，不能各自独立全额回写同一 TB 行。

## 2. 🔴 M3 库存股方向做反

库存股是权益备抵借方，期末 = 期初 + 借 − 贷（与其余权益类贷方相反）。
写"期末 = 期初 + 贷 − 借"的通用逻辑对 M3 是错的。

## 3. 科目名曾大批纠偏（以 ACCOUNT_CODE 为准）

M 循环科目名旧映射曾不符（M5 盈余公积 4101 / M6 未分配利润 4104 枢纽 / M7 专项储备 4201 /
M8 一般风险准备 4104 金融专属 / M9 其他综合收益 4103 / M10 其他权益工具 4003 /
M3 库存股 4002 权益备抵借方）→ 已按 composable ACCOUNT_CODE 纠正。**判科目以组件文件名/常量为权威，非任务标题**。

## 4. 明细表第三种数据丢失形态（read-full-data-write-per-row）

组件读 `X-full-data`（M1-M1-2 / M2-M2-2-listed/unlisted / M7-2 / M9-2 / M10-2），
composable 只写 per-row `X-row-{n}-data` → `-full-data` 从不写 → 刷新明细全丢。
修 = `_syncFullData()` 写组件读取的确切键；**注意 conclusion vs remark 字段与读取路径一致**
（M9-2 读 conclusion 字段而非 remark）。M3-2/M4/M5/M6/M8 的 restore 从 per-row `-data` 键 iterate 重构（正确）。

## 5. AI 空桩 + 半死

M2~M10 handleAI 曾全是空桩；M1 core tabs POST 后 `.catch(()=>{})` 丢弃响应（耗 token 无输出）。
已统一接 Runtime Boundary 的 `generateAiText`。

## 6. 🔴 含底稿编码的对象键必须加引号

M6-1 等作为对象 key 时，`{ M6-1: ... }` 会被 babel 当减法（M6 减 1）→ Vite transform 500，
`get_diagnostics` 查不出，唯 Vite transform 暴露。必须 `{ 'M6-1': ... }`。

## 7. 双模式

`useMxEntryDualMode` 统一封装；el-segmented **禁 v-model**（用 `:model-value` + `@change`，
v-model 抢先改值使 switchMode 健康门控短路）；index/procedure 不参与；删各 tab 冗余双模式。

## 8. M6 利润分配顺序易错

提取盈余公积（净利润×10%，累计达注册资本 50% 可停提）、一般风险准备（金融）、股利分配的顺序与基数
（可分配利润 vs 净利润）容易算错；期末未分配 = 期初 + 净利润 − 各项提取分配。

## 9. M9 OCI 处置转损益判断

其他综合收益处置时：FVOCI 债务工具（G6）转损益、FVOCI 权益工具（G8）转留存收益、
设定受益计划重新计量（J2）不转损益 —— 三类去向不同，附注需分项列示。
