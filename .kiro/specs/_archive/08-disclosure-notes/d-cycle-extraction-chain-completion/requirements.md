# Requirements Document

## Introduction

D1 应收票据的「四表库入库 → 底稿刷新取数 → 披露表 → 附注」链路已由 spec
`d1-extraction-chain-completion` 打通并实测。本 spec 把同一条链路推广到 **D2 应收账款 /
D3 预收账款 / D5 应收款项融资 / D6 合同资产 / D7 合同负债**，裁决者与 D1 一致：

- 🔴 **源 xlsx**：`backend/wp_templates/D/*.xlsx`（运行时权威副本）的审定表 + 两个披露 sheet
- 🔴 **`report_config` DB 表**：报表行公式是科目映射的唯一真源（**不是**代码里的硬编码前缀）
- **F4-* / 各循环校验预设**（`note_check_preset_formulas.json`）：披露列头与勾稽的裁决者
- **DB 实证**：`account_chart` / `account_mapping` / `trial_balance` / `tb_balance`

### 已实证的科目映射真源（本 spec 的取数基准）

| 循环 | 报表行 | `soe_standalone` 公式 | 现有 Tier A 预设 | 判定 |
|------|--------|----------------------|-----------------|------|
| D1 应收票据 | BS-005 | `TB('1121') − TB('1231-01')` | 同左 | ✅ 已修（前序 spec） |
| D2 应收账款 | BS-006 | `TB('1122') − TB('1231-02')` | `TB('1122')` | 🔴 **缺减备抵** |
| D3 预收账款 | BS-046 | `TB('2203')` | `TB('2203')` | ✅ |
| D5 应收款项融资 | BS-007 | `TB('1124')` | `TB('1124')` | 🔴 **`1124` 科目不存在** |
| D6 合同资产 | **BS-011** | `TB('1141')` | `TB('1402')` | 🔴 **取错科目族** |
| D7 合同负债 | BS-047 | `TB('2205')` | `TB('2205')` | ✅ |

补充实证：

- `account_chart`（`source='standard'`）中 **`1141 合同资产` 存在**、
  **`1402` 是「在途物资」**（存货类）、**`1124` 完全不存在**（10 个候选码逐一查过）。
- `1231-02 坏账准备-应收账款` 存在且 `direction='credit'`（备抵）。
- `listed_standalone` 的 BS-006 用**整个 `1231`**（含应收票据/其他应收款的坏账）→
  报表行虚减，属**平台级报表配置缺陷**，本 spec 只报告不改（影响全部项目报表）。

### 已实证的链路断点

| # | 循环 | 环节 | 现状 | 证据 |
|---|------|------|------|------|
| 1 | D2 | Tier A TB 核对行 | ❌ 预设取原值 `TB('1122')`，而审定表比的是**净值合计**（源模板 A27 = 三、应收账款净值合计，`A22=A8−A15` 逐行相减）→ 差异恒等于坏账准备的**假差异** | `d_cycle_extraction_presets.json` vs 源模板 `审定表D2-1` |
| 2 | D2 | 附注模板 | ❌ 上市 五、5 **17 张表 `columns` 与 `guidance` 全缺**、`_aligned_by=None`；国企 八、5 **13 张表全缺** + **4 张表有占位行/假表头行** → seed 路径被 `_infer_groups_from_headers` 塞凭空父表头 | 扫描 `note_template_{listed,soe}.json` |
| 3 | D6 | 四表取数 | ❌ Tier A 预设 `TB('1402','期末余额')`（在途物资）→ 合同资产取数恒错/恒空 | `report_config` BS-011 = `TB('1141')` |
| 4 | D5 | 四表取数 | ❌ 报表行 BS-007 与预设都引 `TB('1124')`，该码在 `account_chart` 不存在 → 取数恒空且无人察觉 | `account_chart` 查询 |
| 5 | D2/D3/D6/D7 | 明细 seed | ⚠️ 只有 D6 有明细 seed（`D_CYCLE_DETAIL_SEED_ENABLED`）；D2 明细表 D2-2/坏账 D2-3 是否可从 `tb_balance` 叶子诚实取数待逐项核查 | `_TIER_B_PROVENANCE` D2=2 条 / D6=2 条 |

断点 1 与 D1 完全同款（前序 spec 已实测：审定净值 vs 原值差异恰好等于坏账准备）；
断点 3 与归档 spec `k2-four-table-extraction-and-dynamic-rows` 的「取错整个科目族」同款。

## Requirements

### Requirement 1: D 类各循环的四表取数走报表科目映射，不再硬编码科目前缀

**User Story:** 作为审计助理，我希望 D 类每个循环的取数科目与报表映射规则一致，
这样客户自定义科目编码时底稿仍能正确取数，也不会取到别的科目族。

#### Acceptance Criteria

