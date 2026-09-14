# Design Document

## Overview

本设计落地 requirements.md 的 7 条需求，全部**增量 / 灰度默认关 / 分批可回退**，不删任何既有端点、按钮、表或数据。五个改动面各自独立可发布：

1. **前端自动同步**（Req1）：新建单一 composable `useDisclosureAutoSync`，各披露 tab 保存成功回调一行接入；手动按钮保留、走同一 payload 与 URL。
2. **URL 收敛**（Req2）：把 5 处非 canonical `sync-from-workpaper` 调用（H3/H4/H5/J1/D6）改走 canonical，payload 显式带 `year`；vitest 契约守卫防回归。
3. **合并附注 V2 落库**（Req3）：在既有 `generate_full_consol_notes` 内新增落库步骤（复用单体 `sync_from_workpaper` 的复活/元数据/幂等范式），灰度 `CONSOL_NOTES_V2_ENABLED` 默认关。
4. **stale_source 回填**（Req4）：只读判定 + 单条 UPDATE 的幂等脚本，非迁移。
5. **公式灰度按项目**（Req5）：新建统一入口 `note_formula_gray_service`，4 处消费点改调它；就绪度看板暴露状态；项目级 override 存 `project.wizard_state` JSONB（无新列）。

## Architecture

```
【Req1+Req2 底稿→附注 push 链（前端）】
  披露 tab 保存成功 ──► useDisclosureAutoSync.scheduleAutoSync(syncFn)
                          │ 防抖 800ms · 只读 gate · 失败静默
                          ▼
                  syncFn()（各 tab 既有 syncToDisclosureNotes，走 canonical）
                          ▼
   POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper  ◄── 唯一 canonical
                          ▼
        wp_disclosure_sync_service.sync_from_workpaper（后端不变）
                          ▼
        disclosure_notes（last_sync_at/source 更新）──► 就绪度看板 / 状态条实时反映

【Req3 合并附注 V2 落库链（后端）】
  consol_cascade_refresh_service.refresh_all（步骤6，调用点不变）
       └─► generate_full_consol_notes(db, pid, year)
              ├─ Step1-7 现状：汇总 180 章节 + lineage（返回 list，不变）
              └─ Step8 新增：_persist_consol_sections_v2(...)  ◄── 仅 CONSOL_NOTES_V2_ENABLED=True
                     │ 逐章节 upsert 到 disclosure_notes（复活软删/幂等/元数据解析）
                     │ 写 source_project_id + consolidation_breakdown + last_sync_source='consolidation'
                     ▼
              note_consol_drilldown_service 读 consolidation_breakdown ──► has_breakdown=true

【Req5 公式灰度按项目（后端）】
  disclosure_engine / note_source_resolvers / report_note_sync_service / note_formula_evaluator
       └─► note_formula_gray_service.is_note_formula_enabled(db, project_id)
              ├─ 全局 settings.DISCLOSURE_NOTE_FORMULA_ENABLED=True → 全开（向后兼容）
              └─ 否则查 project.wizard_state.disclosure_note_formula_enabled（项目级 override）
       readiness.summary.formula_enabled ──► NoteReadinessPanel 显示"公式求值：已启用/未启用"
```

## Components and Interfaces

### 1. `useDisclosureAutoSync`（前端新建，Req1）

`audit-platform/frontend/src/components/workpaper/composables/useDisclosureAutoSync.ts`

```ts
interface DisclosureAutoSyncOptions {
  isReadonly?: () => boolean        // 只读态返回 true 则不触发（EQCR/归档/无编辑权）
  debounceMs?: number               // 默认 800
}
interface DisclosureAutoSync {
  scheduleAutoSync: (syncFn: () => Promise<void> | void) => void  // 防抖调度，非阻塞
  cancelPending: () => void         // onUnmounted 清定时器
}
export function useDisclosureAutoSync(opts?: DisclosureAutoSyncOptions): DisclosureAutoSync
```

