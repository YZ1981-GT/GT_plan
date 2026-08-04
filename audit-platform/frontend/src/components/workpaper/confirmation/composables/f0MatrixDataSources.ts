/**
 * f0MatrixDataSources.ts — F0-1 矩阵三个数据源的取数编排
 *
 * 🔴 本模块是 Task 23 的核心 —— 上一版把 `bookAmounts`/`altTotals` 全传 `undefined`
 * 并留 TODO 注释，导致矩阵 4 个百分比行恒 `-`、替代确认恒 0，
 * 立项要解决的「F0-1 指标全是手工填 0」原地不动。
 *
 * 三个数据源（全部实证过取数路径，非猜测）：
 * ┌────────────────┬──────────────────────────────────────────────────────────┐
 * │ bookAmounts    │ F1/F3/F4 的 render-config `project_context.tb_amount`     │
 * │                │ （三者是独立 working_paper，各有独立 wp_code）              │
 * ├────────────────┼──────────────────────────────────────────────────────────┤
 * │ altF05/F06     │ F0-5/F0-6 的 `html_data._format='alternative-f0{5,6}-v1'` │
 * │ Totals         │ 的 `companies[].block{1..4}_rows[].voucher_amount`        │
 * │                │ （与 F0-1 同属一个 working_paper 的不同 sheet）             │
 * ├────────────────┼──────────────────────────────────────────────────────────┤
 * │ manualOverrides│ `checklist_responses` 的 `F0-1-matrix-{品种}-{指标}` 键     │
 * └────────────────┴──────────────────────────────────────────────────────────┘
 *
 * 设计约束：
 * - **缺失返 undefined 不返 0** —— 「本项目无此科目」与「余额为 0」是两种状态
 * - 任一数据源失败不阻断其余（Promise.allSettled + 逐项兜底）
 * - 全程 `_silent: true`，取数失败只在 console 留痕，不弹 ElMessage 打断用户
 *
 * 🔴🔴 **HTTP 客户端必须用 `@/services/apiProxy` 的 `api`，不能用 `@/utils/http`**
 * （2026-08-03 浏览器实测抓到的 P0，`apiProxy.ts` 自己的文件头就写着这条区别）：
 * - `http.get(url)` 返回 **AxiosResponse** → 取业务数据要 `const { data } = await http.get(...)`
 * - `api.get(url)` **直接返回业务数据**
 * 上一版 `import api from '@/utils/http'` 却按 apiProxy 的形态读
 * （`(idRes as any)?.wp_id`）→ **恒为 undefined** → 三个品种的 `tb_amount` 全部取不到，
 * 矩阵账面金额行永远空、四个百分比行永远「-」。
 * `get_diagnostics` / vitest / Vite 200 全绿（响应体在 TS 里是 `any`），只有浏览器能发现。
 * 平台既有 20+ 处调用 `wp-id-by-code` 一律用 `@/services/apiProxy`，本模块与之对齐。
 */

import { api } from '@/services/apiProxy'
import {
  F0_MATRIX_CATEGORIES,
  F0_BOOK_AMOUNT_SOURCES,
  computeAltTotalsFromCompanies,
  type F0Category,
  type F0Metric,
  type F0AltTotals,
  type F0AltCompanyLike,
} from './f0SummaryAggregation'

// ─── 类型 ─────────────────────────────────────────────────────────────────────

export interface F0MatrixSources {
  bookAmounts: Partial<Record<F0Category, number>>
  altF05Totals: F0AltTotals
  altF06Totals: F0AltTotals
  /** 各数据源的取数状态（供 UI 溯源提示） */
  diagnostics: F0SourceDiagnostics
}

export interface F0SourceDiagnostics {
  /** 成功取到 tb_amount 的品种 */
  bookResolved: F0Category[]
  /** 未取到的品种（含无固定科目的「本期采购」） */
  bookMissing: F0Category[]
  /** F0-5 是否有替代程序数据 */
  altF05Found: boolean
  /** F0-6 是否有替代程序数据 */
  altF06Found: boolean
  /** 取数过程中的错误（不阻断，仅记录） */
  errors: string[]
}