1. WHEN 任一 D 类循环（D2/D3/D5/D6/D7）需要确定取数科目 THEN 系统 SHALL 经
   `resolve_report_line_account_codes(db, project_id, row_code, fallback=[...])`
   解析 `report_config.formula`，`row_code` 取值 SHALL 为 BS-006 / BS-046 / BS-007 /
   BS-011 / BS-047（逐循环对应）
2. WHEN 解析出的标准码集合含备抵科目 THEN 系统 SHALL 按 `account_chart` 的
   `direction=='credit'` 或名含「坏账准备」/「减值准备」拆为原值码集与备抵码集
3. WHEN 需要在 `tb_balance` 查询某标准码 THEN 系统 SHALL 先经 `account_mapping`
   反解为该项目原始码集，再以原始码前缀查询，并只聚合**叶子**科目
4. WHEN 解析失败 / `report_config` 无该行 THEN 系统 SHALL fail-open 回退到显式 fallback
   且不阻断 render
5. WHEN 取数完成 THEN render SHALL 输出 `tb_source_codes`（含 `resolved_from`）供前端溯源展示，
   且该输出 SHALL 有前端消费方（不得是 dead output）
6. WHEN 灰度开关 `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 为 False THEN 各 render 输出
   SHALL 与本 spec 改动前逐字节等价

### Requirement 2: D6 取数科目纠正（1402 在途物资 → 1141 合同资产）

**User Story:** 作为审计助理，我希望 D6 合同资产审定表的试算平衡表数取的是合同资产，
而不是存货类的在途物资。

#### Acceptance Criteria

1. WHEN D6 Tier A 预设求值 THEN 其 `expression` SHALL 引用 `1141`（合同资产），
   SHALL NOT 引用 `1402`
2. WHEN D6 render 解析取数科目 THEN SHALL 以 `BS-011` 为 `row_code`、`['1141']` 为 fallback
3. WHEN 预设 description 说明取数口径 THEN SHALL 写明依据（`report_config` BS-011 四准则一致）
4. WHEN 守卫测试运行 THEN SHALL 断言 D 类全部预设的科目码 ∈ `account_chart`
   （`source='standard'`），并**反向自检**（构造一个不存在的码必须被判红）

### Requirement 3: D2 Tier A TB 核对行改净额口径

**User Story:** 作为审计助理，我希望 D2-1 审定表的「试算平衡表数」与被比较的审定合计同口径，
这样差异栏显示的是真实差异而不是恒等于坏账准备的假差异。

#### Acceptance Criteria

1. WHEN D2 Tier A 预设求值 THEN `expression` SHALL 为
   `TB('1122','期末余额') - TB('1231-02','期末余额')`（净额）
2. WHEN D2 render 提供 seed 回退标量 THEN 该标量 SHALL 与 Tier A 预设**同口径**（净额），
   原值 SHALL 保留在独立键供取数溯源
3. WHEN 项目无备抵科目数据 THEN 净额转换 SHALL 空操作（净额恒等于原值），
   保持灰度开/关逐字节等价
4. WHEN 审定表渲染 TB 核对区块 THEN SHALL 展示取数溯源（原值 − 备抵 = 净额）
5. WHEN 守卫测试运行 THEN SHALL 断言预设与回退标量同口径（防日后单侧改回原值）

### Requirement 4: D5 取数口径诚实化（宁缺勿造 + 显式报告）

**User Story:** 作为现场经理，我希望公式管理面板里 D5 的预设不指向一个不存在的科目，
而是明确告诉我这个报表项目无法从四表库干净取数。

#### Acceptance Criteria

1. WHEN `1124` 在 `account_chart` 中不存在 THEN D5 的 Tier A 预设 SHALL NOT 静默保留该码
2. WHEN D5 无法从四表库干净取数 THEN 系统 SHALL 或（a）改用可实证的科目映射、
   或（b）移除该预设并在溯源登记中写明原因，SHALL NOT 保留恒空的取数
3. WHEN 作出（b）选择 THEN `_TIER_B_PROVENANCE['D5']` SHALL 记录「无法干净取数」的依据
4. WHEN 守卫测试运行 THEN SHALL 锁死该决策（防日后有人凭「常识」把 1124 加回来）

### Requirement 5: D2 附注模板结构对齐源模板

**User Story:** 作为业务合伙人，我希望新建项目生成的附注 五、5 / 八、5 表格结构、
两级表头与列头就是对的，而不是等到底稿推送后才对。

#### Acceptance Criteria

1. WHEN 复核附注 五、5（17 表）/ 八、5（13 表）THEN 差异清单 SHALL 逐表记录（无差异亦记录），
   列头字面以校验预设为裁决者、表结构以源 xlsx 披露 sheet 为裁决者
2. WHEN 修订模板 THEN SHALL 由幂等脚本 `fix_note_d2_ar_structure.py` 完成
   （`--dry-run` / `--check`）并 `--check` 归零
3. WHEN 表为源模板单行表头 THEN 其 `columns` SHALL 显式 `flat`；
   WHEN 为同表并列双期 THEN SHALL 用 `group` 承载父表头
4. WHEN 模板 `rows` 含占位说明（「可无限量添加行」/「……」）或 `row_type=header_label`
   THEN SHALL 删除，语义移入 `guidance`
5. WHEN `guidance` 写入 THEN SHALL 为纯文本（不得含 `**` markdown，防与平台级
   `fix_note_bold_markers.py` 互相打架）
6. WHEN 同步载荷的子表名 / 列键与模板不一致 THEN 契约测试 SHALL 失败

### Requirement 6: 披露表与源模板的结构/口径复核（D2/D3/D5/D6/D7）

**User Story:** 作为质量控制复核合伙人，我希望披露表的列结构、动态插行区与账龄段
与源模板一致，附注拿到的是同构数据。

#### Acceptance Criteria

1. WHEN 复核各循环两版披露 Tab THEN SHALL 以源 xlsx 披露 sheet 为裁决者产出差异清单
2. WHEN 披露页小节标题与源模板小节标题不一致 THEN SHALL 按源模板逐字修正，
   且同一页内小节编号 SHALL NOT 重复
3. WHEN 披露表存在按账龄分档的行集 THEN 其档位 SHALL 由项目账龄枚举
   （3 年段 / 5 年段 / 自定义）驱动，SHALL NOT 硬编码档位
4. WHEN 项目账龄口径与既有行名不一致 THEN SHALL 以只读提示列出，SHALL NOT 自动删除用户数据
5. WHEN 披露表存在动态插行区 THEN 新增行 SHALL 与附注侧同构（表名 / 列键一致）

### Requirement 7: 公式管理预设与溯源登记修订

**User Story:** 作为现场经理，我希望公式管理面板里 D 类各循环的预设指向真实存在的
sheet 与科目，这样审计师看到的取数说明是可信的。

#### Acceptance Criteria

1. WHEN `prefill_formula_mapping.json` 登记 D 类循环的 sheet 名 THEN 其值 SHALL 与源模板
   真实 sheet 名逐字一致
2. WHEN 登记 `TB` / `TB_AUX` 公式 THEN 其科目码 SHALL ∈ `account_chart`
   且维度名 SHALL ∈ `tb_aux_balance.aux_type` 实际存在的值
3. WHEN 审定表需要底稿间连接取数说明 THEN SHALL 补 `WP()` 条目；
   明细表侧 SHALL NOT 出现 `WP()`（防循环）
4. WHEN 溯源登记（`_TIER_B_PROVENANCE`）描述取数来源 THEN 描述 SHALL 与实际实现一致
   （不得留「不从四表库填」这类已过时的说明）

### Requirement 8: 守卫与实测

**User Story:** 作为质量控制复核合伙人，我希望每个断点都有守卫，避免再次静默失效。

#### Acceptance Criteria

1. WHEN 任一 D 类预设引用的科目码不在 `account_chart` THEN 守卫测试 SHALL 失败
2. WHEN 任一循环的 Tier A 预设与 render 回退标量口径不一致 THEN 守卫测试 SHALL 失败
3. WHEN 附注模板表名与源 xlsx 小节标题不一致 THEN 守卫测试 SHALL 失败
   （直读 xlsx 交叉比对，含反向自检）
4. WHEN 本 spec 交付 THEN 后端 `backend/tests/d_cycle_extraction/` 与各循环相关测试、
   前端 D 类相关测试 SHALL 全绿（既有基线失败除外）
5. WHEN 本 spec 交付 THEN SHALL 以真实项目在浏览器实测每个改动循环：
   四表入库 → 审定表/明细表有数 → 披露表有数 → 推送后附注落库正确，测试数据用后复原

## Glossary

| 术语 | 含义 |
|------|------|
| 原始码 | 客户科目表编码，存 `tb_balance.account_code`（如 `1122.01`、`1231.02`） |
| 标准码 | 平台标准科目编码，存 `trial_balance.standard_account_code`（如 `1122`、`1231-02`） |
| 备抵科目 | 抵减资产账面余额的贷方科目（D2 即坏账准备 `1231-02`） |
| 净额口径 | 原值 − 备抵；审定表「三、xx净值」与报表行列示口径 |
| Tier A / Tier B | Tier A = 可编辑单条提取公式（`trial_balance` 审定口径）；Tier B = 复杂归集预填（`tb_balance`/`tb_aux_balance`，未审口径） |
| 账龄枚举 | 项目级账龄配置（3 年段 / 5 年段 / 自定义），单一真源 `useAgingConfig` + `disclosureAgingLabels` |
