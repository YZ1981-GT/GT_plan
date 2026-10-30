# 设计：证据采集单一入口（attachment-evidence-intake）

需求见 `requirements.md`。ADR 编号 ADR-AEI-NN；变异编号见 §6。

## 1. 边界

| 不在本 spec | 归属 |
|---|---|
| 函证附件抽屉的上传（函证中心挂件、`confirmation_list` 引用）、跟函 / 替代程序子模块挂件、替代程序按单据类型抽取 | Spec C |
| `sampled_vouchers` 与证据绑定、盘点「照片」列（H1 / H2 / H5 / H7 的 `photoUrl` 手填文本）、D4-12 合同卡片预览 | Spec D / F |
| 归档打包、QC-17 口径、A 类签字件 | Spec E |
| 旧版本模型（按文件名归链）的列表 / 回滚口径、`ocr_fields_cache` 整体覆盖、治理链路切换 | Spec G |
| 入口覆盖台账 `wp_bound_entry_coverage.json` 全量重生成（全仓 `is_clean()` 已红，Spec A 新增路由也未登记） | 全局治理；本 spec 只删本 spec 删掉的那条、补本 spec 新增的那条 |

## 2. 决策

**ADR-AEI-01 单一入口，失败不降级。** 新模块 `services/workpaper_evidence_intake.py`：`create_evidence(db, wp, file_name, content, evidence_type, user, position)` 是底稿内建证据的唯一服务端写法（上传策略 → 建附件 → 整稿关联或行级链接，只 flush）；OCR 端点、入口上传端点都调它。原 `provision_wp_linked_attachment` 失败时返回临时 id 继续识别，行里存的 id 在附件表不存在（评估报告 3.3-1 的成因）——删除该函数，建附件失败直接报错。

**ADR-AEI-02 行级位置放 `evidence_links`，行级上传不写整稿关联。** 用户拍板事项 1。整稿关联表示「这份文件是本底稿的证据」，行级链接表示「是这一行的证据」；两者都写会让「移除本行证据」后文件仍以整稿身份留在底稿里，编制人又没有整稿解除权限（ADR-AEI-04）。只写链接则移除即彻底脱钩，文件留在项目附件池。代价是读取方要认链接：统一视图（需求 4.1）、可见性隔离 `_linked_wp_ids`、OCR 写回的已关联判定（需求 3.7）在本 spec 一并改；QC-17 与归档枚举在 Spec E。`attachment_working_paper.row_ref` 无写入方也无读取方，不再使用（不删列）。

**ADR-AEI-03 入口上传不进旧的同名自动建版本。** 旧模型按（项目、文件名、reference）归链：同一底稿两行各传一份「扫描件.pdf」会被串成 v1 / v2 并发替换信号，把前一份的下游标为失效。入口上传 `version_chain=False`：恒为版本 1、不加链锁、不发信号。`reference_type` 整稿写 `working_paper`、行级写 `workpaper_item`（与附件管理页的无引用上传隔开链键）。残留：旧模型的版本列表 / 回滚仍按文件名归组，同底稿同名的两份入口附件会被列成一条链（版本弹窗零挂载，只经接口可见）——归 Spec G。

**ADR-AEI-04 权限：新证据按底稿内容写，已有附件整稿关联照旧。** 入口上传、OCR 建附件、证据链接增删 = 底稿内容编辑：路径项目 edit + 统一门 `dedicated_write` / `dedicated_delete`（路由注册时自动挂，编制人可用，复核人与只读历史身份不可）+ 归档 423。把项目里已有的附件整稿关联到底稿仍是 `attach_associate`（仅 lead / admin / supervisor，`test_associate_assignee_denied` 与 `test_no_dimension_splice_assignee_cannot_borrow_lead_action` 钉住，属可见性隔离 spec 的设计，不在本 spec 放宽）。行级链接只能挂本底稿已有的附件（需求 3.2），所以不构成绕过整稿关联的口子。评估报告第八节 11（编制人不能关联自己底稿的附件）由此收口：编制人的常见动作是上传新证据，走入口。

