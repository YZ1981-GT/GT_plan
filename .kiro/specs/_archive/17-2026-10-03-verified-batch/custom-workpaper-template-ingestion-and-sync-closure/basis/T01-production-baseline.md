# Task 1 — 生产基线与已有内核边界（取证冻结）

_Requirements: 1.1, 1.2, 1.5, 12.2, 12.7, 13.1, 13.3, 13.4_

取证日期 2026-09-08。所有结论均给出可复现文件/行定位，未推断。

---

## A. 三条入口的真实语义（Requirement 1.1–1.5）

### A1 `batch_create_blank` — 已具正确语义，但缺稳定 action id
`audit-platform/frontend/src/components/workpaper/custom/GtCustomWpBatchDialog.vue`
- L225–245 `onExcelChange`：`readWorkbookAoa(raw)` 后 `const first = sheetNames[0]`，**只取首 sheet** 当「清单」（编号/名称/循环三列），与模板摄取无关；
- L275–287 `doCreate`：POST `create-custom-batch`，body 只有 `{items:[{wp_code,wp_name,audit_cycle}], year}`，**无任何二进制**；
- L290–297 成功文案 `已创建 N 个，跳过 M 个` —— 语义正确（未谎称上传/发布）；
- 违反点仅 **1.4**：telemetry/action 无稳定 id，行为完全靠中文按钮文字 `确认创建` 与端点路径区分。

### A2 `maintain_metadata` — 已具正确语义，但零 scope
`backend/app/routers/custom_templates.py` `POST ""` → `CustomTemplateService.create_template`
- L37 `TemplateCreate.template_file_path: str` —— **客户端可传任意路径字符串**，服务端不校验存在性、不做任何文件读取；
- `custom_template_service.create_template` L33–45：直接 `db.add(tpl)`，零 quarantine、零 preflight、零 candidate、零 publication；
- 违反 1.5：这条链仍是正式 ingestion 路径（`/api/custom-templates` 是唯一「上传模板」入口），且可接受任意 `template_file_path`。

### A3 `ingest_excel_template` — **不存在**
全库无 multipart 文件上传入口。`GtCustomWpBatchDialog` 的 `el-upload` 是 `action="#"` + `:auto-upload="false"`（L43–45），纯客户端 SheetJS 解析，字节从未离开浏览器。

---

## B. `validate_template` 空内容恒 valid（Requirement 5.7 / Property 8）

`backend/app/services/custom_template_service.py` L187–216：

```python
async def validate_template(self, file_content: str | None = None) -> dict:
    issues: list[dict] = []
    if not file_content:
        return {"valid": True, "issues": [], "message": "无内容需要验证"}
```

空 / `None` / 空白字符串一律 `valid=True` 且 `issues=[]`。且 `POST /api/custom-templates/validate` 的
`ValidateRequest.file_content: str | None = None` —— 客户端**可不传**任何内容即拿到 `valid: true`。
违反 Requirement 5.7（空/异常 report 永不 valid）。

---

## C. `custom_cells` 原地改 current 再 CAS（Requirement 12.2 / 12.7 / Property 17）

`backend/app/routers/custom_workpaper_cells.py::update_custom_cells`，顺序：

```python
# ① 原地写 current 文件 —— 已经不可回滚
written = write_cells_to_xlsx(ctx.wp.file_path, sheet_name, normalized)

# ② 之后才取 revision，取的是【服务器最新】而非客户端 base
expected_revision = await writer.current_revision(wp_id)

# ③ CAS 失败仅抛 409，此时 xlsx 已被永久改写
receipt = await writer.commit_bytes(..., expected_revision=expected_revision, ...)
```

三重违反：
1. **12.2** 未先校验客户端 base revision（payload `CustomCellsUpdateRequest` 里**根本没有** base revision 字段，只有 `sheet_name/updates`）；
2. **12.7** 正式写链仍是 `write_cells_to_xlsx(ctx.wp.file_path, ...)`，无 staging copy；
3. **12.5** CAS 失败无法撤销 —— `expected_revision` 取自「刚写完之后的服务器值」，故 CAS 自身近乎恒成功，真并发被掩盖成「文件已被别人改了但服务器 revision 正好接上」。

注：该端点 Task 19 迁移已把「提交出口」统一到 `ContentMutationService.commit`，`db.commit()` 与版本字段推进已去除 —— **这是唯一已收敛的部分**，写链本体未动。

---

## D. scope 完全缺失（Requirement 2.1）

