# Requirements Document

## Introduction

N1（递延所得税资产，科目 1811）的两张附注披露 sheet（`附注披露信息（上市公司）` / `附注披露信息（国企）`）当前是**孤岛**：只在底稿内自取数（本轮已修复其从 N1-2/N1-5 的真源取数与派生），但与附注模块（`disclosure_notes`）完全没有联动——

现状（本 spec 起草前逐一核实）：

- **无结构化推送**：N1 没有 `n1NoteSectionMap.ts` / `buildN1SyncPayload`，两张披露 tab 均无「同步到附注」按钮，从不调 `POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper` → 附注模块的表格永远只能靠引擎从 TB 取数或手工录入。
- **无正向跳转**：`noteDisclosureJump.ts` 无 N1 分支 → 在附注模块打开「递延所得税资产和递延所得税负债」章节时，「跳转至披露表」按钮不出现。
- **无反向跳转**：`noteDisclosureReverseJump.ts` 的 `DISCLOSURE_NOTE_SECTION_MAP` 无 N1 条目 → 披露表无「↩ 跳转回附注」入口。
- **叙述文本单向且不定向**：披露 tab 已发 `disclosure:note-text-updated`（本轮补齐了 `accountCode:'1811'` / `projectId` / `sectionIds`），但附注正文（`text_content`）从不由披露表推送，`useNoteRefresh` 也未登记 N1 家族谓词。

**本 spec 的特殊性（最关键约束）**：N1（递延所得税资产）与 N3（递延所得税负债）**共用同一个附注章节**——权威源 `backend/data/note_template_variant_matrix.json` 的 `di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de`：`listed_standalone/consolidated = 五、30`、`soe_standalone/consolidated = 八、31`，章节标题「递延所得税资产和递延所得税负债」。该章节第一张表（`未经抵销的递延所得税资产和递延所得税负债`）在**同一张表内**同时含「递延所得税资产：」段与「递延所得税负债：」段行。而 `sync_from_workpaper` 对 `sub_table_data` 是**按子表键浅合并、同名键整体覆盖**——若 N1 与 N3 各自推送同名子表键，必然互相覆盖，导致「同步 N3 后 N1 的资产段消失」。因此**章节所有权与行分工必须在本 spec 内显式定义**，不能照抄单科目独占章节的既有范式（D1/F3/H9/E1 等）。

范围内：N1 两张披露 tab ↔ 附注模块 五、30 / 八、31 的结构化推送、叙述正文推送、正/反向跳转、定向刷新、覆盖率守卫登记、以及与 N3 的所有权边界定义。

范围外：不改 `sync_from_workpaper` 的浅合并语义（除 Req3 明确的可选行级合并方案被采纳时）、不改附注模板 JSON、不改附注引擎从 TB 取数逻辑、不实现 N3 侧的推送（N3 只作为边界被定义，其落地属独立 spec）、不碰 N1 底稿内已完成的取数/公式/调整分录联动。

## Requirements

### Requirement 1: 附注章节映射单一真源

**User Story:** 作为审计师，我希望 N1 披露表与附注章节的对应关系来自权威映射表，不被硬编码猜测污染，以免推送到错误章节。

#### Acceptance Criteria

1. THE 系统 SHALL 以 `note_template_variant_matrix.json` 的 `di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de` 为 N1 附注章节唯一真源：listed = `五、30`，soe = `八、31`。
2. WHEN 前端需要 N1 的附注章节号 THEN 系统 SHALL 从单一模块常量（`N1_NOTE_SECTION`）读取，且该常量的值与权威矩阵一致。
3. THE 正向跳转谓词、反向跳转映射、结构化推送载荷 SHALL 共用同一章节常量（禁止三处各写一份字面量）。
4. WHERE 章节号为纯序号形态（`五、30` / `八、31`）THE 判定 SHALL 使用精确相等，禁止 `startsWith`（否则 `五、3` 会误命中 `五、30`，反之 `五、30` 会误吞 `五、300` 类未来章节）。
5. IF 权威矩阵中该 `account_key` 的章节号发生变更 THEN 契约测试 SHALL 失败，提示同步常量。

### Requirement 2: N1 披露表结构化推送到附注

**User Story:** 作为审计师，我在 N1 披露表（上市/国企）打磨好表格后，希望一键把表格推到附注模块，附注不再需要重录。

#### Acceptance Criteria