**ADR-AEI-05 OCR 带 id 必须是本底稿的附件。** `load_reusable_ocr` 只按 id 取附件，任何能写自己底稿的用户都能传他项目附件 id 读走识别全文。入口先校「同项目 + 已关联到本底稿」，不过即 404（不区分不存在与无权）。重识别读附件已存原件（本地存储取原路径；Paperless 存储时才用请求里的文件写临时文件），避免把文件 B 的识别结果写到附件 A 上。

**ADR-AEI-06 证据类型。** 登记表 `EVIDENCE_TYPES`（需求 1.2）是 Spec A `ATTACHMENT_TYPES` 的子集（去掉 `general`、`workpaper_item`），守卫钉住子集关系与前端选项一致。缺省：底稿编码的证据声明恰好一类 ⇒ 该类；否则 `evidence`。OCR 端点各有本循环类型（§3.2 表）与编码前缀，底稿编码属于该前缀才用端点类型，`d4/contract-ocr` 被 C 类、函证替代程序借用时按缺省规则。

**ADR-AEI-07 统一视图是底稿附件的唯一读口。** 新模块 `services/attachment_wp_view.py` 承接 `AttachmentService.get_wp_attachments` 的组装（原方法改为委托，签名不变），新增 `evidence_link` 来源与 `linked_wp_count`。`attachment_service.py` 现 1432 行（白名单 1391，门限 1460），挪出后回到白名单以下并下调登记值。侧栏附件页签改读统一视图；process-record 的底稿附件读端点保留（零调用方，只读、有底稿门），写端点 `link-attachment` 删除。

**ADR-AEI-08 前端一个上传函数、一个按底稿共享的链接仓。** `components/attachment/workpaperEvidence.ts` 的 `uploadWorkpaperEvidence` 是底稿内上传的唯一写法；`composables/useWpEvidenceLinks.ts` 按（项目, 底稿）缓存链接列表，同一底稿的所有 `ItemAttachment` 只发一次请求（49 个标签里有表格每行一个的用法；同 URL 并发 GET 还会被 http 去重取消先发的那个）。上传 / 移除后失效并重取。

## 3. 接口

### 3.1 入口上传

`POST /api/projects/{project_id}/workpapers/{wp_id}/evidence/upload`，multipart：`file`；可选 `evidence_type`、`sheet_name`（≤100）、`cell_ref`（≤100）、`page_ref`（≤50）。

```
200 {"attachment": {..._to_dict..}, "evidence_link": null | {..链接..}}
400 位置字段超长 | 404 底稿不属于路径项目 / 已删除 | 413 超上限 | 422 上传策略或证据类型 | 423 归档
```

### 3.2 OCR 端点

26 个路由签名加三个可选表单字段 `evidence_type`、`evidence_sheet`、`evidence_cell`；处理统一为：

```
src = await intake_ocr_upload(db, wp_id=…, file=…, attachment_id=…, force_reocr=…, user=…,
                              native_type=<本端点类型>, native_prefix=<本循环编码>, …)
try:
    if src.reused: return <复用响应>
    text = (await UnifiedOCRService().recognize(src.path))["text"]
    … 大模型抽取（不变）…
    await finalize_linked_ocr_writeback(db, wp_id=…, linked_att_id=src.attachment_id, …)
finally:
    src.cleanup()   # 只删临时文件，不删附件原件
```

| 端点（`/api/workpapers/{wp_id}/…`，N2 为 `/api/n2-taxes-payable/{wp_id}/contract-ocr`） | 本循环编码 | 端点类型 |
|---|---|---|
| d4/contract-ocr、g1/contract-ocr、h3/contract-ocr | D4、G1、H3 | contract |
| d2/derecognition-ocr | D2 | contract |
| e1/account-list-ocr、commit-ocr、credit-ocr | E1 | support |
| e1/statement-ocr | E1 | bank_statement |
| e1/cutoff-ocr、large-check-ocr | E1 | voucher |
| f2/contract-ocr、f2-spe/contract-ocr | F2 | contract |
| f2-st/contract-ocr | F2 | stocktake |
| f2-val/contract-ocr | F2 | evidence |
| f3/contract-ocr | F3 | note |
| f4/contract-ocr | F4 | evidence |
| f5/contract-ocr、g8 / g9 / g10 / g11 contract-ocr、n2 contract-ocr | F5、G8…G11、N2 | voucher |
| h1/property-title-ocr、vehicle-title-ocr、h3/real-estate-title-ocr | H1、H3 | contract（与 H3 声明「产权 / 权属证明」同类） |
| h1/stocktake-summary-ocr | H1 | stocktake |

