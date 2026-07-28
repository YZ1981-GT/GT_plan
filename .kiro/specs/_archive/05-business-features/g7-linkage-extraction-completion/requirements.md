# Requirements Document

## Introduction

G7 长期股权投资是平台联动面最广的底稿群：三个工作簿（`g7-long-term-equity-main` / `-method` / `-subsidiary`）共 22 个 sheet，向下游连接附注（上市 五、18；国企 七、合并范围 13 个子节 + 八、18）、合并工作底稿（`info` / `cost` / `equity_inv` / `net_asset` 四张表 + 建议草稿）、试算表（1511 原值 / 1512 减值）、集中调整登记、G11 投资收益、公式管理中心。

本 spec 收口 G7 复盘中「机制已具备但未接线」与「取数缺失」两类缺口，**不重做任何已工作的链路**：

- 已通不动：G7-14 → G7-3 建议分录跨册推送（ACNR `resolve-instance` + `if_match`）、两张披露表 → 附注 sync（`sync-from-workpaper` / `sync-batch-from-workpaper`）、附注 ↔ 披露表正反向跳转、审定表 TB 回写（1511/1512）、册内 window 事件（`g7:detail-updated` / `g7:adjustment-writeback` / `g7:impairment-updated` / `g7:adjustment-pushed`）、合并联动服务的映射与只填空语义、公式管理 surfaced 目录（20 个 sheet / 68 条）。
- 本 spec 范围：G7 底稿侧发起合并联动的入口、G7-2 / G7-1 的四表与跨册取数、抽凭引擎在处置与后续计量检查表的铺开、联动过期（stale）常驻提示、合并范围反向补录 G7-4、合并联动端点与草稿表的集成测试。

### 前置实证结论（已用 postgres 只读核实，作为需求边界依据，不可臆造）

1. `tb_aux_balance` 对 1511 存在**真实的被投资单位维度**：`aux_type='客户'`（全库该科目仅此一种 aux_type，无多维度冗余）、`aux_dimensions_raw` 形如 `客户:260369,重药控股淮北有限公司`，逐户带 `opening_balance / debit_amount / credit_amount / closing_balance`。故 G7-2 明细逐户取数**有干净数据源**。
2. `tb_balance` 1511 子科目为：`1511.01 对子公司的投资`、`1511.02 联营企业投资成本`、`1511.03 损益调整`、`1511.04 其他权益变动`（`.04.01` 属于其他综合收益 / `.04.02` 不属于）、`1512 长期股权投资减值准备`。故按子科目 → G7-2 列（投资成本 / 权益法损益调整 / OCI / 其他权益变动 / 减值）的分类合计交叉核对**可落地**。
3. G7-1 审定表是**逐户行结构**（一、对子公司投资（成本法）／二、对合营企业投资（权益法）／三、对联营企业投资（权益法）／减值组，每组逐个被投资单位行 + 小计 + 投资合计），与 1 中的客户维度可按单位名称归并匹配。
4. 合并联动端点已存在且已注册：`GET/POST /api/consol-worksheet-data/g7-linkage/{project_id}/{year}/{preview,import}`，权限分别 `readonly` / `edit`；建议草稿写入 `consol_worksheet_data.sheet_key='g7_suggestions'`。
5. G7 三个组是三个不同 `wp_id`，跨册取数只能经 HTTP（既有范式：`/api/acnr/resolve-instance` 解析目标 wp_id + `/api/workpapers/{wp_id}/checklist-responses` 读写 + `if_match` 乐观锁）。

## Glossary