// ─── 单个底稿的 project_context 取数 ─────────────────────────────────────────

/**
 * 按 wp_code 拉某底稿的 render-config，取首个 sheet 的
 * `html_data.project_context.tb_amount`。
 *
 * 🔴 不走 `fetchWorkpaperHtmlRows` —— 那个函数按 `_format` 匹配 sheet，
 * 而 F1/F3/F4 审定表的 `_format` 各不相同且与本需求无关；
 * 这里要的是「任一 sheet 的 project_context」（render 对每个 sheet 都注入同一份）。
 */
async function fetchTbAmountByWpCode(
  projectId: string,
  wpCode: string,
  pick: (htmlData: any) => unknown,
): Promise<number | undefined> {
  // `api.get` 直接返回业务数据（已由 http 拦截器剥掉 {code,message,data} 信封）
  const idRes = await api.get<{ wp_id?: string }>('/api/custom-query/wp-id-by-code', {
    params: { project_id: projectId, wp_code: wpCode },
    _silent: true,
  } as any)
  const wpId = idRes?.wp_id
  if (!wpId) return undefined

  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, {
    _silent: true,
  } as any)
  const sheets = cfg?.sheets ?? []

  // 逐 sheet 试取 —— 键名按品种声明（F1/F3/F4 三者各不相同，见 F0_BOOK_AMOUNT_SOURCES.pick）
  for (const sheet of sheets) {
    const hd = sheet?.html_data ?? sheet?.htmlData
    const amount = Number(pick(hd))
    if (Number.isFinite(amount)) return amount
  }
  return undefined
}

// ─── 替代程序取数（同 working_paper 的其他 sheet） ───────────────────────────

/**
 * 从**当前底稿**（F0）的 render-config 里按 `_format` 取两张替代程序 sheet 的 companies。
 *
 * F0-5/F0-6 与 F0-1 同属一个 working_paper → 用当前 wpId，不必再查 wp-id-by-code。
 *
 * 🔴🔴 **必须一次请求取两张表，不能并行发两次同 URL 请求**
 * （2026-08-03 浏览器实测，症状是 `diagnostics.errors` 出现 `F0-5: canceled`）：
 * `utils/http` 的请求去重键是 `method:url:JSON.stringify(params)`，两次 F0 render-config
 * 的 URL 与 params 完全相同 → 键相同 → 后发者 `addPending` 时 **abort 掉先发的那个**
 * （`pendingMap.get(key)!.abort()`）→ F0-5 永远拿不到数据、替代确认勾稽恒不成立。
 * 同族风险：任何「Promise.all 并行请求同一 URL」的写法都会被这套去重打掉一个。
 */
async function fetchAltCompaniesBoth(
  wpId: string,
): Promise<{ f05: F0AltCompanyLike[] | null; f06: F0AltCompanyLike[] | null }> {
  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, {
    _silent: true,
  } as any)
  const sheets = cfg?.sheets ?? []

  const found: { f05: F0AltCompanyLike[] | null; f06: F0AltCompanyLike[] | null } = {
    f05: null,
    f06: null,
  }
  for (const sheet of sheets) {
    const hd = sheet?.html_data ?? sheet?.htmlData
    if (!Array.isArray(hd?.companies)) continue
    if (hd._format === 'alternative-f05-v1') found.f05 = hd.companies as F0AltCompanyLike[]
    else if (hd._format === 'alternative-f06-v1') found.f06 = hd.companies as F0AltCompanyLike[]
  }
  return found
}

// ─── 主编排 ───────────────────────────────────────────────────────────────────

/**
 * 并行加载矩阵三个数据源。
 *
 * @param projectId 项目 ID（查 F1/F3/F4 用）
 * @param wpId 当前 F0 底稿 ID（查 F0-5/F0-6 用）
 */
