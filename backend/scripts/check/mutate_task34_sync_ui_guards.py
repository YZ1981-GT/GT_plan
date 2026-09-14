# -*- coding: utf-8 -*-
"""Task 34 守卫变异检验（状态条 / 冲突对话框 / recovery 面板 / 详情 timeline）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
Requirements: 14.7 · Property 57（变异检验本身）

## 四态

| 判定 | 含义 | 归因 |
|---|---|---|
| ``RED`` | **预期那条**判据打红 | 守卫有效 |
| ``GREEN`` | 无新增失败 | **守卫缺陷** |
| ``WRONG-TEST`` | 打红了但不是预期项 | 锚点错行 / 污染残留 |
| ``ANCHOR-MISS`` | 锚点非唯一命中 / 未落盘 | **本脚本缺陷** |

退出码不作判据；判定只看失败名差集。

## 本任务专属的三条

1. **`want` 一律用 vitest 的中文标题片段**，不带任何路径前缀 —— Task 36 首轮
   44/44 WRONG-TEST 纯粹来自 `want` 里多写了目录前缀。
2. **`.vue` 的变异不能靠 TS 报错生效**：vitest 走 esbuild，只剥类型不做检查。
   于是「把 v-if 改成 true」在运行时表现为门失效 —— 正是要打红的缺陷形态。
   反过来，任何真语法错误会让整份 SFC 编译失败、差集被清空 ⇒ 误判 GREEN，
   故每条替换体都必须是合法 TS/模板。
3. **共用错误码的形态单独立一条**（M59）：两层门用同一个码时，删掉外层看不出差别 ——
   平台变异运行已三次抓到这个形态，本任务把它做成一条显式变异。

## 用法

    py -3 backend/scripts/check/mutate_task34_sync_ui_guards.py --list
    py -3 backend/scripts/check/mutate_task34_sync_ui_guards.py --check-anchors
    py -3 backend/scripts/check/mutate_task34_sync_ui_guards.py --run fe --out <path>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

FRONTEND = REPO / "audit-platform" / "frontend"
_FE_JSON = REPO / "backend" / "scripts" / "check" / "_wip_task34_fe.json"

SYNC = "audit-platform/frontend/src/components/workpaper/sync"
PRES = f"{SYNC}/workpaperSyncPresentation.ts"
BAR = f"{SYNC}/WorkpaperSyncStatusBar.vue"
DIALOG = f"{SYNC}/WorkpaperSyncConflictDialog.vue"
RECOVERY = f"{SYNC}/WorkpaperSyncRecoveryPanel.vue"
DRAWER = f"{SYNC}/WorkpaperSyncDetailsDrawer.vue"

#: 覆盖面分母：Task 34 的四个组件 + 一个纯投影层，各自一个判据文件。
GUARD_FILES = {
    "workpaperSyncPresentation.spec.ts": "投影表穷尽性、close 仲裁、冲突解析、批量范围、fence、recovery 推导、timeline 投影",
    "WorkpaperSyncStatusBar.spec.ts": "24 个可观测状态逐一可辨、error 优先、三个 verdict 布尔、追溯 chips、四个动作出口",
    "WorkpaperSyncConflictDialog.spec.ts": "三级分组、双侧可追溯、金额经 store、逐项/批量裁决、关闭不应用、八项 fence",
    "WorkpaperSyncRecoveryPanel.spec.ts": "list 前不可见、claim 前三实体空且无重试、claim 后三实体齐备、download-only 不称回写完成、scope 交叉核对",
    "WorkpaperSyncDetailsDrawer.spec.ts": "追溯行与缺口留白、两条 timeline 分离、rollback 只提交 opaque UUID、二次确认",
}

FE_FILTERS = [
    "workpaperSyncPresentation",
    "WorkpaperSyncStatusBar",
    "WorkpaperSyncConflictDialog",
    "WorkpaperSyncRecoveryPanel",
    "WorkpaperSyncDetailsDrawer",
]

# ── want 常量（vitest 中文标题片段，短 nodeid 形态，无路径前缀）
_TABLE_AUDIT = "表自证通过"
_TERMINAL_SETTLED = "三个终态一律 settled"
_NO_SUCCESS_TEXT = "close_recovery_required 与 recovery_download_only 的文案与提示都不含成功字样"
_HINT_CONCRETE = "每条动作提示都点得出一个具体动作"
_CLOSE_SUCCESSOR = "接任者已完成（结局 applied）仍可辨"
_CLOSE_NO_ID = "宿主没回传 intent id 时显式说明"
_CLOSE_LATEST = "同一会话内反复失权时取"
_CLOSE_VISIBLE = "仲裁行可见性：三种真实结局都要显示"
_BAR_NO_ARBITRATION = "从未发生 close 仲裁时不渲染仲裁行"
_AMOUNT_FMT = "amount 经注入的 fmtAmount"
_VALUE_THREE = "三种「没有值」互不相同"
_ADJ_MISSING = "缺 adjudicable_by_value_choice"
_ENVELOPE = "值信封缺 present 布尔"
_BULK_RESOLVED = "已裁决的项不进任何范围"
_BULK_ANCHOR = "没有锚点的「本行/本表/本工作表」被拒绝"
_BULK_SCOPES = "四个范围各自取到不同的目标集"
_BULK_TEXT = "二次确认文案逐字点出范围名、条数与裁决动作"
_FENCE_OK = "宿主给了 room durable fence"
_FENCE_NUMERIC = "room fence 用了 numeric revision 冒充 UUID"
_RECOVERY_NO_FENCE = "宿主没给冻结身份 ⇒ 一条明确原因"
_RECOVERY_CLAIM_OFF = "服务端关掉 claim"
_RECOVERY_ENTITIES = "claim 前三实体逐项"
_RECOVERY_TL_EMPTY = "claim 之前三实体为 null"
_TL_SEQ = "缺 sequence_no 的事件被丢掉"
_GAP_PLACEHOLDER = "占位符不是空串也不是"
_GAP_REGISTRY = "五项已登记缺口都有 id/label/reason"

_BAR_ALL_STATES = "24 个状态的 data-state"
_BAR_HINTS = "settled 状态一律带具体动作提示"
_BAR_FROZEN = "命令未被受理（forcesave_frozen）与命令已受理不是同一句话"
_BAR_APPLIED_FAIL = "applied 之后 reload 失败"
_BAR_TEXT_SOURCE = "状态条不自己拼状态文案"
_BAR_SUCCESSOR = "合法 successor 完成后阶段标签归因于接任者"
_BAR_NO_SUCCESSOR = "close_recovery_required：显式说明无接任者需重新授权"
_BAR_DUP = "duplicate 同时显示 requested → canonical 两个 id"
_BAR_DUP_ABSENT = "primary 快照下不渲染 duplicate 折叠行"
_BAR_RETRY_RECOVERY = "recovery 期间即便裁决可重试也不给普通重试"
_BAR_RETRY_NO_OP = "没有 requested operation 时也不给普通重试"
_BAR_GATES = "409 stale identity ⇒ 三个布尔全 false"
_BAR_REVISION = "修订号标签逐字声明"
_BAR_STORE_IMPORT = "四个 UI 文件都不从 store 模块 import fmtAmount"
_BAR_DOWNLOAD_ONLY = "download-only 终态不含"

_DLG_FETCH = "打开面板即拉一次预览"
# 🔴 三种关闭方式的判据标题是**模板字面量**（`经 ${testid} 关闭：…`），
# 所以 want 只能取那句里的**字面**片段；写 `经 wp-sync-conflict-close 关闭` 会让
# `--list` 的「want 可定位」校验直接判红（首轮实测两条 FAIL）——
# 这正是它存在的意义：定位不到的 want，判定永远只能是 WRONG-TEST。
_DLG_CLOSE_ANY = "resolveConflicts 零调用、选择清空"
_DLG_CLOSE_ESC = "ESC 关闭同样零应用"
_DLG_CLOSE_STRUCT = "关闭路径里没有任何提交调用"
_DLG_TWO_STEP = "只点预览不点确认"
_DLG_BULK_TEXT = "确认文案逐字含范围名、条数与裁决动作"
_DLG_BULK_ANCHOR = "未选锚点就点「本行」"
_DLG_BULK_ROW = "确认后只落到范围内的条目上"
_DLG_FENCE_BLOCK = "宿主没给 ⇒ 两条阻断原因逐项渲染"
_DLG_FENCE_SUBMIT = "宿主给了 room durable fence ⇒ 提交按钮可用"
_DLG_PROGRAMMATIC = "缺 fence 时**程序化**提交也被拦"
_DLG_STAY_OPEN = "服务端拒绝裁决 ⇒ 面板留在原地"
_DLG_STRUCTURAL = "结构冲突不给选边入口"
_DLG_MANUAL_TEXT = "手工合并只对文本字段开放"
_DLG_PROTECTION = "保护策略逐项中文化"
_DLG_AMOUNT = "amount 列渲染成千分符"
_DLG_AMOUNT_LIVE = "切换平台单位后同一单元格随之变化"
_DLG_ABSENT_NULL = "缺字段与显式空值渲染成两句不同的话"

_RCV_NOT_LISTED = "未查询时候选 / bundle 摘要 / 动作按钮全不在 DOM 里"
_RCV_ENTITIES = "三实体逐项渲染「尚未创建」"
_RCV_NO_RETRY_DOM = "DOM 里没有任何「重试」入口"
_RCV_NO_RETRY_SRC = "剥注释后源码里根本不出现 retryOperation"
_RCV_TIMELINE = "三实体取自 recovery case timeline"
_RCV_THREE = "成功后三实体同时渲染"
_RCV_DRIFT_OP = "timeline 的 operation 与桥跟踪的不一致"
_RCV_DOWNLOAD = "终结后显式声明未执行结构化回写"
_RCV_DOWNLOAD_SRC = "源码里没有「回写完成」字样"
_RCV_SCOPE_WP = "宿主传错底稿 id"
_RCV_CLAIM_DISABLED = "宿主没给冻结身份 ⇒ 摘要显示「未提供」、claim 禁用"
_RCV_NO_CANDIDATE = "没有候选确认 ⇒ 明说没有合法基线且 claim 禁用"
_RCV_PICK_FIRST = "没选候选就点 claim"
_RCV_ACTIONS_OFF = "服务端关掉两个动作"

_DRW_GAPS = "五项已登记缺口只渲染占位符"
_DRW_INCOMING = "回传 incoming 摘要那一行不得被发出侧 artifact 摘要顶替"
_DRW_ROLLBACK_BODY = "确认后请求体逐字"
_DRW_ROLLBACK_STRUCT = "rollback 只提交 versionId"
_DRW_TWO_STEP = "二次确认真的是两步"
_DRW_NOT_OPAQUE = "抽屉自己的门先拦住"
_DRW_RECOVERY_TL = "有恢复项 ⇒ 单独加载 recovery timeline"
_DRW_EVIDENCE = "证据关联标识取自已加载事件的最后一个非空 correlation_id"
_DRW_REFRESH = "refresh_required 状态下该行渲染「是」"
_DRW_TL_EMPTY = "未加载时两张表都不渲染事件行"


MUTATIONS: list[Mutation] = [
    # ═══════════ A. 投影表：等待语义 / 基调 / 提示 ═══════════
    Mutation(
        id="M01",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  close_recovery_required: 'settled',",
        new="  close_recovery_required: 'progress',",
        want=_TERMINAL_SETTLED,
        wants=(_TABLE_AUDIT, _BAR_NO_SUCCESSOR, _BAR_ALL_STATES),
        why="把「无合法接任者」标成进行中 ⇒ 状态条转圈、用户永远等一个不会来的接任者。"
        "Task 34 明文「不得渲染成无限等待」，而「文案非空」这类判据对它全绿",
    ),
    Mutation(
        id="M02",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  recovery_download_only: 'info',",
        new="  recovery_download_only: 'success',",
        want=_TABLE_AUDIT,
        wants=(_NO_SUCCESS_TEXT, _BAR_DOWNLOAD_ONLY),
        why="download-only 用成功基调 ⇒ 颜色是用户最先读到的那一层，绿色等于宣称回写完成。"
        "AC 5.8 明文 download-only 永不创建 application/operation",
    ),
    Mutation(
        id="M03",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  close_recovery_required: '请联系有权用户重新授权，并在恢复面板中认领或仅下载',",
        new="  close_recovery_required: '',",
        want=_TABLE_AUDIT,
        wants=(_BAR_HINTS, _BAR_NO_SUCCESSOR, _HINT_CONCRETE),
        why="settled 态没有下一步提示 ⇒ 界面停在一句「需重新授权」而不说怎么授权，"
        "对用户就是无限等待。表自证正是为拦这个而存在",
    ),
    Mutation(
        id="M04",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="        outcome: 'successor_applied',",
        new="        outcome: 'not_applicable',",
        want=_CLOSE_SUCCESSOR,
        wants=(_BAR_SUCCESSOR,),
        why="接任者完成被判成「与 close 无关」⇒ 状态条只显示 `applied` 的「结构化回写完成」，"
        "与「我自己保存成功了」逐字同态。Task 34 要求 successor 接任进展可辨",
    ),
    Mutation(
        id="M05",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="            ? '本次关闭由合法接任者完成保存（接任者标识未由宿主回传）'",
        new="            ? '本次关闭由合法接任者 00000000-0000-0000-0000-000000000078 完成保存'",
        want=_CLOSE_NO_ID,
        why="宿主没回传 intent id 时编一个 ⇒ 「有合法接任者」凭空成立。桥的 "
        "`notifyCloseSuccessorApplied` 只校验不保存该 id，这里编造无人能证伪",
    ),
    Mutation(
        id="M06",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  for (let index = transitions.length - 1; index >= 0; index -= 1) {",
        new="  for (let index = 0; index < transitions.length; index += 1) {",
        want=_CLOSE_LATEST,
        why="正序扫描 ⇒ 同一会话里「先无接任者、后有接任者接任」会被读成前者。"
        "close 仲裁在一次会话内可以反复发生（AC 4.10 的 successor 链）",
    ),
    # ═══════════ B. 金额与值信封 ═══════════
    Mutation(
        id="M07",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (valueType === 'amount') return fmtAmount(value)",
        new="  if (valueType === 'amount') return String(value)",
        want=_AMOUNT_FMT,
        wants=(_DLG_AMOUNT, _DLG_AMOUNT_LIVE),
        why="金额绕过 displayPrefs ⇒ 千分符/小数位/单位后缀全失效，平台单位切换对冲突面板"
        "不起作用。AC 8.2 明文金额使用平台 `displayPrefs.fmtAmount()`",
    ),
    Mutation(
        id="M08",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (!envelopeValue.present) return WP_SYNC_VALUE_ABSENT_TEXT",
        new="  if (!envelopeValue.present) return WP_SYNC_VALUE_NULL_TEXT",
        want=_VALUE_THREE,
        wants=(_DLG_ABSENT_NULL,),
        why="「字段缺失」与「显式空值」合并成一句 ⇒ 裁决界面说不清用户在选什么。"
        "后端刻意用 `present` 布尔把两者分开落库，读侧合并等于把那份设计作废",
    ),
    Mutation(
        id="M09",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="          if (typeof i.adjudicable_by_value_choice !== 'boolean') {",
        new="          if (false) {",
        want=_ADJ_MISSING,
        wants=(_DLG_STRUCTURAL,),
        why="服务端漏给可裁决布尔时不再 fail visible ⇒ 结构冲突会被渲染成「选一侧就能收敛」，"
        "而结构冲突必须先修结构（AC 8.3 / SchemaAnomalyKind 的非 value-adjudicable 分支）",
    ),
    Mutation(
        id="M10",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (typeof wire.present !== 'boolean') {",
        new="  if (false) {",
        want=_ENVELOPE,
        why="值信封缺 `present` 时不拦 ⇒ `{value:1}` 被读成 `present=undefined`（假），"
        "于是一个**有值**的一侧被渲染成「无此字段」",
    ),
    # ═══════════ C. 批量范围 ═══════════
    Mutation(
        id="M11",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="    !item.resolved && item.adjudicableByValueChoice",
        new="    item.adjudicableByValueChoice",
        want=_BULK_RESOLVED,
        why="已裁决的项重新进入批量目标 ⇒ 用户的上一次裁决被静默覆盖，"
        "而「批量作用范围明确」的判据只看范围不看是否已裁决",
    ),
    Mutation(
        id="M12",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (scope !== 'all_unresolved' && anchor === null) {",
        new="  if (false) {",
        want=_BULK_ANCHOR,
        wants=(_DLG_BULK_ANCHOR,),
        why="没有锚点也放行「本行/本表/本工作表」⇒ 作用范围不明确，AC 8.3 要求批量选择"
        "必须明确作用范围并二次确认",
    ),
    Mutation(
        id="M13",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="    return item.rowKey === pin.rowKey",
        new="    return true",
        want=_BULK_SCOPES,
        wants=(_DLG_BULK_ROW,),
        why="「本行」范围漏比行键 ⇒ 点「仅本行」实际改了同表所有行。这是最典型的"
        "「范围看起来选了、其实没生效」形态",
    ),
    Mutation(
        id="M14",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  return `即将对${where}的 ${count} 条冲突统一裁决为「${choiceLabel}」（范围：${WP_SYNC_BULK_SCOPE_LABEL[scope]}），请确认。`",
        new="  return `即将对${where}的冲突统一裁决，请确认。`",
        want=_BULK_TEXT,
        wants=(_DLG_BULK_TEXT,),
        why="确认文案不点条数与裁决动作 ⇒ 用户按下确认时不知道会改多少条、改成哪一侧。"
        "AC 8.3 的「明确作用范围」是文案义务，不只是内部集合正确",
    ),
    # ═══════════ D. resolve fence ═══════════
    Mutation(
        id="M15",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="      roomLatestDurableApplicationId: pinned.applicationId,",
        new="      roomLatestDurableApplicationId: preview.canonicalApplicationId,",
        want=_FENCE_OK,
        wants=(_DLG_FENCE_SUBMIT,),
        why="拿 canonical application 顶替 room 的 latest durable ⇒ 客户端断言了一个它"
        "观测不到的 room 事实，而服务端会照着这个断言做 fence 裁决（AC 8.5）",
    ),
    Mutation(
        id="M16",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (durable === null || !isOpaqueUuid(durable.applicationId)) {",
        new="  if (durable === null) {",
        want=_FENCE_NUMERIC,
        why="宿主把 numeric revision 当 application id 传进来时不再报缺 ⇒ 一个非 opaque 值"
        "被当成合法 fence 发给服务端（AC 8.7 / 10.6 的碰撞面）",
    ),
    # ═══════════ E. recovery 推导 ═══════════
    Mutation(
        id="M17",
        side="fe",
        path=PRES,
        kind="delete",
        anchor="    blocking.push('宿主未提供冻结的 definition bundle 摘要与写栅栏，无法发起认领')",
        want=_RECOVERY_NO_FENCE,
        wants=(_RCV_CLAIM_DISABLED,),
        why="宿主没给冻结 bundle/fence 时不再阻断 ⇒ claim 按钮亮起，点下去只能靠服务端拒。"
        "AC 5.8 要求 claim 必须冻结非空 bundle 与 fence",
    ),
    Mutation(
        id="M18",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (!recoveryCase.actions.claim) {",
        new="  if (false) {",
        want=_RECOVERY_CLAIM_OFF,
        wants=(_RCV_ACTIONS_OFF,),
        why="忽略服务端给的能力布尔 ⇒ 已 claim / 已终结 / 已过期的 case 仍显示可认领。"
        "Task 28 的 router 注释里记着同一个坑（终态集写死字面量导致漂移）",
    ),
    Mutation(
        id="M19",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="      value: row.value === null ? '尚未创建' : row.value,",
        new="      value: row.value === null ? '' : row.value,",
        want=_RECOVERY_ENTITIES,
        wants=(_RCV_ENTITIES,),
        why="claim 前三实体渲染成空白 ⇒ 「还没创建」与「取数失败」不可区分。"
        "AC 5.8 的三实体全空是**可观测事实**，必须显式说出来",
    ),
    Mutation(
        id="M20",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="    hasThreeEntities: wire.has_three_entities === true,",
        new="    hasThreeEntities: true,",
        want=_RECOVERY_TL_EMPTY,
        why="三实体齐备恒真 ⇒ claim 之前的 case 也显示「三实体齐备」，"
        "而那时 request/application/operation 一个都不存在",
    ),
    Mutation(
        id="M21",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (typeof sequenceNo !== 'number' || !Number.isInteger(sequenceNo)) return null",
        new="  if (false) return null",
        want=_TL_SEQ,
        why="缺号事件不再丢弃 ⇒ timeline 里出现一行没有序号的事件，"
        "而 `(stream, parent_id, sequence_no)` 才是事件的业务身份",
    ),
    Mutation(
        id="M22",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  if (text === '') return WP_SYNC_TRACE_GAP_PLACEHOLDER",
        new="  if (text === '') return '-'",
        want=_GAP_PLACEHOLDER,
        why="缺读取面的摘要显示成一个破折号 ⇒ 与「值就是空」不可区分。"
        "已登记缺口必须显式说出「无读取面」，否则下一个人会以为它本该是空",
    ),
    Mutation(
        id="M23",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="    reason: 'GET operations/{id} 不带 incoming artifact digest，descriptor 的摘要是发出侧',",
        new="    reason: '',",
        want=_GAP_REGISTRY,
        why="缺口不写成因 ⇒ 界面上只剩一个占位符，读者无从判断是「服务端没给」还是"
        "「前端忘了接」。缺口登记的价值全在成因上",
    ),
    # ═══════════ F. 状态条：文案真源与 error 优先 ═══════════
    Mutation(
        id="M24",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="const feedback = computed(() => props.bridge.feedback.value)",
        new="const feedback = computed(() => ({ kind: 'success' as const, message: '同步成功' }))",
        want=_BAR_TEXT_SOURCE,
        wants=(_BAR_ALL_STATES, _BAR_APPLIED_FAIL),
        why="状态条自己编一句成功文案 ⇒ AC 11.3 明令禁止统一显示「同步成功」，"
        "Property 48 也要求真失败后不得被成功文案覆盖。文案真源只能是桥",
    ),
    Mutation(
        id="M25",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="  feedback.value.kind === 'error' ? 'danger' : WP_SYNC_STATE_TONE[state.value],",
        new="  WP_SYNC_STATE_TONE[state.value],",
        want=_BAR_APPLIED_FAIL,
        wants=(_BAR_ALL_STATES, _BAR_FROZEN),
        why="失败基调不盖过状态基调 ⇒ `applied` 后重载失败时状态条仍是绿色，"
        "用户据此以为回写已落地",
    ),
    Mutation(
        id="M26",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="  if (feedback.value.kind === 'error') return `失败于：${text}`",
        new="  if (feedback.value.kind === 'error') return text",
        want=_BAR_FROZEN,
        wants=(_BAR_APPLIED_FAIL, _BAR_ALL_STATES),
        why="失败时阶段标签不加前缀 ⇒ 一个带 sticky error 的 `applied` 会显示成"
        "「结构化回写完成」，两种结局在界面上不可辨",
    ),
    Mutation(
        id="M27",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="    return `接任者代为完成：${text}`",
        new="    return text",
        want=_BAR_SUCCESSOR,
        why="接任者代为完成不做归因 ⇒ 与「我自己保存成功」逐字同态。"
        "Task 34 明文 successor 接任进展不得渲染成保存成功",
    ),
    Mutation(
        id="M28",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="        v-if=\"waitKind === 'progress'\"",
        new='        v-if="true"',
        want=_BAR_ALL_STATES,
        wants=(_BAR_NO_SUCCESSOR, _BAR_DUP),
        why="转圈无条件渲染 ⇒ 终态（duplicate / download-only / close-recovery-required）"
        "上永远转圈，正是 Task 34 禁止的无限等待",
    ),
    Mutation(
        id="M29",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="  if (snapshot === null || snapshot.shape !== 'duplicate') return null",
        new="  if (snapshot === null) return null",
        want=_BAR_DUP_ABSENT,
        why="非 duplicate 也渲染折叠行 ⇒ 一次正常 primary 回写被显示成「已被折叠」，"
        "而 requested 与 canonical 此时本来就相同，形态判据分不出来",
    ),
    Mutation(
        id="M30",
        side="fe",
        path=BAR,
        kind="replace",
        scope="const plainRetryVisible = computed(() => {",
        offset=1,
        anchor="  if (['recovery_pending', 'recovery_claiming', 'recovery_download_only'].includes(state.value)) {",
        new="  if (false) {",
        want=_BAR_RETRY_RECOVERY,
        why="recovery 期间也给普通重试 ⇒ AC 5.8 末句明文 nullable operation 的 recovery case"
        "不得进入普通 operation retry",
    ),
    Mutation(
        id="M31",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="  if (props.bridge.requestedOperationId.value === null) return false",
        new="  if (false) return false",
        want=_BAR_RETRY_NO_OP,
        why="没有 requested operation 也给重试 ⇒ 点下去桥会拒（`bridge_no_requested_operation`），"
        "而 crash 早于 forcesave 时本来就没有可重试的 operation",
    ),
    Mutation(
        id="M32",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="        返回编辑：{{ verdict.canEnterEditing ? '允许' : '禁止' }}",
        new="        返回编辑：允许",
        want=_BAR_GATES,
        why="三个 verdict 布尔之一被写死 ⇒ 409 stale identity 之后界面仍宣称可以返回编辑，"
        "而 `classifySyncFailure` 在每个分支里都把它判为 false",
    ),
    Mutation(
        id="M33",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="        内容修订号（仅展示/乐观锁）：{{ revisionText }}",
        new="        内容修订号：{{ revisionText }}",
        want=_BAR_REVISION,
        why="修订号不再标注「仅展示/乐观锁」⇒ 下一个人会拿它拼 route。"
        "AC 8.7 明文 per-wp numeric revision 不得作 scope lookup key",
    ),
    Mutation(
        id="M34",
        side="fe",
        path=BAR,
        kind="replace",
        anchor="import { useDisplayPrefsStore } from '@/stores/displayPrefs'",
        new="import { useDisplayPrefsStore, fmtAmount } from '@/stores/displayPrefs'",
        want=_BAR_STORE_IMPORT,
        why="从 store 模块具名 import `fmtAmount` ⇒ 它是 store **成员**而非模块级导出，"
        "浏览器会把整页崩成「does not provide an export named fmtAmount」，"
        "而 Volar / vitest / get_diagnostics 三层全绿",
    ),
    # ═══════════ G. 冲突对话框：关闭不应用 ═══════════
    Mutation(
        id="M35",
        side="fe",
        path=DIALOG,
        kind="insert",
        scope="function onCloseRequested(_source: 'button' | 'cancel' | 'mask' | 'escape'): void {",
        offset=1,
        anchor="  resetLocalState()",
        new="  void props.bridge\n"
        "    .resolveConflicts({\n"
        "      fence: fenceDraft.value.fence as never,\n"
        "      resolutions: resolutions.value,\n"
        "    })\n"
        "    .catch(() => {})",
        want=_DLG_CLOSE_ANY,
        wants=(_DLG_CLOSE_ESC, _DLG_CLOSE_STRUCT),
        why="关闭时顺手提交一次裁决 ⇒ AC 11.7 明文「关闭面板不得自动应用任何一侧」。"
        "只断言「面板收起了」的判据对它全绿",
    ),
    Mutation(
        id="M36",
        side="fe",
        path=DIALOG,
        kind="delete",
        scope="function onCloseRequested(_source: 'button' | 'cancel' | 'mask' | 'escape'): void {",
        offset=1,
        anchor="  resetLocalState()",
        want=_DLG_CLOSE_ANY,
        wants=(_DLG_CLOSE_STRUCT,),
        why="关闭不清空本地选择 ⇒ 下次打开面板时上次没提交的选择还在，"
        "用户以为那是服务端的既有裁决",
    ),
    Mutation(
        id="M37",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor='            v-if="bulkPending !== null"',
        new='            v-if="true"',
        want=_DLG_TWO_STEP,
        wants=(_DLG_BULK_ANCHOR,),
        why="批量确认块无条件渲染 ⇒ 二次确认退化成一步，AC 8.3 要求批量选择二次确认",
    ),
    Mutation(
        id="M38",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor="const canSubmit = computed(() => fenceReady.value && resolutions.value.length > 0)",
        new="const canSubmit = computed(() => resolutions.value.length > 0)",
        want=_DLG_FENCE_BLOCK,
        why="fence 不齐也允许提交 ⇒ 桥会拒（`bridge_resolve_fence_incomplete`），"
        "但用户看到的是一个可点的按钮和一个看不懂的错误",
    ),
    Mutation(
        id="M39",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor="  if (fence === null || resolutions.value.length === 0) {",
        new="  if (resolutions.value.length === 0) {",
        want=_DLG_PROGRAMMATIC,
        why="程序化提交不再检查 fence ⇒ 门只长在 `:disabled` 上。"
        "本任务把提交入口 expose 出来正是为了让这条可被证伪",
    ),
    Mutation(
        id="M40",
        side="fe",
        path=DIALOG,
        kind="insert",
        anchor="    submitError.value = refusal",
        new="    emit('update:visible', false)",
        want=_DLG_STAY_OPEN,
        why="提交失败后仍收起面板 ⇒ 用户以为裁决已生效。失败必须留在原地并说明原因",
    ),
    Mutation(
        id="M41",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor='                  <div v-if="item.adjudicableByValueChoice" class="wp-sync-conflict__choices">',
        new='                  <div v-if="true" class="wp-sync-conflict__choices">',
        want=_DLG_STRUCTURAL,
        why="结构冲突也给选边入口 ⇒ 用户选了一侧却收敛不了（服务端会拒），"
        "而结构/身份异常必须先修结构（AC 6.15 的 fail-closed 侧）",
    ),
    Mutation(
        id="M42",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor="                    <label v-if=\"item.valueType === 'text'\">",
        new='                    <label v-if="true">',
        want=_DLG_MANUAL_TEXT,
        why="手工合并对金额也开放 ⇒ 用户会在文本框里敲一个带千分符的金额，"
        "而 AC 8.3 只允许**文本字段**输入合并值",
    ),
    Mutation(
        id="M43",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor="                  {{ protectionText[item.protectionPolicy] ?? item.protectionPolicy }}",
        new="                  {{ item.protectionPolicy }}",
        want=_DLG_PROTECTION,
        why="保护策略显示裸英文枚举 ⇒ 平台 UI 铁律要求全中文状态标签，"
        "`read_only_masked_cell` 这类值对审计师毫无意义",
    ),
    Mutation(
        id="M44",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor="      const raw = await props.bridge.fetchConflicts()",
        new="      const raw = props.bridge.conflicts.value",
        want=_DLG_FETCH,
        why="打开面板不拉预览、只读桥里可能过期的缓存 ⇒ 用户裁决的是一份旧冲突集，"
        "而 `conflict_set_digest` 乐观锁会在提交时才失败",
    ),
    Mutation(
        id="M45",
        side="fe",
        path=DIALOG,
        kind="replace",
        anchor="    displayPrefs.fmtAmount(value),",
        new="    String(value),",
        want=_DLG_AMOUNT,
        wants=(_DLG_AMOUNT_LIVE,),
        why="冲突面板的金额不经 store ⇒ 平台单位/小数位切换对它无效，"
        "AC 8.2 明文金额使用平台 `displayPrefs.fmtAmount()`",
    ),
    # ═══════════ H. recovery 面板 ═══════════
    Mutation(
        id="M46",
        side="fe",
        path=RECOVERY,
        kind="replace",
        anchor="const listed = ref(false)",
        new="const listed = ref(true)",
        want=_RCV_NOT_LISTED,
        why="未经 authorization-first list 就进入「已列出」态 ⇒ 面板先画一张空壳，"
        "而 AC 5.8/10.6 的可见性门就是服务端那次 list",
    ),
    Mutation(
        id="M47",
        side="fe",
        path=RECOVERY,
        kind="insert",
        anchor='      <div class="wp-sync-recovery__actions">',
        new='        <el-button size="small" data-testid="wp-sync-recovery-retry"'
        ' @click="props.bridge.retryOperation()">重试回写</el-button>',
        want=_RCV_NO_RETRY_DOM,
        wants=(_RCV_NO_RETRY_SRC,),
        why="给 recovery 面板加一个普通重试入口 ⇒ AC 5.8 末句明令禁止；"
        "claim 之前 operation 为空，点下去只能得到一个 404",
    ),
    Mutation(
        id="M48",
        side="fe",
        path=RECOVERY,
        kind="replace",
        anchor="    if (tracked === null || projected.claimedOperationId !== tracked) {",
        new="    if (false) {",
        want=_RCV_DRIFT_OP,
        why="claim 后不核对「跟踪的是不是原 operation」⇒ 服务端换了一条 operation 时"
        "界面照样显示「已认领」，而 AC 5.8 要求 claim 沿同一 operation 推进",
    ),
    Mutation(
        id="M49",
        side="fe",
        path=RECOVERY,
        kind="replace",
        anchor="    const timeline = await props.bridge.fetchRecoveryCaseTimeline(item.caseId)",
        new="    const timeline = {\n"
        "      case_id: item.caseId,\n"
        "      claimed_operation_id: tracked,\n"
        "      claimed_application_id: tracked,\n"
        "      recovery_request_id: tracked,\n"
        "      has_three_entities: true,\n"
        "      events: [],\n"
        "    }",
        want=_RCV_TIMELINE,
        wants=(_RCV_THREE,),
        why="三实体自己编 ⇒ claim 的 202 回执里**没有** request id，桥也没保存它；"
        "编造出来的三个 id 全指向同一个 operation，而真值来自 recovery case timeline",
    ),
    Mutation(
        id="M50",
        side="fe",
        path=RECOVERY,
        kind="replace",
        anchor="          已仅下载并终结该恢复项，未执行结构化回写；请求 / 内容应用 / 回写任务三者均未创建。",
        new="          回写完成。",
        want=_RCV_DOWNLOAD,
        wants=(_RCV_DOWNLOAD_SRC,),
        why="download-only 显示「回写完成」⇒ Task 34 逐字禁止；"
        "它永不创建 request/application/operation（AC 5.8）",
    ),
    Mutation(
        id="M51",
        side="fe",
        path=RECOVERY,
        kind="replace",
        anchor="  if (bridgeWp !== props.scope.wpId) {",
        new="  if (false) {",
        want=_RCV_SCOPE_WP,
        why="不核对显式 scope 与桥实际 scope ⇒ 宿主传错底稿 id 时面板照着错的 scope 显示，"
        "而 list/claim 用的是桥的 scope —— 界面与动作对象不是一回事",
    ),
    Mutation(
        id="M52",
        side="fe",
        path=RECOVERY,
        kind="replace",
        anchor="  if (blockingOf(item).length > 0) return false",
        new="  if (false) return false",
        want=_RCV_CLAIM_DISABLED,
        why="claim 门不看阻断原因 ⇒ 阻断原因列在界面上、按钮却亮着，"
        "用户点下去才由服务端拒（且拒绝原因未必可读）。"
        "🔴 首轮实测 GREEN：判据当时没先选候选确认，于是关掉门的其实是「未选候选」"
        "那一道 —— 判据已改成先选候选再断言禁用（`_RCV_NO_CANDIDATE` 那条结构上"
        "无法隔离本门，故不再挂进 wants）",
    ),
    Mutation(
        id="M53",
        side="fe",
        path=RECOVERY,
        kind="replace",
        anchor="  return typeof selectedConfirmation.value[item.caseId] === 'string'",
        new="  return true",
        want=_RCV_PICK_FIRST,
        why="不要求先选候选确认 ⇒ claim 会带一个 undefined 的 prior confirmation id，"
        "而 AC 5.8 要求 claim 必须引用同 room/代际的既有确认",
    ),
    # ═══════════ I. 详情抽屉 ═══════════
    Mutation(
        id="M54",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor="      value: WP_SYNC_TRACE_GAP_PLACEHOLDER,",
        new="      value: shortDigest(d?.artifactSha256 ?? null),",
        want=_DRW_GAPS,
        wants=(_DRW_INCOMING,),
        why="已登记缺口被相邻字段顶替 ⇒ 用发出侧 artifact 摘要充当回传摘要，"
        "「回来的文件就是我发出去的那份」凭空成立（Task 33 抓过同形态）",
    ),
    Mutation(
        id="M55",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor="      versionId: target.versionId,",
        new="      versionId: String(target.revision),",
        want=_DRW_ROLLBACK_BODY,
        wants=(_DRW_ROLLBACK_STRUCT,),
        why="用 numeric revision 拼 rollback 路由 ⇒ 两个不同底稿都存在 revision 1，"
        "会在授权索引里撞成同一行（AC 8.7 / 10.6）",
    ),
    Mutation(
        id="M56",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor='            @click="rollbackConfirming = true"',
        new='            @click="onRollbackConfirm()"',
        want=_DRW_TWO_STEP,
        why="回滚一步到位 ⇒ 一次误点就改写 current pointer。"
        "design §API 明文 rollback 需编辑权限和二次确认",
    ),
    Mutation(
        id="M57",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor="  if (target === null || !rollbackTargetUsable.value) {",
        new="  if (target === null) {",
        want=_DRW_NOT_OPAQUE,
        why="抽屉自己的 opaque 门失效 ⇒ 非 UUID 目标一路传到 API 层才被拒，"
        "用户得到的是一个契约错误而不是可读原因",
    ),
    Mutation(
        id="M58",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor="      code: 'details_rollback_target_not_opaque',",
        new="      code: 'version_id_not_opaque',",
        want=_DRW_NOT_OPAQUE,
        why="两层门共用一个码 ⇒ 删掉抽屉那层看不出差别（API 层照样抛同一个码），"
        "于是外层门的判据永远 GREEN。本 spec 的变异运行已三次抓到这个形态",
    ),
    Mutation(
        id="M59",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor="      await props.bridge.fetchRecoveryCaseTimeline(caseId),",
        new="      await props.bridge.fetchTimeline(),",
        want=_DRW_RECOVERY_TL,
        why="recovery timeline 走 operation 端点 ⇒ 两条流被合成一条，"
        "claim 之前的 recovery 事件必须借一个 operation id 才挂得上（P68 明令禁止）",
    ),
    Mutation(
        id="M60",
        side="fe",
        path=DRAWER,
        kind="replace",
        scope="const evidenceCorrelationId = computed<string | null>(() => {",
        offset=6,
        anchor="  return null",
        new="  return 'evidence-unknown'",
        want=_DRW_EVIDENCE,
        why="没加载事件时编一个证据关联标识 ⇒ 审计追溯拿到一个不存在的 correlation id，"
        "而它只能来自已加载的 append-only 事件",
    ),
    Mutation(
        id="M61",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor="    present('refresh_required', '需重载编辑器确认新基线', state.value === 'refresh_required' ? '是' : '否'),",
        new="    present('refresh_required', '需重载编辑器确认新基线', '否'),",
        want=_DRW_REFRESH,
        why="refresh-required 恒显「否」⇒ 服务端已合并、需要重开代际时追溯面板说不需要，"
        "而 AC 11.11 要求 refresh-required 可追溯",
    ),
    Mutation(
        id="M62",
        side="fe",
        path=DRAWER,
        kind="replace",
        anchor='          v-if="operationTimeline === null"',
        new='          v-if="false"',
        want=_DRW_TL_EMPTY,
        why="未加载也当已加载 ⇒ 渲染一张空表，用户以为「这个回写任务没有事件」，"
        "而实际只是没点加载",
    ),
    Mutation(
        id="M63",
        side="fe",
        path=PRES,
        kind="replace",
        anchor="  return arbitration.outcome !== 'not_applicable'",
        new="  return true",
        want=_CLOSE_VISIBLE,
        wants=(_BAR_NO_ARBITRATION,),
        why="仲裁行无条件显示 ⇒ 一次从未发生 close 仲裁的普通保存也会挂上一句"
        "「关闭仲裁」，用户以为自己的关闭被别人接管了",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 34 同步 UI 守卫变异检验",
            frontend_filters=FE_FILTERS,
            frontend_dir=FRONTEND,
            vitest_json=_FE_JSON,
        )
    )