- **Main_Group**：`g7-long-term-equity-main` 工作簿（G7A / G7-1 / G7-2 / G7-3 / 附注上市 / 附注国企 / 底稿目录）。
- **Method_Group**：`g7-long-term-equity-method` 工作簿（G7-4 / G7-5 / G7-6 / G7-13 / G7-14 / G7-15 / G7-16 / G7-17）。
- **Sub_Group**：`g7-long-term-equity-subsidiary` 工作簿（G7-7 ~ G7-12 / G7-18）。
- **Consol_Linkage**：G7 → 合并工作底稿的受控联动（既有 `g7_consol_linkage_service` + 两个端点），语义为「只把 G7 审定基础数据转换为合并侧输入，不自动生成正式抵消分录」。
- **Suggestion_Draft**：联动时用户勾选写入 `sheet_key='g7_suggestions'` 的建议草稿（商誉/少数股东、股比变动、G7-3 调整分录、投资成本差额、未确认损失、内部交易、会计政策调整）。
- **Linkage_Stale**：G7 源 checklist 保存后由 `mark_consol_linkage_stale_from_g7` 在合并侧 `data._g7_linkage.stale` 打的过期标记。
- **Aux_Investee_Source**：`tb_aux_balance` 中 `aux_type='客户'` 且 `account_code LIKE '1511%'` 的逐户余额行（本 spec 唯一的被投资单位维度取数源）。
- **Leaf_Category_Source**：`tb_balance` 中 1511/1512 的叶子子科目余额（用于分类合计交叉核对，不用于逐户明细）。
- **Cross_Book_Pull**：跨工作簿取数范式（ACNR `resolve-instance` 解析 wp_id → 读 `checklist-responses` → 纯函数映射 → 前端展示/带入）。
- **Persist_First**：已有用户手工值的单元格不被取数覆盖；仅填空或经用户显式确认后覆盖。
- **Extraction_Flag**：灰度开关 `G7_FOUR_TABLE_EXTRACTION_ENABLED`，默认 `False`；关闭时取数路径逐字节等价于当前行为。

## Requirements

### Requirement 1: G7 底稿侧发起合并联动

**User Story:** 作为编制 G7 的审计助理，我希望在 G7 底稿内就能看到「本底稿数据已联动到合并工作底稿的状态」并能发起联动，而不是只能由合并模块操作者发起。

#### Acceptance Criteria

1. WHEN 用户在 Main_Group 打开 G7-1 审定表或底稿目录 THEN 系统 SHALL 显示一个「联动到合并工作底稿」入口。
2. WHEN 用户点击该入口 THEN 系统 SHALL 调用既有 `GET /api/consol-worksheet-data/g7-linkage/{project_id}/{year}/preview` 展示预览摘要（可导入行数、目标表、未匹配主体、Linkage_Stale 状态、建议草稿条数），并 SHALL NOT 新建后端端点或新的映射口径。
3. WHEN 用户在该入口确认导入 THEN 系统 SHALL 调用既有 `POST .../import` 并透传 `expected_versions`，且 WHEN 返回 409 THEN 系统 SHALL 提示源数据已变更并自动重新预览。
4. IF 当前用户无编辑权限或底稿为只读态 THEN 系统 SHALL 禁用确认导入（预览仍可查看）。
5. IF 项目存在多个 G7 主表实例或未生成 G7 主表 THEN 系统 SHALL 显示后端返回的配置错误原因（422），而不是静默失败。
6. WHEN 联动完成 THEN 系统 SHALL 提供跳转到合并工作底稿的入口，供用户核对写入结果。

### Requirement 2: G7-2 明细表逐户四表取数

**User Story:** 作为审计助理，我希望 G7-2 明细表的被投资单位与期初/本期增减/期末能从账套自动带入，而不是逐户手打。

#### Acceptance Criteria

1. WHEN 用户在 G7-2 点击「从四表取数」 THEN 系统 SHALL 从 Aux_Investee_Source 提取逐户期初/借方/贷方/期末，并按被投资单位名称生成或匹配明细行。
2. 系统 SHALL 锁定单一 `aux_type='客户'` 取数，IF 同一项目同一科目出现多个 aux_type THEN 系统 SHALL 只取被明确选定的一种并提示，SHALL NOT 跨 aux_type 相加。
3. WHEN 目标明细行已有用户手工值 THEN 系统 SHALL 遵循 Persist_First，仅填空值；WHEN 用户显式选择「覆盖」 THEN 系统 SHALL 覆盖并提示影响行数。
4. 系统 SHALL 在取数结果上标注来源（科目编码、aux 维度原文、取数时间），使每个自动值可追溯。
5. IF Aux_Investee_Source 无该项目数据 THEN 系统 SHALL 提示「账套无被投资单位辅助余额，请手工录入」并 SHALL NOT 用科目合计臆造逐户金额。
6. WHEN Extraction_Flag 为 `False` THEN 取数入口 SHALL 不产生任何数据写入，且 G7-2 既有行为逐字节不变。

