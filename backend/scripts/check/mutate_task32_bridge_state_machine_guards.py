# -*- coding: utf-8 -*-
"""Task 32 守卫变异检验（桥状态机 / 模式存储 / composable + 跨文档锚点）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
Requirements: 14.7 · Property 57（变异检验本身）

## 四态

| 判定 | 含义 | 归因 |
|---|---|---|
| ``RED`` | **预期那条**判据打红 | 守卫有效 |
| ``GREEN`` | 无新增失败 | **守卫缺陷** |
| ``WRONG-TEST`` | 打红了但不是预期项 | 锚点错行 / 污染残留 |
| ``ANCHOR-MISS`` | 锚点非唯一命中 / 未落盘 | **本脚本缺陷** |

退出码不作判据；判定只看失败名差集。

## 硬约束（沿用 Task 31 的三条实证）

1. **一律 `scope`+`offset` 相对定位或唯一整行锚点，不写绝对 `line=`**。
2. **替换体必须语法合法** —— TS 编译不过时整套挂掉、差集被清空，判定会误报 GREEN。
3. **前端变异走 vitest JSON reporter**（`_mutation_kit.runner.run_vitest` 负责），
   控制台 FAIL 行会按终端宽度折行。

## 状态机专属的第四条

状态机最典型的死代码是「声明了一个状态却没有任何一条边通向它」。M17 把
`descriptor_mounted --document_ready--> confirming_descriptor` 改成直通 `oo_editing`，
于是 `confirming_descriptor` 变成孤岛 —— 判据必须同时打红「每个状态都有入边」与
「confirm 是 oo_editing 的唯一入口」。只打红后者说明可达性判据没起作用。

## 用法

    py -3 backend/scripts/check/mutate_task32_bridge_state_machine_guards.py --list
    py -3 backend/scripts/check/mutate_task32_bridge_state_machine_guards.py --check-anchors
    py -3 backend/scripts/check/mutate_task32_bridge_state_machine_guards.py --run fe --out <path>
    py -3 backend/scripts/check/mutate_task32_bridge_state_machine_guards.py --run be --out <path>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

FRONTEND = REPO / "audit-platform" / "frontend"
_FE_JSON = REPO / "backend" / "scripts" / "check" / "_wip_task32_fe.json"

SYNC = "audit-platform/frontend/src/components/workpaper/sync"
MACHINE = f"{SYNC}/workpaperSyncBridgeMachine.ts"
STORAGE = f"{SYNC}/workpaperSyncModeStorage.ts"
BRIDGE = f"{SYNC}/useWorkpaperSyncBridge.ts"

#: 覆盖面分母：本任务的守卫文件 → 归属说明。空分母会让覆盖统计恒成功。
GUARD_FILES = {
    "workpaperSyncBridgeMachine.spec.ts": "状态域/转换表/终态/快照投影/P46 随机序列",
    "workpaperSyncModeStorage.spec.ts": "统一键、旧键幂等迁移、capability 回落",
    "useWorkpaperSyncBridge.spec.ts": "端点接线、门控、duplicate 授权顺序、P48 粘性 error",
    "test_task32_bridge_state_domain.py": "AC 11.2 / design 键模板 / 后端枚举的跨文档锚点",
}

BE_ARGS = [
    "backend/tests/workpaper_sync/test_task32_bridge_state_domain.py",
    "-q",
    "--tb=no",
    "-p",
    "no:randomly",
]
FE_FILTERS = [
    "workpaperSyncBridgeMachine",
    "workpaperSyncModeStorage",
    "useWorkpaperSyncBridge",
]

MUTATIONS: list[Mutation] = [
    # ═══════════════ 状态机：终态与非法转换 ═══════════════
    Mutation(
        id="M01",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="  applied: ['applied', 'error'],",
        new="  applied: ['applied', 'error', 'merging', 'conflict', 'application_bound'],",
        want="applied 不得回退到 merging/conflict",
        why="给 applied 加回退边 ⇒ 一份迟到的 merging 快照会把「结构化回写完成」推回"
        "「正在合并」，用户以为回写丢了并重新 forcesave。转换表是唯一判据，"
        "只断言「applied 存在」的判据对回退边全绿",
    ),
    Mutation(
        id="M02",
        side="fe",
        path=MACHINE,
        kind="insert",
        anchor="  applied: ['applied', 'error'],",
        new="  duplicate: ['applied'],",
        want="除 reset 外的**每一个**事件都被拒",
        wants=(
            "duplicate 观测被拒的码是「该阶段不接受观测」",
            "声明的三个 terminal 出边只有 reset",
        ),
        why="让 duplicate 接受 operation 观测 ⇒ 「duplicate 必须是 terminal」被破坏："
        "被折叠掉的那次请求会显示成自己完成了回写。三条判据必须同时红 ——"
        "只红一条说明另两条（终态自证 / 拒绝码分型）没起作用",
    ),
    Mutation(
        id="M03",
        side="fe",
        path=MACHINE,
        kind="replace",
        scope="    recovery_download_only: {",
        offset=1,
        anchor="      reset: 'html_idle',",
        new="      reset: 'html_idle', reload_completed: 'applied',",
        want="download-only 是独立终态：任何事件（除 reset）都不能把它变成 applied",
        wants=("声明的三个 terminal 出边只有 reset",),
        why="给 download-only 加一条通向 applied 的边 ⇒ 「仅下载」被显示成「结构化回写完成」。"
        "AC 5.8 明令 download-only 三实体恒 0 且不得转 applied",
    ),
    Mutation(
        id="M04",
        side="fe",
        path=MACHINE,
        kind="replace",
        scope="    close_recovery_required: {",
        offset=1,
        anchor="      reset: 'html_idle',",
        new="      reset: 'html_idle', close_successor_applied: 'applied',",
        want="无合法 successor ⇒ close_recovery_required，且它是终态",
        wants=("声明的三个 terminal 出边只有 reset",),
        why="让「无合法 successor」的终态还能滑向 applied ⇒ AC 4.10 的 "
        "`recovery_required` 会被渲染成保存成功，而用户的编辑其实要重新授权才能恢复",
    ),
    Mutation(
        id="M05",
        side="fe",
        path=MACHINE,
        kind="replace",
        scope="    error: {",
        offset=1,
        anchor="      reset: 'html_idle',",
        new="      reset: 'html_idle', reload_completed: 'html_idle',",
        want="error 不接受 reload_completed",
        wants=("error 只能由 reset 或用户显式重试离开",),
        why="给 error 加一条 reload 出边 ⇒ 「失败后的清理/重载成功」把失败洗成正常结束，"
        "正是 AC 11.10 / Property 48 明令禁止的 fail-open 形态",
    ),
    Mutation(
        id="M06",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="  close_authorization_stale: ['close_authorization_stale', 'error'],",
        new="  close_authorization_stale: ['close_authorization_stale', 'applied', 'error'],",
        want="authorization_stale 不能靠 operation 观测变成 applied",
        why="让失权状态能被一份 applied 快照直接推成成功 ⇒ 「有合法 successor」与"
        "「无 successor」两种结局在 UI 上不可区分。AC 4.10 要求前者显示 successor 进展、"
        "后者显示 recovery-required，两者都不是普通成功",
    ),
    Mutation(
        id="M07",
        side="fe",
        path=MACHINE,
        kind="insert",
        anchor="  applied: ['applied', 'error'],",
        new="  forcesave_accepted: ['application_bound'],",
        want="forcesave_accepted 只能经 shell_tracking_started 继续",
        why="让 202 之后可以直接跳到 application_bound ⇒ AC 4.1 的「先跟踪两 link 均空的 "
        "shell」阶段被绕过。绕过之后 primary/duplicate 的分叉点消失，"
        "duplicate 只能靠猜",
    ),
    Mutation(
        id="M08",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="      document_ready: 'confirming_descriptor',",
        new="      document_ready: 'oo_editing',",
        want="确认之前不存在任何通向 oo_editing 的边",
        wants=("除初态外每个状态都有入边",),
        why="让 onDocumentReady 直接进 editing ⇒ Property 11 后半（ready 后必须服务端"
        "幂等确认才可编辑/可 forcesave）被破坏，同时 `confirming_descriptor` 变成没有入边的"
        "孤岛。两条判据必须同时红：只红前一条说明可达性自证没起作用",
    ),
    # ═══════════════ 状态机：进入前置条件 ═══════════════
    Mutation(
        id="M09",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="    if (requested === '') {",
        new="    if (false) {",
        want="shell 跟踪缺 requested operation id ⇒ 拒绝",
        why="删掉 requested id 前置 ⇒ 桥可以在不知道自己那条 operation 是哪一条的情况下"
        "进入 shell 跟踪，后续 GET/timeline/retry 只能拿 canonical id 去问，"
        "duplicate 的「你发起的那次被折叠到哪一次」就说不出来了",
    ),
    Mutation(
        id="M10",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="    if (successor === '') {",
        new="    if (false) {",
        want="显示成功必须有 successor intent id",
        why="删掉 successor 前置 ⇒ close leader 失权后可以无凭据地显示成功。"
        "AC 4.10 要求「有合法 successor」才可能成功，否则只能是 recovery-required",
    ),
    Mutation(
        id="M11",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="    if (!entities || entitiesPresent(entities).length !== 3) {",
        new="    if (false) {",
        want="claim 成功必须同时带三实体，缺一即拒",
        why="删掉三实体齐备前置 ⇒ 一次只创建了 request 却没绑 application 的 claim 会被"
        "当成成功，UI 显示 application-bound 而 shell 其实停在 pre-correlation（AC 5.8）",
    ),
    Mutation(
        id="M12",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="      if (present.length > 0) {",
        new="      if (false) {",
        want="进入 recovery_pending 时任一实体非空即拒（逐实体参数化）",
        wants=("claim 失败回 pending 且三实体仍为 0",),
        why="删掉「claim 前三实体必须全空」⇒ 一个伪造了 operation_id 的 case 会让 UI 显示"
        "普通「重试」，而 AC 5.8 明令 nullable-operation 的 case 必须先 "
        "authorization-first claim",
    ),
    Mutation(
        id="M13",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="    if (shape !== 'primary' && shape !== 'duplicate') {",
        new="    if (false) {",
        want="claim 成功进 primary 或 terminal duplicate；形态缺失即拒",
        why="删掉形态前置 ⇒ 缺 shape 时三元表达式落到 duplicate，一次 primary claim 会被"
        "显示成「已折叠到别人的操作」。形态必须显式给出而不是走默认分支",
    ),
    # ═══════════════ 状态机：快照投影 ═══════════════
    Mutation(
        id="M14",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="  if (snapshot.shape === 'pre_correlation' && snapshot.resultRevision !== null) {",
        new="  if (false) {",
        want="pre-bind shell 带 result_revision ⇒ 拒绝（不得伪造完成凭证）",
        why="删掉 pre-bind 结果凭证门 ⇒ 一份 application_id=NULL 却带 result_revision 的"
        "快照会被读成「已完成」。Property 14 末句明令 pre-bind shell 不得伪造 result revision",
    ),
    Mutation(
        id="M15",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="      return snapshot.durableAt === null ? 'waiting_application' : 'incoming_durable'",
        new="      return 'waiting_application'",
        want="pre_correlation 按 durable_at 区分 waiting_application 与 incoming_durable",
        wants=("shell → durable → primary bound → merging → applied",),
        why="把 durable 判定压平 ⇒ 「OO 文件已耐久保存」这个状态永远不出现，"
        "而 AC 11.3 要求它与「命令已接受」分别表达（文件已落盘 vs 命令刚被受理，"
        "两者对用户能不能关页面的含义完全不同）",
    ),
    Mutation(
        id="M16",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="      if (snapshot.shape === 'primary') {",
        new="      if (false) {",
        want="primary 形态即使 state 仍是 accepted 也投影成 application_bound",
        why="删掉「已绑 application 是更强事实」⇒ 一份已绑定但 state 还没推进的快照会被"
        "读回 shell 阶段，于是 UI 在 bound 之后又退回「等待回传」",
    ),
    Mutation(
        id="M17",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="      return 'close_authorization_stale'",
        new="      return 'error'",
        want="authorization_stale 投影成 close_authorization_stale 而不是 error",
        why="把失权投影成普通 error ⇒ 用户看到一个可重试的失败，而实际发生的是"
        "「关闭发起人失去资格、需要等接任者或重新授权」。AC 4.10 要求这两者可区分",
    ),
    # ═══════════════ 状态机：mode 与文案 ═══════════════
    Mutation(
        id="M18",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="  applied: 'oo',",
        new="  applied: 'html',",
        want="applied 之后必须经 reload_completed 才回 html",
        wants=("shell → durable → bound → applied，reload 用的最小 revision 等于 result revision",),
        why="让 applied 立刻翻 mode ⇒ HTML 还没按 result revision 重载就切了过去，"
        "用户看到旧 revision 并以为回写没生效（Property 14 的反面）",
    ),
    Mutation(
        id="M19",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="  error: 'inherit',",
        new="  error: 'html',",
        want="recovery 状态 mode 继承（失败/恢复不改原模式）",
        why="给 error 钉死 html ⇒ OO 里的一次失败把用户踢回表单模式，而 OO 里可能还有"
        "没耐久的编辑。AC 11.6 明文「失败后保持原模式并提供重试」",
    ),
    Mutation(
        id="M20",
        side="fe",
        path=MACHINE,
        kind="replace",
        anchor="  applied: '结构化回写完成',",
        new="  applied: '同步成功',",
        want="四类结果文案两两不同，且没有任何一条是「同步成功」",
        why="把「结构化回写完成」换成「同步成功」⇒ AC 11.3 明令禁止的统一成功文案。"
        "「命令已接受 / 文件已耐久 / 结构化回写完成 / 发生冲突」必须分别表达，"
        "因为四者对「能不能关页面」「要不要裁决」的含义完全不同",
    ),
    # ═══════════════ 模式存储 ═══════════════
    Mutation(
        id="M21",
        side="fe",
        path=STORAGE,
        kind="replace",
        anchor="const LEGACY_KEY_RE = /^([a-z0-9][a-z0-9-]*)-dual-mode:(.+)$/",
        new="const LEGACY_KEY_RE = /^(f2)-dual-mode:(.+)$/",
        want="每个真实前缀构造的 per-wp 与 per-sheet 旧键都能被解析",
        why="把按键形态扫描收窄成「只认一个前缀」⇒ 其余 50 余个 dual-mode composable 的"
        "存量偏好永远迁不过来，而「迁移函数被调用了」的判据全绿。分母必须是源码里"
        "真实存在的全部前缀",
    ),
    Mutation(
        id="M22",
        side="fe",
        path=STORAGE,
        kind="replace",
        anchor="  if (supported.includes(candidate)) {",
        new="  if (true) {",
        want="single_html 遇到存量 oo ⇒ 回落 html 并删旧值",
        wants=("single_onlyoffice 遇到存量 html ⇒ 回落 oo",),
        why="删掉 capability 门 ⇒ 存量值会打开这条 entry 根本不支持的模式"
        "（AC 11.8 末句「过期值不得打开不支持模式」）",
    ),
    Mutation(
        id="M23",
        side="fe",
        path=STORAGE,
        kind="replace",
        anchor="    const shouldWrite = legacyMode !== null && existingRaw !== candidate",
        new="    const shouldWrite = true",
        want="用户在两次迁移之间手动改过模式 ⇒ 第二次不得覆盖回旧值",
        why="每次迁移都写一遍 ⇒ 第二次调用把用户手动切换的模式覆盖回旧值。"
        "幂等的判据是「跑两次的存储快照逐键相同」，不是「函数返回同一个值」",
    ),
    Mutation(
        id="M24",
        side="fe",
        path=STORAGE,
        kind="replace",
        anchor="  if (injected !== undefined) return injected",
        new="  if (injected) return injected",
        want="localStorage 不可用时显式上报，不静默当成「没有偏好」",
        why="把显式的 `null`（宿主声明「没有存储」）悄悄升级成全局 localStorage ⇒"
        "「不该持久化」被执行成「持久化到全局」。这条正是本任务写判据时打红抓到的真实缺陷",
    ),
    Mutation(
        id="M25",
        side="fe",
        path=STORAGE,
        kind="replace",
        anchor="  if (!supported.includes(mode)) {",
        new="  if (false) {",
        want="持久化一个 capability 不支持的模式 ⇒ 拒绝且不落盘",
        why="删掉写入侧 capability 门 ⇒ 一个打不开的模式被落盘，下次加载时按它打开"
        "不支持的编辑器。读侧回落与写侧拒绝是两道独立的锁，各自都要能证伪",
    ),
    # ═══════════════ composable：门控 ═══════════════
    Mutation(
        id="M26",
        side="fe",
        path=BRIDGE,
        kind="replace",
        scope="  const canForcesave = computed(",
        offset=1,
        anchor="    () => state.value === 'oo_editing' && confirmation.value?.forcesaveUnlocked === true,",
        new="    () => true,",
        want="confirm 之前不进 oo_editing、不可 forcesave",
        why="把 forcesave 门恒开 ⇒ 编辑器刚挂载就能 forcesave，而服务端还没确认过这份"
        "descriptor 身份。Property 11 明令确认成功前不得 forcesave",
    ),
    Mutation(
        id="M27",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (!confirmed.forcesaveUnlocked) {",
        new="    if (false) {",
        want="confirm 返回 forcesave_unlocked=false ⇒ 不进 editing",
        why="忽略服务端的 `forcesave_unlocked=false` ⇒ 一份「已确认但不可写」的确认"
        "（只读 participant）被读成可编辑。这类确认在协议上合法，读错就是最贵的假绿",
    ),
    Mutation(
        id="M28",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="      described.staleIdentity || described.errorCode.startsWith('pending_mutation_token_')",
        new="      false",
        want="pending token 过期（409）：停留 HTML 且 mode 不变",
        wants=("bundle identity 陈旧（409 stale identity）：三门全关且停留 HTML",),
        why="把 token/identity 类失败当普通同步失败 ⇒ 它们会走 `sync_failed` 进 error "
        "并保留 OO 模式，而 AC 3.2 要求这类失败「模式切换停留在 HTML」",
    ),
    Mutation(
        id="M29",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="      claimedShape: landed.shape,",
        new="      claimedShape: 'primary',",
        want="claim 命中既有 application ⇒ 进 terminal duplicate（不得默认成 primary）",
        why="claim 的 202 响应体没有 shape（服务端 `outcome.shape` 没投影出来），"
        "写死 'primary' ⇒ 命中既有 application 的 duplicate 会被显示成 primary "
        "application-bound。AC 5.8 要求这两个终态可区分",
    ),
    Mutation(
        id="M30",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (landed.shape === 'pre_correlation') {",
        new="    if (false) {",
        want="claim 后 operation 仍是两 link 均空的 shell ⇒ fail visible（不猜终态）",
        why="claim 之后仍是 pre-correlation shell 时不 fail visible ⇒ 桥会拿一个没绑"
        "application 的 shell 当 primary 终态。AC 5.8 要求 claim 在同一事务内创建/命中"
        "application 并绑定 shell",
    ),
    Mutation(
        id="M31",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="      await options.reloadHtml(revision)",
        new="      await options.reloadHtml(0)",
        want="reload 用的最小 revision 等于 result revision",
        why="重载不带最小 revision ⇒ Property 14 的「加载 revision 不低于 "
        "application.result_revision」失去客户端侧约束，宿主可能加载到一个更旧的缓存",
    ),
    Mutation(
        id="M32",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (revision === null) {",
        new="    if (false) {",
        want="applied 但快照缺 result_revision ⇒ 拒绝重载（不得伪造完成凭证）",
        why="缺 result revision 也照样重载 ⇒ 宿主收到 `null` 作最小 revision，"
        "「重载后 revision 不低于结果」这条根本无从校验",
    ),
    Mutation(
        id="M33",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="      if (lastError.value !== null) {",
        new="      if (false) {",
        want="reload 失败后，后续 destroy/迁移成功都不改回成功文案",
        why="让状态文案盖过 sticky error ⇒ Property 48 的「任一真同步步骤失败后不得调用"
        "success 文案」失效。error 必须优先于任何状态文案",
    ),
    Mutation(
        id="M34",
        side="fe",
        path=BRIDGE,
        kind="replace",
        scope="  function beginAttempt(): void {",
        offset=1,
        anchor="    lastError.value = null",
        new="    void 0",
        want="只有用户显式发起的新尝试才清掉 sticky error",
        why="新尝试不清 error ⇒ 用户重试成功后仍看到上一次的失败文案。"
        "粘性 error 的正确边界是「用户显式发起的新尝试」与 `reset()`，两侧都要能证伪",
    ),
    # ═══════════════ composable：身份与授权顺序 ═══════════════
    Mutation(
        id="M35",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (requested !== null && snapshot.requestedOperationId !== requested) {",
        new="    if (false) {",
        want="跟错一条 operation ⇒ 拒绝（必须沿同一 requested operation）",
        why="不校验快照身份 ⇒ 桥会把别人那条 operation 的状态显示成自己的。"
        "AC 5.10 要求沿同一 requested operation 推进",
    ),
    Mutation(
        id="M36",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (snapshot.canonicalOperationId !== known.canonicalOperationId) {",
        new="    if (false) {",
        want="canonical primary 换了一个 id ⇒ 拒绝（不得新建 operation）",
        why="不校验 canonical 稳定性 ⇒ duplicate 的后续读取可能落到一条新建的 "
        "operation/application 上，而 AC 5.10 明令 duplicate 的 GET/timeline/retry/resolve"
        "只要求 canonical primary 唯一绑定 application、不新建",
    ),
    Mutation(
        id="M37",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    const requested = requestedOperationId.value ?? operation.value?.requestedOperationId ?? ''",
        new="    const requested = operation.value?.canonicalOperationId ?? ''",
        want="五条调用逐一带 requested id（不是 canonical id）",
        why="改成拿 canonical id 去调 ⇒ 服务端「先按 requested scope 授权、再 canonicalize」"
        "的顺序被绕过，duplicate 的调用方等于直接对别人的 primary 发起操作",
    ),
    Mutation(
        id="M38",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (known !== null && known !== input.applicationId) {",
        new="    if (false) {",
        want="不同 canonical application ⇒ 进 refresh_required（需重载新基线）",
        why="不区分 canonical application 变化 ⇒ 「较新且 canonical application 不同的"
        " durable incoming 才 supersede」这条被压成「永远只 fold」，用户在一个已被"
        "supersede 的基线上继续裁决冲突",
    ),
    Mutation(
        id="M39",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="      applicationEffectiveSequence.value = previous === null ? next : Math.max(previous, next)",
        new="      applicationEffectiveSequence.value = next",
        want="sequence 单调 fold：更低的 sequence 不把它拉回去",
        why="把单调 fold 改成直接赋值 ⇒ 一份迟到的低 sequence 会把 effective sequence "
        "拉回去，后续 resolve 带着过期 fence 提交并被服务端拒（AC 5.10 的 fold 是单调的）",
    ),
    # ═══════════════ composable：离开阻断与失败分型 ═══════════════
    Mutation(
        id="M40",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (WP_BRIDGE_IN_FLIGHT_STATES.includes(state.value)) {",
        new="    if (false) {",
        want="forcesave accepted / waiting callback 期间阻断",
        wants=("applied 但还没重载时仍阻断（否则用户下次看到旧 revision）",),
        why="只按 dirty 判阻断 ⇒ forcesave 已受理/等回调期间关页面不再提示，"
        "而 AC 4.8 明列这三种状态都要提示",
    ),
    Mutation(
        id="M41",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (routeLeaveGuard()) return",
        new="    if (true) return",
        want="dirty 时真的 preventDefault（同一个已注册的 handler）",
        why="beforeunload handler 永远早退 ⇒ 阻断计算得再对也不生效。"
        "这正是 Vue/DOM 侧「有 flag 没消费方」的形态：`canLeave` 照样是 false，"
        "只有真的派发一次 beforeunload 事件看 `defaultPrevented` 才能证伪",
    ),
    Mutation(
        id="M42",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="  if (wire.status === 404 || wire.status === 403) {",
        new="  if (wire.status === 404) {",
        want="403 与 404 归一成同一个码（两者不可区分）",
        why="让 403 落到本地/传输桶 ⇒ 「无权限」与「网络失败」用不同码、不同可重试性"
        "呈现，而服务端刻意把四种原因压成同一个响应体正是为了不泄露存在性",
    ),
    Mutation(
        id="M43",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="  const retryable = wire.status === null || wire.status === 500 || wire.status === 503",
        new="  const retryable = false",
        want="三个分桶用三个互不相同的码",
        wants=("5xx 纯文本可重试，4xx 纯文本不可重试（都归到本地/传输桶）",),
        why="把本地/传输失败一律判成不可重试 ⇒ AC 4.4 的「forcesave 失败/callback 未到达/"
        "超时时保持 OO 并允许重试」在 UI 上不可达，用户只能刷新页面（丢掉未耐久的编辑）",
    ),
    Mutation(
        id="M44",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (missing.length > 0) {",
        new="    if (false) {",
        want="resolve 的 room fence 缺项 ⇒ 拒绝，不替调用方编造",
        why="fence 缺项不拒 ⇒ 桥会把 `undefined`/空串发给服务端做 fence 裁决。"
        "`room_latest_durable_*` 在当前 16 条用户路由里没有读取面，"
        "缺项只能 fail visible，不能替调用方编一个",
    ),
    Mutation(
        id="M45",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (String(roomId).trim() === '' || generation === null || !Number.isInteger(generation)) {",
        new="    if (false) {",
        want="list 缺 room/generation 且无 descriptor ⇒ 拒绝，不打端点",
        why="缺 room/generation 也照样发请求 ⇒ 服务端 422，而调用点很容易把 422 当"
        "「暂时没有恢复项」。AC 10.6 把这两个参数声明为必填正是因为「列出全部 case」"
        "本身是存在性泄露面",
    ),
    Mutation(
        id="M46",
        side="fe",
        path=BRIDGE,
        kind="replace",
        anchor="    if (!candidate) {",
        new="    if (false) {",
        want="prior confirmation 不在候选内 / bundle digest 非法 / fence 形态非法 ⇒ 发出前拒绝",
        why="不校验 prior confirmation 属于本 case 的候选集 ⇒ 客户端可以指定任意 base，"
        "而 design §API 明文「claim 只提交 case/participant/confirmation/expected bundle/fence，"
        "不允许客户端指定 base」",
    ),
    # ═══════════════ 后端跨文档锚点 ═══════════════
    Mutation(
        id="M47",
        side="be",
        path=MACHINE,
        kind="delete",
        scope="export const WP_BRIDGE_AC_11_2_REQUIRED_STATES = [",
        offset=1,
        anchor="  'html_idle',",
        want="test_required_state_constant_equals_ac_11_2_verbatim",
        why="从 AC 11.2 登记清单里删一个状态 ⇒ 前端「我覆盖了 AC 要求的状态」这句话不再"
        "成立，而前端自己拿这个常量去校验状态域是自证（同一文件同一作者的两个常量）。"
        "真源只有 requirements.md，判据必须从那里解析",
    ),
    Mutation(
        id="M48",
        side="be",
        path=STORAGE,
        kind="replace",
        anchor="export const WP_SYNC_MODE_KEY_PREFIX = 'workpaper-sync-mode:'",
        new="export const WP_SYNC_MODE_KEY_PREFIX = 'wp-sync-mode:'",
        want="test_unified_mode_key_template_matches_design",
        why="改掉统一键前缀 ⇒ 与 design §legacy migration 的模板漂开，"
        "存量偏好写到一个没人读的键上。键模板的真源是 design.md，不是代码",
    ),
    Mutation(
        id="M49",
        side="be",
        path=BRIDGE,
        kind="delete",
        scope="    fetchTimeline,",
        offset=2,
        anchor="    resolveConflicts,",
        want="test_bridge_exposes_the_api_surface_design_names",
        why="从返回对象里删掉一个 design 点名的公开面 ⇒ Task 34 的冲突面板拿不到它，"
        "而「函数在文件里定义了」的判据全绿。零消费方的实现就是死代码",
    ),
    Mutation(
        id="M50",
        side="be",
        path=MACHINE,
        kind="replace",
        anchor="    case 'authorization_stale':",
        new="    case 'authorization_stale_typo':",
        want="test_operation_state_switch_covers_the_backend_enum",
        why="把一个 case 标签写错 ⇒ 该后端状态落到 `default` 分支被 fail visible，"
        "用户看到「未知状态」。case 标签集必须逐项等于后端 `OperationState` 枚举，"
        "而那只能在后端侧比",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 32 桥状态机 / 模式存储 / composable 守卫变异检验",
            backend_args=BE_ARGS,
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
        )
    )