export async function loadF0MatrixSources(
  projectId: string | undefined,
  wpId: string | undefined,
): Promise<F0MatrixSources> {
  const diagnostics: F0SourceDiagnostics = {
    bookResolved: [],
    bookMissing: [],
    altF05Found: false,
    altF06Found: false,
    errors: [],
  }
  const bookAmounts: Partial<Record<F0Category, number>> = {}
  let altF05Totals: F0AltTotals = { total: 0 }
  let altF06Totals: F0AltTotals = { total: 0 }

  // ── 账面金额：F1/F3/F4 并行拉取 ──
  if (projectId?.trim()) {
    const bookTasks = F0_MATRIX_CATEGORIES.map(async (category) => {
      const source = F0_BOOK_AMOUNT_SOURCES[category]
      if (!source) {
        // 「本期采购」无固定科目（营业成本需走 D4 取数）→ 如实标 missing
        diagnostics.bookMissing.push(category)
        return
      }
      try {
        const amount = await fetchTbAmountByWpCode(projectId, source.wpCode, source.pick)
        if (amount != null) {
          bookAmounts[category] = amount
          diagnostics.bookResolved.push(category)
        } else {
          diagnostics.bookMissing.push(category)
        }
      } catch (e: any) {
        diagnostics.bookMissing.push(category)
        diagnostics.errors.push(`${category}(${source.wpCode}): ${e?.message || '取数失败'}`)
      }
    })
    await Promise.allSettled(bookTasks)
  } else {
    diagnostics.errors.push('缺少 projectId，无法取账面金额')
    diagnostics.bookMissing.push(...F0_MATRIX_CATEGORIES)
  }

  // ── 替代程序合计：F0-5/F0-6（同一次 render-config 请求取两张表，见函数注释）──
  if (wpId?.trim()) {
    try {
      const { f05, f06 } = await fetchAltCompaniesBoth(wpId)
      if (f05) {
        altF05Totals = computeAltTotalsFromCompanies(f05)
        diagnostics.altF05Found = true
      }
      if (f06) {
        altF06Totals = computeAltTotalsFromCompanies(f06)
        diagnostics.altF06Found = true
      }
    } catch (e: any) {
      diagnostics.errors.push(`F0-5/F0-6: ${e?.message || '取数失败'}`)
    }
  } else {
    diagnostics.errors.push('缺少 wpId，无法取替代程序合计')
  }

  return { bookAmounts, altF05Totals, altF06Totals, diagnostics }
}

// ─── 手工覆盖持久化 ───────────────────────────────────────────────────────────

/**
 * 矩阵手工覆盖的 checklist item_id 构造。
 *
 * design.md 声明的键式：`F0-1-matrix-{品种}-{指标}`
 */
export function matrixOverrideItemId(category: F0Category, metric: F0Metric): string {
  return `F0-1-matrix-${category}-${metric}`
}

/** 从 checklist responses 中解析出全部矩阵手工覆盖值 */
export function parseManualOverrides(
  allResponses: Map<string, any> | Record<string, any> | undefined | null,
): Record<string, number> {
  const result: Record<string, number> = {}
  if (!allResponses) return result

  const readValue = (itemId: string): unknown => {
    if (allResponses instanceof Map) {
      const entry = allResponses.get(itemId)
      return entry?.value ?? entry?.remark ?? entry
    }
    const entry = (allResponses as Record<string, any>)[itemId]
    return entry?.value ?? entry?.remark ?? entry
  }

  for (const category of F0_MATRIX_CATEGORIES) {
    // 只有「本期（期末）账面金额」行可手工覆盖（其余是派生值）
    const metric: F0Metric = '本期（期末）账面金额'
    const itemId = matrixOverrideItemId(category, metric)
    const raw = readValue(itemId)
    const num = Number(raw)
    if (raw != null && raw !== '' && Number.isFinite(num)) {
      result[`${category}::${metric}`] = num
    }
  }
  return result
}