### Requirement 3: G7-1 审定表未审数取数与分类核对

**User Story:** 作为审计助理，我希望审定表的未审数与账套一致，并能立刻看出与账套分类合计的差异。

#### Acceptance Criteria

1. WHEN 用户在 G7-1 点击「从 G7-2 带入未审数」 THEN 系统 SHALL 按被投资单位名称把 G7-2 的期初/期末未审数带入对应控制类型分组行，并保留该行既有 AJE/RJE。
2. 系统 SHALL 依据 Leaf_Category_Source 展示分类合计核对：1511 叶子子科目合计（投资成本 / 损益调整 / 其他权益变动）与审定表相应合计的差异，1512 与减值组的差异。
3. IF 差异绝对值 > 0.01 THEN 系统 SHALL 以告警样式提示差异金额与可能原因（分类归属、未纳入范围、账套未标准化）。
4. 系统 SHALL 只汇总叶子科目，SHALL NOT 把父级科目与其子科目同时计入（防双算）。
5. 带入与核对 SHALL NOT 改变既有 TB 回写行为（仅保存后 `writebackTb=true` 才回写 1511/1512）。

### Requirement 4: G7-1 从 G7-14 权益法测算跨册带入

**User Story:** 作为审计助理，我希望权益法测算出的期末余额能直接带到审定表的合营/联营行，而不是人工搬数。

#### Acceptance Criteria

1. WHEN 用户在 G7-1 点击「从 G7-14 带入权益法期末余额」 THEN 系统 SHALL 经 Cross_Book_Pull 读取 Method_Group 的 G7-14 数据，并按被投资单位名称带入合营/联营分组行。
2. 系统 SHALL 在带入前展示逐户对照（G7-14 期末余额 vs 审定表当前值）并要求用户确认。
3. 系统 SHALL 遵循 Persist_First：未确认覆盖时仅填空值。
4. IF Method_Group 未实例化或 G7-14 无数据 THEN 系统 SHALL 提示来源缺失并保持审定表不变。
5. 带入后系统 SHALL 展示 G7-14 与 G7-2/G7-1 的期末勾稽差异（复用既有 `calcClosingReconVariance` 口径，不新造公式）。

### Requirement 5: 抽凭引擎铺开到处置与后续计量检查表

**User Story:** 作为审计助理，我希望在后续计量与处置检查表也能用抽凭引擎抽取凭证，而不只有 G7-18。

#### Acceptance Criteria

1. WHEN 用户在 G7-10、G7-11、G7-12 打开抽凭 THEN 系统 SHALL 挂载抽凭引擎并传齐 `account-code`、`phase`、`workpaper-id`、`year` 四个必需属性。
2. 系统 SHALL 使用合法 `phase` 取值（`preliminary` | `final`），SHALL NOT 传入非法值。
3. WHEN 抽凭回填 THEN 系统 SHALL 从 `payload.samples` 解构样本并按各表行模型映射（凭证号/日期/借贷金额/对方科目），且按凭证号去重。
4. IF 当前为只读态或缺少 `wpId`/`projectId` THEN 系统 SHALL 隐藏抽凭入口。

### Requirement 6: 联动过期状态常驻可见

**User Story:** 作为项目经理，我希望在合并工作底稿与 G7 底稿都能立刻看到「G7 数据已变更、合并侧联动结果已过期」。

#### Acceptance Criteria

1. WHEN 合并侧存在 Linkage_Stale 标记 THEN 合并工作底稿 SHALL 在主界面常驻提示（不只在联动弹窗内），并列出过期的目标表。
2. WHEN G7 底稿检测到合并侧存在 Linkage_Stale THEN G7 SHALL 提示「合并侧联动结果已过期，请重新联动」。
3. WHEN 用户完成一次成功导入 THEN 两侧提示 SHALL 消失。
4. IF 状态查询失败 THEN 系统 SHALL 静默降级不显示提示，SHALL NOT 阻断页面。

### Requirement 7: 合并范围反向补录 G7-4

**User Story:** 作为审计助理，我不想把合并范围里已有的子公司清单在 G7-4 再录一遍。

#### Acceptance Criteria

