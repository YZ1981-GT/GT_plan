# Requirements Document

## Introduction

154 个披露 Tab（`*TabDisclosure*.vue`）中有 **64 个完全没有「推数据到附注」的链路**：它们既没有 `syncToDisclosureNotes`，也不打 `POST /api/projects/{id}/disclosure-notes/sync-from-workpaper`，更没有走 `useDisclosureAutoSync`。审计人员在这些 Tab 里录入的披露信息只存在 `checklist_responses`，**附注模块永远拿不到**，最终导出的财务报表附注缺这些章节的内容。

这与「附注不跟随底稿内容」（spec `disclosure-note-follow-actual-content`）是两个不同层级的问题：那个 spec 解决的是「有链路但不自动触发」，本 spec 解决的是**链路根本不存在**。

## 取证（2026-07-30 全量扫描）

| 分类 | 数量 | 判定依据 |
|------|------|----------|
| 有同步链路 | **90** | 自有 `syncToDisclosureNotes`(65) + 用别的 syncFn 走 `scheduleAutoSync`(25) |
| **无同步链路** | **64** | 三个标记全无 |
| 合计 | 154 | — |

**曾被误判为「有链路」的 37 个 emit 型已排除**：它们 emit 的事件只有 `navigate`(27)、
`imported`(7)、`disclosure:note-text-updated`(5)。前两者与同步无关；后者的消费方
`useNoteRefresh.onDisclosureNoteTextUpdated` 仅调 `fetchDetail` 刷新界面，且首行
`if (!currentNote.value) return`（附注页未打开直接返回）—— **完全不推数据落库**。
抽查 `N2TabDisclosureListed` / `L2TabDisclosureListed` 确认 `disclosure-notes` 端点 0 命中。

64 个覆盖 35 个循环：D2(1) F4(2) G4(2) G5(2) G6(1) G8(1) G9(3) G10(2) G11(2) G12(2)
H4(1) H5(1) H6(2) H7(2) J2(2) L2(2) L4(2) L5(2) L6(2) L7(2) L8(2) M1(2) M2(2) M3(1)
M4(2) M5(2) M6(2) M7(2) M8(2) M9(2) M10(2) N2(2) N3(1) N4(2) N5(2)。

清单固化在 `disclosureAutoSyncCoverage.spec.ts` 的 `MISSING_SYNC_PATH`（守卫只允许变短）。

## Glossary

| 术语 | 含义 |
|------|------|
| 披露 Tab | `*TabDisclosure*.vue`，底稿内录入对外披露信息的页签 |
| 同步链路 | 披露 Tab → `sync_from_workpaper` → `disclosure_notes.table_data.sub_table_data` 的数据通道 |
| `syncToDisclosureNotes` | 各 Tab 的同步函数（手动按钮与自动同步共用，幂等） |
| `buildXSyncPayload` | 载荷构建器：把 composable 的行模型转成 `{sub_table_data, columns}` |
| `XNoteSectionMap.ts` | 该循环的 sheet_name ↔ 附注章节号映射（前端唯一真源） |
| `note_workpaper_sync_registry.json` | 由各 `XNoteSectionMap.ts` 生成的后端映射产物 |
| `ColumnDef` | 列定义（`key`/`label`/`is_label`/`group`/`flat`/`format`），决定附注表头 |
| `useDisclosureAutoSync` | 自动同步封装（防抖 800ms / 非阻塞 / 失败静默 / 只读 gate） |
| `sub_table_data` | `{表名: [业务键行]}`，附注表格的唯一权威存储 |
| 空载荷 no-op | `sync_from_workpaper` 收到空 `sub_table_data` 时不清空既有子表 |

## Requirements

### Requirement 1: 补齐同步链路

**User Story:** 作为审计助理，我在任意循环的披露 Tab 里录入的披露信息，都应该能进到附注模块，而不是只存在底稿里、导出附注时发现缺内容。

#### Acceptance Criteria

1. WHEN 用户在已补齐的披露 Tab 修改数据并保存 THEN 系统 SHALL 经 `sync_from_workpaper` 把数据写入对应 `disclosure_notes` 章节的 `sub_table_data`
2. WHEN 补齐一个 Tab THEN 该 Tab SHALL 具备：`XNoteSectionMap.ts` 映射、`buildXSyncPayload` 载荷构建器、每张子表的 `columns`、`syncToDisclosureNotes` 函数、手动同步按钮
3. WHEN 补齐一个 Tab THEN 该 Tab SHALL 接入 `useDisclosureAutoSync`，触发条件监听**实际数据**（与载荷构建所用字段一致），**不得**只监听提示横幅类状态，**不得**使用 `_xxxMounted` 一次性防护
4. WHERE 同一循环有 listed / soe 两个变体 THE 两者 SHALL 各自映射到自己的章节号，且对不适用变体 `buildXSyncPayload` 返回 null 而跳过同步
5. WHEN 同步载荷构建 THEN 子表名 SHALL 与 `note_template_*.json` 对应章节的 `tables[].name` **逐字一致**，否则会产生孤儿子表（附注 TAB 永空 + 底稿数据丢失）
6. WHEN 定义 `columns` THEN 每张表 SHALL 在 `group`（多级表头）与 `flat`（单级表头）之间明确表态，禁止两者都不声明
7. IF 某披露 Tab 经核实**不应**推送附注（如纯过程记录、纯分析类）THEN 该 Tab SHALL 从 `MISSING_SYNC_PATH` 移入显式豁免清单并写明理由，而非默默留在缺口里

