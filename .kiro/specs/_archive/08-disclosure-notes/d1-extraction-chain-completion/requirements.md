# Requirements Document

## Introduction

D1 应收票据的「四表库入库 → 底稿刷新取数 → 披露表 → 附注」链路目前**中间断裂两处**，
导致即使四表库有数、灰度开关打开，附注 五、4 / 八、4 仍拿不到金额。本 spec 以
**源模板 `backend/wp_templates/D/D1 应收票据.xlsx`**（含单元格公式）+ **F4-1~F4-30 校验预设**
+ **DB 实证（report_config / account_mapping / account_chart / tb_balance / tb_aux_balance）**
三方为裁决者，补齐取数链路、修订公式管理预设、修复披露表与附注的结构/口径偏差。

### 实证的科目映射链路（本 spec 的取数基准）

```
tb_balance.account_code        = 客户原始码   1121 / 1121.01 / 1121.02 / 1121.03 / 1231.01
        │  account_mapping(project_id, original_account_code → standard_account_code)
        ▼
trial_balance.standard_account_code = 标准码   1121 / 1231-01
        │  report_config.formula（applicable_standard 维度）
        ▼
报表行 BS-005「应收票据」
     soe_standalone       : TB('1121','期末余额') - TB('1231-01','期末余额')
     listed_* / soe_consol: TB('1121','期末余额')
        │  F4-1 / F4-2
        ▼
附注 五、4 / 八、4 ①分类表.合计行.期末（期初）账面价值
```

实证要点：客户把「坏账准备_应收票据」编在 `1231.01`，`account_mapping` 将其映射到标准码
`1231-01`，而 `soe_standalone` 的 BS-005 公式正是引用 `1231-01` —— 因此**坏账科目不应再由
名称关键字猜测，而应由报表规则映射解析**。

### 实证的链路断点

| # | 环节 | 现状 | 证据 |
|---|------|------|------|
| 1 | tb_balance → D1-2 / D1-4 | ✅ 通（`seed_d1_detail_rows`），但硬编码 `1121`/`1231`+名称含「应收票据」 | `d1_detail_seed.py` |
| 2 | D1-2 → D1-1 原值 | ⚠️ 只认「银行/商业」，其余票据种类（信用证 / 财务公司承兑汇票）**无落点** | `useD1Adjudication.GROSS_ROWS` |
| 3 | D1-4 → D1-1 坏账 | ❌ **完全没有取数**：`bdDetailRows` 只翻 `isFromCrossSheet` 标记、从不写值 | `useD1Adjudication` 第 2 区块 |
| 4 | D1-1 → 披露①分类表 | ❌ **读的锚点全平台无写入方**：`-current-audited` 后缀从不持久化（审定数是 computed），且前缀是 `baddebt-` 而实际是 `bd-` | `useD1Disclosure.CROSS_SHEET_KEYS` vs `d_cycle_anchor_registry.json` D1 正则 |
| 5 | D1-1 → D1-10 监盘 / D1-11 关联方 | ❌ 同类：读 `D1-adj-notes-receivable-current-audited`，无写入方 | `useD1InventoryCount` / `useD1RelatedPartyCheck` |
| 6 | 披露表 → 附注 | ✅ 通（`buildD1SyncPayload` + `useDisclosureAutoSync`） | 已实测 |
| 7 | tb_aux_balance 1121「客户」→ D1-3 | ❌ 未接（仅有序时账期后兑付） | `tb_aux_balance` 实证 1121.01/.02/.03 均有 `aux_type='客户'` |

断点 3 / 4 / 5 之所以长期未被发现：`useD1Disclosure.pbt.spec.ts` 与
`useD1DisclosureDerived.spec.ts` **直接以同款错误键播种 fixture**，测试恒绿而生产恒死。

## Requirements

### Requirement 1: 四表取数走报表科目映射，不再硬编码科目前缀

**User Story:** 作为审计助理，我希望 D1 的四表取数与报表科目映射规则一致，这样客户自定义科目
编码（坏账准备编在 1231.07、票据原值编在 1121 以外）时底稿仍能正确取数。

#### Acceptance Criteria

