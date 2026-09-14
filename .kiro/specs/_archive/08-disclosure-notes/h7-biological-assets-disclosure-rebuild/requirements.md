# Requirements Document

## Introduction

H7 生产性生物资产（1621，上市 §五、24 / 国企 §八、24）的两个披露 Tab 是 H 循环**唯一从未
建立同步链路**的循环 —— 既没有 `h7NoteSectionMap.ts`，也没有 `h7DisclosureSyncPayload.ts`，
两个组件的注释里明确写着「暂无同步链路，需按 G6 范式结构对齐重建」。`disclosure-sync-path-buildout`
批 2 曾一度接线后**主动撤回**，因为组件数据模型与源模板结构差距过大，强推等于自造披露内容。

源模板权威 = `backend/wp_templates/H/H7 生产性生物资产.xlsx`，实证结构：

**上市 `附注披露信息（上市公司）`** —— 两张**列转置 + 两级表头**表，openpyxl 合并区实证
（表1 `A9:A10` / `B9:C9` / `D9:E9` / `F9:G9` / `H9:I9` / `J9:J10`；表2 同构于 R51:R52）：

- 列 = 项目（rowspan 2）+ 4 个产业（种植业 / 畜牧养殖业 / 林业 / 水产业，每个下辖
  `类别` + `……` 两个子列）+ 合计（rowspan 2）
- 表1「（1）以成本计量」R11–R44 共 **34 行四层**：账面原值 / 累计折旧 / 减值准备 / 账面价值，
  各层 期初余额 + 本期增加金额{分项} + 本期减少金额{分项 + `……`} + 期末余额
- 表2「（2）以公允价值计量」R53–R64 共 **11 行**：期初余额 / 本期变动{加项 4 + 减项 2 +
  公允价值变动 + `……`} / 期末余额

**国企 `附注披露信息（国有企业）`**（注意是「国有企业」，与 H9/H10 的「国企」不同）——
两张 5 列单级表：项目 / 期初账面价值 / 本期增加额 / 本期减少额 / 期末账面价值，
行 = 4 个产业各 1 行 + 每产业「其中：N．」可扩类别行 + 合计。

现状欠账：

1. **两个披露 Tab 只有单行 `movementRows`**（原值 / 累计折旧 / 减值准备 / 账面价值），
   由 H7-1 审定表 EventBus 推来，**无产业维度、无类别维度、无变动分项** → 无法映射源模板。
2. **完全无同步链路**：无章节映射、无载荷、无 `syncToDisclosureNotes`、无自动同步。
3. 模板侧：上市第 2 张表名是表头首格泄漏 `项  目`（应为「（2）以公允价值计量」）；两版共 4 表
   `columns=0` + 无 `guidance`；上市两表各残留 1 个 `row_type=header_label` 假行；
   国企两表各有 4 个 `……` 纯占位行（可扩类别的「加更多」标记，永远收不到数据）。
4. 国企 `text_sections` 漏源模板 R39「注：应披露公允价值确认依据。」，R40 丢了「（3）」前缀。
5. 两个 Tab 的金额用自造 `toLocaleString`，未走平台 `fmtAmount`；文本域无 AI 辅助。

## Requirements

### Requirement 1: 上市披露表按源模板重建（列转置 + 两级表头）

**User Story:** 作为审计助理，我要在 H7 上市披露表里按产业和类别录入生产性生物资产的四层变动明细，
结构与源模板一致，能推送到附注。

#### Acceptance Criteria

1. WHEN 渲染上市「以成本计量」表 THEN 行 SHALL 为源模板 R11–R44 的 34 行四层结构
2. WHEN 渲染上市「以公允价值计量」表 THEN 行 SHALL 为源模板 R53–R64 的 11 行结构
3. WHEN 构造列 THEN SHALL 为 项目 + 各产业下的类别列（`group` = 产业名）+ 合计，
   且 项目列与合计列 SHALL NOT 带 `group`（源模板 rowspan=2）
4. WHEN 未添加类别 THEN 每个产业 SHALL 有 1 个默认类别列，叶子列名 SHALL 为源模板字面 `类别`
5. WHEN 用户为某产业增删类别 THEN 列 SHALL 随之增删，且列 `key` SHALL 稳定（删中间项不得错位）
6. WHEN 源模板 `……` 作**列头** THEN SHALL NOT 出现在列定义中（永远收不到数据）
7. WHEN 源模板 `……` 作**行** THEN SHALL 保留为可扩明细行并参与所属小计
8. WHEN 计算派生行 THEN 期末余额 SHALL = 期初 + 本期增加 − 本期减少；
   本期增加/减少 SHALL = 其分项之和；期末（期初）账面价值 SHALL = 原值 − 累计折旧 − 减值准备；
   公允价值表 本期变动 SHALL = 加项之和 − 减项之和 + 公允价值变动 + 其他变动；
   期末余额 SHALL = 期初余额 + 本期变动；合计列 SHALL = 各类别列之和

### Requirement 2: 国企披露表按源模板重建（产业 + 可扩类别行）

**User Story:** 作为审计助理，我要在 H7 国企披露表里按产业列示期初/增加/减少/期末账面价值，
并能为每个产业添加具体类别明细行。

#### Acceptance Criteria

