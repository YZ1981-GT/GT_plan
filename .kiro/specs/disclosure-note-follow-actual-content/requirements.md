# Requirements Document

## Introduction

附注模块（`disclosure_notes`）当前是**生成时的静态快照**：底稿改了内容必须人工点「同步到附注」附注才更新；附注模板（`note_template_*.json`）升级后既有项目永远看不到新增表；早期持久化的 `table_data.rows` / `table_data._tables` 与现行真源 `table_data.sub_table_data` 并存，消费方在 `sub_table_data` 为空时回退到旧快照，界面显示的是过期结构。

2026-07-29 对 `note_section IN ('五、9','八、10')` 的 6 条真实记录取证：

| 项目 | 章节 | `sub_table_data` 表数 | 残留 `rows` | 残留 `_tables` |
|------|------|------|------|------|
| 重药控股安徽_2025 | 五、9 | 9 | 是 | 否 |
| 重庆和平药房_2025 | 五、9 | **0** | 是 | 否 |
| 重庆和平药房_2025 | 八、10 | **0** | 是 | **是** |
| 宜宾医药临港店_2025 | 八、10 | **0** | 是 | **是** |
| 陕西华氏医药_2025 | 八、10 | **0** | 是 | **是** |
| 首汽租车_2025 | 八、10 | **0** | 是 | **是** |

只有被人工点过同步的 1 个项目有内容，其余 5 个项目的存货附注一张表都没有；模板已含 11 张表（上市）/ 3 张表（国企），这 5 个项目界面上仍是旧的 3 张表快照，且带着已从模板删除的 `header_label` 假数据行。

本 spec 的目标是让附注**跟随底稿实际内容**：底稿保存即自动同步、模板升级可回流既有项目、单一真源、无业务的表按实际情况折叠或标注而非留空表。

范围为平台级（全部披露章节，不限于 F2 存货）。F2 存货作为首个验证载体，其结构对齐工作已在 `f2-inventory-disclosure-template-alignment` 完成。

## Glossary

| 术语 | 含义 |
|------|------|
| 附注模块 | `disclosure_notes` 表 + `DisclosureEditor.vue`，对外披露的财务报表附注 |
| `sub_table_data` | `table_data.sub_table_data`，形态 `{表名: [业务键行]}`，**当前唯一权威存储** |
| `_sub_table_columns` | `table_data._sub_table_columns`，形态 `{表名: [ColumnDef]}`，列头元数据 |
| 投影 | `note_sub_table_projector` 把 `sub_table_data` + 列头**读时**转成 `_tables[]`，不持久化 |
| legacy 快照 | 历史持久化在 `table_data` 顶层的 `rows` / `_tables`，早于 `sub_table_data` 契约 |
| seed 路径 | 新建项目或重新生成附注时按 `note_template_*.json` 生成初始结构 |
| 同步路径 | 底稿点「同步到附注」→ `wp_disclosure_sync_service.sync_from_workpaper` |
| 模板回流 | 模板新增/改名表后，把差异补进既有项目的附注结构 |
| 空表语义 | 某表在本期无业务（如非房企的「开发成本」），应折叠或标注「本期无此情形」而非留空 |
| `WORKPAPER_SAVED` | 底稿保存事件（EventBus），已驱动一致性检查与 C/F/D~N 循环联动 |
| `is_stale` | `disclosure_notes.is_stale`，标记该章节数据可能过期 |

## Requirements

### Requirement 1: 底稿保存自动同步到附注

**User Story:** 作为审计助理，我在底稿披露表里填完数据保存后，希望附注模块立刻就是最新内容，不需要记得额外点一次「同步到附注」，否则复核人看到的是旧数据。

#### Acceptance Criteria

