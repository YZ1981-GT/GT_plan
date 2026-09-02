# -*- coding: utf-8 -*-
"""Task 31 守卫变异检验（前端 DTO/API/tracker + 后端 contract 生成器）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
Requirements: 14.7 · Property 57（变异检验本身）

## 四态

| 判定 | 含义 | 归因 |
|---|---|---|
| ``RED`` | **预期那条**判据打红 | 守卫有效 |
| ``GREEN`` | 无新增失败 | **守卫缺陷** |
| ``WRONG-TEST`` | 打红了但不是预期项 | 锚点错行 / 污染残留 |
| ``ANCHOR-MISS`` | 锚点非唯一命中 / 未落盘 | **本脚本缺陷** |

退出码不作判据（pytest 收集错误、vitest 噪声 warning 都会非零）；判定只看失败名差集。

## 本脚本的硬约束（都踩过）

1. **一律 `scope`+`offset` 相对定位，不写绝对 `line=`** —— 文件上下增删行就会让绝对行号
   指到别的内容，而 `--list` 之外的子命令未必当场发现。
2. **替换体必须语法合法** —— TS/py 任一处编译不过时，整套挂掉、失败差集被清空，
   判定会给出 GREEN（「守卫没拦住」），实为脚本缺陷。
3. **前端变异跑 vitest 必须 `--reporter=json --outputFile=<绝对路径>`**（由
   `_mutation_kit.runner.run_vitest` 统一负责）—— 控制台的 FAIL 行会按终端宽度折行。

## 用法

    py -3 backend/scripts/check/mutate_task31_frontend_contract_guards.py --list
    py -3 backend/scripts/check/mutate_task31_frontend_contract_guards.py --check-anchors
    py -3 backend/scripts/check/mutate_task31_frontend_contract_guards.py --run fe --out <path>
    py -3 backend/scripts/check/mutate_task31_frontend_contract_guards.py --run be --out <path>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

FRONTEND = REPO / "audit-platform" / "frontend"
_FE_JSON = REPO / "backend" / "scripts" / "check" / "_wip_task31_fe.json"

API = "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncApi.ts"
DTO = "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncDto.ts"
TRACKER = (
    "audit-platform/frontend/src/components/workpaper/sync/workpaperSyncOperationTracker.ts"
)
GEN = "backend/scripts/gen/generate_workpaper_sync_frontend_contract.py"

#: 覆盖面分母：本任务的守卫文件 → 归属说明。空分母会让覆盖统计恒成功。
GUARD_FILES = {
    "workpaperSyncDto.spec.ts": "DTO 域/不变量/失败分型（P10/P11/P47 前端侧）",
    "workpaperSyncApi.spec.ts": "URL 拼接 / Idempotency-Key / envelope / recovery client / rollback",
    "workpaperSyncOperationTracker.spec.ts": "SSE 优先、轮询恢复、operation+revision 去重",
    "test_task31_frontend_contract.py": "生成物 ↔ 真实 router/枚举/confirm_payload 的后端锚点",
}

BE_ARGS = [
    "backend/tests/workpaper_sync/test_task31_frontend_contract.py",
    "-q",
    "--tb=no",
    "-p",
    "no:randomly",
]
FE_FILTERS = ["workpaperSyncDto", "workpaperSyncApi", "workpaperSyncOperationTracker"]

MUTATIONS: list[Mutation] = [
    # ═══════════════ 前端：URL 与显式 scope ═══════════════
    Mutation(
        id="M01",
        side="fe",
        path=API,
        kind="replace",
        scope="export function encodeEntryId(entryId: string): string {",
        offset=11,
        anchor="  return text",
        new="  return encodeURIComponent(text)",
        want="分隔符 `/` 原样进入 URL",
        why="把逐段 encode 改成整串 encode ⇒ 多段 entry_id 里的 `/` 变 `%2F`。"
        "Task 28 的 B01 已证明默认转换器下每个端点恒 404；`%2F` 是同一个缺陷的客户端侧"
        "对偶（Starlette 解出的 entry_id 不再等于原值）。此处必须用真实四段 entry 才能测出",
    ),
    Mutation(
        id="M02",
        side="fe",
        path=API,
        kind="replace",
        scope="async function request(options: RequestOptions): Promise<Record<string, unknown>> {",
        offset=21,
        anchor="    headers['Idempotency-Key'] = key",
        new="    void key",
        want="的请求带非空 Idempotency-Key",
        why="服务端把七个端点的 header 声明为必填（Task 28 已证明改可选时零测试失败，"
        "后果是复合幂等键最后一项恒空、同 participant 两次 forcesave 折叠成一次）。"
        "客户端不发 header 是同一缺陷的客户端侧对偶，只断言「函数被调用」的判据抓不到",
    ),
    Mutation(
        id="M03",
        side="fe",
        path=API,
        kind="replace",
        scope="export async function rollbackVersion(",
        offset=8,
        anchor="  if (!isOpaqueUuid(input.versionId)) {",
        new="  if (false) {",
        want="numeric revision ⇒ 发出前拒绝拼 route",
        why="删掉 opaque UUID 门 ⇒ numeric revision 直接拼进 `versions/{id}/rollback`。"
        "两个不同 wp 都有 revision 1，用它作 scope key 会在授权索引里碰撞成同一行"
        "（AC 10.6 / 8.7），而服务端只会回一个统一 404，UI 分辨不出",
    ),
    Mutation(
        id="M04",
        side="fe",
        path=API,
        kind="replace",
        scope="export function buildClaimRequestBody(",
        offset=10,
        anchor="    expected_current_revision: input.expectedCurrentRevision,",
        new="    expected_current_revision: input.expectedCurrentRevision,"
        " client_confirmed_base_version_id: 'x',",
        want="claim body 是白名单构造，不含任何 client 指定的 base",
        wants=("claim 的 case_id 走 route 段而不是 body",),
        why="给 claim body 塞一个客户端指定的 base ⇒ design §API 明文「客户端不得提交任意 "
        "base/bundle」被破坏。白名单交叉锁死是唯一能抓到「随手多塞一个字段」的判据；"
        "只断言「必填项都在」的判据对多余字段全绿",
    ),
    # ═══════════════ 前端：envelope 只解一次 ═══════════════
    Mutation(
        id="M05",
        side="fe",
        path=DTO,
        kind="replace",
        scope="export function assertUnwrappedOnce(payload: unknown, label: string): Wire {",
        offset=1,
        anchor="  const wire = asWire(payload, label)",
        new="  const wire = asWire((payload as { data?: unknown })?.data ?? payload, label)",
        want="载荷仍是 {code,message,data} 时 fail visible，不再解一层",
        wants=("只带 code 或只带 data 的业务载荷不误判为 envelope",),
        why="在 API 层之外再解一次 envelope ⇒ 「拦截器某天停止解包」与「响应本来就长这样」"
        "两种情形都静默通过，而两者的正确处理完全不同。这条变异正是 Requirement 「平台 "
        "envelope 只在 API 层解一次」的反面",
    ),
    # ═══════════════ 前端：operation 三态 ═══════════════
    Mutation(
        id="M06",
        side="fe",
        path=DTO,
        kind="replace",
        scope="export function classifyOperationShape(input: {",
        offset=6,
        anchor="  if (applicationId !== null && duplicateOfOperationId !== null) {",
        new="  if (false) {",
        want="同时带 application 与 duplicate 指针 ⇒ 拒绝",
        why="删掉 primary/duplicate 互斥门 ⇒ 一个同时绑定 application 与 duplicate 指针的 "
        "operation 会被判成 duplicate。AC 5.5 明令二者互斥；后端 `classify_operation_shape` "
        "在同一位置抛 `DuplicateLinkError`，前端投影不得比它宽松",
    ),
    Mutation(
        id="M07",
        side="fe",
        path=DTO,
        kind="replace",
        scope="export function parseOperationSnapshot(payload: unknown): WorkpaperSyncOperationSnapshot {",
        offset=3,
        anchor="    WP_SYNC_OPERATION_STATES,",
        new="    [...WP_SYNC_OPERATION_STATES, String((wire as Record<string, unknown>).state)]"
        " as readonly string[],",
        want="未知 operation state fail visible，不得兜底成 error",
        why="把封闭域临时扩成「包含本次收到的任何值」⇒ 未知状态静默通过。AC 4.9 明文"
        "「未知状态 SHALL fail visible」；兜底成 error 会让审计师去点一个协议上不允许的重试",
    ),
    # ═══════════════ 前端：recovery 三实体 ═══════════════
    Mutation(
        id="M08",
        side="fe",
        path=DTO,
        kind="replace",
        scope="export function parseRecoveryCase(payload: unknown): WorkpaperSyncRecoveryCase {",
        offset=17,
        anchor="  const entities = { operationId, applicationId, forcesaveRequestId }",
        new="  const entities = { operationId }",
        want="unclaimed 却带 application_id ⇒ 拒绝",
        wants=("unclaimed 却带 forcesave_request_id ⇒ 拒绝",),
        why="只检查三实体中的一个 ⇒ 另两个可以在 claim 前伪造。这正是本 spec 反复抓到的"
        "「守卫只覆盖一条分支、其余永远绿」形态；`operation_id` 那条仍会红，所以判据必须"
        "逐个实体参数化，否则单条通过就掩盖另两条",
    ),
    Mutation(
        id="M09",
        side="fe",
        path=DTO,
        kind="replace",
        scope="/** bundle 的三个 typed slot 必须**全在**（Requirement 2.3）。 */",
        offset=1,
        anchor="const REQUIRED_BUNDLE_SLOTS = ['template', 'instrumentation', 'contract'] as const",
        new="const REQUIRED_BUNDLE_SLOTS = ['template'] as const",
        want="缺 typed slot instrumentation 时拒绝（三个必须全在）",
        wants=("缺 typed slot contract 时拒绝（三个必须全在）",),
        why="只要求一个 slot ⇒ 缺 instrumentation/contract 的 descriptor 可挂载。"
        "Requirement 2.3 要求三个 typed slot 全在（可选 child 只能用 typed null marker）；"
        "少一个 slot 意味着 bundle identity 不完整而编辑器已经开了",
    ),
    Mutation(
        id="M10",
        side="fe",
        path=DTO,
        kind="replace",
        scope="/** download-only 响应里出现任一项即视为伪造 applied。 */",
        offset=5,
        anchor="  'result_revision',",
        new="  'x_never_present',",
        want="download-only 响应带 result_revision ⇒ 拒绝（伪造 applied）",
        why="把 `result_revision` 从禁项里摘掉 ⇒ download-only 回执可以带一个 revision，"
        "UI 就会显示「结构化回写完成」。AC 5.8 明令 download-only 永不创建 "
        "request/application/operation，也不得冒充 applied",
    ),
    # ═══════════════ 前端：SSE 优先 / 去重 ═══════════════
    Mutation(
        id="M11",
        side="fe",
        path=TRACKER,
        kind="replace",
        scope="  async start(): Promise<void> {",
        offset=12,
        anchor="    // 初次读一次当前状态：SSE 只投递之后的事件。",
        new="    this.enterDegradedPolling()",
        want="SSE 健康时只读一次，之后不轮询",
        why="无条件起轮询 ⇒ design §API 的「优先 SSE/事件，轮询作为断线恢复」被破坏。"
        "功能上完全「正常」（状态照样更新），只有 poll 计数判据能看出来 —— 在 6000 会话"
        "规模下这条是把 operation GET 打成常态流量的入口",
    ),
    Mutation(
        id="M12",
        side="fe",
        path=TRACKER,
        kind="replace",
        scope="export function operationSnapshotDedupeKey(",
        offset=6,
        anchor="    snapshot.resultRevision === null ? '-' : String(snapshot.resultRevision),",
        new="    '-',",
        want="同 state 但 revision 推进也必须通知",
        wants=("operation 去重键含 canonical id / state / result revision 三段",),
        why="去重键丢掉 revision ⇒ same-application 的 sequence fold 只推进 applied revision "
        "而不改 state，于是新 revision 被当重复事实丢掉，UI 停在旧 revision。"
        "「按 operation 去重」的朴素写法正是这个缺陷",
    ),
    Mutation(
        id="M13",
        side="fe",
        path=TRACKER,
        kind="replace",
        scope="export function contentUpdateDedupeKey(payload: unknown): string | null {",
        offset=7,
        anchor="  return `${wpId}|${revision}`",
        new="  return `${wpId}|${revision}|${String(wire.operation_id ?? '')}`",
        want="content.updated 按 wp_id + revision（AC 11.9），不含 operation",
        why="把 operation 塞进 content.updated 的去重键 ⇒ 同一个 revision 会被投递两次"
        "（一次来自 operation 应用、一次来自纯表示升级）。AC 11.9 明文按 `wp_id + revision` 去重",
    ),
    # ═══════════════ 后端：生成物 ↔ 真源 ═══════════════
    Mutation(
        id="M14",
        side="be",
        path=GEN,
        kind="replace",
        scope="    routes: list[dict[str, Any]] = []",
        offset=1,
        anchor="    for route in _router_module.router.routes:",
        new="    for route in list(_router_module.router.routes)[:10]:",
        want="test_route_table_covers_every_real_user_route",
        wants=("test_generated_file_is_fresh",),
        why="投影少 6 条路由 ⇒ 那 6 个端点前端永远打不到，而所有「路径模板长得对」的判据"
        "仍然全绿（它们只检查已投影的那些）。分母必须是 router 的全部路由",
    ),
    Mutation(
        id="M15",
        side="be",
        path=GEN,
        kind="replace",
        scope='            if str(getattr(param.field_info, "alias", "")) == _IDEMPOTENCY_HEADER:',
        offset=1,
        anchor="                required = bool(param.field_info.is_required())",
        new="                required = False",
        want="test_idempotency_key_projection_equals_the_dependant_truth",
        wants=("test_generated_file_is_fresh",),
        why="把「服务端是否强制」写死成 False ⇒ 必填集变空，前端不再发 header。"
        "Task 28 已证明这一侧改动零功能测试失败；判据必须取自 FastAPI 解出的 dependant，"
        "不能是一张手抄名单",
    ),
    Mutation(
        id="M16",
        side="be",
        path=GEN,
        kind="replace",
        scope='            raise ContractGenerationError(f"models 里没有枚举 {enum_name}")',
        offset=1,
        anchor="        facts[key] = [member.value for member in enum]",
        new="        facts[key] = [member.value for member in enum][:3]",
        want="test_closed_domain_equals_the_backend_enum",
        wants=("test_generated_file_is_fresh",),
        why="封闭域只投影前三个值 ⇒ 其余状态在前端变成「未知状态」而 fail visible，"
        "或（若前端兜底）被静默归类。域必须逐项等于后端 Enum",
    ),
    Mutation(
        id="M17",
        side="be",
        path=GEN,
        kind="replace",
        scope="    for machine in _PROJECTED_TERMINALS:",
        offset=1,
        anchor="        terminals = _models.TERMINAL_STATES.get(machine)",
        new="        terminals = set(_models.OperationState)",
        want="test_terminal_set_equals_the_state_machine",
        wants=(
            "test_operation_terminal_set_is_a_strict_subset_of_the_state_domain",
            "test_generated_file_is_fresh",
        ),
        why="terminal 集被整体误抄成状态域 ⇒ 前端会在 `error` / `accepted` 这类非终态上"
        "停止等待并显示「完成」。`error` 可重试（AC 5.8），它绝不能进 terminal 集",
    ),
    Mutation(
        id="M18",
        side="be",
        path=GEN,
        kind="replace",
        scope='        "descriptor_fields": list(DESCRIPTOR_REQUIRED_FIELDS),',
        offset=1,
        anchor='        "descriptor_confirm_keys": sorted(descriptor.confirm_payload()),',
        new='        "descriptor_confirm_keys": sorted(descriptor.as_dict()),',
        want="test_confirm_keys_come_from_a_real_confirm_payload_call",
        wants=("test_generated_file_is_fresh",),
        why="confirm 回传清单改成 descriptor 响应键集 ⇒ 前端会回传 20 项而服务端只比对 10 项，"
        "或反过来漏掉改名项 `content_revision`。design §API 的 confirm 是十项，"
        "真源只能是 `confirm_payload()` 的真实调用结果",
    ),
    Mutation(
        id="M19",
        side="be",
        path=GEN,
        kind="replace",
        scope='        "rejection_status": {',
        offset=1,
        anchor="            str(exc.error_code): int(status)",
        new="            str(exc.error_code): 422",
        want="test_rejection_status_equals_the_single_mapping_point",
        wants=("test_stale_identity_codes_are_both_409", "test_generated_file_is_fresh"),
        why="把全部拒绝码压成 422 ⇒ 前端把 409（陈旧 identity，三门必须全关）与 403/404/500 "
        "全当成「内容不适配」。`classify_materialize_rejection` 是唯一映射点，抄第二份必漂",
    ),
    Mutation(
        id="M20",
        side="be",
        path=GEN,
        kind="replace",
        scope="    prefix = str(_router_module.USER_SYNC_PREFIX)",
        offset=6,
        anchor='    prefix_template = prefix.replace("{entry_id:path}", "{entry_id}")',
        new="    prefix_template = prefix",
        want="test_prefix_template_drops_the_path_converter_but_keeps_all_three_scope_segments",
        wants=(
            "test_a_real_slashed_entry_id_still_routes_through_the_generated_template",
            "test_generated_file_is_fresh",
        ),
        why="把 Starlette 的 `:path` 语法留在模板里 ⇒ 前端会拼出字面量 "
        "`.../entries/{entry_id:path}` 并拿到统一 404。模板是给 URL 用的，不是给路由声明用的",
    ),
    Mutation(
        id="M21",
        side="be",
        path=API,
        kind="replace",
        scope="export function buildSyncEndpointUrl(",
        offset=30,
        anchor="  return buildSyncEntryPrefix(scope) + suffix",
        new="  return buildSyncEntryPrefix(scope) + suffix +"
        " '/api/workpaper-sync/rooms/x/onlyoffice-callback'",
        want="test_the_callback_route_is_never_projected_to_the_frontend",
        why="让客户端代码里出现 callback 路径 ⇒ callback 是 DocServer 的服务凭证面，"
        "响应体是顶层 `{\"error\": N}`（被 ResponseWrapperMiddleware 刻意排除包装），"
        "前端解包层套上去必然错一层。判据必须剥掉注释再扫代码 —— 模块 docstring 里"
        "**必须**写清「为什么没有 callback 调用面」，裸 `in` 扫源码会假红",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 31 前端 DTO/API/tracker 与 contract 生成器守卫变异检验",
            backend_args=BE_ARGS,
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
        )
    )
