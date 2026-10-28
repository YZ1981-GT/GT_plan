# 设计：归档与 A 类证据（attachment-archive-and-a-class-evidence）

需求见 `requirements.md`。本文只写决策、结构与验证口径，不复述需求。

## 1. 总览

```
完整性检查 ──┐                      ┌─ manifest.json（逐项 sha256）
             ├─ archive_inventory ──┤
打包步骤 ────┘   （同一份清单）       └─ archive_package_builder → storage/archives/{pid}/{job}.zip
                                                     │
编排：gate → package → push_to_cloud? → lock → purge_local?      下载：GET …/archive/jobs/{job}/package
```

新增模块（均为新文件，避开超行数门的旧文件）：

| 文件 | 作用 |
|---|---|
| `backend/app/services/archive_inventory.py` | 项目归档清单：底稿文件 / 现行附件 / 交付件的可读性判定；孤儿文件扫描 |
| `backend/app/services/archive_package_builder.py` | 按清单 + 数据快照 + 章节生成器写 zip 与 manifest |
| `backend/app/services/archive_completeness_evidence.py` | 完整性检查新增 5 类 |
| `backend/app/services/qc_rule_attachment_sufficiency.py` | QC-17 规则（从 `qc_engine.py` 移出） |
| `backend/app/services/checklist_index_parser.py` | A30 电子底稿归档检查表解析 |
| `backend/app/services/checklist_template_loader.py` | 核对表模板加载统一入口（A30 → xlsx 列映射 → docx） |
| `backend/app/services/attachment_file_purge.py` | 彻底删除后删物理文件 |
| `backend/app/services/archive_gate.py` | 归档门禁：就绪检查 + 完整性自检阻断项，服务端现算（走查补，ADR-AE-14） |
| `audit-platform/frontend/src/utils/passwordConfirm.ts` | 编程式二次确认 |
| `audit-platform/frontend/src/composables/useArchiveChecklistSuggest.ts` | A30「按项目底稿建议」 |

## 2. 决策（ADR）

| 编号 | 决策 | 否决项与理由 |
|---|---|---|
| ADR-AE-01 | 归档包从数据库清单构建，完整性检查与打包共用 `archive_inventory` | 保留目录打包：真库多数底稿不在 `storage/projects`，附件 / 交付件 / 数据快照全缺；两套判定会让「检查通过、打包缺件」 |
| ADR-AE-02 | 缺件即失败：清单任一项读不到、章节生成器抛错 ⇒ 打包步骤失败；生成器返回空记「跳过」 | 缺件跳过照样成功：归档包是审计档案，静默缺件比失败更糟 |
| ADR-AE-03 | 步骤 `gate → package → push_to_cloud → lock → purge_local`；锁定放在打包与推送之后 | 先锁后打包：打包因缺件失败时项目已锁，用户无法补救 |
| ADR-AE-04 | 锁定 = 项目状态 `archived` + `archived_at` / `retention_until` + 未删除底稿状态 `archived`，失败即任务失败 | 只写保留期：现有编辑锁看的是项目状态，归档后仍可编辑 |
| ADR-AE-05 | 云端推送上传归档包本身（`CloudStorageService.upload_archive_package`，失败抛错；配置了 sftp / s3 但缺依赖库直接报错，不退回本地复制） | 继续上传 `storage/projects` 目录：与归档包内容不一致，且吞异常 |
| ADR-AE-06 | 删除 3 个旧归档端点与 `WpStorageService.archive_project`、`ProjectArchiveService`（删后 grep 0 调用方） | 保留 deprecated：只要登录即可对任意项目归档 / 锁底稿，前端已无调用方 |
| ADR-AE-07 | 密码错误改 403 + `error_code=PASSWORD_INVALID` + `attempts_remaining`（偏离 phase6 F6.3 的 401） | 前端给 verify-password 加豁免标记：401 是会话语义，任何客户端都会误判；且拦截器刷新后重发，一次输错计两次失败 |
| ADR-AE-08 | 前端 `requestConfirmationToken(title)` 动态挂载现有 `PasswordConfirmDialog`；归档 / 签字 API 的令牌参数必填（类型强制每个调用方先确认） | 每个页面各放一个对话框：5 处调用重复状态管理 |
| ADR-AE-09 | QC-17 按证据声明判定（`evaluate_wp_evidence_requirements`，与抽屉同一实现），无声明不出结论，严重程度不变 | 改提示：行为变更，规则本意是充分性 |
| ADR-AE-10 | 声明键 `=编码` 精确匹配且优先于前缀键；新证据类型 `signed`「签字件」 | 给 A16-1~7 逐个写空声明：配置加载会丢弃空列表，无法表达「不继承」 |
| ADR-AE-11 | A30 用独立解析模块，三个渲染入口改走 `checklist_template_loader` 一个函数 | 往 `checklist_xlsx_parser.py`（805 行，未登记白名单）里加分支：触发行数门；三处各写一遍分派会再次漂移 |
| ADR-AE-12 | 回收站彻底删除后按「路径在附件根内且无其他行引用（含已删除行）」删本地文件；Paperless 不删 | 只删行：孤儿文件长期堆积；不查引用：同一文件被版本行共用时会误删 |
| ADR-AE-13 | 解除归档 = 锁定的逆操作：锁定步骤把底稿原状态记进进度，解除时按最近一次成功作业的记录恢复（只动仍是「已归档」的、记录用过即标 `restored_at`），清归档时间 / 保留期；仍归档时成功作业才算幂等命中（走查补） | 只改项目状态：底稿恒只读、归档时间残留使独立性门禁跳过、准则切换被拒；恢复成固定状态：丢掉复核通过等原状态 |
| ADR-AE-14 | 门禁与向导「下一步」同口径服务端现算（`archive_gate`：就绪检查 + 完整性自检阻断项），客户端评估 id 只作记录（走查补） | 沿用评估 id + 退回导出门禁：「未就绪」的 id 退回后只评导出门禁 ⇒ 绕过向导可直接归档并锁定 |

