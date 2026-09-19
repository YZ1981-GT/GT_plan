# Requirements Document

## Introduction

E0 货币资金/借款函证有其他枢纽都没有的一层：**发函前清单**（函证对象来源台账），共四张：

- `货币资金发函记录表E0-3`：所属科目 / 开户银行 / **是否函证** / 账户名称 / 银行账号 / 币种 / 利率 / 账户类型 / 账户余额（原币）/ 是否资金归集 / 起止日期 / **是否存在冻结担保或使用限制** / 备注
- `借款发函记录表E0-4`：借款人 / 借款账号 / 余额 / 借款日期 / 到期日 / 利率 / 抵质押品担保人 / 借款类型 / 期末应付利息
- `应付银行承兑汇票发函记录表E0-5`
- `理财产品发函记录表E0-6`

平台现状：这四张 sheet 走通用 `d-form-table`，而其列定义来自 `backend/data/ledger_adapters/wp_render_schema/generated/E0.yaml`——**该文件自述「此文件为草稿，关键字段需人工审核」**，字段名是 `col_a` / `col_d`，label 被抓成「编制日期：」「3」→ 这四张 sheet 目前实际是**占位表**，审计师填不了源模板要求的列。

**前置依赖**：E0 的 `confirmation-*` 重建（E0-1 → `confirmation-summary` 等）与「清单 → E0-1 带入」能力归 `confirmation-hub-workbench-tabs`（Wave 2，用户已拍板 B 方案）。本 spec 只做**这四张清单 sheet 自身的列结构正确性**，使带入有可靠上游。

**范围边界**：不改 `confirmation-summary` 与 confirmation-v1 数据模型；不改 E0 的 componentType 归属决策（归 `confirmation-hub-workbench-tabs`）；不改后端 render 策略调度；不新增源模板没有的列；不做 E0 其他 sheet（E0-1/E0-2/E0-7/E0-8/F1-12）。

## Glossary

| 术语 | 含义 |
|------|------|
| Send_List_Sheet | E0 发函前清单 sheet（E0-3 货币资金 / E0-4 借款 / E0-5 应付银行承兑汇票 / E0-6 理财产品） |
| Schema_Draft | `wp_render_schema/generated/E0.yaml`（自述草稿，字段名 `col_*`、label 抓错） |
| Confirm_Flag | 清单行的「是否函证」列，决定该账户/借款是否进入 E0-1 |
| Restriction_Flag | E0-3 的「是否存在冻结担保或使用限制」列（受限货币资金披露的关键来源） |
| Pull_To_Summary | 「清单 → E0-1 带入」能力（本 spec 只保证上游列可用，带入实现归 `confirmation-hub-workbench-tabs`） |
| Four_Table_Source | 平台四表库（trial_balance / tb_balance / tb_ledger / tb_aux_balance） |

## Requirements

### Requirement 1: 四张 Send_List_Sheet 按源模板落列

**User Story:** 作为审计助理，我要在货币资金发函记录表里逐账户填开户银行、账号、币种、余额、是否函证，而不是面对 `col_a` 这样的占位表。

#### Acceptance Criteria

1. WHEN 渲染任一 Send_List_Sheet THEN 系统 SHALL 提供该 sheet 源模板的全部列，列名与顺序 SHALL 与源模板一致
2. WHEN 落列 THEN 系统 SHALL NOT 使用 Schema_Draft 中 `col_*` 形式的占位字段名与错误 label
3. WHERE 某列为枚举语义（是否函证 / 账户类型 / 是否资金归集 / 是否存在冻结担保或使用限制 / 借款类型）THE 系统 SHALL 以点选录入而非自由文本
4. WHERE 某列为日期（起止日期 / 借款日期 / 到期日）THE 系统 SHALL 以日期控件录入
5. WHERE 某列为金额或利率 THE 系统 SHALL 按平台数值格式呈现（金额千分符两位小数、利率明确 scale）并右对齐
6. WHEN 落列方式选定 THEN 系统 SHALL 优先走「配置/schema 驱动」而非为四张表各写一套硬编码模板，除非有实测证明配置驱动无法承载

### Requirement 2: Schema_Draft 人工审定或被替代

**User Story:** 作为平台维护者，E0 的 schema 草稿是错的，要么审定它要么明确不再用它。

#### Acceptance Criteria

