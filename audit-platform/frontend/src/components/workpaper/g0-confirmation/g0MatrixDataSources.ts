/**
 * g0MatrixDataSources.ts — G0-1 下区矩阵的取数编排（账面金额 + 手工覆盖）
 *
 * spec: g0-confirmation-source-alignment，Task 7（Requirement 4.3 / 3.4 / 3.5）
 *
 * 数据源两个：
 * ┌────────────────┬──────────────────────────────────────────────────────────┐
 * │ bookAmounts    │ G1/G4/G5/G6/G7/G8/G9/G10 的 render-config                 │
 * │                │ `project_context.tb_amount`（八者是独立 working_paper）    │
 * ├────────────────┼──────────────────────────────────────────────────────────┤
 * │ manualOverrides│ `checklist_responses` 的 `G0-1-matrix-{品种}-{指标key}` 键 │
 * └────────────────┴──────────────────────────────────────────────────────────┘
 *
 * 🔴 三条从 F0 那轮浏览器实测继承的硬约束（`f0MatrixDataSources.ts` 文件头有完整记录，
 *    此处照搬，勿重蹈）：
 * 1. **HTTP 客户端必须用 `@/services/apiProxy` 的 `api`，不能用 `@/utils/http`** ——
 *    `api.get` 直接返回业务数据；`http.get` 返回 AxiosResponse。混用会让 `?.wp_id`
 *    恒为 undefined，八个品种的 `tb_amount` 全取不到，而四层验证全绿（响应体是 `any`）。
 * 2. **禁止并行请求同一 URL** —— `utils/http` 的去重键是 `method:url:JSON.stringify(params)`，
 *    同键后发者会 abort 先发者。本模块的 8 个 `wp-id-by-code` 请求 params 各不相同
 *    （wp_code 不同）、8 个 render-config URL 也各不相同（wpId 不同）→ 并行安全。
 * 3. **缺失返 `undefined` 不返 0** —— 「本项目无此科目/未编制该审定表」与「余额为 0」
 *    是两种状态，混同会让矩阵比例行出现假 0。
 *
 * 任一品种取数失败不阻断其余（`Promise.allSettled` + 逐项兜底），全程 `_silent`，
 * 但**错误如实进 `diagnostics.errors` 并在 UI 暴露** —— 静默吞掉是 F0 那轮的教训。
 */

import { api } from '@/services/apiProxy'
import { G0_MATRIX_CATEGORIES, type G0MetricKey } from './g0SummaryMatrix'

// ─── 类型 ─────────────────────────────────────────────────────────────────────

export interface G0MatrixSources {
  /** 品种名 → 账面金额（缺失不落键） */
  bookAmounts: Record<string, number>
  diagnostics: G0SourceDiagnostics
}

export interface G0SourceDiagnostics {
  /** 成功取到 tb_amount 的品种 */
  bookResolved: string[]
  /** 未取到的品种（本项目无此科目 / 未编制该审定表 / 取数失败） */
  bookMissing: string[]
  /** 取数过程中的错误（不阻断，仅记录并暴露） */
  errors: string[]
}

// ─── 单个底稿的 project_context.tb_amount ────────────────────────────────────

/**
 * 按 wp_code 拉某底稿的 render-config，取首个含 `project_context.tb_amount` 的 sheet。
 *
 * 不走 `fetchWorkpaperHtmlRows`（它按 `_format` 匹配 sheet，与本需求无关）——
 * render 对每个 sheet 都注入同一份 `project_context`，任一 sheet 皆可。
 */