1. WHEN 审计师在 N1 披露 tab 点击「同步到附注」THEN 系统 SHALL 调用 `POST /api/projects/{project_id}/disclosure-notes/sync-from-workpaper`，请求体包含 `wp_id` / `sheet_name` / `section_id` / `sub_table_data` / `columns` / `current_standard` / `year`。
2. THE `sub_table_data` 的每个子表键 SHALL 与 `columns` 的键**逐字相同**（投影器按键名匹配，键不一致则附注端渲染不出列头）。
3. THE 子表列头 SHALL 逐字取自附注模板该章节的 `tables[].headers`（listed 用「期末余额 / 上年年末余额」，soe 用「期末余额 / 期初余额」），禁止用英文字段名或自造列名。
4. THE `year` SHALL 显式传入项目审计年度（来自 `useAuditContext`），禁止依赖后端默认自然年。
5. THE `current_standard` SHALL 按变体传 `listed_standalone` / `soe_standalone`。
6. WHEN 推送成功 THEN 系统 SHALL 提示同步的章节与行数；WHEN 推送失败（含请求被取消）THEN 系统 SHALL 给出可区分的提示且不谎报成功。
7. THE 推送 SHALL 为单向（底稿 → 附注），不反向改写 N1 底稿数据。

### Requirement 3: 与 N3 共用章节的所有权与不覆盖保证

**User Story:** 作为审计师，我不希望「同步 N1」把附注里 N3 的递延所得税负债数据冲掉，也不希望反过来。

#### Acceptance Criteria

1. THE 设计 SHALL 显式定义 五、30 / 八、31 章节内每张子表的**所有权**（哪张表由 N1 推送、哪张表由 N3 推送、哪张表由双方共同构成）。
2. WHERE 一张子表同时含资产段与负债段行（`未经抵销的递延所得税资产和递延所得税负债`）THE 设计 SHALL 采用下列之一并说明取舍：
   - **方案 A（推荐，无后端改动）**：由 N1 作为该表唯一 owner 推送完整行；负债段行取自 N3 已发布的跨底稿键（`N1-4-total-deferred-tax-liability` 或 N3 侧发布键），N3 未编制时负债段留空并在 UI 提示「负债段待 N3 编制后重新同步」。
   - **方案 B（需后端增量）**：为指定子表键引入按行标签合并语义（`sub_table_merge_mode`），N1/N3 各推自己的段行。
3. WHEN N1 推送 THEN 系统 SHALL NOT 清空该章节内不属于 N1 所有权的其他子表（依赖 `sync_from_workpaper` 的「未推送子表保留」语义，且不得传空 `{}` 触发 no-op 误判）。
4. IF 采纳方案 A 且负债段数据缺失 THEN 系统 SHALL 推送资产段并把负债段行留空（值为 null），不得用 0 冒充。
5. THE 单元测试 SHALL 覆盖「N1 推送后 N3 所有权子表键仍在」与「负债段缺失时不写 0」。

### Requirement 4: 叙述正文与说明推送

**User Story:** 作为审计师，我在披露表写的披露说明/结论，希望同步成为附注章节的正文，不必在附注里重写。

#### Acceptance Criteria

1. WHEN 推送时披露表存在说明/结论文本 THEN 系统 SHALL 以 `_note_texts`（`sub_table_data` 内的 `list[{section,title,text}]`）随同步提交，由服务端 pop 后写入 `text_content`。
2. THE 空文本 SHALL NOT 覆盖附注既有正文（无文本时不提交 `_note_texts`）。
3. THE 手工在附注模块编辑过的正文 SHALL 受既有 `_manual_override` 保护语义约束（本 spec 不放宽）。
4. THE 推送成功后 SHALL 继续发 `disclosure:note-text-updated`（携 `accountCode:'1811'`、`projectId`、`sectionIds`），使已打开的附注定向刷新。

### Requirement 5: 正向跳转（附注 → N1 披露表）

**User Story:** 作为审计师，我在附注模块看到递延所得税章节有疑问时，希望一键跳到 N1 披露表核对。

#### Acceptance Criteria

1. WHEN 附注章节为 `五、30`（listed）或 `八、31`（soe）THEN `resolveNoteDisclosureJumpTarget` SHALL 返回 N1 披露表目标（`wpCode='N1'` + 对应 sheet 名）。
2. THE sheet 名 SHALL 与 `workpaper_sheet_classification` 中 N1 的真实 tab 名逐字一致（预期 `附注披露信息（上市公司）` / `附注披露信息（国企）`，全角括号；实现时必须以 DB 核实为准）。
3. THE N1 分支 SHALL NOT 被通用 `syncedSheet` 回退分支（多循环共用同名披露 sheet）抢占，且 SHALL NOT 抢占其他章节（尤其 `五、3` 衍生金融资产、`五、31`、`八、3`、`八、32`）。
4. THE `DisclosureEditor` 的族标签映射 SHALL 包含 `N1 → 递延所得税资产`。
5. WHERE 该章节由 N1/N3 共用 THE 默认跳转目标 SHALL 为 N1，且设计 SHALL 说明是否提供切到 N3 的备选入口（N3 披露表尚未纳入本 spec 时可仅注释保留扩展位）。