1. WHEN 本 spec 落地 THEN Schema_Draft 中 E0 相关 sheet 的字段定义 SHALL 或被人工审定为源模板真实列，或被显式标注为不再作为渲染真源
2. WHERE 采用人工审定 THE 系统 SHALL 保留该文件的自动生成入口不被破坏（后续再生成不得覆盖审定结果，或有明确的覆盖保护/重生成流程）
3. WHEN 审定完成 THEN 系统 SHALL 具备守卫：E0 相关 sheet 的渲染列与源模板清单（数据文件登记）一致，漂移即失败
4. WHERE 其他底稿也依赖同一 Schema_Draft 文件 THE 系统 SHALL NOT 因 E0 审定改变其他底稿的渲染列

### Requirement 3: Confirm_Flag 驱动 Pull_To_Summary 的上游可靠性

**User Story:** 作为审计助理，我在清单里勾了「是否函证 = 是」，就应该能一键把这些账户带进 E0-1，不用重抄。

#### Acceptance Criteria

1. WHEN Send_List_Sheet 的行有 Confirm_Flag THEN 该值 SHALL 持久化且刷新后回显
2. WHEN Pull_To_Summary 执行 THEN 系统 SHALL 能从清单读到：被询证单位名称（开户银行 / 借款人）、账号或产品名称、币种、余额、账户品种，作为 E0-1 行的来源字段
3. WHERE 清单缺少 Pull_To_Summary 所需的某字段 THE 系统 SHALL 在本 spec 内补齐该列（若源模板有）或明示该字段需在 E0-1 手工补（若源模板无）
4. WHEN 清单行被修改 THEN 系统 SHALL NOT 自动覆盖已带入 E0-1 且已被审计师编辑过的行（手工优先由 `confirmation-hub-workbench-tabs` 保证，本 spec 只保证清单侧数据可读）

### Requirement 4: Restriction_Flag 与披露链

**User Story:** 作为审计助理，我在货币资金清单里标了「存在冻结/担保/使用限制」的账户，这应该能支撑受限货币资金的披露。

#### Acceptance Criteria

1. WHEN E0-3 存在 Restriction_Flag 为「是」的行 THEN 系统 SHALL 使这些行可被识别汇总（清单内可筛选或有汇总提示）
2. WHERE 受限货币资金披露在 E1 底稿或附注侧有承载 THE 系统 SHALL 提供索引提示或跨底稿引用芯片，且 SHALL NOT 自动写入其他底稿
3. WHERE 源模板未定义受限金额列 THE 系统 SHALL NOT 新增金额列（仅保留标志与备注）

### Requirement 5: 四表取数（可选增强，宁缺勿造）

**User Story:** 作为审计助理，银行账户清单如果能从余额表按辅助维度带出来，就不用手工抄一遍。

#### Acceptance Criteria

1. WHERE Four_Table_Source 中存在可靠的账户级维度数据（如 tb_aux_balance 的开户行/账号维度）THE 系统 MAY 提供「从余额表带入清单」
2. WHEN 提供带入 THEN 系统 SHALL 仅在清单为空或按行去重的前提下写入，且 SHALL NOT 覆盖审计师已录行
3. WHERE Four_Table_Source 无账户级维度（只有科目级总额）THE 系统 SHALL NOT 臆造账户明细，且 SHALL 明示需手工录入
4. WHEN 带入落地 THEN 系统 SHALL 标注每行来源（取数 / 手工），使可追溯

### Requirement 6: 零回归

**User Story:** 作为平台维护者，E0 是最高频函证场景，改列不能让已录数据丢。

#### Acceptance Criteria

1. WHEN 本 spec 改动落地 THEN 既有 E0 底稿已录数据 SHALL 可回显或有明确迁移路径，SHALL NOT 静默丢弃
2. WHEN 本 spec 改动落地 THEN 其他底稿走 `d-form-table` 的渲染行为 SHALL 逐字不变
3. WHEN 本 spec 改动落地 THEN 既有函证域测试与 render schema 相关测试 SHALL 全部通过
4. WHERE 四张清单按 sheet 分批实施 THE 每张 SHALL 独立可发布且可单独回退

### Requirement 7: 属性化可测

**User Story:** 作为平台维护者，清单列要有守卫，避免 schema 再生成把审定结果冲掉。

#### Acceptance Criteria

1. WHEN 定义列集合 THEN 系统 SHALL 具备契约测试：四张 Send_List_Sheet 的渲染列与源模板清单一致
2. WHEN 定义 Confirm_Flag THEN 系统 SHALL 具备属性测试：仅 `是否函证 = 是` 的行进入 Pull_To_Summary 的候选集合，重复带入去重
3. WHEN 定义既有数据回显 THEN 系统 SHALL 具备 round-trip 属性测试
4. WHEN 定义 Requirement 2 THEN 系统 SHALL 具备守卫：Schema_Draft 若被重新生成且覆盖审定结果，测试 SHALL 失败
