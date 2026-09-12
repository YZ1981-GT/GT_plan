# Implementation Plan: 自定义 Excel 模板摄取与整册同步闭环

## Overview

实施顺序为“真实基线 → scope/审批/政策 → multipart/quarantine → package/semantic preflight → 四生命周期 → mapping/adapter/candidate → 整册表示 → visibility saga → F-SHELL UI 与双向 → merge/version/retention → 变异/浏览器 → X evidence”。所有任务 required。

本 spec 不复制 G-C0 contracts、guidance consumer、F-SHELL 或 sync/version kernel。外部 gate 未完成时任务标 BLOCKED，不以 custom 特供实现绕开。

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 0, "name": "真实生产基线", "tasks": [1]},
    {"wave": 1, "name": "scope、capability 与审批", "tasks": [2]},
    {"wave": 2, "name": "政策与 scanner provenance", "tasks": [3]},
    {"wave": 3, "name": "三入口、multipart 与 quarantine", "tasks": [4]},
    {"wave": 4, "name": "package scanner 与 lifecycle repository", "tasks": [5, 7]},
    {"wave": 5, "name": "semantic preflight", "tasks": [6]},
    {"wave": 6, "name": "mapping、identity 与 adapters", "tasks": [8]},
    {"wave": 7, "name": "candidate 静态预览与 guidance", "tasks": [9]},
    {"wave": 8, "name": "整册项目表示与 namespace", "tasks": [10]},
    {"wave": 9, "name": "pending visibility finalize saga", "tasks": [11]},
    {"wave": 10, "name": "公共 UI 与双向接线", "tasks": [12, 13, 14]},
    {"wave": 11, "name": "merge 与 remap", "tasks": [15]},
    {"wave": 12, "name": "版本、pin、withdraw 与回滚", "tasks": [16]},
    {"wave": 13, "name": "引用图、retention 与 artifact 安全", "tasks": [17]},
    {"wave": 14, "name": "行为、变异与 Playwright", "tasks": [18]},
    {"wave": 15, "name": "X milestones 与归档", "tasks": [19]}
  ],
  "critical_path": [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 13, 15, 16, 17, 18, 19],
  "hard_dependencies": {
    "2": [1],
    "3": [2],
    "4": [2, 3],
    "5": [3, 4],
    "6": [5],
    "7": [2, 4],
    "8": [6, 7],
    "9": [7, 8],
    "10": [7, 8, 9],
    "11": [2, 7, 9, 10],
    "12": [8, 9, 10],
    "13": [8, 10, 11],
    "14": [10, 11],
    "15": [13, 14],
    "16": [11, 15],
    "17": [7, 11, 16],
    "18": [5, 6, 8, 9, 11, 12, 13, 14, 15, 16, 17],
    "19": [18]
  },
  "parallelizable": [
    [5, 7],
    [12, 13, 14]
  ],
  "external_dependencies": {
    "consumes": [
      {"milestone": "G-C0", "producer_spec": "workpaper-guidance-content-closure", "required_by_tasks": [2, 9], "on_missing": "BLOCKED"},
      {"milestone": "G-ID", "producer_spec": "workpaper-guidance-content-closure", "required_by_tasks": [8, 10], "on_missing": "BLOCKED"},
      {"milestone": "G-HANDOFF-CONSUMER", "producer_spec": "workpaper-guidance-content-closure", "required_by_tasks": [11], "on_missing": "BLOCKED"},
      {"milestone": "F-SHELL", "producer_spec": "workpaper-page-formula-toolbar-closure", "required_by_tasks": [12, 18], "on_missing": "BLOCKED"},
      {"milestone": "SYNC-UNIFIED-ROOM", "producer_system": "workpaper-sync-version-kernel", "required_by_tasks": [14], "on_missing": "BLOCKED"},
      {"milestone": "SYNC-MULTI-RESOLVER", "producer_system": "workpaper-sync-version-kernel", "required_by_tasks": [10, 14], "on_missing": "BLOCKED"},
      {"milestone": "SYNC-DURABLE-APPLICATION", "producer_system": "workpaper-sync-version-kernel", "required_by_tasks": [14], "on_missing": "BLOCKED"},
      {"milestone": "SYNC-ENTRY-NAMESPACE", "producer_system": "workpaper-sync-version-kernel", "required_by_tasks": [10, 14], "on_missing": "BLOCKED"}
    ],
    "produces": [
      {"milestone": "X-HANDOFF-CONFORMANCE", "task": 19, "consumers": ["workpaper-guidance-content-closure:G22"]},
      {"milestone": "X-RUNTIME-EVIDENCE", "task": 19, "consumers": ["workpaper-guidance-content-closure:G23"]}
    ]
  }
}
```

## Tasks

### Foundation, Security and Preflight

- [x] 1. 冻结生产基线与已有内核边界
  - 核实 batch dialog、TemplateManager、custom template router、validate_template、custom_cells、writer、forcesave/callback/revision 真实链路
  - 记录首 sheet 空白、元数据无真实文件、path/file_content、空内容 valid、原地改 current 后 CAS、room/durable/application/namespace debt
  - 反查 sync/version primitives，形成必须复用/禁止复制和并发 WIP 清单；不因文件存在勾任务
  - 产物：`.kiro/specs/custom-workpaper-template-ingestion-and-sync-closure/basis/T01-production-baseline.md`
  - _Requirements: 1.1, 1.2, 1.5, 12.2, 12.7, 13.1, 13.3, 13.4_

- [x] 2. 消费 `G-C0`，建立 tenant scope、capability 与 ApprovalIntent
  - import TemplateAuthorityIdentity/handoff/sections/refs/evidence/ACK schema，不复制同名接口
  - 所有对象绑定 tenant/org/project scope；上传、确认、发布、实例化、写入 capability 前置
  - immutable ApprovalIntent 冻结 candidate/policy/scope/digest/initiator/approver/expiry；组织发布 initiator≠approver
  - authorizationEpoch/writeFence 独立于 content fingerprint；角色矩阵服务端复验
  - 产物：`backend/app/services/custom_template_ingestion/authorization.py`、`actions.py`、
    `backend/tests/custom_template_ingestion/test_authorization.py`（31 例）、`test_actions.py`（10 例）；
    变异 8 条全 RED（`scripts/diagnose/mutate_custom_ingestion_task2.py --check-anchors` 0 ANCHOR-MISS）
  - 已实测登记的两个**结构性缺口**（不假绿）：① PG enum `userrole` 只有 7 值、**无 `template_admin`**，
    故「方法论/模板管理员发起组织级发布」在迁移落地前**不可达**（`test_template_admin_role_is_declared_but_not_provisioned_in_pg_enum` 锁死）；
    ② 平台无 Organization 实体、`tenant_id` 恒 `'default'`（`test_implicit_scope_never_accepts_client_supplied_values` 锁死推导面）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 11.7, 16.2, 16.4_

- [x] 3. 发布单一 ingestion policy、quota 与 scanner provenance
  - `CustomTemplateIngestionPolicy` frozen+slots 版本化对象，24 个阈值单一真源
    （upload 50MiB / expanded 512MiB / 20000 entries / 压缩比 100:1 / 256 sheets /
    500 万非空 cell / 2000 万声明范围 cell / XML bytes+depth+nodes+relationships /
    CPU 60s / wall 120s / RAM 2GiB / FD 256 / temp disk 4GiB / org concurrency+storage /
    TTL 24h-7d-30d）；构造即自洽校验（正数、有限浮点、压缩比一致性、上传≤解压、
    TTL 严格递增）
  - OOXML 能力矩阵 28 项 fail-closed：`.xlsx`=ALLOW_TO_PREFLIGHT、`.xlsm`=PREFLIGHT_ONLY
    且不在 `FINALIZE_CAPABLE`（Requirement 4.4 的 finalize 阻断是结构性保证，非散落 if）、
    VBA/XLM/DDE/ActiveX/OLE/远程连接/external link/relationship/data connection=BLOCK
    （4.5/4.6 v1 永久阻断）、未知能力=`BLOCK_PENDING_POLICY`（4.7 唯一 fail-closed 点）、
    11 个允许项登记进 `PRESERVATION_INVENTORY_FEATURES`（4.7 禁止静默丢失）
  - `validate_against_policy()`：空观测→单条 BLOCKER；负数/NaN/inf/bool→`invalid_observation`
    BLOCKER；超限→`POLICY.<field>_exceeded` 结构化 BLOCKER；通过→显式 INFO
    `all_within_limits`。`derive_verdict()` **无隐式 PASS 分支**——空 findings 返回 BLOCKED
    （Requirement 3.6「不得返回空报告或 valid=true」的实现点）
  - `ScannerProvenance`：policy fingerprint + scanner build digest + worker image digest
    + parser versions 派生 `fingerprint()`；`is_stale_for()` 按**指纹等值**比较（version 相同
    但阈值漂移仍判 stale）；`build_provenance()` 不接受客户端传入 policy_fingerprint；
    资源用量单独序列化供审计但**不参与** stale 判定（波动会让 stale 失去意义）
  - `check_organization_quota()`：pending_upload 累加进已用存储再比较（否则并发请求全
    通过后存储爆库）；输入非法 fail-closed 拒绝而非放行
  - 产物：`backend/app/services/custom_template_ingestion/policy.py`、
    `backend/tests/custom_template_ingestion/test_policy.py`（45 例）；
    变异 **18 条全 RED**（`scripts/diagnose/mutate_custom_ingestion_task3.py
    --check-anchors` 0 ANCHOR-MISS；无 GREEN/WRONG-TEST），覆盖空报告 valid、
    越界忽略、非法值放行、未知能力 ALLOW、.xlsm finalize、VBA/DDE 放行、外链放行、
    阈值变化不 stale、scanner build 复用、version 字符串比较、fingerprint 回声输入、
    存储忽略 pending、quota code 改名、bool 当数字、压缩比/TTL 自洽绕过
  - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 4.3, 4.4, 4.5, 4.6, 4.7, 6.7_

- [x] 4. 拆分三入口并实现 multipart/private quarantine
  - batch blank、metadata、ingest excel 使用独立 action/route/权限/文案/成功语义
    （action id 真源 = Task 2 的 `actions.py`；独立 router
    `backend/app/routers/custom_template_ingestion.py`，前缀
    `/api/custom-template-ingestion/*`，与旧 `/api/custom-templates` 并列）
  - UploadFile 流式 hash/size/MIME/magic，随机 storage identity；文件名只展示且清洗
    - `PrivateQuarantine.ingest()`：`CHUNK_SIZE`（1 MiB）逐块写 + 流式 SHA-256 +
      逐块大小上限；扩展名白名单（`.xlsx`/`.xlsm`）先于任何写入，非白名单
      **零字节落盘**即返回 REJECTED
    - `display_filename()`：basename → 剥控制字符 → 剥首尾多余点/空格
      （**保留扩展名前的点**，否则 `.xlsx` 变 `xlsx` 使白名单判定失效）→
      剥扩展名前空格 → 截断 `MAX_DISPLAY_FILENAME_LEN`
    - 三重校验顺序：extension → MIME → 写盘 → ZIP magic；内容校验失败（扩展名/
      MIME/ZIP magic）**返回 REJECTED 产物**而非抛异常（正常拒绝结果，可直接回
      结构化原因给提交者）；I/O 失败（空文件/超上限/读流异常）才抛
      `QuarantineError`，二者语义分离
  - preflight 前不生成 HTML/OO/project/runtime —— **结构性保证**：本模块没有任何
    产出这类对象的函数；测试 `test_no_runtime_artifacts_generated_during_ingest`
    用**目录树后缀集合 + 目录名字面量**双重判据锁死（只允许 `.bin`/`.json`，
    禁 `.html/.htm/.wopi/.xlsx/.docx/.doc`，禁 `onlyoffice/wopi/config/runtime/
    workpapers/projects` 目录名）
  - 旧 path/file_content/首 sheet 链退出正式路径 —— **新链已并列上线 + 有迁移
    删除门**（`LEGACY_MIGRATION_DEADLINE = "2026-12-31"`，
    `test_legacy_chain_is_parallel_and_marked_for_removal` 锁死）；旧
    `custom_templates.py` 本体**未改**（存量前端仍依赖），仍见下方缺口②
  - quota/cancel/failure 幂等清理：扩展名/MIME 拒绝**不落盘**；写盘中失败
    （OVERSIZE/READ_ERROR/EMPTY_FILE/ZIP_MAGIC）**整目录 `rmtree`**；
    `delete_artifact()` 重复调用返回 False 不抛错（retention 可重试）
  - 日志不写正文/token/PII：`logger.info` 只记 `artifact_id + size`；
    `RejectionReason` 只记 code/detail/bytes，不含文件名正文
    （`test_rejection_reason_serializes_without_filename_body` 用「工资明细/客户A
    不得出现在 rejection 序列化里」锁死）；`QuarantineArtifact.to_dict()`
    不含 `relativePath`/绝对路径（`test_manifest_never_leaks_storage_path`）
  - `ArtifactState` 枚举封闭于 quarantine 域（QUARANTINED/PREFLIGHT_READY/
    PREFLIGHT_FAILED/REJECTED/EXPIRED），`ALLOWED_TRANSITIONS` 未登记即抛
    `InvalidTransition` —— 跨域跳转（如 → ACTIVE）结构性不可达
  - 🔴 **本次发现并修复的四个真实缺陷（不假绿登记）**：
    1. **router 从未被 `include_router`（本任务最贵的一条）**：
       `backend/app/routers/custom_template_ingestion.py` 已完整实现
       （`POST /ingest` multipart + `GET /actions` + `GET /artifacts/{id}` +
       `GET /quota`），但 app 启动日志直接报
       「未注册的 router 模块（共 1 个）: ['app.routers.custom_template_ingestion']」，
       `/api/custom-template-ingestion/*` 零条路由。service 单测全绿 + Volar/
       pytest/get_diagnostics 四层全绿，用户点上传却是 404 —— memory 假绿三源
       第①种（additive 注入即死代码）的最贵变体。**修复** = 在
       `router_registry/workpaper.py` 的 `"其他"` 组注册（该 router 无 `{wp_id}`
       路径参数、自带 capability 校验，故不需 `dedicated_wp_gate`）。
       **守卫** = `test_ingestion_router_is_registered_in_main_app` 直接从
       `app.main.app` 读真实路由表断言四条路径存在（判据是路径集合成员检查，
       不是 grep 字符串）
    2. **`GET /actions` 对非摄取 action 抛 ValueError → 500**：
       `_capability_for_action()` 只映射 `INGEST_EXCEL_TEMPLATE`，遍历三条
       action 时在 `batch_create_blank` 上抛 `ValueError`，整个入口发现端点
       500 —— fail-open 变成 fail-hard。批量建空白与元数据维护是前端本地语义
       （Requirement 1.1/1.2），不走本服务 capability。**修复** = 返回 `None`
       表示「无 capability 门槛」，调用方对 `None` 跳过过滤
    3. **Windows 平台级缺陷**：`_org_dir()` 原 sanitize 允许 `:`，导致
       `organization_id="org:bj1"` 在 win32 上 `os.mkdir` 报
       `NotADirectoryError [WinError 267] 目录名称无效`（`:` 是 ADS 分隔符/
       drive 前缀）。原实现只在 Linux 语义下可跑，Windows 全量 23 例 quarantine
       测试恒失败。修复 = `_safe_org_component()` 把 `[^A-Za-z0-9._-]` 映射到
       `-` 并补 Windows reserved device names（CON/PRN/AUX/NUL/COM1-9/LPT1-9）
       尾部点处理；同时新增 `logical_org_component()` 让 `relative_path`/
       manifest 保留原始逻辑标识（`org:bj1`），避免 Windows 部署悄悄改写逻辑
       scope 使比对失配
    4. **manifest 键名不一致 + `contains()` 无法拦 `..` 折叠**：
       (a) `QuarantineArtifact.to_dict()` 写 camelCase `expiresAt`，而
       `cleanup_expired()` 读 `expires_at` → TTL 恒判过期。修复 = cleanup 读
       `expiresAt` 并兼容历史 snake_case；(b) `artifact_bytes_path("org:bj1", "..")`
       的 `path.resolve()` 把 `..` 折叠后仍在 quarantine 根内，`contains()` 判
       True 不抛错。修复 = 新增 `_assert_safe_artifact_id()` 做**字面量**校验
       （含 `/` `\` `..` NUL 或空串即拒绝），与 `contains()` 互补而非替代
  - 产物：`backend/app/services/custom_template_ingestion/quarantine.py`、
    `backend/app/routers/custom_template_ingestion.py`（本次修
    `_capability_for_action`）、`backend/app/router_registry/workpaper.py`
    （新增注册，**该文件是共享文件、并发会话也在改**，本次只 append 一行 import
    + 一行组内成员）、
    `backend/tests/custom_template_ingestion/test_quarantine.py`（**34 例**）、
    `backend/tests/custom_template_ingestion/test_ingestion_routes.py`
    （**11 例，新增**）、
    `backend/scripts/diagnose/mutate_custom_ingestion_task4.py`
  - 变异 **7 条全 RED**（`--check-anchors` 0 ANCHOR-MISS；无 GREEN/WRONG-TEST）：
    绕扩展名白名单、放行非 ZIP magic、storage key 由文件名派生、拒绝产物携带
    `valid` 字段、状态枚举混入 ACTIVE、TTL 改用真实墙钟、`/actions` 隐藏全部
    入口
  - 🔴 **变异检验抓出的守卫缺陷并已修**：
    `test_storage_key_never_contains_user_input` 原断言只查
    `display_name not in relative_path`，可被「把点换成横线」这类字符变换绕过
    （`escape.xlsx` → `escape-xlsx` 即骗过旧断言，而原始文件名语义仍在路径里）。
    已改为**原始输入名 + display_name 主体段**双重判定
  - 实测：`python -m pytest backend/tests/custom_template_ingestion/ -q` →
    **131 passed**（quarantine 34 / routes 11 / policy 45 / authorization 31 /
    actions 10）；`test_ie_route_inventory.py` + `test_ie_prefix_reachability.py`
    → **43 passed**；app 启动无「未注册 router」警告，2393 条路由含 4 条摄取链
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.6, 3.7_

- [x] 5. 实现 ZIP/XML/OOXML package security scanner
  - path 做 slash/NFKC/casefold，拒绝 absolute/drive/UNC/dot/empty/trailing/ADS/reserved/symlink/collision/越界
  - XML 禁 DTD/entity/network并应用 bytes/depth/nodes/relationship/resources 限制
  - 按矩阵阻断 corrupt/encrypted/xlsm finalize/macro/DDE/ActiveX/OLE/external link/unknown feature
  - worker 禁网；异常/timeout/budget 结构化失败并清 temp，允许项输出 preservation inventory
  - 产物：`package_paths.py` / `package_xml.py` / `package_scanner.py`；
    `test_package_paths.py` + `test_package_scanner.py`（38 例）；
    变异 7 条全 RED（`mutate_custom_ingestion_task5.py --check-anchors` 0 ANCHOR-MISS）
  - 结构性保证：scanner AST 不含 urllib/httpx/requests/openpyxl；不生成 HTML/WOPI 函数；
    空 findings → BLOCKER 永不 valid；`.xlsm` 走 PREFLIGHT_ONLY + finalize_blocked；
    VBA/外链/未知 ContentType 为 BLOCKER
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1_

- [x] 6. 实现逐 workbook/sheet semantic preflight
  - 输出 artifact/policy/scanner digests、relationships、cross-sheet formulas、defined names 与 preservation inventory
  - 输出 sheet stable observations、ranges/freeze/protection/merge/hidden/regions/cell/formula/table/name/validation/CF/drawing/comment
  - 分析 existing/instrumentable identity carriers、duplicates/drift、guidance candidate 和 projection recommendation
  - finding 含 code/severity/locator/ref/policy/remediation；空/异常 report 永不 valid
  - 产物：`semantic_preflight.py`；`test_semantic_preflight.py`（13 例）；
    变异 4 条全 RED（`mutate_custom_ingestion_task6.py`）
  - 结构性：安全门 BLOCKER 禁止 openpyxl；能力矩阵 BLOCKER 仍可读结构但 overall BLOCKED；
    九段 guidance 恒 `custom_candidate`/`review_pending`；无载体不得推荐 editable_grid
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

### Lifecycles, Candidate and Publication

- [x] 7. 实现四 lifecycle repositories、idempotency、lease 与 injectable clock
  - 分离 UploadArtifact、MappingDraft/TemplateCandidate、TemplatePublication、ProjectOperation 状态机
  - draft 可变版本化，candidate/publication/version immutable；operation 保存 base/current/incoming/write fence
  - transition 校验 revision/capability/idempotency/lease/digests/reason；watchdog 可恢复/补偿
  - retention 使用 injectable clock，不以 sleep/真实墙钟测试
  - 产物：`lifecycles.py` + `InMemoryLifecycleRepository`；`test_lifecycles.py`（9 例）；
    变异 4 条全 RED（`mutate_custom_ingestion_task7.py`）
  - 结构性：Upload 枚举无 ACTIVE；Publication 无 PREFLIGHT_*；idempotency key 复用同 operation；
    lease 过期禁止 COMMITTED + watchdog → FAILED→COMPENSATED
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 8. 消费 `G-ID`，完成逐 sheet mapping、identity carrier 与 adapter SPI
  - 确认纳入、wp_code、regions/fields/formulas/read-only/dynamic/mode/preservation
  - 优先 existing carrier；instrumentation 必须创建新 immutable candidate并做 reopen/roundtrip/diff
  - 无稳定 carrier 降级；editable_grid 强制 manifest+adapter，read-only 强制 extractor，OO-only 不建空对端
  - adapter 实现 extract/validate/apply/diff/rebase/merge，声明 managed/unmanaged 与 formula boundary
  - _Requirements: 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

- [x] 9. 生成 immutable candidate、静态预览与 candidate guidance
  - freeze artifact/policy/scanner/mapping/guidance/adapter digests；修改创建新 revision
  - 只生成 sanitized static HTML/image/structure preview，不生成生产 OO/WOPI config
  - 公式/链接/comments/properties 全按文本；展示 managed/unmanaged、identity/mode/preservation
  - 使用 G-C0 candidate handoff；不填 finalized 字段、不 confirmed，变化/过期使 preview token/evidence stale
  - _Requirements: 6.2, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [~] 10. 建立一份 `ProjectWorkbookInstance`、child entries 与统一 namespace
  - 2026-09-09：域模型已交付 — `workbook_instance.py` / `namespace_migration.py` /
    `V158__project_workbook_instance.sql` / ORM；守卫 8 passed；统一 `pwi-…` entry；
    rename/reorder 不改 entry_id；`advance_generation` 刷新 affected child
  - **仍 BLOCKED**：`SYNC-MULTI-RESOLVER`（count=4）与 `SYNC-ENTRY-NAMESPACE`
    （opaque wp_code/wp_id 分裂）未归零，不得宣称 pointer/generation/rollback 平台唯一；
    见 `basis/T10-workbook-instance.md` 与 `probe_namespace_gates()`
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 11. 消费 `G-HANDOFF-CONSUMER` 并实现 pending visibility finalize saga
  - `finalize_saga.py`：FinalizeLock → PENDING_VISIBILITY → 四 consumer ACK ledger →
    全 ACCEPTED 才 ACTIVE；reject/idempotency digest conflict；instantiate 门
  - 守卫 `test_finalize_saga.py` 7 passed；消费
    `guidance_handoff_consumer_service.compute_handoff_digest`，不复制 ACK schema
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 16.4_

### UI, Runtime and Bidirectional Sync

- [x] 12. 消费 `F-SHELL` 完成 ingestion wizard 与 active custom host 接入
  - `useCustomIngestionWizard.ts` + `CustomIngestionWizard.vue` + 路由
    `extension/custom-templates/ingest`；`assertFShellConsumerCompatible`；
    candidate 仅静态预览；ACTIVE 才 `hostFactsRegistered`；权限撤销清 host facts
  - vitest 5 passed；不复制 formula button/dialog/location store/fixed rail CSS
  - _Requirements: 1.6, 2.6, 9.1, 9.3, 16.3_

- [x] 13. 实现 HTML→staging xlsx→单一 writer CAS
  - `staging_cas.py`：client base / fence / pwi-entry 门 → clone staging → apply →
    `commit_bytes(expected=…)`；失败丢 staging；禁止旧原地写符号
  - 守卫 `test_staging_cas.py` 5 passed（含 CAS 竞态丢 staging）
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [~] 14. 通过四个 sync gates 接通 OnlyOffice→durable→HTML
  - `sync_gates.py` + `test_sync_gates.py`：四 gate 只读探测，当前全 BLOCKED（诚实锁死）
  - 未新建 custom callback/writer 绕开；待上游 SYNC 归零后再接线 OO→durable→HTML
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

- [x] 15. 实现 adapter three-way merge、结构 remap 与 crash recovery
  - `merge_remap.py`：different-field 自动合并；same-field typed conflict（禁 LWW）；
    RemapCandidate 阻断自动 projection；ProjectOperation crash 可重放
  - 守卫见 `test_merge_publication_retention.py`
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

### Version, Retention and Evidence

- [x] 16. 实现 immutable publication、project pin、升级/回滚、withdraw/revocation
  - `publication_ops.py`：ACTIVE 才 instantiate；pin；upgrade 需 ApprovalIntent + staging；
    WITHDRAWN 保留 pin；SECURITY_REVOKED 清 pin 并返回影响清册
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 15.1, 15.2, 15.3, 15.4_

- [x] 17. 实现 artifact reference graph、retention、访问与审计
  - `retention.py`：reference graph + TTL + injectable clock；PROTECTED kinds / 仍被引用
    不删；EvidenceEnvelope 禁 token/正文
  - _Requirements: 15.5, 15.6, 15.7, 16.1, 16.2_

- [~] 18. 定向行为、逐项变异 RED 与完整 Playwright
  - 定向守卫已覆盖 Task 10–17 新模块（backend ≈27 + frontend 5）
  - 2026-09-09：`mutate_custom_ingestion_task18.py --run` **5/5 RED**
    （PWI empty / NS gate / saga ACTIVE / CAS base / no-LWW）；
    evidence `basis/T18-mutation-report.json`（基线+恢复后均 GREEN）
  - **未完成**：三入口/双人审批/HTML↔OO Playwright
    （被 Task 14 SYNC gate 与真 OO 环境挡住）——不得因模块变异勾 [x]
  - _Requirements: 17.1, 17.2, 17.3, 17.4_

- [~] 19. 发布 X milestones、全量清册门并归档
  - 已写 partial evidence：`evidence/X-HANDOFF-CONFORMANCE.json`、
    `evidence/X-RUNTIME-EVIDENCE.json`（verdict=PARTIAL）
  - **不得归档**：SYNC 四 gate + Task 18 Playwright 未齐；不等待 guidance C2
  - _Requirements: 16.5, 16.6, 16.7, 17.5, 17.6_

## Property Coverage

| Property | Implemented/verified by Task |
|---|---|
| 1 | 1, 4, 12, 18 |
| 2 | 2, 11, 16, 18 |
| 3 | 2, 12, 18 |
| 4 | 4, 18 |
| 5 | 3, 4, 5, 17, 18 |
| 6 | 5, 18 |
| 7 | 3, 5, 18 |
| 8 | 6, 18 |
| 9 | 7, 18 |
| 10 | 10, 13, 14, 18 |
| 11 | 8, 10, 14, 18 |
| 12 | 8, 12, 13, 14, 15, 18 |
| 13 | 9, 12, 18 |
| 14 | 11, 18, 19 |
| 15 | 10, 16, 18 |
| 16 | 2, 16, 18 |
| 17 | 13, 18 |
| 18 | 10, 13, 18 |
| 19 | 14, 18 |
| 20 | 15, 18 |
| 21 | 7, 11, 13, 14, 15, 18 |
| 22 | 16, 17, 18 |
| 23 | 2, 11, 12, 17, 18 |
| 24 | 19 |
| 25 | 18, 19 |

## Completion Notes

- Task 19 只发布 X evidence 并按 custom 自身完成门归档；不等待 guidance Task 22/23 或 C2 PASS。
- `editable_grid` 没有 manifest+adapter 就是 BLOCKED/降级，不存在 adapter=null 的字段级合并承诺。
- candidate 不交生产 OnlyOffice；`.xlsm` 和 external links 在 v1 均 finalize blocked。
- 多 sheet 始终是一份 workbook instance/current/room；child entry 不是二进制副本。
- sync 四 gate 缺失即显式 BLOCKED，禁止新增 custom callback/writer/namespace 绕开。

## Task 4 已交付边界与剩余缺口（2026-09-08 实测，不假绿勾选）

🔴 判据一律为「代码 grep + 路由表实测 + app 启动日志」，不靠推测。

Task 4 的**服务内核 + HTTP 路由**已交付且全绿（见上）。2026-09-08 实测发现
并修复了「router 从未被 `include_router`」这个最贵的假绿缺陷后，仍有**两个
真实缺口**不能因后端绿就宣称 Requirement 1 完成：

| 缺口 | 现状 | 判据 | 归属 |
|---|---|---|---|
| ① **前端未接线** | `GtCustomWpBatchDialog.vue` 的 `el-upload` 仍为 `action="#"` + `:auto-upload="false"`，纯客户端 SheetJS 解析，**字节从未离开浏览器**；全前端无任何调用 `/api/custom-template-ingestion/ingest` 的代码 | `grep -rn "custom-template-ingestion" audit-platform/frontend/src` = 0 命中 | 需 Task 12 做三入口 UI + multipart 接线 |
| ② **旧链本体未改造**（Requirement 1.5） | `POST /api/custom-templates`（`custom_templates.py`）仍接受客户端 `template_file_path` 字符串并直接 `db.add()`；`validate_template` 空内容仍 `valid=True`。新链已并列上线且有 `LEGACY_MIGRATION_DEADLINE = 2026-12-31` 删除门，但旧路由本体未下线 | `basis/T01-production-baseline.md` §A2/§B 取证仍成立；本 spec 未触碰该文件 | 需 migration 删除门到期下线 + `custom_templates.py` 改造 |

**已锁死的反向事实（防误判就绪）**：
* `test_ingestion_router_is_registered_in_main_app` 从**真实** `app.main.app`
  路由表断言四条路径存在 —— 删掉 registry 里那一行 import 这条立即红；
* `test_legacy_chain_is_parallel_and_marked_for_removal` 锁死「旧链保留 + 新链
  已注册 + 迁移删除门存在」三态，防止误删旧链或误判新链未上线；
* `test_ingest_without_file_returns_422` / `test_ingest_enforces_upload_capability`
  证明新链的权限与入参校验在真实 HTTP 语义下生效（403/422，非 service 层）。

## 外部依赖阻塞归因（2026-09-09 复测）

| Task | 阻塞的 gate | 上游归属 | 实测证据 |
|---|---|---|---|
| 10（证明项） | `SYNC-MULTI-RESOLVER`、`SYNC-ENTRY-NAMESPACE` | sync Task 71/36 | `multi_resolver_count=4`；opaque split note 仍在 — 域模型已交付，gate 证明仍 `[~]` |
| 11 | — | G-HANDOFF-CONSUMER 已交付 | Task 11 `[x]` |
| 12 | — | F-SHELL 已交付 | Task 12 `[x]` |
| 14 | SYNC 四 gate | workpaper-sync-version-kernel | `probe_all_sync_gates().all_clear=False` |
| 18–19 | Task 14 + 真 OO Playwright | 同上 | partial X evidence only |

**可交付边界（2026-09-09）**：Task 1–9、11–13、15–17 已交付。Task 10/14/18/19 因 SYNC 四 gate 诚实 `[~]`。

**平台级前置（非本 spec 可解）**：
1. PG enum `userrole` 缺 `template_admin` —— 组织级发布发起路径在迁移落地前结构性不可达；
2. 无 Organization 实体、`tenant_id` 恒 `'default'` —— 真多租户隔离需平台级落地。
两条已在 `test_authorization.py` 中用测试锁死事实，防止误以为权限就绪。
