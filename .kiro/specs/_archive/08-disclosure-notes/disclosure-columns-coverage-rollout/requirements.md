# Requirements Document

## Introduction

`f2-inventory-disclosure-template-alignment` 验证通过了一条完整的两级表头链路：

```
ColumnDef.group ──(后端 note_sub_table_projector._extract_column_groups)──> _column_groups
                          │
        ┌─────────────────┴──────────────────┐
        ▼                                    ▼
DisclosureEditor.activeTableColumns   note_word_exporter._build_two_level_header_rows
（嵌套 el-table-column 两级表头）        （fill_multi_header 两行表头）
```

但 `backend/scripts/check/check_disclosure_columns_coverage.py` 实测：90 个披露同步调用点中
**14 个仍未携带 `columns` 列头元数据**，其附注侧只能退化成「项目」单列或英文字段键：

| 循环 | 未覆盖 Tab |
|------|-----------|
| H4 | `H4TabDisclosureListed` |
| J1 | `J1TabDisclosureListed` / `J1TabDisclosureSoe` |
| K4 | `K4TabDisclosureSoe` |
| K5 | `K5TabDisclosureListed` / `K5TabDisclosureSoe` |
| K6 | `K6TabDisclosureListed` / `K6TabDisclosureSoe` |
| K7 | `K7TabDisclosureListed` / `K7TabDisclosureSoe` |
| L1 | `L1TabDisclosureListed` / `L1TabDisclosureSoe` |
| L3 | `L3TabDisclosureListed` / `L3TabDisclosureSoe` |

同时，**已覆盖的 76 个调用点里绝大多数把两级表头压平**成「期末账面余额」这类拼接
label，靠后端 `_infer_groups_from_headers` 的前缀推断反向猜父表头 —— 推断对单级表会
凭空造出父表头（实测 F2 房企 3 表被加了「本期」），对语义不规则的表则完全猜不出。

本 spec 把 F2 验证过的范式推广到全部披露 Tab：补齐缺失的 `columns`，并把压平 label
迁移为 `label` 子列名 + `group` 父表头，让附注与 Word 导出的表样直接由声明驱动。

## Glossary

| 术语 | 含义 |
|------|------|
| `ColumnDef` | `composables/disclosureColumnDefs.ts` 的列头元数据（`key`/`label`/`is_label`/`format`/`group`） |
| `group` | 分组父表头；相邻同 `group` 的列在渲染时合并为两级表头 |
| `_column_groups` | 后端产出的 `[{group, start, span}]`，前端与 Word 导出共同消费 |
| 压平 label | 把两级表头拼成单串（如「期末账面余额」）塞进 `label`，丢失层级语义 |
| 前缀推断 | `_infer_groups_from_headers` 从 headers 共享前缀反猜分组（≥4 列才触发） |
| 覆盖守卫 | `check_disclosure_columns_coverage.py`，扫前端同步调用点是否带 `columns` |
| 源模板 | `基础数据/致同通用审计程序及底稿模板（2025年修订）/…` 各循环披露 sheet |

## Requirements

### Requirement 1: 补齐 14 个未覆盖 Tab 的 `columns`

**User Story:** 作为编制附注的审计助理，我从 H4/J1/K4~K7/L1/L3 披露表同步过去后，希望附注里看到中文列头的完整表格，而不是只有「项目」一列或英文字段键。

#### Acceptance Criteria

1. WHEN 运行 `check_disclosure_columns_coverage.py` THEN 系统 SHALL 报告未覆盖数为 0（或全部登记 allowlist 并注明原因）
2. WHEN 为某 Tab 声明 `columns` THEN 每个 `label` SHALL 逐字取自该 Tab 既有 `el-table-column label` 或其源模板单元格，禁止用英文字段键或凭常识杜撰
3. WHEN 某子表存在标签列 THEN 该列 SHALL 标注 `is_label: true`，且为 `columns` 的首项
4. WHEN 某列为金额 / 比例 THEN 系统 SHALL 分别标注 `format: 'amount'` / `format: 'percent'`
5. WHEN `sub_table_data` 含某子表键 THEN `columns` SHALL 含同名键（一一对应，无遗漏、无多余）