### 3.3 证据链接

- `GET …/evidence?sheet_name=&cell_ref=` → `{items:[{…链接, attachment:{id,file_name,file_size,file_type,attachment_type,ocr_status,created_at}}], total}`
- `POST …/evidence/link`、`…/batch-link`：校验见需求 3.2；`created_by` 字段删除（pydantic 默认忽略多余字段，旧前端照常可用）
- `DELETE …/evidence/{link_id}`：链接须属路径底稿
- 统一视图「本底稿已有」= 整稿关联 ∪ `reference_type='working_paper'` 指向本底稿 ∪ 本底稿证据链接 ∪ 本底稿函证挂载

### 3.4 统一视图新增字段

```
item.sources ⊇ ["evidence_link"]，item.evidence_positions = [{link_id, sheet_name, cell_ref, page_ref, evidence_type}]
item.linked_wp_count = 附件出现的底稿数（整稿关联 ∪ 行级证据链接 ∪ reference，去重；实施修订，见 §8.2-1）
```

主来源优先级 associated > referenced > confirmation > evidence_link。

## 4. 前端

| 文件 | 改动 |
|---|---|
| `components/attachment/workpaperEvidence.ts`（新） | `EVIDENCE_TYPE_OPTIONS`、`uploadWorkpaperEvidence`、`itemCellRef`、位置标签 |
| `composables/useWpEvidenceLinks.ts`（新） | 共享链接仓（单飞、失效、移除） |
| `ItemAttachment.vue` | 用上面两者；props 加 `evidenceType`、`readonly` |
| `WorkpaperAttachmentsDrawer.vue`、`workpaperAttachmentSources.ts` | 证据类型选择、「上传此类证据」、位置标签、提示文案 |
| `AttachmentTabPanel.vue` | 统一视图；关联底稿悬停再取 |
| `EvidenceLinkPanel.vue` | 文件名 / 位置；从本底稿附件选择；类型选项统一 |
| `AttachmentDropZone.vue`、`AttachmentDropZoneOverlay.vue` | 入口上传（后者零挂载，一并改免得守卫豁免） |
| F2 IPO ×2、F3 逾期、F4 ×3 | 行内上传改入口（位置 = 原 objectId 的表页与槽位），识别仍带 `attachment_id` |
| C22 ×2、C23、C24、C25、C26、C 控制测试子页 | 入口上传（位置 = 表页 + 样本序号），把附件 id 交给随后的识别调用 |
| `GtB212Evaluation.vue`、`LedgerPenetrateDrawer.vue` | 入口上传；B2-12 附件链接改 `downloadAttachment` |
| 客户访谈、固定资产 / 存货监盘弹窗 | `http-request` + 入口；按回执取 id |
| `ocrAttachmentLinkage.ts` | `uploadAndAssociateToWorkpaper` 改入口；`buildLinkedOcrFormData` 不前置上传 |
| `AttachmentManagement.vue` | `linked_wp_count` 统计；`ACCEPT_TYPES` 加音视频 |
| `commonApi.ts`、`apiPaths/system.ts` | 删 `linkAttachment` |
| `__tests__/NativeLoadBearerGuard.spec.ts` | 按 `<template>` 块取模板 + 自检样例；新扫出的逐条处理 |
| `__tests__/LegacyUploadCallersGuard.spec.ts`（新） | 旧上传端点调用方白名单 |

## 5. 权限

| 操作 | admin / lead / supervisor | 编制人（assignee） | 复核人 | 非成员 |
|---|---|---|---|---|
| 入口上传、OCR 建附件 | 允许 | 允许 | 404（统一门） | 403 |
| 证据链接列表 | 允许 | 允许 | 允许 | 403 |
| 证据链接增删 | 允许 | 允许 | 404 | 403 |
| 已有附件整稿关联 / 解除整稿关联 | 允许 | 404（原矩阵） | 404 | 403 |
| 归档项目上的写 | 423 | 423 | — | — |