1. WHEN 披露类底稿 sheet 保存成功 THEN 系统 SHALL 通过 `WORKPAPER_SAVED` 事件自动触发该 sheet 对应章节的同步，无需人工点击
2. WHEN 自动同步执行 THEN 系统 SHALL 复用现有 `sync_from_workpaper` 的全部守卫（manual_override 保护、空载荷 no-op、`_removed_table_keys` 清理），不得绕过
3. IF 目标章节 `is_local_override = true` 或载荷命中 manual_override 守卫 THEN 系统 SHALL 跳过写入并记录审计日志，同步结果标记为 skipped
4. WHEN 自动同步失败（异常/超时）THEN 系统 SHALL fail-soft：不阻断底稿保存，记 warning 日志，并把该章节 `is_stale` 置 true
5. WHEN 自动同步成功 THEN 系统 SHALL 更新 `last_sync_at` / `last_sync_source` / `last_sync_wp_id`，并把 `is_stale` 置 false
6. WHERE 底稿页仍保留手动「同步到附注」按钮 THE 系统 SHALL 使手动与自动走同一服务函数，行为完全一致
7. WHEN 同一底稿在短时间内连续保存 THEN 系统 SHALL 对同步做去抖或幂等处理，避免重复写库放大

### Requirement 2: 模板升级回流既有项目

> **补充取证（2026-07-29，F2 存货实测）**：给 `note_template_listed.json` 的 14 张表补齐
> `guidance` 与 `flat` 后，拉真实后端 `GET /api/disclosure-notes/{p}/{y}/五、9`（投影后）：
> 全部 9 张表 `guidance` 仍为 **0 字**，「存货跌价准备及合同履约成本减值准备（续）」的
> `_column_groups` 仍为 **None**。根因：`guidance` 只经 `disclosure_engine._carry_seed_table_guidance`
> 在 seed 路径生效；`_sub_table_columns` 是上次同步写入的旧值。**改模板与改前端载荷代码，
> 对既有项目一律不生效**，这正是本 Requirement 要解决的问题。


**User Story:** 作为质量控制复核合伙人，模板按最新监管要求补了披露表之后，我希望既有在做项目的附注也能补上这些表，而不是只有新建项目才有，否则同一年度不同项目的披露口径不一致。

#### Acceptance Criteria

1. WHEN 用户对某章节触发「按模板补齐结构」THEN 系统 SHALL 比对 `note_template_*.json` 与该章节现有表集合，列出缺失表、改名表、列结构差异
2. WHEN 用户确认补齐 THEN 系统 SHALL 只新增缺失表与修订列结构，**不得**覆盖已有表的行数据
3. IF 模板表名与既有表名构成改名关系（模板 `_renamed_from` 或结构同构）THEN 系统 SHALL 迁移而非新建，避免产生孤儿空表
4. WHEN 补齐操作执行 THEN 系统 SHALL 在 `template_lineage` 记录本次补齐的模板版本与差异摘要，供追溯
5. WHERE 存在批量场景 THE 系统 SHALL 支持按项目或按章节批量预览与执行，且预览与执行使用同一差异计算函数
6. IF 章节 `is_local_override = true` THEN 系统 SHALL 默认跳过并在结果中说明原因，仅在用户显式勾选时才处理

### Requirement 3: 收敛到单一真源，清理 legacy 快照

> **🔴 前置依赖（2026-07-29 全库 dry-run 实测）**：572 个 legacy 章节共 982 张待迁移表中，
> **950 张（97%）在模板里也没有 `columns`**。迁移后 `_sub_table_columns` 无从填充，投影器
> 会走降级路径（`_needs_columns: true`，只显示行名、values 恒空），**比现状更糟**
> （legacy 快照至少还有 `headers`）。故本 Requirement 的写入动作（Task 8）**必须等
> `disclosure-columns-coverage-rollout` 把 `columns` 补齐后才能执行**。
>
> 另有脏数据实况：58 个章节存在重名表（按 name 建键会互相覆盖丢表）、79 个章节的表名是
> 表头首格（如「项  目」）而非业务表名 → 迁移需靠模板补表名，其中 150 个只能按序对齐，
> 须人工抽样确认。


**User Story:** 作为开发者，我需要附注结构只有一个真源，否则同一章节在模块页、Word 导出、批量导出三处显示不同结构，排查成本极高。

#### Acceptance Criteria