### Requirement 2: 两级表头改为显式 `group` 声明

**User Story:** 作为复核人，我希望附注表头层级与源模板一致，不因平台猜测而多出或缺少父表头。

#### Acceptance Criteria

1. WHEN 源模板某表为两行表头 THEN 对应 `ColumnDef` SHALL 用 `label`=子列名 + `group`=父表头声明，禁止压平成拼接串
2. WHEN 源模板某表为单行表头 THEN 该表 `columns` SHALL 全部不带 `group`
3. WHEN 迁移某 Tab 的压平 label THEN 迁移后 `_extract_column_groups` 产出的 `_column_groups` SHALL 与源模板的合并区间一致（`start`/`span` 逐项核对）
4. WHEN 同一 `group` 下有多列 THEN 这些列在 `columns` 中 SHALL 相邻（`_extract_column_groups` 按相邻性归组）
5. WHEN 迁移完成 THEN 各 Tab 既有单测中对压平 label 的断言 SHALL 同步更新为 `{label, group}` 断言

### Requirement 3: 单级表显式抑制前缀推断

**User Story:** 作为复核人，源模板是单行表头的表（如房企开发成本/开发产品/周转房），我不希望附注里凭空多出「本期」这类父表头。

#### Acceptance Criteria

1. WHEN `ColumnDef` 标注 `flat: true` THEN `_extract_column_groups` SHALL 返回空分组，且调用方 SHALL 跳过 `_infer_groups_from_headers`
2. WHEN 某表未声明 `columns` THEN 系统 SHALL 保持现有前缀推断行为不变（向后兼容）
3. WHEN 某表声明了 `columns` 但既无 `group` 也无 `flat` THEN 系统 SHALL 保持现有前缀推断行为不变（避免存量 Tab 静默变样）
4. WHEN F2 房企 3 表（开发成本 / 开发产品 / 周转房）标注 `flat: true` THEN 附注渲染 SHALL 不再出现「本期」父表头

### Requirement 4: 恢复覆盖守卫的 CI 绿色

**⚠️ 实测前提（2026-07-29）**：`governance-checks.yml` 的 `disclosure-columns-coverage`
job **已经在跑 `--strict`**，而 `--strict` 对当前 14 个未覆盖项返回 exit 1
（`[FAIL] 14 个同步调用点缺少 columns 且未豁免`）→ **该 CI job 目前是红的**。
因此本 spec 不是"新增守卫"，而是**解除既有 CI 阻塞**，优先级相应提高。

**User Story:** 作为工程治理负责人，我希望 `disclosure-columns-coverage` 这条 CI 检查恢复绿色，并且此后新增披露 Tab 漏带 `columns` 时能立刻被拦住。

#### Acceptance Criteria

1. WHEN 14 个 Tab 全部补齐 `columns` THEN `check_disclosure_columns_coverage.py --strict` SHALL 返回 exit 0
2. WHEN CI 运行 `disclosure-columns-coverage` job THEN 该 job SHALL 通过
3. WHEN 某 Tab 确实无需 `columns` THEN 系统 SHALL 支持在 allowlist 中登记并要求填写原因，缺原因视为未登记
4. WHEN 此后新增未携带 `columns` 的同步调用点 THEN CI SHALL 阻断（既有 `--strict` 行为，保持不变）

### Requirement 5: 回归保护

**User Story:** 作为质量控制复核合伙人，我需要确认这轮跨 8 个循环的列头改造没有破坏既有披露同步与附注/Word 渲染。

#### Acceptance Criteria