## 6. 变异

| # | 改动（磁盘注入，逐字节恢复） | 预期红 |
|---|---|---|
| 1 | OCR 入口去掉「已关联本底稿」校验 | 他项目 / 未关联 id ⇒ 404 用例 |
| 2 | OCR 入口不建附件（返回临时 id） | 不带 id 仍建附件用例 |
| 3 | 行级上传同时写整稿关联 | 行级只写链接用例 |
| 4 | 链接 `created_by` 取请求体 | 伪造 created_by 用例 |
| 5 | 删除链接不限路径底稿 | 跨底稿删除 404 用例 |
| 6 | 统一视图去掉 `evidence_link` 来源 | 新来源用例 |
| 7 | `_linked_wp_ids` 不认证据链接 | 只有行级链接时的可见性用例 |
| 8 | `version_chain` 参数被忽略 | 同名两次上传均为版本 1 用例 |
| 9 | 解除整稿关联不删本底稿证据链接 | 全部解除用例 |
| 10 | 证据类型缺省不看声明 | 单一声明缺省用例 |
| 11 | `ItemAttachment` 改回按 `title` 过滤 | 上传后可见组件用例 |
| 12 | 链接仓去掉单飞 | 多实例一次请求用例 |
| 13 | 原生加载守卫回到「`<script` 之前即模板」 | 扫描器自检 |
| 14 | 底稿组件新增一处旧上传调用 | 旧上传调用方守卫 |

## 7. 测试

后端新目录 `backend/tests/attachment_evidence_intake/`：`test_evidence_upload_endpoint.py`、`test_ocr_intake.py`（参数化覆盖 26 个路由的「不带 id 建附件 + 无旁路文件」，识别与大模型打桩在被测函数下一层）、`test_evidence_links_api.py`、`test_wp_attachment_view.py`、`test_visibility_evidence_links.py`、`test_evidence_types.py`。角色场景复用 `tests/procedure_delegation_visibility` 的造数辅助。前端：`ItemAttachment.spec.ts`、`useWpEvidenceLinks.spec.ts`、`workpaperEvidence.spec.ts`、两个守卫；受影响的既有用例按新调用改写并在本节记录。

## 8. 实施记录

### 8.1 交付

| 层 | 内容 |
|---|---|
| 入口 | `services/workpaper_evidence_intake.py`：证据类型登记表与缺省、位置校验、体量上限、底稿装载、`create_evidence`、OCR 前半段 `intake_ocr_upload` / `record_ocr_response`；`attachment_service` 加 `version_chain`；删 `provision_wp_linked_attachment`、`services/workpaper_side_storage.py` |
| 证据链接 | 路由 / 服务重写（上传端点、`created_by` 取会话、底稿须属路径项目、删除限路径底稿、附件须已在本底稿）；V213 / R213（`cell_ref` 100、外键 NOT VALID、三个索引） |
| OCR | 25 个路由文件 26 个路由改走入口；原来不写回的 8 个补写回；早退分支写回 `failed` |
| 视图 | `services/attachment_wp_view.py`（`evidence_link` 来源、`evidence_positions`、`linked_wp_count`、`linked_workpapers`）；解除整稿关联连带删本底稿链接；`_linked_wp_ids` / `is_attachment_linked_to_wp` 认证据链接；删 `POST /api/process-record/link-attachment` 与台账条目、补上传端点条目 |
| 前端 | `components/attachment/workpaperEvidence.ts`、`composables/useWpEvidenceLinks.ts`；`ItemAttachment` 重写；抽屉（类型选择、「上传此类证据」、行级位置）、侧栏两个页签、附件管理统计；21 处上传点迁移（C 类 7 处把附件 id 交给识别）；删 `linkAttachment`、`uploadAndAssociateToWorkpaper`；守卫 `LegacyUploadCallersGuard.spec.ts` |
| Spec A 遗留 | 白名单 / `ACCEPT_TYPES` 加 11 种音视频；原生加载守卫去掉 script / style 块取模板，新扫出 `D2VcCardView.vue` 缩略图（字段无写入方，登记 dormant）；B2-12 步骤附件改已鉴权下载 |