- `scheduleAutoSync(syncFn)`：清除上一个未触发定时器 → 起 `debounceMs` 定时器 → 到点若 `isReadonly()` 为真则跳过，否则 `Promise.resolve(syncFn()).catch(()=>{})`（失败静默）。
- `syncFn` = 各 tab 既有 `syncToDisclosureNotes`（本身已走 canonical + `buildXSyncPayload`）；自动同步不新造 payload，与手动同源（幂等）。
- **接入点识别（Wave5 实际工作量）**：45 个披露 tab 的保存路径不统一（`debouncedSave` / `saveImmediate` / `emit('save')` 回调 / composable 内 `_persist` 成功分支各异），接入时须逐 tab 找到其"保存成功"分支挂 `scheduleAutoSync`，而非假设统一入口；无独立保存成功回调的 tab（纯 emit 由父级持久化）在 emit 后挂。
- 接入方式（每 tab 一行）：保存成功处 `autoSync.scheduleAutoSync(syncToDisclosureNotes)`；`onBeforeUnmount(() => autoSync.cancelPending())`。
- 试点循环先接一个已在 canonical 的循环（N1），验证后按循环分批铺开（Req6.3）。

### 2. URL 收敛（前端，Req2）

- 目标 canonical：`POST /api/projects/{project_id}/disclosure-notes/sync-from-workpaper`（`wp_disclosure_sync.py` 已注册，47 处已用）。
- 迁移非 canonical 调用（各改为 canonical + payload 带 `year: useAuditContext().year`）：
  - `H3TabDisclosureListed/SOE`（`/api/disclosure-notes/{pid}/sync-from-workpaper`）
  - `H4TabDisclosureListed`（`/api/projects/{pid}/disclosure-notes/{year}/sync-from-workpaper`，带 year 段）
  - `H5TabDisclosureSoe` + `J1TabDisclosureListed/Soe`（`/api/disclosure-notes/{pid}/{year}/{section}/sync-from-workpaper`）
  - `useD6Disclosure.ts`（相对路径 `sync-from-workpaper`）
- **迁移铁律**：改 URL 后 payload 结构（`section_id`/`sub_table_data`/`_note_texts`/`current_standard`/`sub_table_columns`）保持不变，产出逐字节等价（Req2.2）。后端历史端点（`sync-html` 等）不删（Req2.4）。
- 契约守卫 `disclosureSyncUrlContract.spec.ts`：扫描 `components/workpaper/**/*.vue` + `**/composables/use*Disclosure.ts`，断言 `sync-from-workpaper` 字面量仅出现在 canonical 形态或经 `useAuditContext` 拼装（`GtCNoteTable` 等通用组件 allowlist 例外）。

### 3. `_persist_consol_sections_v2`（后端新建，Req3）

`consol_disclosure_service.py` 内新增，`generate_full_consol_notes` 末尾（Step 7 lineage 之后）调用：

```python
async def _persist_consol_sections_v2(
    db, parent_project_id: UUID, year: int, sections: list[dict], template_type: str,
) -> dict:  # {"upserted": n, "skipped": n, "errors": [...]}
```

- **灰度门控**：`generate_full_consol_notes` 内 `if getattr(settings, "CONSOL_NOTES_V2_ENABLED", False): await _persist_consol_sections_v2(...)`（默认 False → 不落库，逐字节等价现状，Req3.3）。**注意**：`consol_cascade_refresh_service` 现用 `getattr(..., True)` 默认 True，本函数内落库 gate 用与 config 一致的默认 **False**（config `CONSOL_NOTES_V2_ENABLED=False`），避免误落库；两处 gate 读同一 settings，config 有定义故实际取 False。
- **落库逻辑**（复用单体 `sync_from_workpaper` proven 范式）：逐章节按 `(project_id=parent, year, note_section=section["section_id"])` 查 active → 无则查软删行**复活复用**（唯一键不含 is_deleted，直接 INSERT 撞键 500）→ 无则新建。
- **字段映射**：`table_data ← section["table_data"]`（保留 `consolidation_breakdown`/`source_project_id` 附在 table_data 或列）；`source_project_id ← parent_project_id`；`consolidation_breakdown ← section["consolidation_breakdown"]`（写 `disclosure_notes.consolidation_breakdown` 列，供穿透端点）；`last_sync_source='consolidation'`；`section_title`/`account_name` 经 `_resolve_section_meta(section_id, source_template)`（复用单体元数据解析，禁用 section_id 当标题）。
- **幂等**（Req3.4）：同键二次生成走"更新"分支不新增行；**跳过用户已 `_manual_override=True` 且锁定的章节**（复用 `_detect_manual_override`）。
- **fail-open**（Req3.5）：单章节落库异常 → 记 `errors` 并 continue，不中断整体；整体不 raise 到 `generate_full_consol_notes` 调用方（cascade 步骤 6 已有 try/except 隔离，但本函数自身也逐章节隔离）。
- **穿透激活**（Req3.2）：落库后 `note_consol_drilldown_service._load_note` 能读到 `consolidation_breakdown` → `has_breakdown=true`。
- **note_section 键隔离**（Req3.4 / Req6.5）：合并项目 `parent_project_id` 与各单体子公司项目是不同 `project_id`，`disclosure_notes` 唯一键 `(project_id, year, note_section)` 天然隔离——合并附注章节落在合并项目 project_id 下，绝不与单体项目的同编号章节冲突。V2 章节 `section_id`（经 `_renumber_sections_consolidated` 重排）作 `note_section` 落库，`source_project_id=parent_project_id`、`last_sync_source='consolidation'` 双重标记合并来源，供前端 / 校验 / 导出区分。
- **🔴 table_data 渲染契约兼容性（Wave3 必核实项）**：V2 `aggregate_section` 产出的 `table_data`（`{rows, method, elimination_columns, ...}`）与前端附注模块渲染契约（`sub_table_data` / `_tables` / `headers` + `note_header_projector` 读时投影）**结构可能不同**。落库前须核实：要么 V2 产出已符合渲染契约，要么落库时做一层结构适配（映射到 `sub_table_data` + 表头），否则前端附注模块打开合并章节会空表 / 报错。若不兼容且适配成本高，回退方案=仅落 `consolidation_breakdown` provenance 激活穿透（Req3.2），表格渲染留 `consol_note_data` 老路径（Req3.3 零回归），并在任务中标注该边界。