1. WHEN 运行各循环披露相关前端单测 THEN 系统 SHALL 全部通过
2. WHEN 运行 `disclosureSyncUrlContract.spec.ts` 与 `disclosureColumnDefs.spec.ts` THEN 系统 SHALL 全部通过
3. WHEN 运行 `test_note_sub_table_projector.py` 与 `test_note_word_export_sub_table.py` THEN 系统 SHALL 全部通过
4. WHEN 抽样 2 个循环（1 上市 + 1 国企）做 Playwright 实测 THEN 附注侧 SHALL 正确渲染两级表头
5. WHEN 运行 `d2NoteSectionMap.spec.ts` / `d2DisclosureNote.spec.ts` THEN 账龄标签映射与孤儿表 diff 的契约断言 SHALL 全部通过
6. WHEN 组合分表重命名后重新同步 THEN Playwright/DB 抽验 SHALL 确认附注无残留空 TAB

### Requirement 6: 账龄档位标签统一为披露口径（方案 A）

**背景（2026-07-29 实测，来源 `d2-ar-disclosure-soe-alignment` §O1）**：底稿账龄行的
label 直接取自 `useAgingConfig` 的**项目账龄配置**，同步到附注后原样呈现，与附注模板/源模板字面不一致：

| 附注实际（项目配置） | 附注模板 / 源模板 |
|---|---|
| `1年以内` | 上市 `1年以内` ／ 国企 `1年以内（含1年）` |
| `1-2年` | `1至2年` |
| `2-3年` | `2至3年` |
| `3-4年` | `3至4年` |
| `4-5年` | `4至5年` |

全模板用词分布实证：`1至2年` 31 次 / `2至3年` 29 次 / `3年以上` 16 次 /
`1年以内（含1年）` 13 次 / `5年以上` 11 次；而 `1-2年`~`4-5年` 各 5 次
——**这 5 处正是配置口径经同步漏进模板的痕迹**，属需一并纠正的污染。

**用户决策：方案 A** —— 在**同步层**做映射，项目账龄配置继续只服务底稿内部
（底稿页仍显示 `1-2年`，审计师日常操作口径不变）。

**User Story:** 作为编制附注的审计助理，我希望附注里的账龄档位用准则/模板口径（`1至2年`），
而不是底稿内部配置的简写（`1-2年`），同时底稿页仍按我熟悉的配置口径显示。

#### Acceptance Criteria

1. WHEN 底稿把账龄行推送到附注 THEN 行 label SHALL 按账龄段 `key` 映射为披露口径标签，而非直接用配置 label
2. WHEN 账龄段 `key` 为预设段（`within1`/`y1to2`/`y2to3`/`y3to4`/`y4to5`/`over3`/`over5`）THEN 系统 SHALL 使用共享映射表的披露口径标签
3. WHEN 某循环首档口径与通用值不同（如国企 `1年以内（含1年）`）THEN 该循环的 `*NoteSectionMap` SHALL 通过 per-section 覆盖声明，而不是改共享映射表
4. IF 账龄段为**自定义段**（`key` 不在预设集合内）THEN 系统 SHALL 原样透传配置 label，禁止杜撰
5. WHEN 账龄表含结构行（`小计` / `减：坏账准备` / `合计`）THEN 推送 label SHALL 与附注模板字面一致（`小 计` / `减：坏账准备` / `合 计`）
6. WHEN 底稿页渲染账龄表 THEN 仍 SHALL 显示项目配置 label（映射只发生在同步载荷构建时）
7. WHEN 运行扫描守卫 THEN 系统 SHALL 列出仍直接推配置口径标签的同步调用点（本 spec 先 warn 不阻断，随各批次收敛）

### Requirement 7: 动态子表名的孤儿表清理

**背景（2026-07-29 实测，来源 `d2-ar-disclosure-soe-alignment` §O2）**：把组合分表
「应收中央企业客户」改名为「应收政府客户」后再同步，附注 `sub_table_data` 与
`_sub_table_columns` **同时残留两个 key** → 附注永久多一个空 TAB。