### 8.2 偏离设计

1. **`linked_wp_count` 口径**：设计写「整稿关联的底稿数」。行级上传只写证据链接（ADR-AEI-02），只数整稿关联会把它们算成「未关联底稿」，附件管理页统计照样失真 ⇒ 改为整稿关联 ∪ 行级证据链接 ∪ `reference` 去重（函证挂载归函证模块，不计）。需求 4.1 已同步修订。
2. **侧栏悬停端点**：`GET /api/process-record/attachments/{id}/workpapers` 原先只要登录，且只读 `reference`（至多一行，侧栏「×N」徽标从未出现过）。改为按附件所属项目判 readonly → 附件 wp-link 隔离 → 与 1 同口径的清单，逐张 `try_gate_wp` 只列当前用户可见的底稿（与底稿搜索同口径，不泄露不可见底稿的编码 / 名称）。
3. **行内「移除」**：C 类、B2-12 等把附件引用记在检查表 JSON 里的组件，行内移除只清表单引用，证据链接仍在（附件抽屉可解除）。行身份 `row:{id}` 与行删除联动属 Spec C / D。
4. **`buildLinkedOcrFormData`**：保留 `projectId` / `wpId` 参数（忽略，兼容 9 处调用），新增 `evidenceType` / `evidenceSheet` / `evidenceCell` 透传；不前置上传后由识别端点建附件（整稿关联）。
5. **`workpaper_item` 附件类型**：已无写入方，留在登记表供历史数据筛选；Spec A 类型字面量扫描器补认 `native_type=` 写法。
6. **删除端点与行级证据**：只挂在行上的附件删除前先过底稿可见性门（与整稿关联同口径）。Spec A `test_delete_referenced_attachment_is_409` 的 evidence_links 例把门换放行桩（SQLite 世界统一门不可用），隔离本身由 PG 用例覆盖。
7. **附件管理「关联到底稿」（走查中发现，设计未列）**：弹窗按底稿索引搜，选项值取了索引条目的 `id`（索引 id），关联端点要底稿 id ⇒ 任何底稿都 404「资源不存在或不可访问」。改为取条目的 `wp_id`，没生成底稿的索引条目不列出（`workpaperEvidence.associateCandidates` + 单测）。
8. **抽屉小修（走查中发现）**：空态按钮原文「前往附件管理上传并关联」，抽屉里已能直接上传 ⇒ 可编辑时提示「可在上方选择证据类型后上传」，按钮改为「前往附件管理关联已有附件」；四个图标按钮只有悬浮提示，补带文件名的 `aria-label`；第二个 `<script>` 块重复注册图标（vue-tsc 8 条 TS2300）删除。

### 8.3 受影响的既有用例

- 后端：附件↔底稿关联 wave1 / 2 / 3 / 4 / 7 与 characterization、`test_metabase_attachments`、`test_attachment_c3_opaque_locator` 的 SQLite 建表补 `evidence_links`（统一视图读证据链接不 fail-open）；wave7 函证 fail-open 用例只让函证那条查询抛错；Spec A `test_attachment_destructive_guard` / `test_upload_policy` / `test_side_storage_wp_id`；OCR 旧用例 d4 / f2 ×3 / e1 / g11。
- 前端：`WorkpaperAttachmentsDrawer.spec`、`GtC22ControlSheet.evidence.spec`（桩改在入口函数一层，并断言识别带附件 id）、`AttachmentDropZoneOverlay.spec`、`ocrAttachmentLinkage.spec`。
- Spec A 遗漏：`visibility_go_live_hardening/test_task4_native_authz_audit.py::test_ocr_fields_deny_outsider_404_before_service` 在 HEAD 上即红（403 ≠ 404）。Spec A 需求 2.3 给 ocr-fields 加了项目门（未缓存要 edit），成员行缺省 readonly，越权成员在项目门就 403、走不到底稿门；该用例只在 PG 上跑，Spec A 的回归没覆盖到。改为给该成员 edit 后断言底稿门 404（detail 为统一的「资源不存在或不可访问」），另加只读成员在项目门 403 的用例，两条都把 OCR 服务换成「被调用即失败」的桩；去掉项目门的变异让后一条红在 `404 == 403`。