`backend/app/models/extension_models.py::WpTemplateCustom` 全列：
`id, user_id, template_name, category, template_file_path, is_published, version, description, is_deleted, created_at, updated_at`
—— **无 `tenant_id`、无 `organization_id`、无 `project_id`、无 `policy_version`、无 digest 类字段**。
`custom_templates.py` 更是 `TEMP_USER_ID = UUID("00000000-0000-...-01")` 硬编码写库主体，`create_template`/`publish_template`/`create_version`/`delete_template` 全走它，`current_user` 依赖注入后**未被使用**。

---

## E. sync/version kernel：必须复用 vs 禁止复制

**可复用（已交付且守卫强）**
- `backend/app/services/workpaper_sync/writer_migration.py::AuthoritativeContentWriter.commit_bytes(project_id, wp_id, entry_id, source, payload, document_type, expected_revision, substrate_path, lane_id, actor_id)` —— 唯一权威写出口，CAS 语义在 `ContentMutationService.commit` 内；
- `lane_id="custom_cells"` + `opaque_entry_gate.authority_model_for_lane("custom_cells") = custom_authoritative_ooxml` —— authority model 由 lane 单向决定，`commit_bytes` 签名已删除 `authority_model` 参数（Task 65）；
- `build_content_mutation_service_writer(db)` / `opaque_entry_id(wp_code=, wp_id=)` / `writer.current_revision(wp_id)` / `writer.publish_committed_events(receipt)`；
- `RevisionConflictError` 窄捕获 → 409；
- `excel_instrumentation.py` / `excel_materialize.py` / `excel_row_shift.py` / `merge.py` / `resolution.py` —— OOXML 侧既有能力。

**禁止复制（custom 侧不得再写一份）**
- 不得自造 callback writer / 自造 room 服务 / 自造 namespace 映射（Requirement 13.4 / 13.6）；
- 不得在 custom 侧新增 `db.commit()` 或版本字段推进（Task 19 已建立的反模式守卫 `test_task19_writer_migration.py` 在查）；
- 不得用 grep 式守卫判「字符串存在」——按 memory 假绿三源，一律行为/结构判据。

**并发在途（勿动）**
- `multi_resolver` 四条行仍 deferred（`get_whole_excel_grid` / `get_sheet_onlyoffice_config` / `get_sheet_wopi_contents` / 第 4 行），裁决 owner = sync spec Task 71 → blocking Task 36（Wave 7）；
- `test_downstream_base_reliability_gate.py` 登记 916 条 blocking facts，912 归 Task 74、4 归 Task 71，Tasks 25–47/58/59 已标 `[x]` 但门未归零 —— **当前处于 `xfail` 挂起态**。

---

## F. 外部依赖实测状态（决定哪些任务 BLOCKED）

| 依赖 | 实测证据 | 状态 |
|---|---|---|
| `G-C0` | `frontend/src/shared/contracts/gc0/index.ts` 存在，9 类型 + `GC0_DISCRIMINATORS` + 判别器函数；`index.spec.ts` 37 例 | **已交付，可消费** |
| `G-ID` | 上游 `workpaper-guidance-content-closure` Task 4 = `[~]` | BLOCKED |
| `G-HANDOFF-CONSUMER` | 上游 Task 16 = `[~]` | BLOCKED |
| `F-SHELL` | 全库 `grep F-SHELL|GtShell|shellOutlet` = 0 命中 | BLOCKED |
| `SYNC-UNIFIED-ROOM` | 无 gate 名注册；`test_task10_orm_repository_contract.py` 仍有 `no_durable_forcesave_ack` 旗标 | BLOCKED |
| `SYNC-MULTI-RESOLVER` | 实测 count=4，全部 deferred | BLOCKED |
| `SYNC-DURABLE-APPLICATION` | `test_workpaper_sync_legacy_baseline.py` 仍报 `missing_forcesave_command` / `missing_durable_callback_ack` | BLOCKED |
| `SYNC-ENTRY-NAMESPACE` | `custom_cells` lane 与 WOPI/offline lane 分属不同 registry 行 | BLOCKED |

## G. 本 spec 自身 git 状态

`git status --porcelain` → `.kiro/specs/custom-workpaper-template-ingestion-and-sync-closure/` 为 `??` 未跟踪。
⇒ 本 spec 目录需尽快入库，否则丢工作树即蒸发（memory 已登记同类问题）。

## H. 环境基线
- 最高迁移号 **V155**（`backend/migrations/V155__oo_content_revision.sql`）；新迁移须 `IF NOT EXISTS` 幂等；
- 分支 `work/2026-08-12-g7-column-alignment-closure`；工作树长期不干净，同一文件禁与并发会话并行编辑。