### 4. `backfill_note_stale_source.py`（后端脚本，Req4）

`backend/scripts/backfill_note_stale_source.py`

- 只读判定 + 单条 UPDATE，**非迁移文件**（避免与并发迁移编号冲突，Req4.5）。
- 逻辑：`SELECT ... WHERE is_stale=true AND stale_source IS NULL` → 对每条判定该 `note_section` 是否有 REPORT linkage（`ReportNoteLinkage` / `report_note_linkage.json`）→ 有标 `report`、否则标 `report_fallback`（Req4.1/4.4）。
- 幂等（Req4.2）：`WHERE stale_source IS NULL` 天然幂等；`is_stale=false` 的行不在 WHERE 集内（Req4.3）。
- 提供 `--dry-run`（默认，只报计数）与 `--apply`。

### 5. `note_formula_gray_service`（后端新建，Req5）

`backend/app/services/note_formula_gray_service.py`

```python
async def is_note_formula_enabled(db, project_id: UUID) -> bool:
    """全局 settings.DISCLOSURE_NOTE_FORMULA_ENABLED=True → True（向后兼容全开）；
    否则查 project.wizard_state.disclosure_note_formula_enabled（项目级 override，默认 False）。
    异常 fail-open 返 False。"""
```

- **消费点改造**（4 处，从直接读 `settings` 改调统一入口）：`disclosure_engine._evaluate_note_formulas` 调用 gate（2 处）、`note_source_resolvers` 的 `_formula_enabled`、`report_note_sync_service`。改造后**全局 False + 无项目 override → False**（与当前逐字节等价，Req5.3/Req6.1）。
- **同步版兜底**：部分消费点在无 db 上下文（如纯 resolver），需要 `project_id`+`db`；`disclosure_engine.generate_notes` 已持有 db + project_id，在生成入口解析一次 `formula_on = await is_note_formula_enabled(db, pid)` 传入下游（避免逐格查库）。
- 项目级 override 写入：`PUT /api/disclosure-notes/{pid}/formula-gray`（body `{enabled: bool}`，权限 manager+），改 `project.wizard_state["disclosure_note_formula_enabled"]`（`flag_modified` 就地改 JSONB，无新列，Req5.1）。
- 就绪度暴露：`note_readiness_service.build_readiness` 的 `summary` 加 `formula_enabled: bool`；`NoteReadinessPanel` 顶部显示"公式求值：已启用/未启用"标签（Req5.2）。

## Data Models

**无新增数据库表 / 列。** 全部复用既有：

- `disclosure_notes.source_project_id` / `.consolidation_breakdown`（Phase 3 已加，供 V2 落库与穿透）
- `disclosure_notes.last_sync_source` / `.last_sync_at`（供自动同步反映）
- `disclosure_notes.stale_source`（V129 已加，供回填）
- `project.wizard_state`（JSONB，存 `disclosure_note_formula_enabled` 项目级 override，惯例见 aging_config / tb_detail_formulas）

## Correctness Properties