1. WHEN 渲染国企两张表 THEN 列 SHALL 为 项目 / 期初账面价值 / 本期增加额 / 本期减少额 /
   期末账面价值，且单级表头 SHALL 显式 `flat`
2. WHEN 渲染行 THEN SHALL 为 4 个产业行（一、种植业 … 四、水产业）+ 每产业下的类别行 + 合计
3. WHEN 某产业有类别行 THEN 该产业行金额 SHALL = 其类别行之和（只读派生）
4. WHEN 某产业无类别行 THEN 该产业行 SHALL 可直接录入
5. WHEN 计算 THEN 期末账面价值 SHALL = 期初账面价值 + 本期增加额 − 本期减少额；
   合计行 SHALL = 4 个产业行之和
6. WHEN 新增类别行 THEN SHALL 先弹窗要求输入类别名称再创建（平台底稿交互铁律）

### Requirement 3: 建立同步链路

**User Story:** 作为项目经理，H7 披露表的数据要能进附注，且不用手动点按钮也会跟随。

#### Acceptance Criteria

1. WHEN 构造载荷 THEN `section_id` SHALL 逐字等于模板 `section_number`（上市 `五、24` / 国企 `八、24`）
2. WHEN 构造载荷 THEN `sheet_name` SHALL 逐字等于源 xlsx tab 名
   （上市 `附注披露信息（上市公司）` / 国企 **`附注披露信息（国有企业）`**）
3. WHEN 构造载荷 THEN 推送的每个表名 SHALL 存在于模板 `tables[].name`（无孤儿子表）
4. WHEN 变体不适用 THEN SHALL 不产生载荷（`isH7DisclosureApplicable` 门控）
5. WHEN 数据变更 THEN SHALL 触发防抖自动同步，且同步函数体内 SHALL NOT 调 `scheduleAutoSync`（禁自调度）
6. WHEN 组件被宿主使用 THEN SHALL 传入 `projectId`（漏传等于同步永久静默失败）
7. WHEN 两个 Tab 从 `MISSING_SYNC_PATH` 移出 THEN 该清单 SHALL 相应变短

### Requirement 4: 模板结构对齐

**User Story:** 作为质量控制复核合伙人，附注模板的列元数据与编制提示要与源模板一致。

#### Acceptance Criteria

1. WHEN 上市第 2 张表名为表头首格泄漏 `项  目` THEN SHALL 正名为「（2）以公允价值计量」，
   且旧名 SHALL 进 `_removed_table_keys`
2. WHEN 校验 4 张表 THEN `columns` SHALL 非空、`columns[].label` 序列 SHALL 等于 `headers`、
   金额列 SHALL `format=amount`
3. WHEN 表头为两级（上市 2 表）THEN SHALL 用 `group` 且 SHALL NOT 标 `flat`；
   单级（国企 2 表）SHALL 显式 `flat`
4. WHEN 模板残留 `row_type=header_label` 假行或 `……` 纯占位行 THEN SHALL 删除
5. WHEN 补 `guidance` THEN 内容 SHALL 只取源模板红字 / 15 号文条款 / 以「勾稽：」标注的工具提示
6. WHEN 国企 `text_sections` 缺源模板 R39「注：应披露公允价值确认依据。」THEN SHALL 补齐；
   R40 SHALL 恢复「（3）」前缀
7. WHEN `text_sections` 含裸表名 THEN SHALL 加 `#### ` 前缀（否则被当披露正文渲染）

### Requirement 5: `_note_texts` 与平台 UI 铁律

**User Story:** 作为项目经理，附注正文不能出现英文键，底稿金额格式要与全平台一致。

#### Acceptance Criteria

1. WHEN 载荷产生 `_note_texts` 条目 THEN 每条 SHALL 带非空中文 `title`
2. WHEN 文本为空白 THEN SHALL 不产生该条目；全空时 SHALL 无 `_note_texts` 键
3. WHEN `_note_texts` 存在 THEN SHALL 位于 `sub_table_data` 内
4. WHEN 显示只读金额 THEN SHALL 走 `fmtAmount()`（禁自造 `toLocaleString`）
5. WHEN 录入金额 THEN SHALL 用 `WpAmountInput`（禁 `el-input-number :formatter`）
6. WHEN 文本域需要辅助 THEN SHALL 接 `/ai/generate-text`，prompt SHALL 写明源模板口径与「不得虚构」

### Requirement 6: 双侧守卫与 CI

**User Story:** 作为质量控制复核合伙人，重建结果必须被自动化守卫锁死。

#### Acceptance Criteria

1. WHEN 运行后端守卫 THEN SHALL 以 openpyxl 直读源 xlsx 交叉比对行集、两级表头与合并区，
   并含反向自检
2. WHEN 运行前端契约 THEN SHALL 断言载荷表名/章节号/sheet 名逐字命中、列 key ≡ 模板列 key、
   行键 ⊆ 列键、两级表头 `group` 正确、派生公式正确、`_note_texts` 规范、无自调度
3. WHEN 提交 THEN CI SHALL 有 `note-h7-structure` 与 `note-h7-frontend` 两个 job
4. WHEN 脚本连续运行两次 THEN 第二次 SHALL 为空操作（幂等）
5. WHEN 实测 THEN SHALL 在真实项目上验证落库结构、派生金额与 `text_content` 中文小标题，
   并按快照复原数据