## 3. 归档清单与打包

### 3.1 清单（`archive_inventory.build_project_inventory(db, project_id)`）

`InventoryEntry(category, source_id, label, arcname, local_path, paperless_document_id, status, reason)`，`status ∈ {ok, missing, skipped}`。

- 底稿文件：未删除底稿 JOIN `wp_index`。`resolve_wp_file(file_path, wp_code=None, allow_template_fallback=False)`：
  - `file` 且不在 `backend/wp_templates` 下 ⇒ ok；在模板库下或 `empty` ⇒ skipped「未生成底稿文件，仅收数据快照」；
  - `missing` / `path_rejected` / `type_mismatch` ⇒ missing，原因取 `VERDICT_LABELS`。
- 现行附件：本项目未删除附件，排除被其他未删除附件以 `previous_version_id` 指向的（已被新版本取代）。本地按下载同口径（记录路径 → `storage/` 相对路径，`is_file()`）；Paperless 记 `paperless_document_id`，打包时下载，Paperless 未启用 ⇒ missing「附件存于 Paperless，但 Paperless 未配置」。
- 交付件：`word_export_task` 状态 ∈ {confirmed, signed, archived} 且未删除；`file_path` 不可读 ⇒ missing。
- 孤儿文件 `orphan_files(db, project_id)`：附件根 `{ATTACHMENT_LOCAL_STORAGE_ROOT}/{pid}` 下的文件，不被本项目任何附件行（含已删除）的 `file_path` 解析到 ⇒ 孤儿。

### 3.2 包（`archive_package_builder.build_archive_package(db, project_id, job_id)`）

1. 清单有 missing ⇒ `ArchivePackageError(problems)`（逐项「类别｜名称｜原因」）。
2. 章节：逐个调用 `archive_section_registry.list_all()` 的生成器；抛错 ⇒ 记入 problems；`None` ⇒ skipped。
3. problems 非空 ⇒ 抛错，不留半成品文件。
4. 写 `storage/archives/{pid}/{job_id}.zip.part` → 改名 `.zip`。包内布局：章节文件在根；`10-底稿/{编码} {名称}{扩展名}`；`11-底稿数据/{编码}.json`（`parsed_data` + 核对表 `item_id/conclusion/remark/wp_ref`）；`40-附件/{附件id前8位}-{文件名}`；`50-交付件/{doc_type}-{id前8位}{扩展名}`；`manifest.json` 最后写。
5. `manifest.json`：`{project_id, job_id, generated_at, entries:[{category, source_id, label, arcname, size, sha256}], skipped:[{category, label, reason}]}`，`ensure_ascii=False`、`sort_keys=True`。
6. 返回 `PackageResult(path, sha256, size, manifest_hash, counts, skipped_count)`；编排写 `job.manifest_hash`、`job.output_url`，并 `persist_checks(export_id=str(job.id), [{file_path: 包绝对路径, sha256}])`。