### 8.4 变异（§6）

独立变异 worktree（分离头 = HEAD + 本 spec 文件），不碰共享开发服务；每条单独一条命令，注入 → 跑判据 → 逐字节恢复并核 sha256，14 条全部一致。

| # | 红在 |
|---|---|
| 1 | `test_foreign_or_unlinked_attachment_is_404` ×4 |
| 2 | `test_upload_creates_linked_attachment_and_writes_back` 26 个路由 |
| 3 | `test_row_level_upload_writes_only_evidence_link` |
| 4 | `test_create_link_takes_creator_from_session` |
| 5 | `test_delete_link_scoped_to_path_wp` |
| 6 | `test_view_includes_row_evidence_with_positions` |
| 7 | `test_row_only_evidence_follows_its_workpaper`（PG） |
| 8 | `test_intake_uploads_are_independent_attachments` |
| 9 | `test_unlink_removes_row_links_of_this_wp_only` |
| 10 | `test_default_evidence_type` ×3、`test_requested_type_wins` |
| 11 | `ItemAttachment.spec` 7 例全红（换回 HEAD 版） |
| 12 | 「同一底稿多个实例只发一次列表请求」「同一底稿并发加载共用一次请求」 |
| 13 | 守卫自检「脚本在前的 SFC 也扫模板」+ 登记失效 |
| 14 | `LegacyUploadCallersGuard` A |

另：单区域 vue-tsc 探针文件 3 条 TS2322（证明该配置真在做类型检查）。

### 8.5 走查（任务 11）

**迁移**：共享库经 `MigrationRunner(...).run_pending()` 应用 V213（独立迁移目录只放 V213，不顺带别人的迁移）；核对 `cell_ref` 长度 100、三个索引、两条外键（NOT VALID）。

**环境**：本地线 HEAD 打不开带程序表的底稿 —— `GtAProgramConsole.vue`、`useProgramRowDelegate.ts` 引用的 `useProgramOverrideTarget.ts`、`useScopeExpansionRetry.ts`、`commonApi.ensureProgramRowTask` 只在远端线上，后端 `template_engine.py` / `recycle_bin.py` 引用的 `procedure_scope_retention` 等 5 个模块同样只在远端线（lazy import 守卫在 HEAD 上即红）；共享主树 3030 同样受影响。走查因此在**远端线候选树**（远端分支头 + 本 spec 改动，也就是要推送的那棵树）上做：后端 9988（进程环境载入仓库根 `.env`，不跑 lifespan）、前端 3038（独立 `.vite`），浏览器只开这一个源。共享库缺远端线的 V206 / V207 / V209，走查路径不碰这三张表。

**造数**：经平台接口建【测试】项目；按编码生成要求试算表 > 0 行，插 2 行最小试算表（清理时按 id 删）；`generate-from-codes` 生成 F3、F4。

| 走查项 | 结果（请求 / 界面证据） |
|---|---|
| OCR 建附件（F4-9「上传并识别」） | `evidence/upload`（F4-9 · 第 1 项，合同 / 协议）→ `f4/contract-ocr` 带该附件 id，识别文本写回同一附件、没有第二个附件；确认框「附件已关联到“当前融资行”」 |
| 行级上传与移除（`ItemAttachment`） | 上传后列表 2 个；移除确认「只移除与本行的链接，附件本身仍保留在项目附件中」→ 删链接；被移除的附件 `linked_wp_count` 0、抽屉不再列出 |
| 抽屉选类型 / 声明满足 | 类型下拉 8 项中文；选「凭证 / 原始单据」上传 ⇒ 整稿关联（「关联证据」「底稿引用」）；F3 缺「票据影像」⇒「上传此类证据」⇒ 变 ✓；解除关联确认文案；解除最后一个后空态 |
| 侧栏两个页签 | 附件页签列统一视图（带「行级证据」）；证据页签列链接，「关联附件」把整稿附件挂到 F4-5 · B6（盘点 / 监盘记录） |
| 附件管理统计 / 悬停清单 | `linked_wp_count` 1 / 0 / 1，「已关联底稿 2」；修 §8.2-7 后把行级附件再关联到 F3，侧栏徽标「📋 ×2」悬停 ⇒ 收紧后的端点返回 F3、F4 两张 |

