/**
 * aiDraftOverlay — 「纳入当前未保存草稿」开关的纯函数集合
 *
 * Feature: chat-host-draft-overlay / Task 5
 *
 * Requirements:
 *   - 4.4：用户必须能**显式关闭**「纳入未保存草稿」（默认关闭，避免误把半成品当权威数据）。
 *   - 5.2：**不改既有「提示未纳入」文案** —— 开关关闭时范围说明逐字不变，开启时才改成
 *     「将纳入当前未保存草稿（基于版本 v…）」。
 *   - 2.5：Manifest 必须能区分「已保存内容」与「未保存草稿」两种来源，**前端在消息上标注**。
 *
 * Design §5 前端要点 1~5。
 *
 * ## 为什么单独一个模块（而不是全写进面板）
 *
 * ① 面板已 1195 行、默认上限 1500 行（`backend/scripts/check/check_file_size.py` 的
 *    `LIMITS['.vue']`），且不在 whitelist 里 —— 往里面堆文案替换 + manifest 解析很快撞墙。
 * ② 这里的四件事（范围文案替换 / 请求载荷构造 / manifest 条目解析 / 消息标注文案）全是
 *    **纯函数**，在这里能被逐条单测覆盖，不必 mount 整个面板。
 *
 * ## 三个边界口径
 *
 * * 开关关闭 ⇒ 面板走 `hostScopeHint()`（既有函数，本模块不改它），文案逐字不变；
 * * 读不到草稿 ⇒ 载荷返回 `null`，请求体里**连键都不出现**（"没提交"与"提交空对象"
 *   在服务端 manifest 里是两种语义）；
 * * manifest 里没有任何 `draft_overlay:*` 条目 ⇒ 返回 `null`，消息上不加标注
 *   （本轮没提交过 overlay 时后端连 `draft_overlay_included` 键都不下发，见
 *   `context_plan.build_context_plan` 的注释）。
 */

import { hostScopeHint, type AiHostRequest } from '@/composables/useAiHostContext'
import type { WorkpaperDraftOverlay } from '@/composables/workpaper/workpaperDraftOverlay'

// ---------------------------------------------------------------------------
// 常量（与后端 / 既有文案逐字对齐）
// ---------------------------------------------------------------------------

/**
 * 开关关闭时范围文案的尾句。
 *
 * 🔴 **需求 5.2 要求这句逐字不变**：本模块只做「把尾句替换掉」这一件事，
 * 不改 `hostScopeHint()` 本身，也不重新拼前缀 —— 前缀里的宿主标签 / 全局模式分支
 * 由 `hostScopeHint()` 继续负责（它已有多处守卫）。
 */
export const SCOPE_TAIL_SAVED_ONLY = '当前未保存修改不会纳入本轮'

/** 开关打开后替换成的尾句（design §5.3）。 */
export const SCOPE_TAIL_WITH_DRAFT = '将纳入当前未保存草稿（基于版本 v'

/** 开关的中文标签（需求 4.4；硬编码中文是全平台约定，不接 i18n）。 */
export const DRAFT_OVERLAY_TOGGLE_LABEL = '纳入当前未保存草稿'

/** 服务端 manifest 里 overlay 条目的 `source_type` 前缀（镜像后端 `DRAFT_OVERLAY_SOURCE_PREFIX`）。 */
export const DRAFT_OVERLAY_SOURCE_PREFIX = 'draft_overlay'

/** 服务端 `ContextManifest.as_dict()` 的分组键（条目按裁决结果分组下发）。 */
const MANIFEST_GROUPS = ['included', 'trimmed', 'denied', 'unavailable'] as const

const CJK_RE = /[\u4e00-\u9fff]/

// ---------------------------------------------------------------------------
// 请求载荷（POST /api/ai-chat/runs 的 draft_overlay 字段）
// ---------------------------------------------------------------------------