## 4. 编排与下载

- `ARCHIVE_SECTIONS = ["gate", "package", "push_to_cloud", "lock", "purge_local"]`（`String(16)` 列，名称都 ≤ 16）。
- 进度写入换新字典：`job.section_progress = {**(job.section_progress or {}), name: {...}}`（原地改 JSONB 不落库）。`package` 步进度带 `path / sha256 / manifest_hash / counts`。
- `push_to_cloud`：从 `package` 进度取包路径，文件不存在或 sha256 不符 ⇒ 失败「归档包文件不存在或已被改动，请重新归档」。
- `lock`：项目状态、归档时间、保留期（+3652 天）、底稿状态批量更新；项目不存在 ⇒ 失败。
- 通知仍 fail-open；`_persist_integrity_hashes` / `_set_project_retention` 删除（职责并入 package / lock）。
- 失败原因 `failed_reason` 截断到 2000 字，完整问题清单在 `section_progress[步骤].problems`。
- 下载 `GET /api/projects/{pid}/archive/jobs/{job_id}/package`：`require_project_access("readonly")`；任务不属于该项目 / 未成功 ⇒ 404；文件不在或 sha256 与完整性记录不符 ⇒ 409；`FileResponse`，文件名 `{项目名}-归档包-{日期}.zip`（RFC 5987）。

## 5. 鉴权与旧端点

- 删：`data_lifecycle.archive_project`、`private_storage.archive_project`、`wp_storage.archive_project` 三个路由函数；`test_archive_deprecated.py` 改为断言三路由不再注册、编排端点仍在。
- `GET jobs/{id}`：`require_project_access("readonly")`；`POST jobs/{id}/retry`：`require_operation("archive:manage")` + `require_confirmation_token`；均校验任务属于路径项目。
- 鉴权基线守卫（`test_project_endpoint_authorization_baseline.py` 等）按现算更新，不新增豁免。

## 6. 二次确认

- 后端：密码错误 `HTTPException(403, {"error_code": "PASSWORD_INVALID", "message": "密码错误", "attempts_remaining": n})`；锁定 423 不变。
- `PasswordConfirmDialog`：请求带 `_silent: true`（对话框内提示，不弹全局）；403 → 剩余次数；423 → 锁定。
- `utils/passwordConfirm.ts`：`requestConfirmationToken(title?) → Promise<string | null>`，`createApp` 挂到 body 下的临时节点，确认 / 取消后卸载；`CONFIRMATION_TOKEN_HEADER = 'X-Confirmation-Token'`、`confirmationHeaders(token)`。
- `archiveApi.startArchiveOrchestrate(pid, body, token)`、`retryArchiveJob(pid, jobId, token)`、`signatureApi.signDocument(params, token)` 令牌必填；`SignatureBlock` 改用 `signDocument`。

## 7. 完整性检查新增类别

`archive_completeness_evidence.py` 产出 `CheckItem`（`wp_code / wp_name / assignee / status`，`status` 放中文明细）：

| 类别 | 判据 | 阻断 |
|---|---|---|
| `evidence_gaps` | 有声明的底稿 `evaluate_wp_evidence_requirements` 未满足的类型；带逐笔拆分的函证类型归下一类 | 否 |
| `unreplied_confirmations` | 函证拆分 `missing > 0`：「N 笔未回函且无替代程序」+ 前 3 个单位 | 否 |
| `unconfirmed_ocr` | 附件有识别结果（`attachment_ocr_text`）但 `is_confirmed` 为假 | 否 |
| `missing_files` | 清单 missing 项（与打包同一实现） | 是 |
| `orphan_files` | 附件根下本项目未被引用的文件 | 否 |

