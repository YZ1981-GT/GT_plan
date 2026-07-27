# 上下文：G 循环特有机制

渲染链路 / 持久化 / 跨底稿事件 / 共享能力见 `.omm/d-cycle-sales/context.md` 与 `shared-runtime/`。
本文只写 G 特有部分。

## 1. 每科目一套 `g{n}Constants.ts` / `g{n}AdjudicationItems.ts`

G 循环把科目常量收敛为独立文件（`g2Constants` `g3Constants` `g5Constants` `g8Constants` `g9Constants`
`g10Constants` `g11Constants` `g12Constants` `g13Constants` `g14Constants`，
以及 `g1AdjudicationItems` `g2AdjudicationItems` `g4AdjudicationItems` `g5AdjudicationItems` `g6AdjudicationItems`）：
- `G{n}_ACCOUNT_CODE`：TB 取数与回写目标
- `G{n}_CHANGE_RATE_THRESHOLD`：变动率超阈值必填原因（多数 0.3，G11/G12 为 0.2）
- 审定表行清单（`*_ADJUDICATION_ITEMS` / `*_DISCLOSURE_*_ROWS`）

改科目归属或审定行只改这一处，四散的 Tab 都消费它。

## 2. TB 解析带名称回退与历史码兼容

G9 有 `g9TbResolve.ts`（`resolveG9TbRow` / `g9TbRowBalance` / `g9TbResolvedCode`）：
按 `G9_ACCOUNT_CODE='1519'` 找不到时按 **科目名称 `其他非流动金融资产` 回退**，并兼容历史项目的 `1510` / `1504`。
G8 用 `account_prefix` + `startsWith` 前缀匹配 TB 行。
→ 金融资产科目码在不同客户账套差异大，**取数不能只精确匹配一个码**。

## 3. 每科目都有 `handbooks/` + `G{n}PreparationHandbookDialog.vue`

G 循环是「编制手册 / 使用手册」范式覆盖最全的循环（G1~G14 几乎每包都有）：
`handbooks/{preparation,usage}.md?raw` + marked + DOMPurify 双 tab 弹窗。
另有 `G{n}AuditTextCards.vue`（审计说明/结论卡片统一渲染）、`G{n}SheetStatusBar.vue`（sheet 级完成状态条）、
`G{n}ImportExportDropdown.vue`（统一导入导出 ▾）—— 这三件套是 G 循环的组件级复用范式。

## 4. 目录页与结论看板

G4/G6/G7/G8~G14 有 `G{n}TabDirectory.vue`（进度条 + 索引表 + 编制提示）；
共享增强块 `GCycleBIndexExtras.vue` 提供编制/使用手册按钮、底稿架构泳道、本循环底稿 grid、
以及 E1 标准的「跨表结论口径看板」（可选 `allResponses` prop，不传则不渲染）。
G1/G2/G3/G5 无 `GxTabDirectory`，目录能力全部由 `GCycleBIndexExtras` 提供。

## 5. 调整分录的对方科目是关键设计点

G 循环调整分录常有固定对方科目集：
- 公允变动 → `6101 公允价值变动损益`（G1/G9/G10）
- OCI → `4002 其他综合收益`（G6/G8/G9）
- 减值 → `1231 坏账准备`（G5 三阶段）/ `1502` 债权投资减值准备（G4）
- 处置结转 → `4104 利润分配—未分配利润`（G12）
`G9_ADJ_ACCOUNT_OPTIONS` / `G9_RELATED_PREFIXES` 这类白名单还用于**从集中登记反向导入**时过滤本科目相关分录。

## 6. 附注章节：G1/G10 一个底稿覆盖两节

- G1 覆盖 **五、2 交易性金融资产 + 五、3 衍生金融资产**（八、2 / 八、3）
- G10 覆盖 **五、34 交易性金融负债 + 五、35 衍生金融负债**（八、34 / 八、35）
→ 正向跳转靠**精确章节号谓词**区分（单字数字必 `===`，五、3 ≠ 五、30+）；
反向跳转的 map 用**节级 key**（如 `G1` / `G1_DERIVATIVE`）而非 wpCode。

- G2 应收利息 / G3 应收股利 **无独立附注节**，作为行并入 K1 其他应收款（五、8 / 八、9）→ 不做独立跳转入口。
- G13 / G14 上市版章节是**关键词标题**（`三、公允价值变动收益` / `三、信用减值损失`），
  DB 里可能被截断（如 `三、信用减值损失（损…`）→ 定位要走 `resolveSectionInList` 模糊→精确解析。