### Requirement 2: 章节映射正确且可追溯

**User Story:** 作为质量控制复核合伙人，我需要确认每个披露 Tab 推到了正确的附注章节，错节比不推更危险——会污染别的科目披露。

#### Acceptance Criteria

1. WHEN 新增 `XNoteSectionMap.ts` THEN 章节号 SHALL 取自 `note_template_variant_matrix.json`（附注章节号权威源），不得凭记忆填写
2. WHEN 新增映射 THEN `sheet_name` SHALL 为源 xlsx 的中文 tab 名（全平台统一约定），不得用 wp_code 式标识
3. WHEN 映射变更 THEN `note_workpaper_sync_registry.json` SHALL 经 `gen_note_wp_sync_registry.py --write` 重新生成，不得手工编辑
4. WHEN 补齐后 THEN 契约测试 SHALL 断言该 Tab 的 section 号存在于对应 variant 的模板中，且子表名与模板 `tables[].name` 一致
5. IF 目标章节在 `note_template_*.json` 中不存在 THEN 补齐工作 SHALL 先补模板章节，再接同步（不得同步到不存在的章节）

### Requirement 3: 表结构对齐源模板

**User Story:** 作为业务合伙人，附注表格的列结构必须和致同源模板一致，否则出具的报告不符合披露格式要求。

#### Acceptance Criteria

1. WHEN 定义某 Tab 的子表 `columns` THEN 列集合与列序 SHALL 逐列对齐源 xlsx 披露 sheet（禁止按「常识」自造列）
2. WHEN 源模板为两级表头 THEN `columns` SHALL 用 `label` 作子列名 + `group` 作父表头，不得压平成单行
3. WHEN 源模板为单行表头 THEN `columns` SHALL 显式标 `flat: true`，避免 `_infer_groups_from_headers` 凭空推断父表头
4. WHEN 表头文本来自附注模版 md THEN SHALL 去除 md 表格的 `<br/>` 排版标记（`el-table-column :label` 与 Word 导出均不解析 HTML）
5. WHERE 源模板存在互斥披露方式（「或：」表达）THE 补齐 SHALL 保留两组表并在 `guidance` 中说明二选一

### Requirement 4: 守卫防回归

**User Story:** 作为开发者，我要确保补齐后不再退化，且新增披露 Tab 时不会又漏掉同步链路。

#### Acceptance Criteria

1. WHEN 任一披露 Tab 缺同步链路且未登记 THEN `disclosureAutoSyncCoverage.spec.ts` SHALL 失败
2. WHEN `MISSING_SYNC_PATH` 中的 Tab 已补齐 THEN 守卫 SHALL 要求把它移出清单（清单只允许变短）
3. WHEN 某 Tab 接入自动同步 THEN 守卫 SHALL 校验触发条件不是只监听提示横幅、且未使用 `_xxxMounted` 防护
4. WHEN 新增披露 Tab THEN 守卫 SHALL 在其缺链路时立即报错，附带「披露数据会停在 checklist_responses」的说明
5. WHERE CI 运行 THE 守卫 SHALL 纳入前端测试套件，缺口数量变化必须显式改断言

### Requirement 5: 零回归

**User Story:** 作为现场经理，补齐工作不能影响已经在用的 90 个 Tab 和既有附注数据。

#### Acceptance Criteria

1. WHEN 补齐任一 Tab THEN 既有 90 个已接链路 Tab 的行为 SHALL 完全不变
2. WHEN 首次同步某章节 THEN SHALL 不覆盖该章节既有的手工编辑内容（沿用 `sync_from_workpaper` 的 manual_override 守卫）
3. WHEN 同步载荷为空 THEN SHALL 走空载荷 no-op，不清空附注既有子表
4. WHEN 全量测试执行 THEN 现有附注相关前后端测试 SHALL 全绿，不允许放宽既有断言
5. WHERE 某循环有 in-flight spec（D2 / F4 等）THE 补齐 SHALL 与该 spec 协调后再动，避免并发回退