`CheckCategory.category` 的 Literal 扩 5 个值；`BLOCKING_CATEGORIES` 加 `missing_files`。每类查询失败只让该类为空并记 WARNING（与 `sampling_records` 同口径），`missing_files` 例外：查询失败 ⇒ 该类给一条「清单检查失败」阻断项，不放行。

## 8. QC-17

- `attachment_wp_view` 抽出 `_collect_items(svc, wp_id)`，`build_wp_attachment_view` 与新函数 `evaluate_wp_evidence_requirements(db, wp_id) -> list[dict] | None` 共用（含函证逐笔拆分，不算 stale）。
- `qc_rule_attachment_sufficiency.AttachmentSufficiencyRule`：规则号 / 名称 / 严重程度不变；无声明 ⇒ 无结论；未满足 ⇒ 一条结论「应收集证据未齐：{标签}（{类型}）…」。`qc_engine.py` 删原类、改为导入（文件 974 行未登记白名单 ⇒ 按改后真实行数登记，理由写明）。

## 9. 签字件与精确键

- `signed`「签字件」加入 `ATTACHMENT_TYPES`、`EVIDENCE_TYPES`、前端 `EVIDENCE_TYPE_OPTIONS`。
- `resolve_requirements_for_wp_code`：先查 `"=" + wp_code`，命中即返回；否则在不以 `=` 开头的键里取最长前缀。`_comment` 补写法说明。
- 声明：`=A16`、`=A10`、`A10-1`、`A9-1`、`A9-2`、`A8-1`、`A17-6`、`A17-7`、`A18-1`、`A18-2`，类型均 `signed`，标签按底稿写（如「管理层声明书签字件」）。

## 10. A30

- `checklist_index_parser.parse_index_checklist(path, wp_code)`：首个工作表第 5 行起；A 列编码去全部空白，B 列名称（`*` 开头或结尾 ⇒ `required=True`，展示时去掉 `*`），D 列为填写列；A 列以「项目合伙人」或「填表说明」开头即停止；编码首字母分节（A~N 对照表，未知字母归「其他」）；`item_id = A30-{编码}`，同编码第二次起 `-2`、`-3`。输出与 `GtChecklistTable` 现有结构同形（节 `conclusionMode` 取 completion：是 / 否 / 不适用）。mtime 缓存。
- `checklist_template_loader.load_checklist_template(wp_code)`：A30 → index 解析；`is_xlsx_checklist` → xlsx；否则 docx。`_checklist.py`、`_review_checklist.py`、`completion_phase.py` 三处改调它。
- 建议端点 `GET /api/workpapers/{wp_id}/archive-checklist/suggestions`（`require_project_access("readonly")` 按底稿所属项目判）：返回 `{item_id: "是"|"否"}`，依据本项目未删除底稿的 `wp_code` 集合。
- 前端 `useArchiveChecklistSuggest`：只对 A30 显示按钮；空项填建议值并走现有保存；已填且与建议不一致的列表提示；只读隐藏。

## 11. 回收站物理删除

`attachment_file_purge.unlink_unreferenced_files(db, file_paths)`：在提交之后调用；对每个本地路径（跳过 `paperless://`）解析到绝对路径，必须在 `ATTACHMENT_LOCAL_STORAGE_ROOT` 内（`ensure_within_root` 同口径），且 `attachments` 表（含已删除）没有其他行的 `file_path` 解析到同一路径 ⇒ `unlink`；返回 `{deleted, kept_referenced, skipped_outside_root, failed}`，失败只记日志。三个彻底删除路径（单条 / 批量 / 清空）先收集附件路径、删行、提交、再调用。

## 12. 前端

- `ArchiveWizard.vue`：启动 / 重试先 `requestConfirmationToken('归档确认')`，取消不发请求；任务 id 取 `resp.id`；成功后「下载归档包」用 `downloadFile(output_url)`；类别与失败步骤显示中文（`archiveLabels.ts` 一张表，向导与完整性报告共用）；启动请求超时放宽到 10 分钟。
- `NativeLoadBearerGuard.spec.ts` 里 `ArchiveWizard` 的 `output_url` 休眠登记删除（改为经 `downloadFile` 带令牌下载）。

