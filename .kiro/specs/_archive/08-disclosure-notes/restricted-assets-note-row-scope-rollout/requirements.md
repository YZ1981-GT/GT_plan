# Requirements Document

## Introduction

「所有权或使用权受到限制的资产」是全库 **29 张多段共享表**里受益面最大的一张
（listed `五、32` 主表 + 「续：」表 / soe `八、93`，段数 6~7，owner 横跨
**E1 / D1 / D2 / D5 / F2 / H1 / H2 / I1** 八个循环）。

它是平台级 `disclosure-note-row-level-merge` 落地后的**第二批消费者**（首批 = E1 外币章节）。
现状：**零 pusher** —— 各循环底稿早已收集自己的受限资产信息（E1 ②表受限明细 /
D1 已质押票据 / D2 质押应收 / F2 抵押存货 / H1 抵押固定资产 / H2 受限在建工程 /
I1 受限无形资产），但没有任何 map 推向该章节，审计师只能在附注模块手工重录一遍。

同时逐格核模板后查出**三处结构缺陷**（详见 Requirement 1），其中两处是 `report_row_code`
错码/缺码，会直接让 owner 段定位错行。

本 spec 的范围 = **这一张共享表**（两变体三张子表）：先修模板结构与平台缺口，
再按 owner 逐个接入行级合并推送。不含其余 27 张共享表（各自另立）。

## Requirements

### Requirement 1: 模板结构缺陷修复

**User Story:** 作为审计师，我需要附注「受限资产」表的行归属与列元数据正确，
这样各循环推送的数据才会落到对的行上，且表头不会凭空多出父表头。

#### Acceptance Criteria

1. WHEN 读 soe `八、93` 的「应收款项融资」行 THEN 该行 SHALL 带
   `report_row_code = "BS-007"`（`report_config` 实证 `BS-007 应收款项融资 = TB('1124')`）
   —— 现为 `null`，导致该行被卷进 D2 的 `BS-006 应收账款` 段
2. WHEN 读 soe `八、93` 的「存货」行 THEN 该行 SHALL 带 `report_row_code = "BS-010"`
   —— 现为 **`BS-008`**，而 `BS-008` 实为「预付款项」（listed 侧标的 `BS-010` 是对的）
3. WHEN 读 soe `八、93` 的末行「其他」 THEN 它 SHALL 被标为**无主行**
   （不属任何 owner），使 `BS-029 在建工程` 段的 owner 推送不会删掉它
4. WHEN 读 listed `五、32` 主表与「续：」表 THEN 两表 SHALL 各有完整 `columns`
   （单级必标 `flat`）与 `guidance`，且 SHALL 删除 `row_type = "header_label"` 的假数据行
5. WHEN 读 soe `八、93` THEN 该表 SHALL 有完整 `columns`（3 列 flat）与 `guidance`
6. WHEN 「续：」表被重命名 THEN 新表名 SHALL 是
   「所有权或使用权受到限制的资产（续：上年年末）」（裸续表名会跨章节撞键），
   AND 旧名 SHALL 进 `_removed_table_keys` 的 legacy 种子
7. WHEN 修订脚本以 `--check` 运行 THEN 它 SHALL 报 0 项欠账且幂等

### Requirement 2: 平台补强 —— 显式「无主行」

**User Story:** 作为平台维护者，我需要模板能显式声明「这一行不属于任何段」，
这样表级兜底行（其他 / 未分类）不会被相邻段的 owner 覆盖。

#### Acceptance Criteria

1. WHEN 模板行带 `row_type = "unowned"` THEN `split_segments` SHALL 把它排除在
   所有段的**可写区**之外（与表级合计行同款处理）