### Property 1: 自动同步防抖合并
连续多次 `scheduleAutoSync` 在 `debounceMs` 内只触发一次 `syncFn`。
**Validates: Requirements 1.1, 1.2**

### Property 2: 自动同步失败静默不抛
`syncFn` reject 时 `scheduleAutoSync` 不向上抛异常、不阻断调用方。
**Validates: Requirements 1.3**

### Property 3: 只读态不触发自动同步
`isReadonly()` 返回 true 时定时器到点不调 `syncFn`。
**Validates: Requirements 1.6**

### Property 4: 自动与手动同 URL 同 payload
自动同步调用的 `syncFn` 即手动按钮的 `syncToDisclosureNotes`，二者 URL 与 payload 构建同源。
**Validates: Requirements 1.7, 2.1**

### Property 5: 无非 canonical URL 残留
契约守卫扫描披露 tab，`sync-from-workpaper` 仅出现在 canonical 形态（allowlist 例外）。
**Validates: Requirements 2.5**

### Property 6: URL 迁移产出等价
迁移前后同一披露表数据 sync 产出的章节归属 / 表格 / 说明 / 年度逐字节等价。
**Validates: Requirements 2.2, 2.3**

### Property 7: V2 落库幂等
同 `(project_id, year, note_section)` 二次 `_persist_consol_sections_v2` 不新增行、不覆盖 `_manual_override` 锁定章节。
**Validates: Requirements 3.4**

### Property 8: V2 fail-open
单章节落库异常时其余章节仍落库，函数不 raise。
**Validates: Requirements 3.5**

### Property 9: V2 开关关零改动
`CONSOL_NOTES_V2_ENABLED=False` 时不落库、不改 `disclosure_notes` / `consol_note_data`。
**Validates: Requirements 3.3, 6.1**

### Property 10: V2 落库激活穿透
落库后 `note_consol_drilldown_service` 对该章节返 `has_breakdown=true` 且 `by_company` 非空。
**Validates: Requirements 3.1, 3.2**

### Property 11: stale 回填幂等且不越界
回填仅改 `is_stale=true AND stale_source IS NULL` 的行；重跑不改已有非空值；`is_stale=false` 不写；无法判定回退 `report_fallback`。
**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 12: 公式灰度按项目 + 关闭态零改动
`is_note_formula_enabled` 在全局 False + 无项目 override 时返 False（逐字节等价当前）；项目 override=True 时该项目返 True；异常 fail-open 返 False。
**Validates: Requirements 5.1, 5.3, 5.4, 6.1**

### Property 13: 就绪度暴露公式状态
`build_readiness().summary` 含 `formula_enabled`，与 `is_note_formula_enabled` 判定一致。
**Validates: Requirements 5.2**

## Error Handling

- 自动同步失败：静默吞（`.catch(()=>{})`），不 toast、不阻断保存（Req1.3）。
- V2 落库单章节失败：记 `errors` continue；整体不 raise（cascade 步骤 6 已 try/except 二次隔离）（Req3.5）。
- 公式灰度判定异常：fail-open 返 False（关闭态，绝不误开）（Req5.4）。
- stale 回填无法判定来源：回退 `report_fallback`，绝不臆造 `report`（Req4.4）。
- URL 收敛：迁移的 tab 若 `useAuditContext().year` 缺失，沿用后端 `_resolve_target_year`（以 `projects.audit_year` 为权威）兜底，不因缺 year 写错年度（Req2.3）。

## Testing Strategy

- **前端**：`useDisclosureAutoSync.spec.ts`（P1-P4：防抖/静默/只读 gate/同源）；`disclosureSyncUrlContract.spec.ts`（P5 扫描守卫）；N1 试点接入后 vitest 断言保存回调调 `scheduleAutoSync`。
- **后端**：`test_consol_notes_v2_persist.py`（P7-P10：幂等/fail-open/开关关零改动/穿透激活，mock session + 真实 PG16 二选一）；`test_backfill_note_stale_source.py`（P11）；`test_note_formula_gray_service.py`（P12-P13）。
- **零回归**：`git stash` 只 stash 本 spec 文件对照既有 disclosure/consol 测试全绿。
- **live/Playwright**（可选）：真实项目开 `CONSOL_NOTES_V2_ENABLED` 后 round-trip（生成合并附注→穿透 has_breakdown=true）+ 披露 tab 保存后自动同步（状态条转"已同步"）；避免污染真实项目用 create→verify→还原。