/**
 * 提交给服务端的未保存草稿（镜像后端 `DraftOverlayRef`，`extra="forbid"`）。
 *
 * 字段名保持 snake_case：这就是**线上契约**的形状，面板只是把它塞进请求体，
 * 中间不再做一次驼峰转换（多一层转换就多一处可能写错键名的地方，而后端对未知键是
 * 直接 422）。
 *
 * `content_length` 只是诊断量（服务端按实际正文重算并覆盖），但**必须一起提交**：
 * design §2 的契约里它是必填诊断字段，缺了会让服务端日志少一个可对账的量。
 */
export interface DraftOverlayPayload {
  host_type: 'workpaper'
  host_id: string
  baseline_version: string
  content: string
  content_length: number
}

/**
 * 构造 `draft_overlay` 请求字段；**读不到草稿时返回 `null`**（调用方据此省略整个键）。
 *
 * 四道 fail-closed 与 `readHostDraftOverlay` 同源（无登记 / 空正文 / 空基线 / 超限），
 * 这里只额外挡住「宿主不是可用底稿」这一种 —— 不能拿别的宿主的内容冒充本宿主草稿
 * （服务端会以 `host_id != request.host.id` 判 422，前端先不发）。
 */
export function buildDraftOverlayPayload(
  request: AiHostRequest | null | undefined,
  overlay: WorkpaperDraftOverlay | null | undefined,
): DraftOverlayPayload | null {
  const host = request?.host
  if (!overlay || !request?.available || !host || host.type !== 'workpaper' || !host.id) {
    return null
  }
  return {
    host_type: 'workpaper',
    host_id: host.id,
    baseline_version: overlay.baselineVersion,
    content: overlay.content,
    content_length: overlay.contentLength,
  }
}

// ---------------------------------------------------------------------------
// 范围文案（需求 5.2）
// ---------------------------------------------------------------------------

const ISO_UTC_PREFIX_RE = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})/

/**
 * 把归一后的业务版本渲染成**短且确定**的展示形态：`2026-11-15 10:00:00 UTC`。
 *
 * 🔴 不做本地时区换算（不用 `new Date().toLocaleString()`）：
 * `normalizeBusinessVersion()` 产出的值恒为 UTC，换算会让同一份草稿在不同机器 /
 * 不同时区上显示成不同时间，用户在两个窗口里对不上账。原样截断 + 标注 UTC 反而可对账。
 * 认不出的形状原样返回（与后端「不猜」的取向一致）。
 */
export function formatDraftBaselineVersion(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  const text = raw.trim()
  if (!text) return ''
  const matched = ISO_UTC_PREFIX_RE.exec(text)
  return matched ? `${matched[1]} ${matched[2]} UTC` : text
}

/**
 * 开关打开时的范围文案。
 *
 * 实现方式是**只替换尾句**，前缀仍由 `hostScopeHint()` 产出 —— 这样：
 * ① 需求 5.2「关闭时不改既有文案」天然成立（关闭时根本不调本函数）；
 * ② 宿主标签、全局知识模式、不可用原因这些分支不需要在这里复述一遍（复述就会漂移）。
 *
 * 前缀不以既有尾句结尾（全局模式 / 宿主不可用）时原样返回：那些情形下根本没有
 * 「未保存草稿」可言，替换会拼出一句自相矛盾的话。
 */
export function hostScopeHintWithDraft(
  request: AiHostRequest,
  baselineVersion: string | null | undefined,
): string {
  const base = hostScopeHint(request)
  if (!base.endsWith(SCOPE_TAIL_SAVED_ONLY)) return base
  const version = formatDraftBaselineVersion(baselineVersion) || '（未知）'
  return `${base.slice(0, -SCOPE_TAIL_SAVED_ONLY.length)}${SCOPE_TAIL_WITH_DRAFT}${version}）`
}

// ---------------------------------------------------------------------------
// 消息标注（需求 2.5 / design §5.5）
// ---------------------------------------------------------------------------

/** 服务端对这份草稿的裁决（`included` / `trimmed` / `denied` / `unavailable`）。 */
export type DraftOverlayNoticeStatus = 'included' | 'trimmed' | 'denied' | 'unavailable'