2. WHEN `stamp_baseline_rows` 处理 `unowned` 行 THEN 该行的 `_seg` SHALL 为空串
3. WHEN 某段的可写区因 `unowned` 行而收窄 THEN 该段 owner 推送 SHALL NOT 删除该行
4. WHEN 表内无 `unowned` 行 THEN 段窗口 SHALL 与引入该字段前**逐字相同**（零回归）
5. WHEN `unowned` 行位于段**中间**（非段尾） THEN 段可写区 SHALL 止于该行之前
   （不做「跨越保留」，避免把 owner 数据劈成两段）

### Requirement 3: 各循环 owner 接入行级合并

**User Story:** 作为审计助理，我在各循环底稿录完受限资产后，附注对应行应自动出现，
且不会覆盖别的循环已录的行。

#### Acceptance Criteria

1. WHEN 某循环披露 Tab 的受限资产数据变更 THEN 载荷 SHALL 带
   `_row_scope: {表名: {owner_row_code: <本循环报表行>}}`
2. WHEN 载荷推送成功 THEN 附注该表内**其他段的行** SHALL 逐字段不变
3. WHEN 某循环无受限资产 THEN 该循环 SHALL NOT 推空段（空推送会把段恢复模板骨架，
   等于清掉审计师手填内容）
4. WHEN owner 段边界解析失败 THEN 服务端 SHALL 跳过该表写入并在返回值
   `row_scope_unresolved` 中报出，前端 SHALL 提示审计师
5. WHEN listed 变体推送 THEN 主表（期末）与「续：」表（上年年末）SHALL **各推一次**
   （双期拆两张表），且两次都带 `_row_scope`
6. WHEN soe 变体推送 THEN 载荷 SHALL 含「受限原因」列（源模板 3 列），
   listed 变体 SHALL NOT 含该列（源模板 2 列）

### Requirement 4: 勾稽与溯源

**User Story:** 作为现场经理，我需要看到「受限资产合计 = 各科目段之和」的勾稽，
以及每一段来自哪张底稿。

#### Acceptance Criteria

1. WHEN 各段均已推送 THEN 合计行 SHALL 等于各段金额之和（容差 0.01 元）
2. WHEN 某段金额与该循环审定表的受限金额不一致 THEN 勾稽 SHALL 报 error 级差异
3. WHEN 某段尚无 owner 接入 THEN 勾稽 SHALL 报 skip 而非 error（宁缺勿造）
4. WHEN 审计师在附注模块查看该表 THEN 每段 SHALL 可追溯到推送它的底稿
   （`_last_sync_wp_id` 是**最后一次**推送方，故段级溯源须由行内 `_seg` + registry 推导）

### Requirement 5: 守卫与零回归

**User Story:** 作为平台维护者，我需要守卫钉死本表的行归属与推送约束，防止后续漂移。

#### Acceptance Criteria

1. WHEN 运行守卫 THEN 它 SHALL 以 openpyxl 直读源 xlsx 交叉比对表名/列头/行集
2. WHEN 某 owner 的 `owner_row_code` 不在该表段集合内 THEN 守卫 SHALL 失败
3. WHEN 任一 owner 推该表却未声明 `_row_scope` THEN 平台守卫
   `disclosureSharedTableRowScope.spec.ts` SHALL 失败
4. WHEN 守卫读源码判定接线 THEN 它 SHALL 先 `stripComments()` 并含反向自检
5. WHEN 本 spec 的改动落地 THEN `disclosure-note-row-level-merge` 的
   characterization 零回归网 SHALL 全绿

## Glossary

| 术语 | 含义 |
|------|------|
| 共享表 | 同一张附注子表内按科目分段、每段归属不同循环；段首行带 `report_row_code` |
| owner / owner_row_code | 某段的归属循环，用该段首行的报表行编码标识（如 E1 = `BS-002`） |
| 可写区 / `data_end` | 段内允许被 owner 整段替换的区间右界，排除表级合计行与 `unowned` 行 |
| `unowned` 行 | 模板显式声明「不属于任何段」的行（表级兜底「其他」等） |
| 续表 | 双期表被 md 重建拆成的第二张表（上年年末），表名须带主表名前缀 |