走查中修了 §8.2-7、§8.2-8 两处，修后在浏览器里复验。截图存 `evidence/`（6 张）。

**清理**：逐底稿解除关联 → 删附件 → 回收站永久删除（5 个）→ 删项目（软删）→ 按 id 删 2 行试算表；对账 `attachments` / `attachment_working_paper` / `evidence_links` / `attachment_versions` / 试算表行全部为 0。项目软删后底稿行仍在（文件在临时 worktree 里，随之删除）。

### 8.6 守卫与回归（任务 10）

**守卫**（本地线 HEAD + 本 spec 与纯 HEAD 各跑一遍）：鉴权三维基线、请求体维、附注编辑门、x3 台账、委派可见性 task16 / 18、函数全局名棘轮、模块别名、lazy import、行数门、数据锚点 `resync_data_line_anchors --check` —— 两边失败集合相同（lazy import 两条，指向本地线缺失的 5 个模块）；ocr-fields 一条见 §8.3（Spec A 遗漏，已修）。基线常量无需下调（各维计数不变）。静态吞异常守卫两边函数级违规数相同（69 = 69）。

**扩大回归**：按文件名与内容（OCR 路由、旁路目录、证据链接、附件服务、可见性入口等 17 个标记）选出 494 个测试文件，25 个一片、单片超时 20 分钟，在「HEAD + 本 spec」上跑；失败用例的文件（82 个）再在纯 HEAD 上跑，按用例 id 逐条比对：

- 只在本 spec 树上失败的 8 条：`test_office_preview_endpoint.py` 7 条 —— SQLite 建表缺 `evidence_links`，预览端点的附件可见性门查行级链接报 no such table（与 §8.3 同类，漏改的一个文件，已补，复跑 7 条全过）；`test_h2_interest_cap_engine_pbt.py` 1 条 —— hypothesis 在本树的样例库里找到反例（利息 1、闲置收益 2 时引擎给 0、用例期望 −1），把同一样例库拷到纯 HEAD 上同样红，属既有缺陷，与本 spec 无关。
- 其余 419 条两边相同（四表 / G7 / K 循环口径、A 类渲染、AI 生成 503、x3 / workpaper_sync 基线陈旧、lazy import 等）；只在纯 HEAD 上失败的 13 条是 `test_a171_*` 随运行顺序变化的状态依赖。

**远端线候选树**（远端分支头 f09205c49 + 本 spec，即推送的那棵树）：同一批文件（500 个，远端线多 6 个）20 片跑完，失败 341 条 / 79 个文件；79 个文件在纯远端头上再跑一遍逐条比对：

- 只在本 spec 树上失败的 1 条：`test_x3_roundtrip_live.py::TestGS7RoundtripLive::test_roundtrip_all_16_sheets`。该文件单独重跑，本 spec 树与纯远端头都是 10 条全过 ⇒ 片内运行顺序相关，与本 spec 无关。
- 只在纯远端头上失败的 13 条同为 `test_a171_*` 顺序依赖；其余 327 条两边相同（四表口径、workpaper_sync 写入方台账陈旧、吞异常守卫等，均为远端线既有失败）。

### 8.7 范围外 / 遗留

- `AttachmentLinkService.link_attachment_to_workpaper` 路由删除后无生产调用方，被 wave1 / 7 / characterization 钉住 ⇒ Spec G 清理。
- 附件管理页行内图标按钮（预览 / OCR 确认 / 关联底稿 / 下载等）同样只有悬浮提示、没有可读名（本 spec 只改了抽屉里的四个）。
- 本地线与远端线分叉期间，本地线 HEAD 引用了只在远端线上的模块（见 §8.5），合并两条线时一并解决，不在本 spec。
- legacy `list_versions` 仍按文件名分组（Spec G）。
- 序时账穿透抽屉按当年年度取数（全仓「按今年传年度」同类问题，另立）。
