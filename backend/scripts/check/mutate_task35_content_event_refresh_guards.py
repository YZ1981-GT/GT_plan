# -*- coding: utf-8 -*-
"""Task 35 守卫变异检验（commit 后 content event → 前端刷新）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 35
Requirements: 14.7 · Property 57（变异检验本身）

## 四态

| 判定 | 含义 | 归因 |
|---|---|---|
| ``RED`` | **预期那条**判据打红 | 守卫有效 |
| ``GREEN`` | 无新增失败 | **守卫缺陷** |
| ``WRONG-TEST`` | 打红了但不是预期项 | 锚点错行 / 污染残留 |
| ``ANCHOR-MISS`` | 锚点非唯一命中 / 未落盘 | **本脚本缺陷** |

退出码不作判据；判定只看失败名差集。

## 本任务的四条约定

1. **锚点一律单行**。跨行锚点（含 ``\\n``）在 CRLF 工作树上必然 MISS。
2. **`want` 分两种形态**：``be`` 用短 nodeid（``file.py::Class::test``，**不带目录前缀**）；
   ``fe`` 用 vitest 的中文标题片段（同样不带路径前缀）。
3. **替换体必须是合法 TS/Python**：``.vue``/``.ts`` 走 esbuild（只剥类型不做检查），
   真语法错误会让整份模块编译失败、差集被清空 ⇒ 误判 GREEN。
4. **共用错误码单独立一条**（M09）：事件形态失败与刷新失败归一到同一个码时，
   较早那条分支会变成永远不可达 —— 本 spec 已三次抓到这个形态。

## 用法

    py -3 backend/scripts/check/mutate_task35_content_event_refresh_guards.py --list
    py -3 backend/scripts/check/mutate_task35_content_event_refresh_guards.py --check-anchors
    py -3 backend/scripts/check/mutate_task35_content_event_refresh_guards.py --run fe --out <path>
    py -3 backend/scripts/check/mutate_task35_content_event_refresh_guards.py --run be --out <path>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

FRONTEND = REPO / "audit-platform" / "frontend"
_FE_JSON = REPO / "backend" / "scripts" / "check" / "_wip_task35_fe.json"

SYNC = "audit-platform/frontend/src/components/workpaper/sync"
CR = f"{SYNC}/workpaperSyncContentRefresh.ts"
BANNER = f"{SYNC}/WorkpaperSyncContentRefreshBanner.vue"
TRACKER = f"{SYNC}/workpaperSyncOperationTracker.ts"
HOST = f"{SYNC}/WorkpaperSyncEditorHost.vue"

CE = "backend/app/services/workpaper_sync/content_events.py"
EVENTS = "backend/app/routers/events.py"
BUS = "backend/app/services/event_bus.py"
OUTBOX = "backend/app/services/workpaper_sync/outbox.py"

#: 覆盖面分母：Task 35 新建的四个判据文件 + 一个被加固的既有文件。
GUARD_FILES = {
    "workpaperSyncContentRefresh.spec.ts":
        "Task 35 新建：信封归一、wp+revision 去重、七个分支可达、dirty 不静默覆盖、"
        "两类失败码不相交、协调器零写入口、订阅接线、文案表自证",
    "WorkpaperSyncContentRefreshBanner.spec.ts":
        "Task 35 新建：六个可见状态的 DOM 形态、三个显式动作真接协调器、"
        "接进编辑器宿主、桥失败与刷新失败互不覆盖",
    "test_task35_content_event_refresh.py":
        "Task 35 新建：三条 lane 的真实 payload 都满足前端消费契约、Stream 往返逐项"
        "不丢、内容事件绝不走 debounce publish（AST + 反向自检）、/events/since 接线"
        "与真实执行",
    "test_task35_content_event_refresh_pg.py":
        "Task 35 新建：真库的 P52（回滚零事件 / 恰一事件 / 重放不重复副作用）、"
        "P53（真实派发 == outbox 行逐项）、P54（失败落 failed 可重放）、"
        "以及整条事件链零新 revision",
    "WorkpaperSyncEditorHost.spec.ts":
        "既有判据（Task 33），被 Task 35 加固：新增的 contentRefresh prop 必须被真驱动，"
        "零消费方判决因此覆盖它",
}

FE_FILTERS = [
    "workpaperSyncContentRefresh",
    "WorkpaperSyncContentRefreshBanner",
    "workpaperSyncOperationTracker",
    "WorkpaperSyncEditorHost",
]

# ── fe want（vitest 中文标题片段）
_FE_ENVELOPE_KEY = "真实 SSE 信封必须能算出 wp_id + revision 去重键"
_FE_SAME_KEY = "扁平形态与信封形态算出同一个键"
_FE_TRACKER_SHARED = "tracker 与本模块共用同一个键实现"
_FE_PAYLOAD_KEPT = "两种信封都保留**整份** payload"
_FE_KEY_SEGMENTS = "必填键集 = design 7 键 + 消费侧 4 键，两段不重叠"
_FE_REFUSAL_CODES = "五类形态各打各的码，五个码互不相同"
_FE_REQUIRED_MISSING = "缺任一必填键都打 required_key_missing"
_FE_DEDUPE_ONCE = "同一 wp+revision 重复投递只刷新一次"
_FE_OTHER_WP = "别的底稿的事件不刷新本底稿"
_FE_REPRESENTATION = "纯表示升级不刷新 HTML"
_FE_STALE = "自己刚提交的那条事件走 stale，不自触发重载"
_FE_ALL_BRANCHES = "七个 outcome 分支在同一个协调器上全部可达"
_FE_DIRTY_NO_RELOAD = "本地有未保存修改 ⇒ 一次 reload 都不发，只落待办"
_FE_DIRTY_MAX = "暂缓期间又来更高 revision ⇒ 待办取最大值"
_FE_ACCEPT_EMPTY = "没有待办时 acceptPending 显式拒绝"
_FE_DISMISS = "保留本地修改 ⇒ 清待办但**不**显示已最新"
_FE_TWO_CLASSES = "事件形态失败与刷新失败是两类：码不相交、可重试性相反"
_FE_NO_WRITE = "协调器的公开面里没有任何写入口"
_FE_SUBSCRIBE = "默认 subscribe 用 projectId + workpaper.content.updated 接共享连接"
_FE_START_IDEMPOTENT = "start() 幂等：重复调用只建一条订阅"
_FE_TEXT_TABLE = "六个状态各有文案，已落地状态各有具体动作提示，两张表零重复"
_FE_NO_SUCCESS = "只有 synced 允许说「已加载到最新」，失败态不得出现成功字样"
_FE_BANNER_IDLE = "无任何动作按钮"
_FE_BANNER_FAILED = "只出现「重试加载」"
_FE_BANNER_REJECTED = "可见但**不给**重试"
_FE_BANNER_DIRTY = "两个显式选择 + 提示逐字来自文案表"
_FE_BANNER_SYNCED = "success 基调 + 已加载修订号可见"
_FE_BANNER_REFRESHING = "转圈可见，且此时一个动作按钮都不渲染"
_FE_NO_DOUBLE_UNWRAP = "只有 extra 而没有 event_type 时不剥层"
_FE_REFRESH_FAILED_STATE = "refresh_failed + 可重试 + 待办保留"
_FE_HOST_RENDERS = "传了协调器 ⇒ 刷新条渲染，且状态随真实事件推进"
_FE_HOST_ABSENT = "未传协调器 ⇒ 整条不渲染，宿主其余部分不受影响"

# ── be want（短 nodeid，无目录前缀）
_T35 = "test_task35_content_event_refresh.py"
_T35PG = "test_task35_content_event_refresh_pg.py"
_BE_ROUND_TRIP = f"{_T35}::TestTypedReplayPreservesPayload::test_full_round_trip_keeps_every_key"
_BE_EXTENSION = f"{_T35}::TestTypedReplayPreservesPayload::test_extension_keys_survive"
_BE_UNPARSEABLE = (
    f"{_T35}::TestTypedReplayPreservesPayload::"
    "test_unparseable_entry_returns_none_instead_of_silently_empty"
)
_BE_SCOPING = f"{_T35}::TestTypedReplayPreservesPayload::test_timestamp_and_project_scoping"
_BE_DEDUPE = f"{_T35}::TestTypedReplayPreservesPayload::test_dedupe_key_matches_the_frontend_shape"
_BE_LANES = (
    f"{_T35}::TestFrontendConsumerContract::"
    "test_every_lane_supplies_every_key_the_consumer_requires"
)
_BE_STREAM_KEY = f"{_T35}::TestReplayEndpointWiring::test_stream_key_has_exactly_one_source"
_BE_SHARED_PROJECTION = (
    f"{_T35}::TestReplayEndpointWiring::test_since_endpoint_uses_the_shared_replay_projection"
)
_BE_SINCE_REAL = (
    f"{_T35}::TestReplayEndpointWiring::test_since_endpoint_really_returns_the_full_payload"
)
_BE_DIRTY_STRUCT = (
    f"{_T35}::TestFrontendCoordinatorHasNoWritePath::test_dirty_branch_does_not_reach_the_reload_hook"
)
_BE_DISJOINT_CODES = (
    f"{_T35}::TestFrontendCoordinatorHasNoWritePath::test_two_failure_classes_have_disjoint_codes"
)
_BE_ROLLBACK = f"{_T35PG}::test_rollback_leaves_no_durable_row_and_no_event"
_BE_REPLAY_NOOP = f"{_T35PG}::test_republish_and_worker_replay_do_not_duplicate_side_effects"
_BE_FAILURE_REPLAY = f"{_T35PG}::test_dispatch_failure_lands_failed_and_is_replayable"
_BE_ITEM_BY_ITEM = f"{_T35PG}::test_dispatched_typed_event_equals_the_outbox_row_item_by_item"


MUTATIONS: list[Mutation] = [
    # ═══════════ A. 信封归一（本任务修掉的真实缺陷） ═══════════
    Mutation(
        id="M01",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  const inner = asWire(outer.extra)",
        new="  const inner = null",
        want=_FE_ENVELOPE_KEY,
        wants=(_FE_SAME_KEY, _FE_TRACKER_SHARED, _FE_PAYLOAD_KEPT, _FE_DEDUPE_ONCE),
        why="退回修点前的形态：不剥 typed SSE 信封 ⇒ `wp_id`/`revision` 取不到、去重键恒 null，"
        "AC 11.9 的按 wp+revision 去重整条失效，而只喂扁平 payload 的判据全绿",
    ),
    Mutation(
        id="M02",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  return `${wpId}|${revision}`",
        new="  return `${wpId}|${revision}|${String(payload.operation_id)}`",
        want=_FE_DEDUPE_ONCE,
        wants=(_FE_TRACKER_SHARED,),
        why="去重键掺进 operation_id ⇒ 同一次 commit 的 operation 应用与纯表示升级被算成"
        "两条事实，同一个 revision 刷两遍（AC 11.9 明文键只由 wp+revision 组成）",
    ),
    Mutation(
        id="M03",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  if (eventName !== null && inner !== null) {",
        new="  if (inner !== null) {",
        want=_FE_NO_DOUBLE_UNWRAP,
        why="只看 `extra` 不看 `event_type` ⇒ 一个恰好带 `extra` 键的扁平 payload 会被误剥一层，"
        "于是内层的别的 wp_id 被当成本次事实",
    ),
    # ═══════════ B. commit 后判据与必填键 ═══════════
    Mutation(
        id="M04",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  if (!isOpaqueUuid(payload.content_version_id)) {",
        new="  if (!isOpaqueUuid(payload.content_version_id) && false) {",
        want=_FE_REFUSAL_CODES,
        why="去掉 commit 后判据 ⇒ 一条 commit 前的进程内 debounce 事件（没有已落库的 content "
        "version）也能驱动刷新，正是 AC 11.9 末句禁止的形态",
    ),
    Mutation(
        id="M05",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  for (const key of WP_CONTENT_EVENT_REQUIRED_KEYS) {",
        new="  for (const key of ([] as readonly string[])) {",
        want=_FE_REQUIRED_MISSING,
        why="必填键校验被清空 ⇒ 缺 `entry_id`/`reason`/`content_revision_advanced` 的半份事件"
        "照样进刷新流程，下游按不完整事实去追溯",
    ),
    Mutation(
        id="M06",
        side="fe",
        path=CR,
        kind="delete",
        anchor="  'content_version_id',",
        want=_FE_KEY_SEGMENTS,
        wants=(_FE_REQUIRED_MISSING,),
        why="消费侧键集少一项 ⇒ 与后端三条 lane 的双向锁死出现缺口，"
        "「11 键」这个分母不再由声明保证",
    ),
    Mutation(
        id="M07",
        side="fe",
        path=CR,
        kind="replace",
        anchor="    payload: Object.freeze({ ...payload }),",
        new="    payload: Object.freeze({ wp_id: payload.wp_id, revision: payload.revision }),",
        want=_FE_PAYLOAD_KEPT,
        why="消费侧白名单裁剪 ⇒ Requirement 13.2 的「不得丢失 extra」在读侧重新失效，"
        "representation/bundle/authority 三类身份在前端全查不到",
    ),
    # ═══════════ C. 七个分支：去重 / 归属 / 表示升级 / stale ═══════════
    Mutation(
        id="M08",
        side="fe",
        path=CR,
        kind="replace",
        anchor="    if (seen.has(key)) {",
        new="    if (seen.has(key) && false) {",
        want=_FE_DEDUPE_ONCE,
        wants=(_FE_ALL_BRANCHES,),
        why="去重表失效 ⇒ 重复投递重复刷新（Requirement 13.3 明令禁止），"
        "协同房间里一条事件被两个 worker 各投一次就刷两遍",
    ),
    Mutation(
        id="M09",
        side="fe",
        path=CR,
        kind="replace",
        anchor="        errorCode: 'content_refresh_reload_failed',",
        # 两处同形态（`lastFailure` 与 `record(...)`）：显式消歧到 `lastFailure` 那一处
        line=454,
        new="        errorCode: 'content_event_not_an_object',",
        want=_FE_REFRESH_FAILED_STATE,
        wants=(_FE_TWO_CLASSES, _FE_BANNER_FAILED),
        why="🔴 两类失败共用一个码 ⇒ 「事件读不懂」与「刷新失败」在 UI 上不可区分，"
        "而两者的可重试性相反（前者不可重试、后者必须给重试）。"
        "本 spec 已三次抓到共用码把较早分支遮成永不可达",
    ),
    Mutation(
        id="M10",
        side="fe",
        path=CR,
        kind="replace",
        anchor="        retryable: false,",
        new="        retryable: true,",
        want=_FE_TWO_CLASSES,
        wants=(_FE_BANNER_REJECTED,),
        why="事件形态失败标成可重试 ⇒ UI 给出「重试加载」，用户点了只会把同一条坏事件"
        "再读坏一次，而真正的新事实只能由下一条事件带来",
    ),
    Mutation(
        id="M11",
        side="fe",
        path=CR,
        kind="replace",
        anchor="    if (update.wpId !== options.wpId.value) {",
        new="    if (update.wpId !== options.wpId.value && false) {",
        want=_FE_OTHER_WP,
        wants=(_FE_ALL_BRANCHES,),
        why="共享连接是**项目级**的：不过滤 wp ⇒ 同项目任一底稿保存都会把当前底稿重载一次，"
        "审计师正在录入的表被别人的保存刷掉",
    ),
    Mutation(
        id="M12",
        side="fe",
        path=CR,
        kind="replace",
        anchor="    if (!update.contentRevisionAdvanced) {",
        new="    if (!update.contentRevisionAdvanced && false) {",
        want=_FE_REPRESENTATION,
        wants=(_FE_ALL_BRANCHES,),
        why="纯表示升级当成业务改动 ⇒ 一次隐形模板升级被推给审计师去重载，"
        "而业务内容一个字节都没变（`content_revision_advanced=false` 就是为它存在的）",
    ),
    Mutation(
        id="M13",
        side="fe",
        path=CR,
        kind="replace",
        anchor="    if (loaded !== null && update.revision <= loaded) {",
        new="    if (loaded !== null && update.revision < loaded) {",
        want=_FE_STALE,
        wants=(_FE_ALL_BRANCHES,),
        why="自己刚提交那条事件（revision == 已加载）不再判 stale ⇒ 每次保存后自触发一次重载，"
        "6000 会话规模下变成常态流量",
    ),
    # ═══════════ D. dirty 时不静默覆盖 ═══════════
    Mutation(
        id="M14",
        side="fe",
        path=CR,
        kind="replace",
        anchor="      rememberPending(update.revision)",
        new="      rememberPending(update.revision)\n      await runReload(update.revision)",
        want=_FE_DIRTY_NO_RELOAD,
        wants=(_FE_ALL_BRANCHES, _BE_DIRTY_STRUCT),
        why="dirty 分支里仍然 reload ⇒ 审计师刚录的未保存修改被服务端版本静默覆盖。"
        "Task 35 正文明文「dirty 时不静默覆盖」",
    ),
    Mutation(
        id="M15",
        side="fe",
        path=CR,
        kind="replace",
        anchor="    pendingRevision.value = known === null ? revision : Math.max(known, revision)",
        new="    pendingRevision.value = known === null ? revision : Math.min(known, revision)",
        want=_FE_DIRTY_MAX,
        why="待办 revision 取最小 ⇒ 用户确认后加载到一个**更旧**的版本，"
        "而 UI 显示「已加载最新」",
    ),
    Mutation(
        id="M16",
        side="fe",
        path=CR,
        kind="replace",
        anchor="        'content_refresh_no_pending_revision',",
        new="        'content_refresh_nothing_to_retry',",
        want=_FE_ACCEPT_EMPTY,
        why="acceptPending 与 retry 共用一个拒绝码 ⇒ 「没有待办可加载」与「没有失败可重试」"
        "不可区分，而两者出现在完全不同的用户路径上",
    ),
    Mutation(
        id="M17",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  function dismissPending(): void {",
        new="  function dismissPending(): void {\n    appliedRevision.value = pendingRevision.value",
        want=_FE_DISMISS,
        why="「保留本地修改」顺手把已加载修订号写成待办值 ⇒ UI 显示已加载到最新，"
        "而我们**根本没有**加载那个版本",
    ),
    # ═══════════ E. 订阅接线 ═══════════
    Mutation(
        id="M18",
        side="fe",
        path=CR,
        kind="replace",
        anchor="      eventName: WP_CONTENT_UPDATED_EVENT_NAME,",
        new="      eventName: 'workpaper.saved',",
        want=_FE_SUBSCRIBE,
        why="订阅错事件名 ⇒ 消费的是 `workpaper.saved`（走 debounce publish 的那条），"
        "正是 AC 11.9 禁止依赖的 commit 前事件；而「订阅了某个事件」这类判据全绿",
    ),
    Mutation(
        id="M19",
        side="fe",
        path=CR,
        kind="replace",
        anchor="    if (subscription !== null) return",
        new="    if (subscription !== null && false) return",
        want=_FE_START_IDEMPOTENT,
        why="start() 不幂等 ⇒ 组件重挂时叠加订阅，一条事件被投递 N 次；去重表能压住刷新，"
        "但共享连接的 refCount 永远归不了零",
    ),
    Mutation(
        id="M20",
        side="fe",
        path=TRACKER,
        kind="replace",
        anchor="  return contentUpdateDedupeKeyImpl(payload)",
        new=(
            "  const wire = payload as Record<string, unknown> | null\n"
            "  if (wire === null || typeof wire !== 'object') return null\n"
            "  const wpId = wire.wp_id\n"
            "  const revision = wire.revision\n"
            "  if (typeof wpId !== 'string' || wpId.trim() === '') return null\n"
            "  if (typeof revision !== 'number' || !Number.isInteger(revision)) return null\n"
            "  return `${wpId}|${revision}`"
        ),
        want=_FE_TRACKER_SHARED,
        why="tracker 退回自己那份只读顶层的实现 ⇒ 两个消费方两套口径，"
        "真实 SSE 信封在 tracker 侧又算不出键（第二真源）",
    ),
    # ═══════════ F. 文案表 ═══════════
    Mutation(
        id="M21",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  deferred_dirty: '请先保存或放弃本地修改，再点击「加载服务端最新版本」',",
        new="  deferred_dirty: '',",
        want=_FE_TEXT_TABLE,
        wants=(_FE_BANNER_DIRTY,),
        why="已落地状态没有下一步提示 ⇒ 界面停在「已暂不覆盖」而不说怎么继续，"
        "对用户就是一次无限等待",
    ),
    Mutation(
        id="M22",
        side="fe",
        path=CR,
        kind="replace",
        anchor="  refresh_failed: '重新加载表单失败：已提交的内容未受影响，可重试加载',",
        new="  refresh_failed: '已加载到最新内容',",
        want=_FE_NO_SUCCESS,
        wants=(_FE_BANNER_FAILED,),
        why="失败态说成已最新 ⇒ AC 11.10 的 fail-open 文案：一次真失败被成功文案盖掉，"
        "而「已提交的内容未受影响」这句安抚也一起消失",
    ),
    # ═══════════ G. 刷新条的门与动作 ═══════════
    Mutation(
        id="M23",
        side="fe",
        path=BANNER,
        kind="replace",
        anchor="  () => status.value === 'deferred_dirty' && props.refresh.pendingRevision.value !== null,",
        new="  () => props.refresh.pendingRevision.value !== null,",
        want=_FE_BANNER_FAILED,
        why="加载失败时也给出「保留本地修改」⇒ 用户以为放弃本地修改能解决一次加载失败，"
        "而失败与 dirty 是两件事（失败走重试）",
    ),
    Mutation(
        id="M24",
        side="fe",
        path=BANNER,
        kind="replace",
        anchor="    status.value === 'refresh_failed' &&",
        new="    status.value === 'event_rejected' &&",
        want=_FE_BANNER_FAILED,
        why="重试门挪到事件形态失败上 ⇒ 真正需要重试的那个状态（加载失败）反而没有出口，"
        "而重放坏事件的那个状态才有；两个状态的可重试性恰好相反",
    ),
    Mutation(
        id="M42",
        side="fe",
        path=BANNER,
        kind="replace",
        anchor="const failureCode = computed(() => props.refresh.lastFailure.value?.errorCode ?? '')",
        new="const failureCode = computed(() => '')",
        want=_FE_BANNER_REJECTED,
        wants=(_FE_BANNER_FAILED,),
        why="失败码不再渲染 ⇒ 一次真失败只剩一句中文，运维/审计师无从判断是事件形态问题"
        "还是加载问题，而两者的处置完全不同",
    ),
    Mutation(
        id="M25",
        side="fe",
        path=BANNER,
        kind="replace",
        anchor="const statusText = computed(() => WP_CONTENT_REFRESH_STATUS_TEXT[status.value])",
        new="const statusText = computed(() => status.value)",
        want=_FE_BANNER_IDLE,
        why="状态徽标改用裸英文标识符 ⇒ 界面出现 `deferred_dirty` 这种审计师读不懂的字样，"
        "违反 UI 全中文化；而「徽标非空」这类判据全绿",
    ),
    Mutation(
        id="M26",
        side="fe",
        path=HOST,
        kind="replace",
        anchor='      v-if="props.contentRefresh"',
        new='      v-if="false"',
        want=_FE_HOST_RENDERS,
        why="刷新条永不渲染 ⇒ 协调器成了没有渲染宿主的死代码：状态推进、待办 revision、"
        "两个显式动作全都只存在于内存里（平台已登记的第①类假绿形态）",
    ),
    Mutation(
        id="M27",
        side="fe",
        path=BANNER,
        kind="replace",
        anchor="        v-if=\"feedback.kind === 'progress'\"",
        new='        v-if="true"',
        want=_FE_BANNER_REFRESHING,
        wants=(_FE_BANNER_IDLE,),
        why="转圈无条件显示 ⇒ 已落地的 `deferred_dirty` / `refresh_failed` 也在转圈，"
        "用户看不出「还在飞」与「已落地、等你动」的差别（Task 34 已登记的无限等待形态）",
    ),
    Mutation(
        id="M28",
        side="fe",
        path=CR,
        kind="delete",
        anchor="    appliedRevision.value = revision",
        want=_FE_BANNER_SYNCED,
        wants=(_FE_DIRTY_MAX,),
        why="加载成功不记已加载修订号 ⇒ 追溯行恒显示占位符，"
        "且下一条同 revision 事件无法判 stale",
    ),
    # ═══════════ H. 后端：replay 投影与 /since 接线 ═══════════
    Mutation(
        id="M29",
        side="be",
        path=CE,
        kind="replace",
        anchor='        "extra": dict(payload.extra) if payload.extra else None,',
        new='        "extra": None,',
        want=_BE_ROUND_TRIP,
        wants=(_BE_EXTENSION, _BE_SINCE_REAL, _BE_DEDUPE),
        why="replay 投影丢掉整片 `extra` ⇒ 退回改动前的形态：断线补拉拿不到 "
        "`wp_id`/`revision`，AC 11.9 的去重与刷新在恢复路径上无从进行（Requirement 13.2）",
    ),
    Mutation(
        id="M30",
        side="be",
        path=CE,
        kind="delete",
        anchor='    "extra",',
        want=_BE_ROUND_TRIP,
        why="replay 项键集里去掉 `extra` ⇒ 契约声明与实际投影漂移，"
        "消费方按声明写代码就永远读不到业务键",
    ),
    Mutation(
        id="M31",
        side="be",
        path=CE,
        kind="replace",
        anchor='    own = str(item.get("project_id") or "")',
        new='    own = str(item.get("project_id") or str(project_id))',
        want=_BE_SCOPING,
        why="无归属事件被当成属于**任何**项目 ⇒ 跨项目事件下发到别人的流里（存在性泄露），"
        "而 Requirement 10.6 要求授权前置于资源读取",
    ),
    Mutation(
        id="M32",
        side="be",
        path=CE,
        kind="replace",
        anchor="    if isinstance(revision, bool) or not isinstance(revision, int):",
        new="    if not isinstance(revision, int):",
        want=_BE_DEDUPE,
        why="`bool` 是 `int` 的子类：`revision=True` 会算出 `wp|True` 这种键 ⇒ "
        "两条不同事实可能撞到同一个键，也可能让一条真事实永远去重不掉",
    ),
    Mutation(
        id="M33",
        side="be",
        path=CE,
        kind="replace",
        anchor='    return f"{wp_id}|{revision}"',
        new='    return f"{wp_id}|{revision}|{extra.get(\'operation_id\')}"',
        want=_BE_DEDUPE,
        wants=(_BE_ITEM_BY_ITEM,),
        why="后端去重键掺进 operation ⇒ 与前端口径分叉，"
        "「两侧同一口径」这个结论凭空成立（第二真源）",
    ),
    Mutation(
        id="M34",
        side="be",
        path=CE,
        kind="replace",
        anchor="        return None",
        # 五处同形态：显式消歧到 `replay_entry_projection` 的 except 分支那一处
        line=91,
        new="        return {}",
        want=_BE_UNPARSEABLE,
        why="解析失败返回空壳而不是 None ⇒ 调用方数不出「丢了几条」，"
        "事件被丢弃这件事在日志与响应里都不可见（Requirement 13.9 点名的形态）",
    ),
    Mutation(
        id="M35",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="        stream_key = EVENT_STREAM_KEY",
        new='        stream_key = "events:stream"',
        want=_BE_STREAM_KEY,
        wants=(_BE_SINCE_REAL,),
        why="退回改动前的第二真源字面量 ⇒ 读一条**没有任何写入方**的 stream，"
        "断线补拉恒返回空列表（Requirement 13.2 的读取面整条失效）",
    ),
    Mutation(
        id="M36",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="            item = replay_entry_projection(msg_id, data)",
        new=(
            "            item = {\n"
            '                "event_id": msg_id,\n'
            '                "event_type": data.get("event_type", ""),\n'
            '                "project_id": data.get("project_id", ""),\n'
            '                "year": None,\n'
            '                "account_codes": None,\n'
            '                "timestamp": None,\n'
            '                "extra": None,\n'
            "            }"
        ),
        want=_BE_SHARED_PROJECTION,
        wants=(_BE_SINCE_REAL,),
        why="端点里再拼一份投影 ⇒ 第二真源，而它（正如改动前那份）把 `extra` 整片丢了；"
        "共享纯函数存在的唯一理由就是不许有第二份",
    ),
    Mutation(
        id="M37",
        side="be",
        path=EVENTS,
        kind="replace",
        anchor="            if not belongs_to_project(item, project_id):",
        new="            if False:",
        want=_BE_SINCE_REAL,
        why="不做项目过滤 ⇒ 别的项目的内容事件被下发给当前项目，"
        "既泄露存在性也会让前端按别人的 revision 刷新",
    ),
    Mutation(
        id="M38",
        side="be",
        path=BUS,
        kind="replace",
        anchor="EVENT_STREAM_KEY = _STREAM_KEY",
        new='EVENT_STREAM_KEY = "events:stream"',
        want=_BE_STREAM_KEY,
        why="公开别名与真实写入键分叉 ⇒ 「唯一真源」只是名义上的，读取方照样读错 stream",
    ),
    # ═══════════ I. 后端：Property 52 / 54 的提交边界与重放 ═══════════
    Mutation(
        id="M39",
        side="be",
        path=OUTBOX,
        kind="replace",
        anchor="        # flush 而不是 commit：耐久性由调用方那一次 commit 提供，Requirement 13.1。",
        new="        await db.commit()",
        want=_BE_ROLLBACK,
        why="入队自己 commit ⇒ 调用方回滚后耐久行仍在，随后被发布出去："
        "下游按一个**不存在**的内容版本去刷新（Property 52 前半的幽灵事件）",
    ),
    Mutation(
        id="M40",
        side="be",
        path=OUTBOX,
        kind="replace",
        anchor="    {EventType.WORKPAPER_SAVED, EventType.WORKPAPER_CONTENT_UPDATED}",
        new="    {EventType.WORKPAPER_SAVED}",
        want=_BE_REPLAY_NOOP,
        why="内容事件不再受 fan-out 闸门管辖 ⇒ worker 重放把订阅它的整片副作用再跑一遍"
        "（Requirement 13.3 明令「重复投递不得重复刷新」）",
    ),
    Mutation(
        id="M41",
        side="be",
        path=OUTBOX,
        kind="replace",
        anchor='        """派发失败后归还派发权，让 worker 重放能重新抢到（Property 54）。"""',
        new='        """mutated."""\n        return False',
        want=_BE_FAILURE_REPLAY,
        why="派发失败后不归还派发权 ⇒ 重放命中闸门被跳过，事件被**永久静默丢失**，"
        "正是 Requirement 13.4 禁止的形态（行看着变绿了，副作用一次都没跑）",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 35 content event → 前端刷新守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task35_content_event_refresh.py",
                "backend/tests/workpaper_sync/test_task35_content_event_refresh_pg.py",
                "-q", "--tb=no", "-rfE", "-p", "no:cacheprovider", "-p", "no:randomly",
            ],
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
            # 冻结基线来源：本次收口前实测（仓库根执行）
            #   test_task35_content_event_refresh.py      27 passed
            #   test_task35_content_event_refresh_pg.py    8 passed
            baseline_backend_passed=35,
            #   workpaperSyncContentRefresh.spec.ts             38
            #   WorkpaperSyncContentRefreshBanner.spec.ts       15
            #   workpaperSyncOperationTracker.spec.ts           13
            #   WorkpaperSyncEditorHost.spec.ts                 41
            baseline_frontend_passed=107,
        )
    )