async function fetchTbAmountByWpCode(
  projectId: string,
  wpCode: string,
): Promise<number | undefined> {
  const idRes = await api.get<{ wp_id?: string }>('/api/custom-query/wp-id-by-code', {
    params: { project_id: projectId, wp_code: wpCode },
    _silent: true,
  } as never)
  const wpId = idRes?.wp_id
  if (!wpId) return undefined

  const cfg = await api.get<{ sheets?: unknown[] }>(`/api/workpapers/${wpId}/render-config`, {
    _silent: true,
  } as never)
  const sheets = (cfg?.sheets ?? []) as Array<Record<string, unknown>>

  for (const sheet of sheets) {
    const hd = (sheet?.html_data ?? sheet?.htmlData) as
      | { project_context?: { tb_amount?: unknown } }
      | undefined
    const raw = hd?.project_context?.tb_amount
    const amount = Number(raw)
    // 🔴 `raw == null` 时 Number(null) === 0 → 必须先排除 null/undefined/''
    if (raw != null && raw !== '' && Number.isFinite(amount)) return amount
  }
  return undefined
}

// ─── 主编排 ───────────────────────────────────────────────────────────────────

/**
 * 加载 8 个品种的账面金额。
 *
 * @param projectId 项目 ID（查 G1..G10 用）
 */
export async function loadG0MatrixSources(
  projectId: string | undefined,
): Promise<G0MatrixSources> {
  const diagnostics: G0SourceDiagnostics = { bookResolved: [], bookMissing: [], errors: [] }
  const bookAmounts: Record<string, number> = {}

  if (!projectId?.trim()) {
    diagnostics.errors.push('缺少 projectId，无法取账面金额')
    diagnostics.bookMissing.push(...G0_MATRIX_CATEGORIES.map((c) => c.name))
    return { bookAmounts, diagnostics }
  }

  await Promise.allSettled(
    G0_MATRIX_CATEGORIES.map(async (cat) => {
      try {
        const amount = await fetchTbAmountByWpCode(projectId, cat.book.wpCode)
        if (amount != null) {
          bookAmounts[cat.name] = amount
          diagnostics.bookResolved.push(cat.name)
        } else {
          diagnostics.bookMissing.push(cat.name)
        }
      } catch (e: unknown) {
        diagnostics.bookMissing.push(cat.name)
        const msg = e instanceof Error ? e.message : '取数失败'
        diagnostics.errors.push(`${cat.name}(${cat.book.wpCode}): ${msg}`)
      }
    }),
  )

  return { bookAmounts, diagnostics }
}

// ─── 手工覆盖持久化 ───────────────────────────────────────────────────────────

/**
 * 矩阵手工覆盖的 checklist item_id。
 *
 * 键式 `G0-1-matrix-{品种}-{指标key}` —— 🔴 用**指标 key**（`book_amount`）而非中文
 * label，改文案不会让已录入值失联（F0 侧用的是中文 label，属该侧遗留）。
 */
export function g0MatrixOverrideItemId(category: string, metric: G0MetricKey): string {
  return `G0-1-matrix-${category}-${metric}`
}

/** 唯一可手工覆盖的指标（源模板该行无公式） */
const EDITABLE_METRIC: G0MetricKey = 'book_amount'

/**
 * 从 checklist responses 解析矩阵手工覆盖值。
 *
 * @param categories 品种全集（默认候选 8 个；传入可含自定义品种）
 */
export function parseG0ManualOverrides(
  allResponses: Map<string, unknown> | Record<string, unknown> | undefined | null,
  categories?: readonly string[],
): Record<string, number> {
  const result: Record<string, number> = {}
  if (!allResponses) return result

  const readValue = (itemId: string): unknown => {
    const entry =
      allResponses instanceof Map
        ? allResponses.get(itemId)
        : (allResponses as Record<string, unknown>)[itemId]
    if (entry == null) return undefined
    if (typeof entry === 'object') {
      const o = entry as Record<string, unknown>
      return o.value ?? o.remark ?? undefined
    }
    return entry
  }

  const names = categories ?? G0_MATRIX_CATEGORIES.map((c) => c.name)
  for (const category of names) {
    const raw = readValue(g0MatrixOverrideItemId(category, EDITABLE_METRIC))
    const num = Number(raw)
    if (raw != null && raw !== '' && Number.isFinite(num)) {
      result[`${category}::${EDITABLE_METRIC}`] = num
    }
  }
  return result
}