根因：同步按 key 浅合并（为支持 H4 只推自己那张表而不清空 H2 的明细），删除须显式上报
`_removed_table_keys`。平台机制齐全（`_drop_removed_tables`，且保证「本次推送的 key 绝不删」），但：
- 只有上市分支上报，国企分支未接；
- 上市侧用**静态**常量 `D2_LISTED_OBSOLETE_TABLE_KEYS`，而组合分表名是**动态**的（随审计师命名），静态列表覆盖不了。

**User Story:** 作为编制附注的审计助理，我在披露表里重命名或删除一个组合分表后，希望附注对应的 TAB 一起消失，而不是留一个空表在那里误导复核人。

#### Acceptance Criteria

1. WHEN 同步成功 THEN 底稿 SHALL 持久化「本次推送的数据子表名清单」（排除 `_` 元数据键）
2. WHEN 下一次构建同步载荷 THEN `_removed_table_keys` SHALL = 上次已同步表名 ∪ 该变体历史遗留静态键 − 本次推送表名
3. WHEN 某表名同时出现在「待删除」与「本次推送」THEN 系统 SHALL 不删（推送优先，既有 `_drop_removed_tables` 行为）
4. WHEN 首次启用（无历史持久化）THEN `_removed_table_keys` SHALL 仍包含该变体的历史遗留静态键，保证既有清理能力不退化
5. WHEN 组合分表被重命名 THEN 重新同步后附注 `sub_table_data` 与 `_sub_table_columns` SHALL 均只剩新表名
6. WHEN 组合分表被删除 THEN 重新同步后附注 SHALL 不再有该 TAB
7. WHEN 只读态 THEN 系统 SHALL 不写入持久化，也不产出 `_removed_table_keys`
8. WHERE 机制实现 THE 逻辑 SHALL 抽为跨循环可复用的纯函数，D2 为首个接入循环

**R7.5 基线播种（用户 2026-07-30 追加）**

上述差集基线来自底稿自己的持久化清单，因此**基线建立之前**就残留在附注里的孤儿表
（实测某项目 §八、5 残留 `组合计提项目：应收中央企业客户`）永远进不了差集、不会自愈。
底稿也无从判断附注里的历史 key 是自己推的还是别的底稿推的 —— 需要显式的**表名命名空间谓词**。

9. WHEN 首次同步（持久化清单为空）THEN 系统 SHALL 读一次附注该章节的现存表名，
   按该底稿的命名空间谓词过滤后作为差集基线
10. WHERE 命名空间谓词 THE 判定 SHALL 只认 ①该变体固定表名全集 ②该底稿动态表名前缀
    ③「已知表名 + 续表后缀」④该变体历史遗留静态旧名；**其余一律不认领**
    （同一附注章节可能被别的底稿推送，误判会删掉别人的数据 —— 宁漏不误杀）
11. WHERE 现存表名来源 THE 取值 SHALL 只取 `table_data.sub_table_data` 与
    `table_data._sub_table_columns` 的键（后端 `_drop_removed_tables` 只从这两处删；
    `_tables` 是读时投影/生成快照，removed 键删不动它，纳入只会虚报）
12. WHEN 持久化清单非空 THEN 播种 SHALL 幂等空操作（不覆盖、不额外请求）
13. WHEN 附注章节尚未生成或读取失败 THEN 系统 SHALL 跳过播种且**不阻断本次同步**
14. WHERE 取数职责 THE HTTP 请求 SHALL 留在组件层，composable 只接收 `table_data`（保持可单测）


### Requirement 8: 同步载荷 `sheet_name` 断言漂移统一清理

