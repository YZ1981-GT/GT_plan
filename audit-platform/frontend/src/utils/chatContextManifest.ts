/**
 * chatContextManifest — 把 `context_ready` 的服务端 manifest 投影成 ChatContextInspector 的 props
 *
 * 🔴 为什么需要这一层（不是多余的中间层）：
 *
 * 服务端 `context_ready.payload.manifest` 是**按决策分组的 dict**，且两套 engine 形状不同：
 *
 *   native (`native_engine._manifest`)：
 *     `{ manifest_version, token_estimate, citation_count, project_tools_enabled,
 *        review_mode, included: [{source_type, source_id, label, decision, char_estimate, is_stale?}] }`
 *   budget policy (`context_budget.ContextManifest.as_dict`)：
 *     `{ manifest_version, total_budget, total_used,
 *        included?/trimmed?/denied?/unavailable?: [{source_type, source_id, status, label?, used_tokens?, reason?, version?, stale?}] }`
 *   dsh (`dsh_engine`)：`{ manifest_version, engine, tools_enabled, project_tools_enabled }`（无条目）
 *
 * 而 `ChatContextInspector` 的 props 契约是**扁平数组** `ContextManifestItem[]`，键名是
 * `decision` / `reason_code` / `token_estimate` / `is_stale`。两边键名与结构都不一致：
 * 把 store 里的 `contextManifest`（原样存的服务端 dict）直接绑上去，`v-for` 会遍历 dict 的
 * **值**，渲染出 `manifest_version` 字符串这类垃圾行，而 `manifest.length === 0` 的空态判断
 * 也恒为 false。所以宿主侧必须投影 —— 组件契约不动（它有独立守卫锁着）。
 *
 * 两条纪律：
 *  - **不发明数据**：服务端没给的键投 `null` / `0`，不猜、不填默认字符串。
 *    尤其 `jump_route` —— 服务端 manifest 目前不下发它，投 `null` 让跳转按钮不渲染，
 *    而不是前端自己拼一个路由（那等于把前端 route 当授权凭据，违反 Req 5.9）。
 *  - **不丢条目**：任何未登记的分组键（将来新增决策）也要落进结果，
 *    decision 落到 `unavailable` 并保留原始 status 作 reason，宁可显示成"未知"也不静默吞掉。
 *
 * Feature: dsh-agent-panel-integration / Task 15 接线补口
 * Validates: Requirements 5.7, 5.9
 * Properties: 12
 */
import type { ContextManifestItem } from '@/components/ai/ChatContextInspector.vue'

/** 服务端分组键 → 组件 decision 值。 */
const GROUP_TO_DECISION: Record<string, ContextManifestItem['decision']> = {
  included: 'included',
  trimmed: 'trimmed',
  denied: 'denied',
  unavailable: 'unavailable',
}

/** 已知的**非条目**顶层键（元信息，不参与遍历）。 */
const META_KEYS = new Set([
  'manifest_version',
  'token_estimate',
  'citation_count',
  'project_tools_enabled',
  'review_mode',
  'total_budget',
  'total_used',
  'engine',
  'tools_enabled',
])

function toInt(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? Math.trunc(n) : 0
}

function toNullableString(value: unknown): string | null {
  if (value === null || value === undefined) return null
  const s = String(value)
  return s.length > 0 ? s : null
}

/**
 * 单条服务端 entry → 组件 item。
 *
 * `token_estimate` 的取数顺序：`used_tokens`（budget policy 口径）→ `token_estimate`
 * → `char_estimate`（native 口径，字符数；组件只用它做相对占比与 tooltip，不当计费依据）。
 */
function normalizeEntry(
  raw: Record<string, unknown>,
  decision: ContextManifestItem['decision'],
  fallbackReason: string | null,
): ContextManifestItem {
  return {
    source_type: String(raw.source_type ?? 'unknown'),
    source_id: String(raw.source_id ?? ''),
    label: String(raw.label ?? raw.source_id ?? ''),
    decision,
    reason_code: toNullableString(raw.reason ?? raw.reason_code) ?? fallbackReason,
    token_estimate: toInt(raw.used_tokens ?? raw.token_estimate ?? raw.char_estimate),
    version: toNullableString(raw.version),
    is_stale: Boolean(raw.stale ?? raw.is_stale ?? false),
    jump_route: toNullableString(raw.jump_route),
  }
}

/**
 * 服务端 manifest（分组 dict）→ 扁平 `ContextManifestItem[]`。
 *
 * 输入不是对象（null / 数组 / 字符串）时：数组按已是扁平形态处理，其余返回 `[]`。
 */
export function normalizeContextManifest(raw: unknown): ContextManifestItem[] {
  if (!raw) return []

  // 已是扁平数组（未来若服务端改成扁平下发，这里不需要跟着改）
  if (Array.isArray(raw)) {
    return raw
      .filter((e): e is Record<string, unknown> => !!e && typeof e === 'object')
      .map((e) => {
        const decision = GROUP_TO_DECISION[String(e.decision ?? e.status ?? 'included')]
        return normalizeEntry(e, decision ?? 'unavailable', decision ? null : String(e.decision ?? e.status ?? ''))
      })
  }

  if (typeof raw !== 'object') return []

  const items: ContextManifestItem[] = []
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (META_KEYS.has(key) || !Array.isArray(value)) continue
    const decision = GROUP_TO_DECISION[key]
    for (const entry of value) {
      if (!entry || typeof entry !== 'object') continue
      const row = entry as Record<string, unknown>
      // 条目自带 decision/status 时以它为准（native 的 included 数组里带 decision）
      const own = GROUP_TO_DECISION[String(row.decision ?? row.status ?? '')]
      items.push(
        normalizeEntry(
          row,
          own ?? decision ?? 'unavailable',
          own || decision ? null : key,
        ),
      )
    }
  }
  return items
}

/**
 * 服务端 manifest 里的 token 预算总量（`total_budget`）。
 *
 * 没有下发时返回 0 —— 组件据此**不渲染**预算条，而不是拿 `token_estimate` 之和当分母
 * （那会画出一条永远 100% 的假进度条）。
 */
export function readContextTokenBudget(raw: unknown): number {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return 0
  return toInt((raw as Record<string, unknown>).total_budget)
}