1. WHEN D1 render 需要确定原值/坏账科目 THEN 系统 SHALL 经 `resolve_report_line_account_codes(db, project_id, 'BS-005', fallback=['1121','1231-01'])` 解析 `report_config.formula` 得到标准码集合
2. WHEN 解析出的标准码集合含多个码 THEN 系统 SHALL 按「备抵科目判定」把它们拆为**原值码集**与**坏账码集**，判定依据为 `account_chart`（`source='standard'`）的 `direction='credit'` 或科目名含「坏账准备」/「减值准备」
3. WHEN 需要在 `tb_balance` 中查询某标准码 THEN 系统 SHALL 先经 `account_mapping`（`project_id` + `standard_account_code`）反解为该项目的**原始科目码集**，再以原始码前缀查 `tb_balance`
4. WHEN `account_mapping` 无该项目记录或反解为空 THEN 系统 SHALL 回退为「标准码去掉 `-` 后作前缀」（`1231-01` → `1231`）并保留既有名称关键字过滤（零回归）
5. WHEN 报表映射解析抛异常 / `report_config` 无该行 THEN 系统 SHALL fail-open 回退到 `fallback` 且不阻断 render
6. WHEN 取数完成 THEN render SHALL 在 `html_data` 输出 `tb_source_codes = {gross: [...], provision: [...], resolved_from: 'report_config'|'fallback'}` 供前端做取数溯源展示
7. WHEN 灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 为 False THEN D1 render 输出 SHALL 与本 spec 改动前逐字节等价

### Requirement 2: 审定表 D1-1 取数链路补齐（坏账区块 + 动态票据种类）

**User Story:** 作为审计助理，我希望四表入库后 D1-1 审定表的原值与坏账两个区块都自动带数，
且客户实际存在的所有票据种类都有落点，这样净值与试算平衡表的差异才是真实差异。

#### Acceptance Criteria

1. WHEN D1-4 坏账准备明细表存在按票据种类小计数据 THEN D1-1「二、应收票据坏账准备」各行 SHALL 从其跨表带入期初/期末未审与调整列（对应源模板 `D1-1!B12='坏账准备明细表D1-4'!B23`、`F12=!K23`）
2. WHEN D1-4 尚未填按票据种类小计 THEN D1-1 坏账行 SHALL 保持可手工录入且 `isFromCrossSheet=false`（不得像现状那样显示「已取数」却是 0）
3. WHEN D1-4 提供了「按票据种类小计」区块 THEN 该区块 SHALL 逐字采用源模板行名「银行承兑汇票小计」「商业承兑汇票小计」，并与 D1-4 合计行做勾稽提示（源模板 `D1-4!R22` 合计 vs `R23+R24`）
4. WHEN D1-2 原值明细表存在「银行承兑汇票」「商业承兑汇票」以外的票据种类（如信用证、财务公司承兑汇票）THEN D1-1 三个区块 SHALL 按 D1-2 实际类别顺序追加**动态行**，固定的银承/商承行排在前
5. WHEN 动态票据种类行被创建 THEN 其锚点 SHALL 形如 `D1-adj-(gross|bd|net)-{slug}-{field}` 并被 `d_cycle_anchor_registry.json` 的 D1 模式锚点接纳
6. WHEN 审定表小计与 D1-2 / D1-4 合计不一致 THEN 系统 SHALL 在审定表内以提示行（非阻断）展示差异

### Requirement 3: 披露①分类表与 D1-10 / D1-11 的跨表取数修复

**User Story:** 作为审计助理，我希望披露表主表自动反映审定表结果，这样点「同步到附注」后附注就有数。

#### Acceptance Criteria

1. WHEN 披露表需要①分类表的原值/坏账/账面价值 THEN 系统 SHALL 经**共享纯函数**从 D1-1 实际持久化的锚点（`D1-adj-{rowKey}-{prior|current}-{unadj|aje|rje}`）读取并按 `审定数 = 未审 + 账项调整 + 重分类调整` 现算，不得再读不存在的 `-current-audited` 锚点
2. WHEN D1-1 存在动态票据种类行 THEN 披露①分类表 SHALL 同步出现对应票据种类行（与 Requirement 2.4 同构）
3. WHEN D1-1 全部区块均无数据 THEN 披露①分类表 SHALL 保持可手工录入（`canEditCategorySummary=true`）与既有导入兜底不变
4. WHEN D1-10 应收票据监盘 / D1-11 关联方检查需要账面余额 THEN 系统 SHALL 复用同一共享纯函数取「一、应收票据原值」期末审定合计，不得再读无写入方的 `D1-adj-notes-receivable-current-audited`
5. WHEN 共享纯函数的锚点集合与 `d_cycle_anchor_registry.json` 的 D1 模式锚点不一致 THEN 守卫测试 SHALL 失败