### Requirement 6: 反向跳转（N1 披露表 → 附注）

**User Story:** 作为审计师，我在 N1 披露表编辑后，希望一键跳回附注对应章节确认呈现效果。

#### Acceptance Criteria

1. THE `DISCLOSURE_NOTE_SECTION_MAP` SHALL 新增 `N1: { listed: '五、30', soe: '八、31' }`。
2. WHEN 审计师在 N1 披露 tab 点击「↩ 跳转回附注」THEN 系统 SHALL 跳转 `/projects/{pid}/disclosure-notes?section={章节}&noteTemplate={variant}`。
3. THE 主按钮变体 SHALL 与当前披露 tab 变体一致（上市 tab → 五、30，国企 tab → 八、31），并提供下拉切换到另一变体。
4. THE 反向映射章节号 SHALL 与正向谓词一致，并由契约测试交叉校验（单一真源守卫）。

### Requirement 7: 附注定向刷新登记

**User Story:** 作为审计师，我在 N1 披露表改完同步后，正打开的附注章节应自动刷新，不必手动重进。

#### Acceptance Criteria

1. THE `useNoteRefresh` 的家族匹配 SHALL 登记 N1 谓词（accountCode `1811` 或 sectionIds 命中 `五、30`/`八、31`）。
2. WHEN 当前查看章节命中 THEN 系统 SHALL 重新拉取该章节详情（缓存旁路），否则不刷新（避免无关章节抖动）。
3. THE 刷新 SHALL 幂等且失败不崩页（fail-open）。

### Requirement 8: 覆盖率守卫与零回归

**User Story:** 作为技术复核人，我要求新增的同步入口被守卫覆盖，且不影响其他科目已有联动。

#### Acceptance Criteria

1. THE `check_disclosure_columns_coverage.py` 的构造器白名单 SHALL 登记 `buildN1SyncPayload`（或其等价构造器），使 `--strict` 仍通过。
2. THE 既有 43+ 调用点与其他科目的正/反向跳转 SHALL 逐字节不受影响（既有 `noteDisclosureJump` / `noteDisclosureReverseJump` 测试全绿）。
3. THE 改动 SHALL 为 additive：不改 `sync_from_workpaper` 既有语义（除 Req3 方案 B 被采纳时的新增可选参数，且缺省行为不变）。
4. THE N1 底稿内既有 162 项前端测试与后端 45 项测试 SHALL 保持全绿。

### Requirement 9: 属性化可测

**User Story:** 作为技术复核人，我要求关键正确性以纯函数属性测试锁定，防回归。

#### Acceptance Criteria

1. THE 载荷构造（`buildN1SyncPayload`）SHALL 为纯函数（输入：披露表行 + 变体 + 上下文；输出：请求体），可单测不依赖组件挂载。
2. THE 属性 SHALL 至少覆盖：章节号正确性、子表键与 columns 键一致、列头逐字对齐模板、负债段缺失不填 0、空文本不覆盖、N3 子表键不被清空、正反向章节号一致。
3. THE 测试 SHALL 不依赖真实 HTTP（mock）；live round-trip 若因项目未实例化无法执行 SHALL 如实标注不假绿。

## Glossary

| 术语 | 含义 |
|------|------|
| 附注模块 | `disclosure_notes` 表 + `DisclosureEditor.vue`，按 `project_id + year + note_section` 存储 |
| 章节号 | 附注章节序号，如 listed `五、30` / soe `八、31` |
| 权威矩阵 | `backend/data/note_template_variant_matrix.json`，account_key → 各变体章节号 |
| 结构化推送 | `POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper`，把披露表表格写入附注 `table_data.sub_table_data` |
| 子表键 | `sub_table_data` 的 key，通常逐字取附注模板 `tables[].name` |
| columns | `sub_table_id → ColumnDef[]`，供附注模块 `note_sub_table_projector` 投影渲染列头 |
| `_note_texts` | 混在 `sub_table_data` 中的正文载荷（`list[{section,title,text}]`），服务端 pop 后写 `text_content` |
| 正向跳转 | 附注 → 底稿披露 sheet（`noteDisclosureJump.ts`） |
| 反向跳转 | 底稿披露 sheet → 附注章节（`noteDisclosureReverseJump.ts`） |
| 所有权 | 共用章节下，某张子表由哪个底稿负责推送 |
| 负债段 | 五、30/八、31 第一张表内的「递延所得税负债」行组（业务上属 N3） |
