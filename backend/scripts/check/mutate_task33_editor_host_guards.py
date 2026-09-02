# -*- coding: utf-8 -*-
"""Task 33 守卫变异检验（Excel/Word 编辑器挂载宿主）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 33
Requirements: 14.7 · Property 57（变异检验本身）

## 四态

| 判定 | 含义 | 归因 |
|---|---|---|
| ``RED`` | **预期那条**判据打红 | 守卫有效 |
| ``GREEN`` | 无新增失败 | **守卫缺陷** |
| ``WRONG-TEST`` | 打红了但不是预期项 | 锚点错行 / 污染残留 |
| ``ANCHOR-MISS`` | 锚点非唯一命中 / 未落盘 | **本脚本缺陷** |

退出码不作判据；判定只看失败名差集。

## 宿主专属的两条

1. **`.vue` 的变异不能靠 TS 报错来「生效」**：vitest 走 esbuild，只剥类型不做检查。
   于是「把 prop 改名」在运行时表现为 `props.descriptor === undefined` ——
   这正是要打红的那个真实缺陷形态（Vue 传不存在的 prop 是静默失效）。
   反过来，任何真语法错误会让整份 SFC 编译失败、差集被清空 ⇒ 误判 GREEN，
   故每条替换体都必须是合法 TS/模板。
2. **零消费方在组件里的形态是「声明了 prop/emit 却没有任何驱动」**。
   M02/M03 就是照这个形态注入的：加一个没人传的 prop、加一个永不触发的 emit，
   都必须被文件末尾的**正面判决**打红。只有「声明存在」类判据会对它们全绿。

## 用法

    py -3 backend/scripts/check/mutate_task33_editor_host_guards.py --list
    py -3 backend/scripts/check/mutate_task33_editor_host_guards.py --check-anchors
    py -3 backend/scripts/check/mutate_task33_editor_host_guards.py --run fe --out <path>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

FRONTEND = REPO / "audit-platform" / "frontend"
_FE_JSON = REPO / "backend" / "scripts" / "check" / "_wip_task33_fe.json"

SYNC = "audit-platform/frontend/src/components/workpaper/sync"
HOST = f"{SYNC}/WorkpaperSyncEditorHost.vue"
RUNTIME = f"{SYNC}/workpaperSyncEditorHostRuntime.ts"
BRIDGE = f"{SYNC}/useWorkpaperSyncBridge.ts"

#: 覆盖面分母。Task 33 的判据全在一个 spec 文件里（宿主的 DOM 与事件是一整块），
#: 故分母只有一项 —— 拆成多文件反而会让「哪条判据在管什么」更难读。
GUARD_FILES = {
    "WorkpaperSyncEditorHost.spec.ts": (
        "挂载顺序、确认门、确认失败收回编辑器、crash→recovery、七个事件的真实触发、"
        "config 唯一来源、prop/emit 正面判决"
    ),
}

FE_FILTERS = ["WorkpaperSyncEditorHost"]

_ORDER = "四步顺序被真实调用序列锁死"
_READY_NOT_SAVEABLE = "ready 不等于可保存"
_READONLY = "只读 participant"
_CONFIG_VERBATIM = "DocEditor config 逐字来自 descriptor"
_NO_HTTP_IMPORT = "宿主两个文件都不 import 任何 HTTP 面"
_FORCESAVE_CONFIG = "config 打开了编辑器侧 forcesave 时拒绝挂载"
_DOC_MISSING = "buildDocEditorConfig 对缺 document 段的 config fail closed"
_CONFIRM_FAIL = "confirm 409 ⇒ 销毁编辑器、撤掉保存入口、状态条粘住失败"
_STICKY_AFTER_TEARDOWN = "确认失败后再卸载（销毁成功）也不得把状态条洗回成功文案"
_CRASH_RECOVERY = "已确认房间内的编辑器异常 ⇒ 服务端列出恢复项 ⇒ 渲染恢复区、不渲染重试"
_CRASH_NO_OPERATION = "claim 之前 recoveryCase 事件不得携带 operation id，三实体全空"
_CRASH_NO_CASE = "服务端列不出可认领项 ⇒ 显式失败，既不渲染恢复区也不退化成重试"
_CRASH_BEFORE_CONFIRM = "确认之前的编辑器异常不进恢复流程"
_FORCESAVE_OK = "forceSave() 真发 forcesave 并 emit saveRequested"
_SAVE_BUTTON = "点击保存按钮走同一条路径"
_DIRTY = "onDocumentStateChange 真实触发 dirty"
_DURABLE = "incomingDurable / terminal 由桥的真实状态推进触发，且不伪造 incoming 摘要"
_TERMINAL_DISTINCT = "conflict 终态与 applied 终态可分辨"
_SYNC_STATE = "getSyncState() 逐项来自桥"
_REMOUNT = "新代际重开：旧编辑器被销毁、新 descriptor 重新挂载并重新 confirm"
_IDEMPOTENT = "同一 descriptor 重复下发不重复挂载"
_IDENTITY_SWAP = "在编辑中被换掉 descriptor 身份 ⇒ 显式失败，不静默替换编辑器"
_SCRIPT_URL = "未注入 loader 时按 documentServerUrl 载入 api.js"
_ENV_FALLBACK = "prop 未给时回落部署期环境变量"
_NO_URL = "没有服务地址也没有 loader ⇒ 显式失败，不停在「正在打开」"
_CTOR_THROWS = "DocEditor 构造抛错 ⇒ 不得上报「已挂载」，且失败可见"
_STICKY_TERMINAL = "宿主上报口在终态下不抛，且仍然记住失败"
_ERROR_CODE = "编辑器回调取码归一"
_DIRTY_STRICT = "dirty 只认 data===true"
_UNREGISTERED_CODE = "未登记的宿主失败码被换成显式的「码未登记」"
_PROP_VERDICT = "组件声明的 prop 集合逐字等于本文件真正驱动过的集合"
_EMIT_VERDICT = "组件声明的 emit 集合逐字等于本文件真正触发过的集合"

MUTATIONS: list[Mutation] = [
    # ═══════════ A. 不存在 prop / 零消费方（Task 33 明文点名的两条） ═══════════
    Mutation(
        id="M01",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="    descriptor: WorkpaperSyncEditorLaunchDescriptor | null",
        new="    launchDescriptor: WorkpaperSyncEditorLaunchDescriptor | null",
        want=_ORDER,
        wants=(_PROP_VERDICT,),
        why="把 prop 改名 ⇒ 父传的 `descriptor` 变成一个**不存在的 prop**，Vue 静默丢掉它，"
        "组件读到 undefined。Volar/vitest/get_diagnostics 三层全绿，只有真的看"
        "「DocEditor 有没有被构造」才能证伪。AC 11.12 点名的就是这个形态",
    ),
    Mutation(
        id="M02",
        side="fe",
        path=HOST,
        kind="insert",
        anchor="    descriptor: WorkpaperSyncEditorLaunchDescriptor | null",
        new="    sheetKey?: string",
        want=_PROP_VERDICT,
        why="加一个**没人传**的 prop ⇒ 死 prop。它不会让任何行为判据变红，"
        "只有「声明集合逐字等于驱动集合」这条正面判决能抓住 —— "
        "而那正是 Task 31 抓出 7 个死导出的同一形态在组件里的样子",
    ),
    Mutation(
        id="M03",
        side="fe",
        path=HOST,
        kind="insert",
        anchor="  recoveryCase: [{ caseId: string; reason: string; operationId?: never }]",
        new="  fallback: []",
        want=_EMIT_VERDICT,
        why="声明一个**永不触发**的 emit（design 的事件表里就写着 `fallback: []`，"
        "而宿主没有任何合法触发路径）⇒ 零消费方。AC 11.5 明文「不得只 emit fallback」，"
        "声明了却不触发同样是死代码",
    ),
    Mutation(
        id="M04",
        side="fe",
        path=HOST,
        kind="delete",
        anchor="  emit('dirty', { dirty })",
        want=_DIRTY,
        wants=(_EMIT_VERDICT,),
        why="删掉 dirty 的唯一触发 ⇒ 声明的事件失去真实触发路径。页面拿不到脏标记，"
        "AC 4.8 的离开阻断在 UI 层就没了依据。两条判据必须同时红",
    ),
    # ═══════════ B. ready 即可保存 ═══════════
    Mutation(
        id="M05",
        side="fe",
        path=HOST,
        kind="replace",
        anchor='      :disabled="!canForcesave"',
        new='      :disabled="!editorLive"',
        want=_ORDER,
        wants=(_READY_NOT_SAVEABLE,),
        why="保存钮改成「编辑器在就能点」⇒ ready（甚至 mount）之后立刻可保存，"
        "而服务端确认还没回来。Property 11 后半明文：确认成功前不得 forcesave",
    ),
    Mutation(
        id="M06",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="  if (!props.bridge.canForcesave.value) {",
        new="  if (false) {",
        want=_READY_NOT_SAVEABLE,
        why="拆掉 `forceSave()` 的确认门 ⇒ 程序化调用直接落到桥。桥自己也会拒，"
        "但走的是不写 `lastError` 的 `refuse()` ⇒ 状态条什么都不变、宿主也不可见。"
        "判据断言的是**具体码**，故 `if (false)` 这类「门看起来还关着」的形态照样红",
    ),
    Mutation(
        id="M07",
        side="fe",
        path=HOST,
        kind="replace",
        anchor='      <div v-if="!editing" class="wp-sync-editor-host__mask" data-testid="wp-sync-host-mask">',
        new='      <div v-if="false" class="wp-sync-editor-host__mask" data-testid="wp-sync-host-mask">',
        want=_ORDER,
        wants=(_READY_NOT_SAVEABLE,),
        why="撤掉确认前的遮罩 ⇒ 用户在服务端还没确认身份时就看见一个「可以编辑」的界面，"
        "在里面输入的内容没有任何 room 基线兜底",
    ),
    # ═══════════ C. 确认失败仍 editing ═══════════
    Mutation(
        id="M08",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="  () => activeDescriptor.value !== null && props.bridge.mode.value === 'oo',",
        new="  () => activeDescriptor.value !== null,",
        want=_CONFIRM_FAIL,
        wants=(_READONLY,),
        why="编辑器渲染不再看 mode ⇒ 桥因 stale identity 回到 HTML 之后，DOM 里仍留着"
        "一个可编辑的编辑器。这是本任务最贵的假绿：状态机是对的，界面是错的",
    ),
    Mutation(
        id="M09",
        side="fe",
        path=HOST,
        kind="delete",
        scope="    if (descriptor === null || props.bridge.mode.value !== 'oo') {",
        offset=2,
        anchor="      destroyEditor()",
        want=_CONFIRM_FAIL,
        why="mode 离开 oo 时不销毁编辑器 ⇒ iframe 还活着、还连着旧 doc_key，"
        "用户的后续编辑会打到一个服务端已经不认的代际上",
    ),
    Mutation(
        id="M10",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="    failHost('confirm_descriptor', error, false)",
        new="    void error",
        want=_CONFIRM_FAIL,
        why="确认失败被吞 ⇒ 宿主不 emit error、不显示原因。桥那边虽然记住了，"
        "但页面级消费方（Task 34 的状态条之外的宿主自身反馈）什么都不知道",
    ),
    Mutation(
        id="M11",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="const feedback = computed(() => props.bridge.feedback.value)",
        new="const feedback = computed(() => ({ kind: 'success', message: '同步成功' }))",
        want=_CONFIRM_FAIL,
        wants=(_STICKY_AFTER_TEARDOWN, _ORDER),
        why="状态条改成自己编一句成功文案 ⇒ 一次真失败之后仍显示「同步成功」。"
        "AC 11.10 / Property 48 明令禁止；文案真源只能是桥",
    ),
    # ═══════════ D. claim 前伪 operation id ═══════════
    Mutation(
        id="M12",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="  emit('recoveryCase', { caseId: claimable.caseId, reason: claimable.reason })",
        new="  emit('recoveryCase', {\n"
        "    caseId: claimable.caseId,\n"
        "    reason: claimable.reason,\n"
        "    operationId: descriptor.operationId,\n"
        "  } as never)",
        want=_CRASH_NO_OPERATION,
        why="claim 之前就给 recovery case 编一个 operation id ⇒ UI 会显示「已有回写任务」，"
        "用户据此去点普通重试，而服务端那边三实体一个都还不存在（AC 5.8）",
    ),
    Mutation(
        id="M13",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="  if (inRecovery.value) return false",
        new="  return true",
        want=_CRASH_RECOVERY,
        wants=(_CRASH_NO_CASE, _CRASH_BEFORE_CONFIRM),
        why="普通 operation 重试的门全开 ⇒ recovery 期间也显示「重试回写」。"
        "AC 5.8 末句明文：nullable operation 的 recovery case 不得进入普通 retry",
    ),
    Mutation(
        id="M14",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="    failHost('list_recovery_cases', hostRefusal('editor_host_recovery_case_absent', message), true)",
        new="    void message",
        want=_CRASH_NO_CASE,
        why="服务端列不出可认领项时静默返回 ⇒ 编辑器崩了、恢复项也没有，界面却什么都不说。"
        "这类静默是「宿主自造 recovery case」的反面，同样不可接受",
    ),
    Mutation(
        id="M15",
        side="fe",
        path=HOST,
        kind="replace",
        scope="    cases = await props.bridge.listRecoveryCases({",
        offset=1,
        anchor="      roomId: descriptor.roomId,",
        new="      roomId: descriptor.docKey,",
        want=_CRASH_RECOVERY,
        why="recovery list 带错 room 身份 ⇒ 服务端按另一个 room 授权与列举。"
        "AC 10.6 要求 list 必须带**显式** room_id/generation，"
        "而 doc_key 与 room_id 都是字符串，形态判据分不出来",
    ),
    Mutation(
        id="M16",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="  if (props.bridge.state.value !== 'oo_editing' || descriptor === null) {",
        new="  if (descriptor === null) {",
        want=_CRASH_BEFORE_CONFIRM,
        why="确认之前的编辑器异常也去查恢复项 ⇒ `recovery_case_observed` 在"
        "`descriptor_mounted` 上没有出边，桥会抛非法转换；而那时服务端根本还没有"
        "unmatched delivery。转换表是唯一判据，宿主必须照表分流",
    ),
    # ═══════════ E. descriptor 是唯一 config 来源 ═══════════
    Mutation(
        id="M17",
        side="fe",
        path=RUNTIME,
        kind="replace",
        anchor="    width: '100%',",
        new="    width: '100%',\n    token: 'forged-by-host',",
        want=_CONFIG_VERBATIM,
        why="宿主自己往 config 里塞一个 token ⇒ 第二份 config 的入口。"
        "包含式判据（descriptor 的键都在）对它全绿，只有**等值**判据能抓住",
    ),
    Mutation(
        id="M18",
        side="fe",
        path=RUNTIME,
        kind="replace",
        anchor="export const WP_SYNC_HOST_ADDED_CONFIG_KEYS = ['width', 'height', 'events'] as const",
        new="export const WP_SYNC_HOST_ADDED_CONFIG_KEYS = ['width', 'height'] as const",
        want=_CONFIG_VERBATIM,
        why="削掉判据的分母常量。它同时证明那条判据**不是**自证式的 —— "
        "若判据是拿常量跟常量比（把被验证的常量当期望值），这条变异会全绿",
    ),
    Mutation(
        id="M19",
        side="fe",
        path=RUNTIME,
        kind="replace",
        anchor="  if (customization.forcesave === true) {",
        new="  if (customization.forcesave === undefined) {",
        want=_FORCESAVE_CONFIG,
        why="编辑器侧自动保存的门失效 ⇒ OO 自己发 forcesave，产生**没有 frozen request** 的"
        "孤儿 callback，只能进 recovery case（AC 4.1 明令禁止把它当保存完成）",
    ),
    Mutation(
        id="M20",
        side="fe",
        path=RUNTIME,
        kind="delete",
        anchor="    refuse('editor_host_config_document_missing')",
        want=_DOC_MISSING,
        why="缺 document 段照挂 ⇒ DocEditor 拿不到 key/url，界面停在空白 iframe，"
        "而「config 非空」这条上游校验只看 config 整体不空",
    ),
    # ═══════════ F. 挂载时序与容器 ═══════════
    Mutation(
        id="M21",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="  await nextTick()",
        new="  void 0",
        want=_REMOUNT,
        why="不等一次渲染就构造 DocEditor ⇒ placeholder 容器还没带上新 id 进 DOM，"
        "OnlyOffice 静默什么都不做、用户只看到空白（legacy 的真实故障形态）。"
        "🔴 首轮实测判定 WRONG-TEST：**首次**挂载碰不到这条 —— 紧随其后的 "
        "`await docsApiLoader()` 恰好也让出一个微任务，Vue 的渲染 flush 在那时已经跑完。"
        "真正需要它的是**重挂**（容器 id 变了但旧 id 还在 DOM 上），故 want 指向重开判据；"
        "把 want 改指过来比强行给首挂判据编一条时序断言诚实",
    ),
    Mutation(
        id="M22",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="    editorInstance = new api.DocEditor(containerId.value, config)",
        new="    editorInstance = new api.DocEditor(`${containerId.value}-drift`, config)",
        want=_ORDER,
        why="传给 DocEditor 的容器 id 与模板渲染出来的那个漂开一格 ⇒ 编辑器找不到容器。"
        "`GtOnlyOfficeSheet` 的注释里记着同一个坑（computed+Date.now() 每次求值都变），"
        "判据必须用 `getElementById` 真查一次",
    ),
    Mutation(
        id="M23",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="    failHost('create_doc_editor', error, true)",
        new="    props.bridge.notifyEditorMounted()",
        want=_CTOR_THROWS,
        why="构造抛错却上报「已挂载」= 伪造挂载。桥于是进 `descriptor_mounted` 并等一个"
        "永远不会来的 `onDocumentReady`，用户卡在「等待文档就绪」",
    ),
    Mutation(
        id="M24",
        side="fe",
        path=HOST,
        kind="delete",
        anchor="    if (mountedKey === key) return",
        want=_IDEMPOTENT,
        why="同一 descriptor 每次下发都重挂 ⇒ 父组件任何一次无关重渲染都会重建 iframe，"
        "用户正在编辑的内容被丢掉，桥还会多收一次 `editor_mounted`",
    ),
    Mutation(
        id="M25",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="  props.documentServerUrl.trim() !== '' ? props.documentServerUrl : ENV_DOCUMENT_SERVER_URL,",
        new="  ENV_DOCUMENT_SERVER_URL,",
        want=_SCRIPT_URL,
        why="显式 prop 被忽略、只认环境变量 ⇒ `documentServerUrl` 成为死 prop。"
        "本仓库 `.env` 里那个值恰好非空，所以「载入成功」照旧成立 —— "
        "只有断言**实际 script src** 才能抓住",
    ),
    # ═══════════ G. 桥上报口（本任务补的 fail-open 缺口） ═══════════
    Mutation(
        id="M26",
        side="fe",
        path=BRIDGE,
        kind="replace",
        scope="  function notifyHostFailure(stage: string, error: unknown): WorkpaperSyncBridgeError {",
        offset=2,
        anchor="    lastError.value = described",
        new="    void described",
        want=_NO_URL,
        wants=(_STICKY_TERMINAL, _CTOR_THROWS),
        why="上报口不记 sticky error ⇒ 状态是 `error` 但文案退回状态表的「同步失败」，"
        "真实原因（没配服务地址 / 内核构造失败）丢失，也不再优先于后续状态文案",
    ),
    Mutation(
        id="M27",
        side="fe",
        path=BRIDGE,
        kind="replace",
        scope="  function notifyHostFailure(stage: string, error: unknown): WorkpaperSyncBridgeError {",
        offset=4,
        anchor="      apply('sync_failed')",
        new="      void 0",
        want=_NO_URL,
        wants=(_CTOR_THROWS, _FORCESAVE_CONFIG),
        why="上报口只记错不推状态 ⇒ 桥永远停在 `oo_loading`（它在 "
        "`WP_BRIDGE_IN_FLIGHT_STATES` 里）：状态条显示进度、离开被阻断、"
        "而编辑器其实根本没挂上。这就是本任务修掉的那个 fail-open 形态",
    ),
    # ═══════════ H. 事件载荷与只读投影 ═══════════
    Mutation(
        id="M28",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="        artifactSha256: null,",
        new="        artifactSha256: activeDescriptor.value?.artifactSha256 ?? null,",
        want=_DURABLE,
        why="拿 descriptor 的（materialize **出去**那份）artifact 摘要充当回传 incoming 的摘要"
        "⇒ 「回来的文件就是我发出去的那份」这个结论凭空成立。"
        "operation 投影里没有 incoming digest 是已登记缺口，缺就得是 null",
    ),
    Mutation(
        id="M29",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="        state: next as 'applied' | 'conflict' | 'refresh_required',",
        new="        state: 'applied',",
        want=_TERMINAL_DISTINCT,
        why="三个终态压成 applied ⇒ 冲突与需重载都被报成「结构化回写完成」。"
        "AC 11.3 要求四类文案分别表达，不得统一显示成功",
    ),
    Mutation(
        id="M30",
        side="fe",
        path=HOST,
        kind="delete",
        anchor="  emit('saveRequested', { operationId })",
        want=_FORCESAVE_OK,
        wants=(_SAVE_BUTTON, _EMIT_VERDICT),
        why="保存受理后不 emit ⇒ 页面拿不到 requested operation id，"
        "后续所有按 operation 的查询/重试都没有入口（声明的事件成了死代码）",
    ),
    Mutation(
        id="M31",
        side="fe",
        path=HOST,
        kind="replace",
        anchor="    canForcesave: props.bridge.canForcesave.value,",
        new="    canForcesave: true,",
        want=_SYNC_STATE,
        why="`getSyncState()` 自己编一份门控结论 ⇒ 第二份状态真源。"
        "调用方据此显示保存可用，而桥那边其实已经在等回传",
    ),
    # ═══════════ I. 纯函数层 ═══════════
    Mutation(
        id="M32",
        side="fe",
        path=RUNTIME,
        kind="replace",
        anchor="  return wrapper.data === true",
        new="  return Boolean(wrapper.data)",
        want=_DIRTY_STRICT,
        why="dirty 判定放宽成真值判断 ⇒ OO 传 `{data:'saved'}` 之类的字符串也被读成脏，"
        "离开阻断会在没有任何未保存修改时把用户困住",
    ),
    Mutation(
        id="M33",
        side="fe",
        path=RUNTIME,
        kind="replace",
        anchor="  return 'editor_error_unknown'",
        new="  return ''",
        want=_ERROR_CODE,
        why="取不到码时回空串 ⇒ 下游 `classifySyncFailure` 会因空码抛契约错误，"
        "一次真实的编辑器异常变成一个看不懂的内部错误",
    ),
    Mutation(
        id="M34",
        side="fe",
        path=RUNTIME,
        kind="replace",
        anchor="  if (text === undefined) {",
        new="  if (false) {",
        want=_UNREGISTERED_CODE,
        why="未登记的失败码不再被拦 ⇒ UI 直接显示一个裸英文标识符，"
        "AC 11.6 要求阻断原因对当前用户可读",
    ),
    # ═══════════ J. 重开与结构判据 ═══════════
    Mutation(
        id="M35",
        side="fe",
        path=HOST,
        kind="delete",
        anchor="    descriptor.representationGeneration,",
        want=_IDENTITY_SWAP,
        why="挂载身份不把 representation 代际算进去 ⇒ 只差 representation 的一次替换被"
        "当成同一份 descriptor 吞掉，编辑器仍指着旧 representation 而没人知道。"
        "`mountedKey` 少一项就是少一次重开",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 33 编辑器挂载宿主守卫变异检验",
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
        )
    )
