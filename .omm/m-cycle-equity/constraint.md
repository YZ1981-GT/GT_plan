# 约束（M 循环）

平台通用铁律见 `.omm/d-cycle-sales/constraint.md`。以下为 M 循环附加约束。

1. **M3 库存股方向 = 期初 + 借 − 贷**（权益备抵借方）；其余权益类贷方 = 期初 + 贷 − 借。不得对 M3 套贷方公式。
2. **同码科目（M3/M4=4002、M6/M8=4104）不得各自独立全额回写同一 TB 行**；审定合计关系须显式核对。
3. **科目名以 composable 的 ACCOUNT_CODE / 组件文件名为权威**，非任务标题。
4. **明细表 restore 读 `X-full-data` 时 composable 必须 `_syncFullData()` 写该确切键**
   （字段 conclusion vs remark 与读取路径一致，M9-2 读 conclusion）。
5. **AI 用 Runtime Boundary `generateAiText`**（inject 'generateAiText'），context 全转 `Record<string,string>`；
   禁空桩 / 禁 `.catch(()=>{})` 丢弃响应。
6. **含底稿编码的对象 key 必须加引号**（`{ 'M6-1': ... }`），防 babel 当减法 → Vite transform 500。
7. **双模式用 `useMxEntryDualMode` + `:model-value` + `@change`**（禁 v-model）；index/procedure 不参与；不留 tab 级冗余双模式。
8. **M6 利润分配按源模板顺序**（净利润 → 提盈余公积 → 提一般风险准备 → 分股利 → 期末未分配），
   盈余公积 M5 / 一般风险准备 M8 / 应付股利 M1 是其下游。
9. **M9 OCI 处置转损益按类型判断**（FVOCI 债务转损益 / FVOCI 权益转留存 / 设定受益不转），附注分项列示。
10. **权益变动最终汇入所有者权益变动表（SCE）**，M1~M10 审定回写各科目 + `substantive:adjudicated` 联动附注。
