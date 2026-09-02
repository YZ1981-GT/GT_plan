# -*- coding: utf-8 -*-
"""底稿 HTML ↔ OnlyOffice Excel/Word 双向回写同步域。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure

Wave 1 已落模块：

* :mod:`app.services.workpaper_sync.models` —— domain enum、允许状态边、identity
  计算与纯不变式校验（不放 ORM，ORM 在 ``app/models/workpaper_sync_models.py``）
  · Task 10
* :mod:`app.services.workpaper_sync.repository` —— 只 flush 不 commit 的仓储层：
  wp advisory/row lock、business revision 乐观锁、scope index 同事务、
  request/application/operation/delivery/recovery/close-intent 原子写入 · Task 10
* :mod:`app.services.workpaper_sync.limits` —— Requirement 14.11 容量预算与 OOXML
  安全策略的唯一加载入口（禁止代码散落常量）· Task 11
* :mod:`app.services.workpaper_sync.ooxml_security` —— ZIP/展开量/压缩比/entry 名/
  外部关系/宏/嵌入对象/文档类型的有序安全门 + projection 行/field 预算 · Task 11
* :mod:`app.services.workpaper_sync.artifacts` —— `CanonicalArtifactRepository`：
  staging、incoming durable sealing 与 quarantine、内容寻址不可变发布、路径安全、
  Windows 诊断码、candidate 隔离；以及 `OrphanReconciler` · Task 11
* :mod:`app.services.workpaper_sync.retention` —— 版本化 `RetentionPolicyService`：
  dry-run、二次引用复核、逐对象删除审计、不确定即保留告警 · Task 11
* :mod:`app.services.workpaper_sync.canonical_paths` —— **纯同步、零 ORM** 的路径边界
  （Property 42）、文档类型 fail-closed（Property 41）与子码最具体匹配（Property 40）
  单一实现；`artifacts.py` 与 `wp_export/wp_file_resolver.py` 都委托它 · Task 12
* :mod:`app.services.workpaper_sync.definitions` —— immutable definition/bundle store：
  发布 DAG（`template → instrumentation → contract → bundle → representation`）、
  bundle canonicalizer 的 14 条 fail-closed 反例、版本化 typed null marker registry、
  alias（只可用于发布，历史读取恒抛）· Task 12
* :mod:`app.services.workpaper_sync.resolution` —— `CanonicalResolutionService`：
  config/download/callback/materialize/extract/rematerialize/retry/rollback/history/
  evidence **十个意图共用的唯一解析入口**；candidate 隔离与 finalize 前置、
  sheet 可见性只允许 staged（Requirement 9.12）· Task 12

Wave 2 已落模块：

* :mod:`app.services.workpaper_sync.materialize_coordinator` —— HTML→OO 的**唯一**
  编排入口：签名 pending-mutation token（scope/TTL/payload digest/expected revision/
  Idempotency-Key 五类拒绝各一个类型）、authorization-before-idempotency 的阶段链
  （由参数类型强制，`authorize()` 只读非敏感 scope index 并有 AST 判据）、
  Requirement 3.3 的 422 preflight 家族（零 operation / 零 room）、三段事务编排
  （operation shell 先独立提交 → Task 15 唯一业务 commit → 终态记账 + room/participant）、
  构造期即拒绝缺字段的 `EditorLaunchDescriptor`，以及 descriptor-confirm 与
  definitions-only finalize 的委派 · Task 25
* :mod:`app.services.workpaper_sync.oo_to_html` —— OO→HTML 的**唯一**编排入口：
  substrate 只认 `application.incoming_artifact_id` 的 `kind=incoming,state=durable`
  （来源唯一由 AST 判据钉死，禁 room pointer / registry alias / candidate / operation
  path），quarantined 在 application FK、coordinator 入口与 engine **三层各自**拒绝且
  异常类型刻意不同；三方 extract → Task 14 merge → 经 Task 15 唯一 business commit 做
  canonical rematerialize（publish 前与写库前**两道**最终授权 fence，各十条逐条独立）；
  双基线裁决（merged==incoming 才推进 client-confirmed，否则 refresh-required
  + supersede）；durable 后失败一律 ack=0、保留 incoming、同一 primary timeline 可
  retry · Task 26

* :mod:`app.services.workpaper_sync.conflict_resolution` —— 冲突预览 / resolve fence /
  recovery-aware retry / opaque-version rollback 的唯一编排入口 · Task 27
* :mod:`app.services.workpaper_sync.endpoint_guard` —— 用户端 sync API 的**唯一**固定
  guard：`认证 → 显式 route scope + opaque ids/signed claim → 只查 scope index →
  visibility → action/workflow/lease/generation/fence/bundle`。五阶段不可交换，
  三种 404 原因跑常量工作量后由唯一抛出点统一抛（同 envelope / 同阶段 / 同时序桶）·
  Task 28
* :mod:`app.services.workpaper_sync.redaction` —— 版本化 `RedactionPolicy`：字段
  allowlist 递归投影 + 键名层敏感词 + 值形态层（JWS/Bearer/URL/长不透明串）+ URL 只留
  `scheme://host/前 N 段 path`；`assert_no_leak` 反向自证 · Task 29
* :mod:`app.services.workpaper_sync.metrics` —— 指标唯一词汇表 `METRIC_CATALOG`：四级
  归因（operation/room/route/platform）、route 级**禁带** participant（AC 5.1/10.9）、
  `record_outcome` 的 `result/landed` 无默认值、
  :data:`~app.services.workpaper_sync.metrics.FORBIDDEN_GENERIC_ERROR_OUTCOMES`
  拒绝把 same-app fold / 跨 participant 409 / 无 successor 恢复态压成普通 error · Task 29
* :mod:`app.services.workpaper_sync.alerting` —— 版本化 `AlertRuleRegistry`：阈值、
  窗口、severity、去重键、恢复条件与 runbook；与指标目录、Requirement 13.9 条目清单
  三向双向锁死 · Task 29
* :mod:`app.services.workpaper_sync.timeline` —— 四条 append-only event 流的读侧统一
  投影 + `check_projection` 的四条独立一致性判据（Property 68）；recovery case timeline
  **结构上**不含 operation（claim 前零 operation）· Task 29
* :mod:`app.services.workpaper_sync.evidence` —— `derive_required_scenarios` 从
  source-backed `editability/room_model/scenario_profile` + capability + authority model
  推导 required scenario set（纯函数、进 digest），`EvidenceRecomputer` 逐项重算外键/
  hash/复用/stale（Property 69 / 70 / 71）· Task 29

═══ 生产调用方（Task 28 起不再为空）═══

Task 26 收口时留下一笔欠账：`oo_to_html` 与 `conflict_resolution` **没有生产调用方**，
「非死代码」只由 :data:`merge.RETIRED_DEFERRALS` 的登记表 + Task 14 的「merge 域恰一个
消费方」结构性背书。Task 28 落地 `app/routers/wp_sync_router.py` 后翻转成**真实调用链**：

* `POST …/pending-mutations` / `…/materialize` / `…/confirm-descriptor`
  → `materialize_coordinator`
* `POST …/rooms/{room_id}/forcesave` → `request_application` → `command_service`
* `POST …/rooms/{room_id}/close-intents` → `close_intent`
* `POST /api/workpaper-sync/rooms/{room_id}/onlyoffice-callback`
  → `callback_delivery` →（durable + correlate 之后）→ `oo_to_html`
* `GET/POST …/operations/{operation_id}/{conflicts,timeline,resolve,retry}`
  与 `POST …/versions/{version_id}/rollback` → `conflict_resolution` → `oo_to_html`
* `GET …/operations/{operation_id}/timeline` 与
  `GET …/recovery-cases/{case_id}/timeline` → `timeline` → `redaction`（Task 29）
* forcesave / callback / close-intents / recovery claim / download-only 的终态
  → `metrics`（Task 29）；`alerting` 消费 `metrics` 的样本，`evidence` 消费
  `entry_profile` + `definitions`

本模块**刻意 import** 这些符号（下方 `__all__`）：`test_task28_sync_router` 的
AST 判据从 router 出发反查这条链，而 import 面让「谁是本包的对外形态」有一份可核对的
清单 —— 之前这里只有 docstring 提及，于是 Tasks 25~27 的守卫辐射面小到几乎为零
（改本包任何文件都不会牵动别的测试）。
"""

