# Requirements Document

## Introduction

本 spec 把 `docs/proposals/disclosure-note-linkage-review-2026-07-26.md` 复盘遗留台账中
**可执行、非纯运维决策**的部分系统化落地，收口附注模块与底稿 / 合并 / 报表 / 公式
四条联动链上"能力就绪但生产零使用 / 真源分叉"的缺口。

复盘实测（4 项目 / 554 条活跃附注）已确认的事实与本 spec 的对应关系：

| 复盘事实 | 本 spec 需求 |
|---|---|
| 底稿→附注结构化推送零使用（`last_sync_source`=0）；全部 tab 靠手动点「同步到附注」 | Req1 保存后自动同步 |
| `sync-from-workpaper` 前端调用有 **5 套 URL 路径**（`/api/projects/{pid}/…` 47 处、`/api/disclosure-notes/{pid}/{year}/{section}/…` 3 处、`/api/disclosure-notes/{pid}/…` 2 处、带 `{year}` 段 1 处、相对路径 1 处） | Req2 同步端点收敛 |
| 合并附注 V2 `generate_full_consol_notes` 输出**不落 `disclosure_notes`**（源码注释自认），依赖它的附注级穿透端点恒 `has_breakdown=false` | Req3 合并附注 V2 落库 |
| `is_stale` listed 181/181 一刀切；粒度化（P0-3）只影响将来，库内 181 条历史 `stale_source=NULL` | Req4 stale_source 回填 |
| `DISCLOSURE_NOTE_FORMULA_ENABLED` 默认关，已有 119 条 movement binding 可算但从未在真实项目验证 | Req5 公式灰度按项目启用 |

**范围决策（用户拍板 2026-07-26）**：Req3 合并附注 V2 落库**纳入本 spec**；
空 `note_*` 表 + 2 张备份表（`_note_wrong_year_orphan_backup` / `_note_guidance_split_backup`）
的清理 **本 spec 完全不碰表**（属破坏性 DDL，另开运维工单）。

**本 spec 不做**（复盘台账中划为"明确不建议 / 需另 spec / 运维工单"的项）：
批量填 `report_note_linkage.json` 让报表回写附注（方向倒置，决策已定"只校验不写值"）；
给缺 binding 的损益类章节批量臆造科目映射；开 RAG 灰度（知识库索引为空，开了只空转）；
附注模板骨架 / 章节编号体系改动；**任何 drop / 清空数据库表的操作**（空 `note_*` 表与备份表清理另开运维工单）。

## Glossary

- **披露 tab**：各底稿科目组件下渲染"附注披露信息（上市公司）/（国企）"的 Vue 子组件（如 `D1TabDisclosure`、`N1TabDisclosureListed`），已有手动「同步到附注」按钮。
- **Canonical_Sync_URL**：`POST /api/projects/{project_id}/disclosure-notes/sync-from-workpaper`（`wp_disclosure_sync.py` 注册的主端点，47 个 tab 已在用），本 spec 定为唯一同步入口。
- **Auto_Sync**：披露 tab 保存成功后自动触发一次同步到附注（防抖、非阻塞、失败静默、不打断保存），对齐 `GtConfirmationSummary._autoSyncAfterSave` 已 proven 范式。
- **底稿→附注推送模型（push）**：payload 由前端 tab 的 `buildXSyncPayload` 组装（依赖组件内存态），后端无法批量代跑；故自动化只能发生在前端保存回调处。
- **合并附注 V2**：`consol_disclosure_service.generate_full_consol_notes`，产出带 `source_project_id` + `consolidation_breakdown` 的章节 dict，当前**只返回不落库**。
- **附注级穿透**：`note_consol_drilldown_service` 读 `disclosure_notes.consolidation_breakdown` 反查"该合并章节由哪些子公司贡献"，供 `ConsolBreakdownDialog(source=note)`。
- **stale_source**：`disclosure_notes.stale_source`（V129 additive 列），标记 stale 来源（`report` / `report_fallback`）。
- **就绪度看板**：`NoteReadinessPanel` + `GET .../readiness`（本轮复盘 P0-1 已交付），列每章节的同步 / 校验就绪状态。
- **灰度开关**：`DISCLOSURE_NOTE_FORMULA_ENABLED`（表内公式求值）/ `DISCLOSURE_NOTE_RAG_ENABLED`（RAG，本 spec 不动）/ `DISCLOSURE_NOTE_VALIDATION_STRICT`。
- **CONSOL_NOTES_V2_ENABLED**：合并附注 V2 灰度开关，控制 `generate_full_consol_notes` 是否执行与落库。

## Requirements

### Requirement 1: 披露表保存后自动同步到附注