1. WHEN 任一消费方读取附注表格结构 THEN 系统 SHALL 只经 `note_sub_table_projector` 从 `sub_table_data` + `_sub_table_columns` 投影，不得直接读 `table_data.rows` 或 `table_data._tables`
2. WHEN 迁移脚本执行 THEN 系统 SHALL 把仅有 legacy 快照（`sub_table_data` 为空且存在 `rows`/`_tables`）的章节转换为 `sub_table_data` 形态，转换前后表数与行数一致
3. IF legacy 快照含 `row_type == "header_label"` 的假数据行 THEN 迁移 SHALL 删除该行并把其语义并入列头元数据
4. WHEN 迁移完成 THEN 系统 SHALL 从 `table_data` 移除 `rows` / `_tables` 顶层键，且保留一次性备份供回滚
5. WHERE 迁移是破坏性操作 THE 脚本 SHALL 提供 `--dry-run` 与 `--check`，默认不写库，并要求显式确认
6. WHEN 迁移后再次读取 THEN 各消费方（模块页 / Word 导出 / 批量导出）SHALL 得到完全一致的表集合与列结构

### Requirement 4: 空表按实际情况呈现

**User Story:** 作为现场经理，非房地产企业的附注里不该出现三张空白的「开发成本」「开发产品」「周转房」，我希望没有业务的表被折叠或明确标注「本期无此情形」，否则底稿看起来像没做完。

#### Acceptance Criteria

1. WHEN 某表所有数据行的数值列全为空或零且无文字内容 THEN 系统 SHALL 判定该表为空表
2. WHEN 附注模块渲染空表 THEN 系统 SHALL 默认折叠该 TAB 并标注「本期无此情形」，用户可展开填写
3. WHEN Word 导出遇到空表 THEN 系统 SHALL 按导出选项决定「省略该表」或「保留表并标注本期无」，默认省略且在导出摘要中列出被省略的表
4. IF 表在源模版中标注了适用条件（如「由房地产开发企业填列」）THEN 系统 SHALL 在 guidance 中体现该条件，并据此判断空表是否需提示补充
5. WHERE 存在互斥披露方式（源模版用「或：」表达，如按品类组合 vs 按库龄组合计提跌价准备）THE 系统 SHALL 只要求填写其中一组，另一组为空不触发未完成提示
6. WHEN 用户主动展开并填写空表 THEN 系统 SHALL 立即取消折叠与「本期无」标注

### Requirement 5: 过期状态可见且可一键修复

**User Story:** 作为审计助理，附注和底稿不一致时我希望界面直接告诉我哪里不一致、点一下就能同步，而不是自己去猜。

#### Acceptance Criteria

1. WHEN 章节 `is_stale = true` THEN 附注模块 SHALL 显示过期横幅，说明过期原因（`stale_source`）与上次同步时间
2. WHEN 用户点击横幅上的「立即同步」THEN 系统 SHALL 定位来源底稿并执行同步，成功后清除横幅
3. WHEN 底稿结构与附注结构存在差异（表数不同 / 表名不匹配）THEN 系统 SHALL 在章节详情中列出差异明细，而非静默
4. IF 来源底稿不存在或已删除 THEN 系统 SHALL 显示「来源底稿缺失」并禁用同步按钮，不得抛未捕获异常
5. WHEN 同步或补齐操作完成 THEN 系统 SHALL 给出结果摘要（新增表数 / 更新表数 / 跳过原因），不使用无信息量的成功提示

### Requirement 6: 零回归

**User Story:** 作为质量控制复核合伙人，这轮改造触及全部披露章节，我要求既有已同步内容和手工覆盖一个都不能丢。

#### Acceptance Criteria

1. WHEN 改造完成 THEN 既有 `sub_table_data` 非空章节的表集合、行数、行标签、列结构 SHALL 与改造前完全一致
2. WHEN 章节存在手工覆盖（`is_local_override` 或 manual_override 标记）THEN 自动同步与模板回流 SHALL 均不覆盖其内容
3. WHEN 全量测试执行 THEN 现有附注相关后端与前端测试 SHALL 全绿，不允许放宽既有断言
4. WHERE 涉及 DB 迁移 THE 迁移 SHALL 幂等（`IF NOT EXISTS`）且可重复执行
5. WHEN 灰度开关关闭 THEN 系统行为 SHALL 与改造前一致，自动同步不生效