from app.services.workpaper_sync.alerting import AlertRuleRegistry, load_alert_registry
from app.services.workpaper_sync.callback_delivery import CallbackDeliveryService
from app.services.workpaper_sync.close_intent import CloseIntentService
from app.services.workpaper_sync.command_service import CommandServiceClient
from app.services.workpaper_sync.conflict_resolution import ConflictResolutionService
from app.services.workpaper_sync.content_mutation import ContentMutationService
from app.services.workpaper_sync.endpoint_guard import (
    GuardedScope,
    SyncEndpointGuard,
    SyncEndpointRequest,
)
from app.services.workpaper_sync.evidence import (
    EvidenceRecomputer,
    derive_required_scenarios,
)
from app.services.workpaper_sync.materialize_coordinator import (
    MaterializeCoordinator,
    build_materialize_coordinator,
)
from app.services.workpaper_sync.metrics import SyncMetrics, sync_metrics
from app.services.workpaper_sync.oo_to_html import OoToHtmlCoordinator
from app.services.workpaper_sync.redaction import RedactionPolicy, load_redaction_policy
from app.services.workpaper_sync.request_application import RequestApplicationService
from app.services.workpaper_sync.rooms import RoomService
from app.services.workpaper_sync.timeline import SyncTimelineService

__all__ = [
    "AlertRuleRegistry",
    "CallbackDeliveryService",
    "CloseIntentService",
    "CommandServiceClient",
    "ConflictResolutionService",
    "ContentMutationService",
    "EvidenceRecomputer",
    "GuardedScope",
    "MaterializeCoordinator",
    "OoToHtmlCoordinator",
    "RedactionPolicy",
    "RequestApplicationService",
    "RoomService",
    "SyncEndpointGuard",
    "SyncEndpointRequest",
    "SyncMetrics",
    "SyncTimelineService",
    "build_materialize_coordinator",
    "derive_required_scenarios",
    "load_alert_registry",
    "load_redaction_policy",
    "sync_metrics",
]