### Requirement 4: D1-3 客户明细表接入辅助余额表取数

**User Story:** 作为审计助理，我希望 D1-3 原值明细表（按客户）能一键从辅助余额表带出客户明细，
而不必手工录入几十上百行。

#### Acceptance Criteria

1. WHEN 用户在 D1-3 点「从辅助余额表导入」THEN 系统 SHALL 按 `tb_aux_balance`（`aux_type='客户'`、科目 = Requirement 1 解析出的原值原始码集）经 `get_active_filter` 归集出客户级期初/借方/贷方/期末
2. WHEN 同一客户在多个票据种类子科目下都有余额 THEN 系统 SHALL 按客户名合并，并把票据种类记入行内「票据种类」字段（多种类时以「/」连接）
3. WHEN 该项目 `tb_aux_balance` 无「客户」维度数据 THEN 端点 SHALL 返回 `imported_count=0` 且不写入（宁缺勿造，不报错）
4. WHEN D1-3 已有手工录入行 THEN 导入 SHALL 按客户名合并而不覆盖已录入的非取数列（关联方标记、期后兑付、备注）
5. WHEN 导入完成 THEN 归集合计 SHALL 与 `tb_balance` 原值码集期末合计做勾稽提示

### Requirement 5: 公式管理预设修订与补齐

**User Story:** 作为现场经理，我希望公式管理面板里 D1 的预设公式指向真实存在的 sheet 与维度，
这样审计师看到的取数说明是可信的。

#### Acceptance Criteria

1. WHEN `prefill_formula_mapping.json` 登记 D1 的 sheet 名 THEN 其值 SHALL 与源模板真实 sheet 名逐字一致（`原值明细表（按客户）D1-3`、`坏账准备明细表D1-4`，现值 `分析程序D1-3`、`票据明细表D1-4` 为过时值）
2. WHEN 登记 `TB_AUX` 公式 THEN 其维度名 SHALL 是 `tb_aux_balance.aux_type` 实际存在的值（`客户`），不得使用不存在的 `票据类型`
3. WHEN D1-2 / D1-4 需要四表取数说明 THEN `prefill_formula_mapping.json` SHALL 各补条目（D1-2 ← `TB('1121', ...)`，D1-4 ← `TB('1231-01', ...)`）
4. WHEN D1-1 审定表需要底稿间连接取数说明 THEN SHALL 补 `WP('D1','原值明细表（按类别）D1-2', ...)` 与 `WP('D1','坏账准备明细表D1-4', ...)` 两条；明细表侧 SHALL NOT 出现 `WP()`（防循环）
5. WHEN 守卫测试运行 THEN SHALL 校验 D1 全部预设的 `sheet` ∈ 源模板 sheet 名集合、`TB_AUX` 维度 ∈ 平台已知维度集合

### Requirement 6: 披露表与源模板的口径/结构偏差修复

**User Story:** 作为质量控制复核合伙人，我希望披露表算出来的比率与合计和源模板公式一致，
这样附注交付物不会出现 0.0575% 这类明显错误。

#### Acceptance Criteria

