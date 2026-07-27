# 上下文：M 循环特有机制

通用机制见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。本文只写 M 特有部分。

## 1. 科目码常量（各 useM{n}FormData.ts 顶部）

M1 `'2232'`（应付股利，负债）、M2 `'4001'`、M3 `'4002'`（库存股，**备抵借方**）、M4 `'4002'`（资本公积，**与 M3 同码**）、
M5 `'4101'`、M6 `'4104'`、M7 `'4201'`、M8 `'4104'`（一般风险准备，**与 M6 同码**，金融专属）、
M9 `'4103'`、M10 `'4003'`。均以**组件文件名/ACCOUNT_CODE 为权威**（M 循环科目名曾大批纠偏）。

## 2. 🔴 M3 库存股方向特殊

库存股是**权益备抵借方**（4002），期末 = 期初 + **借** − **贷**（与其余权益类贷方相反）。
回购增加库存股（借），注销减少（贷），注销冲减差额进 M4 资本公积。

## 3. M6 利润分配的顺序勾稽

利润分配表口径（源模板固定顺序）：
期初未分配利润 + 本年净利润 − 提取法定盈余公积（净利润×10%，累计达注册资本 50% 可不提）−
提取任意盈余公积 − 提取一般风险准备（金融）− 应付普通股股利 − 转作股本的股利 = 期末未分配利润。
M6 是枢纽，其数据流向 M5（盈余公积）/ M8（一般风险准备）/ M1（应付股利）。

## 4. 明细表 read-full-data-write-per-row 键匹配（M 循环踩过）

M 循环 detail 表曾有**第三种 P0 数据丢失形态**：组件 `_restoreRows` 读 `X-full-data`
（M1-M1-2 / M2-M2-2-listed / M2-M2-2-unlisted / M7-2 / M10-2），但 composable 只写 per-row `X-row-{n}-data` →
`-full-data` 从不写 → 刷新明细全丢。修 = composable 加 `_syncFullData()` 写组件读取的确切键
（注意 conclusion vs remark 字段与读取路径一致；M9-2 读 conclusion 字段而非 remark）。

## 5. AI 全线用 Runtime Boundary 的 generateAiText

M2~M10 的 `handleAI` 曾几乎全是空桩（`function handleAI(_section){}`）；M1 core tabs 是"半死"
（POST `/ai/generate-text` 但 `.catch(()=>{})` 丢弃响应不回填）。已统一接 `inject<GenerateWorkpaperAiText>('generateAiText')`
（context 全转 `Record<string,string>` 避 422 + 回填 textarea + 调保存函数）。
**含底稿编码的对象键（如 M6-1）必须加引号**否则 babel 当减法 → Vite transform 500（get_diagnostics 查不出）。

## 6. 双模式统一 useMxEntryDualMode

每循环 `composables/useMxEntryDualMode.ts`（sheet code → 源 xlsx tab 名映射 + useWorkpaperEntryDualMode 健康门控）。
主入口 el-segmented 用 `:model-value` + `@change="dualMode.switchMode"`（**禁 v-model**）；
index/procedure sheet 不参与双模式；删除了各 tab 内自带的 useMxDualMode（entry 级统一覆盖，避免双重切换栏）。

## 7. 附注 substantive:adjudicated 联动

M2/M4/M5/M6/M8/M9 附注有 `onAdjudicatedRefresh` + onUnmounted off；M7 用 useNoteAutoFill SDK；
M3 手动带入按钮。审定表 TB 回写真实。

## 8. 权益变动的最终去向

M1~M10 全部权益变动汇入**所有者权益变动表（SCE）**（合并/单体报表）。
M6 未分配利润、M9 其他综合收益、M5 盈余公积是 SCE 的主要变动行。