1. WHEN 用户在 G7-4 点击「从合并范围带入」 THEN 系统 SHALL 读取该项目该年度 `consol_scope` 中未删除的主体，生成或匹配 G7-4 行（单位名称、编码、持股比例、纳入范围原因）。
2. 系统 SHALL 遵循 Persist_First：仅补空字段，SHALL NOT 覆盖 G7-4 已有值，SHALL NOT 删除 G7-4 中合并范围没有的主体（如共同经营）。
3. 系统 SHALL 保持 G7-4 比例口径为百分数（0~100）并写入 `ratioScale` 标记。
4. IF `consol_scope` 无数据 THEN 系统 SHALL 提示范围未维护并保持 G7-4 不变。

### Requirement 8: 联动与草稿的自动化测试补齐

**User Story:** 作为质控复核人，我要求这条会写库的联动链有回归保护，而不是只有纯函数测试。

#### Acceptance Criteria

1. 系统 SHALL 覆盖 `preview` / `import` 两个端点的成功路径、409（版本冲突）、422（配置错误/年度不一致）与权限（readonly 不可导入）。
2. 系统 SHALL 覆盖 import 的 DB 写入路径：四张目标表的只填空合并、`consol_scope` 同步不覆盖 `is_included`、Suggestion_Draft 写入、Linkage_Stale 置位与清零。
3. 系统 SHALL 覆盖 Suggestion_Draft 的读取与展示（含未知 type 不崩、字段缺失不崩）。
4. 系统 SHALL 覆盖本 spec 新增取数纯函数（Aux_Investee_Source 归并、Leaf_Category_Source 叶子过滤与分类映射、跨册带入映射）。

### Requirement 9: 零回归与灰度

**User Story:** 作为平台维护者，我要求这些增强不影响 G7 现有 22 个 sheet 与合并侧既有语义。

#### Acceptance Criteria

1. WHEN Extraction_Flag 为 `False` THEN 所有取数路径 SHALL 不写入任何数据，G7 各 sheet 渲染与持久化行为 SHALL 与当前逐字节等价。
2. 系统 SHALL NOT 修改 `g7_consol_linkage_service` 的字段映射、比例口径、只填空语义与「不自动生成抵消分录」约束。
3. 系统 SHALL NOT 修改附注 sync 载荷结构、章节映射与既有正反向跳转。
4. 系统 SHALL NOT 修改审定表 TB 回写触发条件与科目（1511/1512）。
5. 每个需求 SHALL 可独立回退（入口/取数/抽凭/提示/反向补录/测试互不依赖）。

### Requirement 10: 正确性属性可测

**User Story:** 作为质控复核人，我要求关键计算与取数规则有属性化测试而不是只靠示例。

#### Acceptance Criteria

1. 系统 SHALL 为「叶子科目过滤后合计 = 不含父级重复计入」提供属性测试。
2. 系统 SHALL 为「Persist_First：任意手工值集合下取数不改变已填单元格」提供属性测试。
3. 系统 SHALL 为「单一 aux_type 取数：多 aux_type 输入下结果等于选定 aux_type 的子集合计」提供属性测试。
4. 系统 SHALL 为「按名称归并幂等：同一取数重复执行结果不变、不产生重复行」提供属性测试。
5. 系统 SHALL 为「Extraction_Flag 关闭时输出为空/无写入」提供属性测试。

## 附录：复盘二轮增量（部分已直接修复，其余待纳入本 spec 波次）

二轮深入复盘后逐项处置结论（用户指令「能修就直接修，不能就进 spec」）：

**已直接修复（本轮，未 commit）**