## 13. 验证

- 后端单测（SQLite 世界 + 真 PG 只读探针）：清单判定六种情形、打包成功 / 缺件失败 / 生成器抛错 / 生成器返回空、manifest 与包 sha256、编排锁定 / 失败不锁 / 重试续跑 / 进度落库、下载鉴权与 409、旧端点不再注册、retry 需确认令牌、verify-password 403、完整性 5 类、QC-17 三情形、精确键优先级、签字件三处一致、A30 解析（真模板）与建议、物理删除四情形。
- 前端单测：`passwordConfirm`（确认 / 取消 / 卸载）、对话框 403 / 423 分支、向导令牌与 id、签字三处带令牌、A30 建议只填空项。
- 变异（磁盘注入，逐字节恢复）：包内漏写附件、缺件改跳过、锁定不改状态、进度原地改、retry 去掉确认、403 改回 401、QC-17 回退计数、精确键失效、A30 漏 `-2` 后缀、删除不查引用、建议覆盖已填项等，每条须打红且红在预期断言。
- 浏览器走查：【测试】项目跑完整归档（密码框 → 包下载 → 项目只读），完整性 5 类显示，A30 建议，签字件上传，回收站彻底删除后文件消失；走查数据清理并对账。

结果（2026-10-28）：
- 磁盘变异 65 条（后端 E1~E46 / 前端 V1~V19，`tmp_attachment_spec_b/probes/mut_e.py`）：64 条红在预期断言、逐字节复原；V3（去掉 `passwordConfirm` 的 `settled` 守卫）等价 —— Promise 只认第一次 resolve、`app.unmount()` 重复调用无副作用，守卫保留并注释。
- 走查在远端线候选树（`00debcc4d` + 本 spec）+ 独立无头浏览器上做（前端 3038 → 后端 9988），【测试】归档与A类走查_2025：向导完整性 10 类中文、A30 15 节 203 项建议填入并刷新后仍在（A16 / A30 / D0 / E1 = 是）、A16 缺签字件 → 按此类上传 → 满足、回收站彻底删除后磁盘文件消失（回执 `file_cleanup.deleted=1`）、密码输错 403 不登出且显示剩余次数、门禁失败页中文步骤与逐项原因、重试取消不发请求、成功作业页下载的包 sha256 与作业记录一致（11 项，manifest 逐项可复算）、归档后横幅只读、横幅解除归档（原因 + 项目名称）后 4 张底稿恢复「编制中」、解除后再归档新建作业（不命中旧作业）。如实说明：成功作业是门禁修复前产生的 —— 走查用 devtools 把向导强制到第三步，旧门禁对「未就绪」的评估 id 退回只评导出门禁、放行（即 §14-6④），修复后同一操作在门禁步骤失败；打包 / 推送 / 锁定 / 下载代码不受该修复影响。数据经平台路径清理，对账见 §14-9。

## 14. 实施差异