1. WHEN 国企「按组合计提坏账准备的应收票据」表同步到附注 THEN 其 `loss_rate` SHALL 按百分数输出（×100），与同版分类表及源模板 `D36/D39/D42 = C/B*100` 一致
2. WHEN 上市「组合计提项目」表与「按单项计提」表输出合计行 THEN 合计行的预期信用损失率 SHALL 按「合计坏账准备 ÷ 合计账面余额」派生，而不是硬编码 0（源模板 `D68/D74/D82/D89`）
3. WHEN 披露坏账准备变动表自动计算期末数 THEN 公式 SHALL 为 `期初 + 计提 − 收回或转回 − 核销 − 转销 − 其他变动`（源模板上市 `B100` / 国企 `G48`），与 `d1DisclosureConsistency` 的 F4-7 判定同口径
4. WHEN 修复 6.3 THEN D1-4 坏账准备明细表沿用的 `calcBadDebtEndBalance`（源模板 `K=B+SUM(F:G)−SUM(H:J)`，含「其他增加」为加项）语义 SHALL 保持不变
5. WHEN 构建同步载荷 THEN `buildD1SyncPayload` 的 `applicableStandards` 入参 SHALL 取自 `useHostApplicableStandards`，不得传 `null`
6. WHEN 项目账龄口径（3年段 / 5年段 / 自定义）与组合计提行名不一致 THEN 披露表 SHALL 以只读提示列出不属于当前段集的行名，且 SHALL NOT 自动删除用户数据

### Requirement 7: 附注结构复核与报表↔附注映射

**User Story:** 作为业务合伙人，我希望附注 五、4 / 八、4 的表格结构、列头与文本框与源模板一致，
且报表「应收票据」行与附注章节建立可追溯映射。

#### Acceptance Criteria

1. WHEN 以源模板两个披露 sheet 复核附注 五、4（14 表）/ 八、4（12 表）THEN 差异清单 SHALL 逐表记录（无差异亦记录），且列头字面以 F4 校验预设为裁决者
2. WHEN 附注模板存在结构欠账 THEN SHALL 由幂等脚本 `fix_note_d1_notes_receivable_structure.py` 增量修复并 `--check` 归零
3. WHEN `report_note_linkage.json` 缺少 BS-005 → 五、4 / 八、4 映射 THEN SHALL 按 F4-1 / F4-2 人工核实后补入，并同步加入 `test_report_note_linkage_diagnose._VERIFIED_SEED_ROW_CODES` 白名单
4. WHEN 附注侧被推送的子表名 / 列键与模板不一致 THEN `d1NoteSubtableContract.spec.ts` SHALL 失败

### Requirement 8: 守卫与实测

**User Story:** 作为质量控制复核合伙人，我希望这条链路上的每个断点都有守卫，避免再次静默失效。

#### Acceptance Criteria

1. WHEN 任一跨表读取的锚点在全平台无写入方 THEN 守卫测试 SHALL 失败（正向扫描 D1 composables 的读取键 ↔ 写入键）
2. WHEN 测试 fixture 直接以硬编码锚点字符串播种跨表数据 THEN 该锚点 SHALL 取自共享常量而非字面量（防「测试镜像 bug」复发）
3. WHEN 本 spec 交付 THEN 后端 `backend/tests/d_cycle_extraction/` 与前端 D1 相关测试 SHALL 全绿（既有基线失败除外）
4. WHEN 本 spec 交付 THEN SHALL 以真实项目（`0ec33ac9…` / 2025）在浏览器实测：四表入库 → D1-2/D1-4/D1-1 有数 → 披露表有数 → 推送后附注 五、4·八、4 落库正确，测试数据用后复原

## Glossary

| 术语 | 含义 |
|------|------|
| 原始码 | 客户科目表编码，存 `tb_balance.account_code` / `tb_aux_balance.account_code`（如 `1121.01`、`1231.01`） |
| 标准码 | 平台标准科目编码，存 `trial_balance.standard_account_code`（如 `1121`、`1231-01`） |
| 备抵科目 | 抵减资产账面余额的贷方科目（此处即坏账准备 `1231-01`） |
| 锚点 | `checklist_responses.item_id`，底稿单元格的持久化标识 |
| 审定数 | `未审数 + 账项调整(AJE) + 重分类调整(RJE)`，D1-1 中为 computed 列（**不持久化**） |
| 票据种类 | D1-2 的行维度（银行承兑汇票 / 商业承兑汇票 / 财务公司承兑汇票 / 信用证 …） |
| 按票据种类小计 | D1-4 源模板 R23/R24 的额外小计块，专门喂 D1-1 坏账区块 |
| Tier A / Tier B | Tier A = 可编辑单条提取公式（`trial_balance` 审定口径）；Tier B = 复杂归集预填（`tb_balance`/`tb_aux_balance`/序时账，未审口径） |
| F4-n | 应收票据附注校验预设编号（`note_check_preset_formulas.json`），列结构与勾稽的裁决者 |