**User Story:** 作为审计师，我希望在披露表编辑保存后系统自动把结构化表格与说明同步到附注模块，无需每张底稿手动点「同步到附注」，从而消除"46 个 builder 就绪但生产零同步记录"的断层。

#### Acceptance Criteria

1. WHEN 披露 tab 的一次保存成功回调触发 THEN 系统 SHALL 自动调用一次同步到附注（`Auto_Sync`），无需用户点击「同步到附注」按钮。
2. WHEN 自动同步被触发 THEN 系统 SHALL 采用防抖（合并短时间内多次保存为一次同步）且非阻塞（不等待同步完成即返回保存结果）。
3. IF 自动同步请求失败（网络 / 后端错误 / 缺少 project_id / EQCR 只读态） THEN 系统 SHALL 静默吞掉错误并保留既有保存结果，绝不打断保存流程或弹出阻断式错误。
4. WHEN 自动同步逻辑接入各披露 tab THEN 系统 SHALL 复用单一共享封装（如 `useDisclosureAutoSync`），各 tab 仅一行接入其保存成功回调，禁止在 45 个 tab 各写一份防抖 / 请求 / 容错代码。
5. WHEN 自动同步成功 THEN 系统 SHALL 更新该章节的 `last_sync_at` / `last_sync_source`，使就绪度看板与底稿页同步状态条实时反映"已同步"。
6. WHERE 披露 tab 处于只读态（EQCR / 归档 / 无编辑权） THE 系统 SHALL 不触发自动同步。
7. WHEN 保留既有手动「同步到附注」按钮 THEN 系统 SHALL 使手动同步与自动同步走同一 payload 构建与同一 Canonical_Sync_URL，二者行为一致、互不冲突（幂等）。

### Requirement 2: 同步端点 URL 收敛为单一 canonical

**User Story:** 作为维护者，我希望所有披露 tab 的同步调用走同一个 canonical 端点，从而消除当前 5 套 URL 路径并存造成的行为分叉与年度参数不一致。

#### Acceptance Criteria

1. WHEN 前端任一披露 tab 触发同步（手动或自动） THEN 系统 SHALL 调用 `Canonical_Sync_URL`（`POST /api/projects/{project_id}/disclosure-notes/sync-from-workpaper`）。
2. WHEN 迁移当前走非 canonical 路径的 tab（H3 `/api/disclosure-notes/{pid}/…`、H4 带 `{year}` 段、H5 / J1 `/api/disclosure-notes/{pid}/{year}/{section}/…`、D6 相对路径） THEN 系统 SHALL 使其改走 canonical 且**同步产出与迁移前逐字节等价**（章节归属、表格、说明文本、年度不变）。
3. WHEN 同步 payload 组装 THEN 系统 SHALL 显式携带 `year`（取自 `useAuditContext().year`），使后端不因缺省回退到服务器自然年（跨年审计时会写错年度）。
4. IF 后端仍需保留历史 `sync-html` 或其它兼容端点 THEN 系统 SHALL 不删除既有后端路由（只收敛前端调用方），避免破坏未纳入本 spec 的调用者。
5. WHEN 收敛完成 THEN 系统 SHALL 提供一个契约守卫（测试 / 脚本），断言前端披露 tab 不再出现非 canonical 的 `sync-from-workpaper` URL 字面量（`GtCNoteTable` 等通用组件与已在 canonical 的 tab 除外）。

### Requirement 3: 合并附注 V2 输出落 `disclosure_notes`

**User Story:** 作为合并项目的审计师，我希望合并附注生成后能落库并在附注级穿透里看到"该章节由哪些子公司贡献"，从而让合并附注与单体附注复用同一套穿透 / 校验 / 导出能力。

#### Acceptance Criteria

1. WHEN `CONSOL_NOTES_V2_ENABLED=True` 且合并附注生成执行 THEN 系统 SHALL 把 `generate_full_consol_notes` 产出的每个章节 upsert 到 `disclosure_notes`，携带 `source_project_id` 与 `consolidation_breakdown`。
2. WHEN 合并章节落库 THEN 系统 SHALL 使 `note_consol_drilldown_service` 对已落库章节返回 `has_breakdown=true` 且 `by_company` 非空（修前恒 `false`）。
3. WHERE `CONSOL_NOTES_V2_ENABLED=False`（默认） THE 系统 SHALL 完全不改变现状（不落库、不改 `consol_note_data`、逐字节等价当前行为）。
4. WHEN 落库使用 upsert THEN 系统 SHALL 幂等（同 `(project_id, year, note_section)` 二次生成不产生重复行、不覆盖用户已手工编辑并锁定的章节）。
5. IF 单个章节落库失败 THEN 系统 SHALL fail-open 记录并继续其余章节，不整体中断合并流水线。
6. WHEN 合并附注章节的标题 / 科目名写入 THEN 系统 SHALL 复用与单体同源的章节元数据解析（`section_title` / `account_name` 取自附注模板，不用 section_id 当标题）。