**背景（2026-07-29 实测，来源 `f1-prepayment-disclosure-template-alignment` §S7）**：
平台早期用**合成标识**（`F1-note-listed`）当同步载荷的 `sheet_name`，后来统一改为
**源 xlsx 真实中文 tab 名**（`附注披露信息(上市公司)`）—— 这是必要的，因为附注侧
`_last_sync_sheet` 要能被 `GtWpRenderer ?sheet=` 精确匹配，才能「打开同步底稿」反向跳转。

但**只改了实现，没改测试**，留下一批预存在失败。F1 那 2 条已在其 spec 内修掉，
全量 `src/components/workpaper` 实测仍有 **10 条**同类断言分两种漂移形态：

| 形态 | 断言值 | 实现返回 | 文件（失败条数） |
|------|--------|---------|-----------------|
| A1 合成标识 | `F3-note-soe` / `G1-note-listed` / `G2-note-listed` / `G3-note-*` | 真实 tab 名 | `f3NoteSectionMap.spec.ts`(2) / `g1DisclosureListed.spec.ts`(1) / `g2SoeDisclosure.spec.ts`(2) / `g3Disclosure.spec.ts`(3) |
| A2 短名 | `附注上市` / `附注国企` | `附注披露信息（上市公司）` / `附注披露信息（国企）` | `g10DisclosureSyncPayload.spec.ts`(2) / `g11DisclosureSyncPayload.spec.ts`(2) |

**⚠️ 必须区分的合法用法（不得一起改）**：`X-note-listed` 同时是 **wp_code**
形态，用于 `_WP_CODE_OVERRIDE` 映射、`htmlRendererRegistry` 注册契约、
sheet 名归一化函数的**输入样本**。这类断言（`useF2InventoryMainRegistration.spec.ts`
`f1-registry-contract.spec.ts` `g5LongTermReceivable.integration.spec.ts`
`disclosureSyncBar.spec.ts` 等）**正确且必须保留**。判定口径：断言的是
`payload.sheet_name` / `target.sheetName` → 属漂移；断言的是 `overrides[code]` /
`extractSheet(input)` / `isDisclosureSheetName(input)` → 属合法。

**User Story:** 作为工程治理负责人，我希望 `sheet_name` 只有一个口径（源 xlsx 真实 tab 名），
测试断言与之一致，并且此后再漂移能被守卫立刻拦住，而不是攒成一批预存在失败掩盖真实回归。

#### Acceptance Criteria

1. WHEN 修正某 spec 的 `sheet_name` 断言 THEN 断言值 SHALL 取自该循环 `*NoteSectionMap.ts` 的 `X_DISCLOSURE_SHEET_NAME` 常量（或等价 `sheetName` 声明），禁止另写字面量
2. WHEN 某断言实际是 wp_code / sheet 归一化输入 THEN 系统 SHALL 保留原样（按上表判定口径分类，误改视为回归）
3. WHEN 全部 10 条修正完成 THEN `src/components/workpaper` 全量 vitest 中 `sheet_name` / `sheetName` 类失败数 SHALL 为 0
4. WHEN 新增守卫契约测试 THEN 该测试 SHALL 校验每个 `build*SyncPayload` 产出的 `sheet_name` 与 `backend/data/note_workpaper_sync_registry.json` 对应 `wp_code` 的 `sheet_listed` / `sheet_soe` **逐字一致**
5. WHEN 某循环的 `*NoteSectionMap.ts` 改了 sheet 名但未重跑 `gen_note_wp_sync_registry.py` THEN 守卫 SHALL 失败并提示重生成命令
6. WHEN 修正过程中发现某实现真的还在推合成标识 THEN 系统 SHALL 改实现（对齐真实 tab 名），而不是把断言改回合成标识
7. WHERE 本次实测发现但**不属于**本需求范围的预存在失败（`h8RightOfUseAssetsContract` wp_code 映射数 16→20、`useF3Integration` / `useF5Integration` EventBus、`useH4DualMode` OO 健康检查）THE 本 spec SHALL 只登记不修，避免范围蔓延