/** 挂在消息上的「本轮草稿纳入情况」标注（不落库，只在本轮内存消息上）。 */
export interface ChatDraftOverlayNotice {
  readonly status: DraftOverlayNoticeStatus
  /** 中文展示名（后端 `overlay_label`，如「当前未保存草稿（底稿 B1-1）」）。 */
  readonly label: string
  /** `denied` 时的中文原因；其余状态可能为空或英文码（见 `draftOverlayNoticeText`）。 */
  readonly reason: string
  /** 草稿基于的宿主业务版本（归一后的 UTC ISO-8601）。 */
  readonly baselineVersion: string
  /** 服务端重算的正文摘要（`sha256:…`），用于「拒绝的是哪一份草稿」对账。 */
  readonly contentHash: string
}

function normalizeStatus(value: unknown, fallback: string): DraftOverlayNoticeStatus {
  const text = String(value ?? '')
  if ((MANIFEST_GROUPS as readonly string[]).includes(text)) {
    return text as DraftOverlayNoticeStatus
  }
  return (MANIFEST_GROUPS as readonly string[]).includes(fallback)
    ? (fallback as DraftOverlayNoticeStatus)
    : 'unavailable'
}

function readString(entry: Record<string, unknown>, key: string): string {
  const value = entry[key]
  return typeof value === 'string' ? value : ''
}

/**
 * 从 `context_ready.payload.manifest` 里读出本轮的 overlay 条目。
 *
 * 服务端把条目按**裁决结果分组**下发（`included` / `trimmed` / `denied` / `unavailable`），
 * 条目的 `source_type` 形如 `draft_overlay:workpaper`（`context_plan._budget_draft_overlay`）。
 * 因此必须遍历四个分组，只按顶层键找不到 `denied` 的那条。
 *
 * 没有 overlay 条目 ⇒ `null`：本轮没提交草稿（后端此时连 `draft_overlay_included` 都不下发），
 * 消息上不该多出一行标注（需求 6.1：默认关闭时行为与现状完全一致）。
 */
export function readDraftOverlayNotice(manifest: unknown): ChatDraftOverlayNotice | null {
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) return null
  const groups = manifest as Record<string, unknown>
  for (const group of MANIFEST_GROUPS) {
    const rows = groups[group]
    if (!Array.isArray(rows)) continue
    for (const row of rows) {
      if (!row || typeof row !== 'object') continue
      const entry = row as Record<string, unknown>
      if (!readString(entry, 'source_type').startsWith(DRAFT_OVERLAY_SOURCE_PREFIX)) continue
      return {
        status: normalizeStatus(entry.status, group),
        label: readString(entry, 'label'),
        reason: readString(entry, 'reason'),
        baselineVersion: readString(entry, 'baseline_version'),
        contentHash: readString(entry, 'content_hash'),
      }
    }
  }
  return null
}

/**
 * 消息下方那行中文标注。
 *
 * 🔴 `denied` 的原因是后端产出的**中文整句**（`draft_overlay.decide_draft_overlay`），
 * 直接展示即可；但 `trimmed` / `unavailable` 的 `reason` 是**英文码**
 * （`budget_exceeded`），照搬会往全中文界面里塞英文。所以这里判一次是否含汉字：
 * 不含就换成同义中文，绝不让英文码直接露给用户。
 */
export function draftOverlayNoticeText(notice: ChatDraftOverlayNotice): string {
  const version = formatDraftBaselineVersion(notice.baselineVersion)
  const suffix = version ? `（基于版本 v${version}）` : ''
  if (notice.status === 'included') {
    return `本轮已纳入当前未保存草稿${suffix}`
  }
  if (notice.status === 'trimmed') {
    return `本轮已纳入当前未保存草稿${suffix}，但按上下文预算做了裁剪`
  }
  const reason = CJK_RE.test(notice.reason) ? notice.reason.trim() : ''
  if (reason) return `当前未保存草稿未纳入：${reason}`
  if (notice.status === 'unavailable') {
    return '当前未保存草稿未纳入：本轮上下文预算不足'
  }
  return '当前未保存草稿未纳入：草稿已过期，请先保存或刷新后重试'
}