### Requirement 4: stale_source 历史数据回填

**User Story:** 作为附注编辑者，我希望库内既有的 stale 标记也带上来源标识，从而让前端能按来源分级呈现，而不是一片无差别的"已变更"噪声。

#### Acceptance Criteria

1. WHEN 执行历史回填 THEN 系统 SHALL 对 `is_stale=true` 且 `stale_source IS NULL` 的既有章节按保守规则回填 `stale_source`（有 REPORT linkage 关联的标 `report`，否则标 `report_fallback`）。
2. WHEN 回填运行 THEN 系统 SHALL 幂等（重跑不改变已有非空 `stale_source`、不改变 `is_stale` 本身）。
3. WHERE 章节 `is_stale=false` THE 系统 SHALL 不写 `stale_source`（保持 NULL）。
4. IF 回填过程中无法判定某章节的来源 THEN 系统 SHALL 保守回退为 `report_fallback`，绝不臆造 `report`。
5. WHEN 回填以脚本形式提供 THEN 系统 SHALL 只读判定 + 单条 UPDATE，不依赖迁移文件（避免与并发迁移编号冲突）。

### Requirement 5: 附注公式灰度按项目启用并暴露状态

**User Story:** 作为项目负责人，我希望能对单个真实项目开启附注表内公式求值并在就绪度看板看到开关状态，从而在全量启用前先验证 119 条 movement binding 的求值正确性。

#### Acceptance Criteria

1. WHEN 附注公式灰度支持按项目粒度控制 THEN 系统 SHALL 允许在不改全局默认（保持 `False`）的前提下对指定项目启用表内公式求值。
2. WHEN 就绪度看板加载 THEN 系统 SHALL 展示当前项目的公式灰度启用状态（已启用 / 未启用），使审计师知道附注数字是否经公式求值。
3. WHERE 公式灰度对某项目未启用 THE 系统 SHALL 逐字节等价当前行为（不求值、不改附注数据）。
4. IF 表内公式求值对某单元格失败 THEN 系统 SHALL fail-open（该格保持原值、记录 warning），不阻断章节渲染或落库。
5. WHEN 灰度开启后生成 / 刷新附注 THEN 系统 SHALL 使 movement binding（期末=期初+增−减）与合计求值结果落入对应单元格并可被就绪度看板 / 校验消费。

### Requirement 6: 零回归、向后兼容、灰度默认关

**User Story:** 作为维护者，我希望本 spec 的所有改动都是增量且可回退的，从而不影响未使用新功能的既有项目与调用者。

#### Acceptance Criteria

1. WHEN 未启用任何新能力（自动同步未接、V2 开关关、公式灰度关、未跑回填） THEN 系统 SHALL 使既有生成 / 手动同步 / 校验 / 导出行为逐字节等价当前。
2. WHEN 新增数据库列 / 字段 THEN 系统 SHALL 使用 additive 可空列并提供回滚脚本，历史行 NULL 值兼容。
3. WHEN 各能力分批落地（自动同步按循环分批、V2、回填、灰度） THEN 系统 SHALL 使每一批独立可回退、互不阻断。
4. WHEN 既有手动同步按钮 / 既有后端同步端点 / 既有 `consol_note_data` 存储 THEN 系统 SHALL 全部保留，不删除、不改变其对外契约。
5. WHERE 改动触及共享组件（`GtWpRenderer` / 就绪度看板 / 合并流水线） THE 系统 SHALL 保证对未涉及的科目 / 循环零副作用。

### Requirement 7: 属性化可测

**User Story:** 作为质量负责人，我希望上述行为有基于属性的自动化测试覆盖，从而防止回归。

#### Acceptance Criteria

1. WHEN 自动同步逻辑落地 THEN 系统 SHALL 有测试断言防抖合并、失败静默不抛、只读态不触发、与手动同走 canonical URL。
2. WHEN URL 收敛落地 THEN 系统 SHALL 有契约守卫断言无非 canonical 字面量残留。
3. WHEN V2 落库落地 THEN 系统 SHALL 有测试断言 upsert 幂等、fail-open、开关关时零改动、落库后穿透 `has_breakdown=true`。
4. WHEN stale 回填落地 THEN 系统 SHALL 有测试断言幂等、非 stale 不写、无法判定回退 `report_fallback`。
5. WHEN 公式灰度落地 THEN 系统 SHALL 有测试断言按项目启用、fail-open、关闭态零改动。