1. `SignatureBlock.vue` 未改（需求 4.3 已改写）：它发 `{object_type: 'workpaper_sheet', object_id: "${wpId}:${sheet}", role}`，后端 `SignRequest` 要 UUID `object_id` + `signer_id` + `signature_level`，且替不是平台用户的出纳签字 —— 签字模型不兼容，另需产品决定，带令牌也签不成。
2. A30 建议端点放在 `completion_phase.py`：`GET /api/projects/{pid}/workpapers/{wp_id}/archive-checklist/suggestions`（readonly；注册级 `dedicated_wp_gate` 同样生效），不另建路由（免改 router_registry）。
3. 云端目录的审计年度取 `resolve_project_audit_year`，取不到即推送失败「项目未设置审计年度…」，不按今年兜底（audit-year-calendar-fallback 棘轮）。远端线的棘轮测试是重做过的版本（`FROZEN_TOTAL_CAP=0`），本 spec 不改它。
4. 覆盖台账 `wp_bound_entry_coverage.json` 不更新（其漂移测试自 2026-10-07 起跳过，重生成会吸收别的会话的漂移）；写入方清册 / resolver 矩阵不重生成（HEAD 上已红，非本 spec 引入）。
5. 顺修 `GtChecklistTable.vue` 既有编译错误：`withDefaults` 引用 `<script setup>` 里的常量（3f7d857d2 起整页加载失败），常量移到 `checklistTypes.ts`；全仓 2476 个 SFC 扫描余 0 处。`MyTemplatesDialog.vue` 在 `<script setup>` 里 `export`（无引用，属高级查询会话）只登记不改。
6. 走查补修（都配了用例与变异）：①A30 结论「是 / 否 / 不适用」保存恒 422 —— 核对表保存的默认白名单只有 Y / N / X/I / X/W / N/A，补 `A30-` / `A17-5-` 分支 ②章节适用性弹窗直接「确认」什么都不存 ⇒ 每次打开都再弹（只存改过的章节）；只读也弹 ③「本章节批量标记」在是 / 否 / 不适用表里仍给 Y / X/I… ④门禁可被绕过（ADR-AE-14）⑤解除归档后底稿恒只读、归档时间残留、再归档命中旧作业（ADR-AE-13）；横幅「解除归档」只发一个没有页面监听的事件 ⇒ 改为横幅内完成（原因 → 输入项目名称 → 接口 → 刷新）⑥包内名双空格（模板名带前导空格）。
7. 测试隔离：A30 用例按生产注册挂载、统一门拒绝时 `DenialResponder` 用全局引擎另开会话写 outbox ⇒ 连接留在全局池且绑在已关闭的事件循环上，后面用全局引擎的 `test_checklist_responses_crud` 报 Event loop is closed（此前被当成偶发）。改为截住 `_write_outbox`（仓内既有写法）；开发库 outbox 未留行（写入因外键失败）。
8. 走查过程勘误：头几轮前端代理落到共享后端 9980（`vite.wt.config.ts` 只改了端口，基础配置缺省代理 9980），上传文件落进主树 `backend/storage`。已经 9980 的平台接口解除关联 / 删除 / 彻底删除，残留的一个孤儿文件手工删除并核对目录为空；配置改为在文件里定死 9988 后全部步骤重走。
9. 走查数据对账：附件 / 整稿关联 / 行级链接 / 版本行 / 插入的试算表行均为 0；项目软删，底稿 4、核对表填写 218、归档作业 2、包指纹 1 随项目保留（平台回收站可恢复）；包与云端本地副本在候选树目录里，随 worktree 删除。
10. 范围外发现（未改）：基线上已红、与本 spec 无关的用例 —— `test_rotation_retention::TestRetentionCheck` 两例（`data_lifecycle_service` 比较带 / 不带时区的时间）、`test_wopi_working_paper_qc_review` 跑在 `test_checklist_responses_crud` 之前时后者 Event loop is closed（全局连接池泄漏，基线 worktree 同样复现）；ACNR 的 `acnr/immutability.record_project_registry_version`（归档时锁定目录版本，现为进程内字典）注释要求归档流程调用，生产代码 0 调用，归 ACNR 会话；`data_lifecycle` 的恢复 / 彻底清理端点只要登录；`completion_phase.py` 其余端点只要登录；`_cascade_delete_project` 清理不删附件文件；A17-5 各表在渲染配置里是 skip（后端已能存其是 / 否值）；向导第三步「就绪检查 已通过」是写死的标签（正常流程只有通过才到得了）；解除归档请求体的 `password_confirm` 字段未使用。
11. 推送后收尾：第 10 项的保留期比较已修 —— `data_lifecycle_service.purge_project_data` 把带时区的当前时间与去掉时区的保留期直接比较，一比较就 TypeError（保留期内外都报 500；本 spec 归档成功即写 `retention_until`，归档过的项目彻底清理恒失败）。改为两边都按不带时区的 UTC（`time_utils.utcnow()`；带时区的值先换算到 UTC 再去时区），补 PG 带时区返回值的回放用例（+08:00 表示的一小时前过期值，直接去时区会误判仍在保留期）；变异 3 条全红；同类写法全仓扫描（同一函数内带时区的当前时间与去时区的值相比 / 相减）仅此一处。`test_data_lifecycle_router` 两例（建项目缺 `company_code` / `short_name`）基线同红，未改。