- P0-1 G7 → K11 减值来源断链：G7-17 `persistRows` 发 `impairment:calculated { wpCode:'G7', accountCode:'1512', totalRequiredProvision: 减值合计 }`（K11 `handleImpairmentCalculated` 白名单含 G7、读 `totalRequiredProvision`）。**不在 G7-1 substantive payload 加 auditedAmount=减值**（`crossWpEventBridge` 会把 auditedAmount/adjudicatedAmount 互填，污染 1511 原值）。
- P0-2 G7-3 → A13 未更正错报：`G7TabAdjustment` 加「推送错报至 A13」按钮 + `eventBus.emit('a13:push-misstatement', { wpCode:'G7-3', accountCode:'1511', entries:[...] })`，走全局唯一消费者 `useA13MisstatementBridge`（形态 B）；只推已填金额且非「建议草稿」的分录。
- P1-3 method / subsidiary 两册无「底稿目录」sheet：新增共享 `g7-shared/G7SheetNavBar.vue`（导航条 + 编制进度 + 编制/使用手册入口，自读 checklist-responses 判各 sheet 是否已编制），两册主入口 HTML sheet 顶部挂载，`@navigate` 转发 `navigate-sheet` 由 GtWpRenderer 切 tab。不新增 sheet、不依赖 DB classification。
- P2-6 覆盖契约：`tests/test_g7_sheet_override_contract.py` 锁定三册编码型 sheet（G7-N）均在 `wp_code_overrides.json` 映射到本册 componentType，防新增/改名 sheet 漏 override 静默落通用兜底。
- P2-9 注释纠正：`_g7_long_term_equity_method.py` docstring「科目 1401」→「1511」。

**进 spec（结构性/跨模块，待本 spec 波次实现）**

### Requirement 11: G7-1 TB 核对科目走规则映射（P1-4）

**User Story:** 作为集团项目审计助理，我希望 G7-1 原值/减值核对科目能跟随项目自定义子科目口径，而不是硬编码 1511/1512 前缀。

#### Acceptance Criteria

1. WHEN render G7-1 THEN 系统 SHALL 经 `resolve_report_line_account_codes(row_code=长期股权投资报表行, fallback=['1511'])` 解析项目级源科目码集，并从中拆分原值码集（非 1512 开头）与减值码集（1512 开头），fallback 保持 1511/1512 前缀（零回归）。
2. 系统 SHALL 输出 `project_context.tb_source_codes.{gross,impairment}` 供前端溯源。
3. IF 报表行为净额单行无法拆分原值/减值 THEN 系统 SHALL 回退按 1511/1512 前缀叶子聚合（保持当前行为），SHALL NOT 因映射不含拆分信息而取空。

### Requirement 12: G11 处置损益/成本法股利联动补齐（P2-5）

**User Story:** 作为审计助理，我希望 G7-11/G7-12 处置损益与 G7-2/G7-10 成本法股利也能带入或核对到 G11-2 投资收益，而不只有权益法。

#### Acceptance Criteria

1. WHEN 用户在 G11-2 THEN 系统 SHALL 提供从 G7-11/G7-12 带入处置损益、从 G7-2 `cashDividend`/G7-10 带入成本法股利的入口，复用既有 Cross_Book_Pull 与「从 G7-14 带入」范式。
2. 系统 SHALL 遵循 Persist_First 且提供差异对照，SHALL NOT 覆盖手工值。

### Requirement 13: 披露 sync 状态可见与自动同步（P2-7，附注模块级）

**User Story:** 作为项目经理，我希望在 G7 披露表看到「是否已同步到附注、上次同步时间」，而不是不知道 46 个 buildXSyncPayload 从未被点过。

#### Acceptance Criteria

1. WHEN 打开 G7 披露表 THEN 系统 SHALL 显示同步状态（未同步 / 已同步于 T），G7 soe 一次覆盖 14 章节的状态 SHALL 可见。
2. WHEN 保存披露表 THEN 系统 SHALL 支持保存后自动触发同步（可配），并在成功后刷新状态。
3. 本需求属附注模块级通用能力，SHALL 以不破坏既有 sync 载荷结构为前提。

## 后续记录（不进本 spec，仅登记）

- P2-8 「七、合并范围」双写边界：G7 soe 披露 sync 写七、13 子节，合并模块另有 `consol_scope` 合并范围章节。当前 `CONSOL_NOTES_V2_ENABLED=False` 且 V2 未落 `disclosure_notes`，暂无冲突；合并 V2 落库前须先定 owner（同 N1/N3 共用五、30 教训）。
- P2-10 大文件：`g7_consol_linkage_service.py`（2267 行）、`G7TabAdjudication.vue`（1200+ 行）可拆，属技术债非功能缺口。
- P2-11 序时账凭证级取数：1511 借贷发生额的凭证级溯源（增减笔数、对方科目）未做，可作 R2 取数的后续增强。
