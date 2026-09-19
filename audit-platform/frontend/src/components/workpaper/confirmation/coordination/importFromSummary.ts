/**
 * importFromSummary — 从各循环 *-1 函证汇总表带入行的共用能力
 *
 * 模式对齐 H0-5 / G0-6：
 *   wp-id-by-code → render-config → 筛 confirmation-v1 rows → 调用方 map/import
 *
 * 不依赖 cycle 专属 unreplied-entities API，D0/F0 可立即接通。
 */
// 🔴 必须用 apiProxy 的 `api`（**直接返回业务数据**），不是 `@/utils/http` 的 axios 实例
//   （**返回 AxiosResponse，payload 在 `.data`**）。`apiProxy.ts` 文件头写明了这个区别。
//   2026-08-03 浏览器实测：本模块原写 `import api from '@/utils/http'` 却按 apiProxy 语义
//   读 `(idRes as any)?.wp_id` → **恒 undefined** → `fetchConfirmationSummaryRows` 恒返 null
//   → 七个循环的「从汇总表带入」全部提示「未找到 X-1 或尚未编制」。
//   （`cfg?.sheets ?? cfg?.data?.sheets` 那个双写 fallback 让 render-config 一侧碰巧能用，
//     正是这种不对称掩盖了错配 —— 与 `f0MatrixDataSources` 同款。）
import { api } from '@/services/apiProxy'
import type { ConfirmationRow } from '../confirmationTypes'
import { isNotReplied, isRepliedTrue } from '../replyStatus'

export type SummaryRow = ConfirmationRow

export interface FetchSummaryResult {
  wpId: string
  rows: SummaryRow[]
}

/**
 * 默认：未回函（含**显式**未回函且非相符）
 *
 * 🔴 判据走 `isNotReplied` 归一谓词，**不写 `r.is_replied === false`**：
 * 完整表格视图（`kind: 'bool'` → el-checkbox）写入布尔 `false`，而明细面板与
 * Excel 导入写入字符串 `'否'` —— 裸 `=== false` 对后者恒不成立
 * ⇒ 改造前「明细面板录入的未回函行」永远进不了 F0-5/F0-6「从 X0-1 带入」
 * （2026-08-05 浏览器实测）。
 *
 * 未填（`undefined`）**不算**未回函 —— 空行不得被带进替代程序底稿（宁缺勿造）。
 */
export function defaultUnrepliedFilter(r: SummaryRow): boolean {
  return r.match_status === '未回函' || (isNotReplied(r) && r.match_status !== '相符')
}

/** 已回函且差异 ≠ 0（供差异调节表） */
export function defaultDiffFilter(r: SummaryRow): boolean {
  // 🔴 走 `isRepliedTrue` 归一谓词而非 `!r.is_replied` —— 字符串 `'否'` 是 truthy，
  // 裸真值判断会把「明确未回函」的行当成已回函放进差异调节表。
  //
  // 🔴 2026-08-07 修：此处原写 `isReplied(r) !== true`，而 import 清单里只有
  // `isNotReplied` / `isRepliedTrue` ⇒ 运行时 `ReferenceError: isReplied is not defined`，
  // 整条「差异行带入 X0-4 调节表」链路崩溃（5 个既有测试同时红）。
  // `get_diagnostics` **查不出漏 import**（平台已记同款教训，Python/TS 各踩过一次）。
  // `isReplied(r) !== true` 与 `!isRepliedTrue(r)` 语义逐字等价（后者定义即 `isReplied(row) === true`），
  // 故改用已导入的谓词，行为不变。
  if (!isRepliedTrue(r) && r.match_status !== '不符') return false
  if (r.match_status === '相符') return false
  const sent = Number(r.amount) || 0
  const reply = Number(r.reply_amount) || 0
  const diff = Math.round((sent - reply) * 100) / 100
  return diff !== 0 || r.match_status === '不符'
}

/** 电子回函（传真/电子邮件）— 供可靠性验证表 */
export function defaultElectronicReplyFilter(r: SummaryRow): boolean {
  const method = String(r.reply_method || '')
  return /传真|电子|email|Email|EMAIL|传真\/邮件|电子邮件/.test(method)
}

/** 按科目大类过滤（可选） */
export function accountTypeFilter(types: string[]): (r: SummaryRow) => boolean {
  const set = new Set(types.map(t => t.trim()).filter(Boolean))
  return (r) => {
    if (!set.size) return true
    const t = String(r.account_type || '').trim()
    return set.has(t)
  }
}

/**
 * 把 sheet 级编码退化为工作簿级编码：`F0-1` → `F0` / `D0-5` → `D0`。
 *
 * 🔴 存在理由（2026-08-03 实测）：**多 sheet 工作簿的 sheet 不是独立 wp_code**。
 * 项目 `2aa00f57` 的 `wp_index` 里 F0 族只有 `F0` 一条，`wp-id-by-code?wp_code=F0-1`
 * 直接 **404「底稿 F0-1 在当前项目不存在」** → 按 sheet 码解析汇总表结构性行不通。
 * （另一些项目如 `c8621493` 确实拆出了 `F0-1`/`F0-2`… 独立记录 → 两种形态并存，
 *  故先试原码、再退工作簿码，两条都覆盖。同族坑见 memory 的 `fetchWorkpaperHtmlRows`。）
 */
export function workbookCodeOf(sheetCode: string): string {
  return String(sheetCode || '').replace(/-\d+[A-Za-z]?$/, '')
}

/** 按 wp_code 解析 wp_id；404/无结果返回 null（不抛，交由调用方走回退） */
async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  if (!wpCode?.trim()) return null
  try {
    const idRes = await api.get<{ wp_id?: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return idRes?.wp_id ?? null
  } catch {
    // 该项目未拆出这一 sheet 级底稿（404）—— 正常形态，回退工作簿码
    return null
  }
}

/**
 * 拉取同项目汇总表 confirmation-v1 全部行
 *
 * 解析顺序：① sheet 级 wp_code（`F0-1`，部分项目确实独立建档）
 *          ② 工作簿级 wp_code（`F0`，多 sheet 工作簿的常态）
 * 两者都拿不到 wp_id 才返回 null（由调用方提示「未找到 / 尚未编制」）。
 *
 * @throws 网络错误；未找到底稿时返回 null
 */
export async function fetchConfirmationSummaryRows(
  projectId: string,
  summaryWpCode: string,
): Promise<FetchSummaryResult | null> {
  if (!projectId?.trim() || !summaryWpCode?.trim()) return null

  let wpId = await resolveWpId(projectId, summaryWpCode)
  if (!wpId) {
    const fallback = workbookCodeOf(summaryWpCode)
    if (fallback && fallback !== summaryWpCode) {
      wpId = await resolveWpId(projectId, fallback)
    }
  }
  if (!wpId) return null

  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, { _silent: true } as any)
  const sheets = cfg?.sheets ?? []
  let rows: SummaryRow[] = []
  for (const sheet of sheets) {
    const hd = sheet?.html_data ?? sheet?.htmlData
    if (hd?._format === 'confirmation-v1' && Array.isArray(hd.rows)) {
      rows = hd.rows
      break
    }
  }
  return { wpId, rows }
}

export async function filterSummaryRows(
  projectId: string,
  summaryWpCode: string,
  filterFn: (r: SummaryRow) => boolean = defaultUnrepliedFilter,
): Promise<{ wpId: string; rows: SummaryRow[] } | null> {
  const result = await fetchConfirmationSummaryRows(projectId, summaryWpCode)
  if (!result) return null
  return { wpId: result.wpId, rows: result.rows.filter(filterFn) }
}

// ─── 辅助余额表（tb_aux_balance）精确余额匹配 ────────────────────────────────
//
// 立项依据（f0-confirmation-linkage-and-structural-enhancement R2.3 / Task 25）：
// 汇总表的 `amount` 是**发函金额**（审计师抽样时填的口径），而替代程序底稿的
// 「期末余额」应为该往来单位的**账面余额**。二者常有差异（发函可能只函部分金额）。
// 辅助余额表按往来单位维度存有精确账面余额 → 命中时优先使用。
//
// 🔴 本能力原写在 `f0AltSupplierSeed.ts`（零消费方），Task 25 并入此处使
//    D0/F0/G0/H0/K0/L0 六个循环的「从汇总表带入」全部受益。

/** 辅助余额表行（只取本模块需要的字段） */
export interface AuxBalanceRow {
  /** 往来单位名称 */
  auxName: string
  /** 科目码 */
  accountCode: string
  /** 期末余额 */
  closingBalance: number
}

/**
 * 往来单位维度优先关键词 —— 与后端 `four_table/aux_aggregation.AUX_TYPE_PREFERRED_KEYWORDS`
 * **逐字同源**（改一侧必须同步另一侧，守卫已交叉锁死）。
 */
export const AUX_TYPE_PREFERRED_KEYWORDS = ['客户', '供应商', '往来', '单位', '个人', '职员', '员工'] as const

/**
 * 从 `(auxType, 行数, 余额绝对值合计)` 候选中挑唯一归集维度。
 *
 * 🔴 优先级 **关键词 > 余额 > 行数**，与后端 `pick_aux_type` 逐条同源。
 * 原实现只按「行数最多」——实测该项目「客户」265 行 / 「成本中心」249 行，
 * 行数规则**碰巧**选对了客户；一旦成本中心行数更多，替代程序的期末余额就会
 * 静默按成本中心维度校准（金额不对但界面无任何提示）。
 */
export function pickAuxType(
  candidates: readonly { auxType: string; rowCount: number; absAmount: number }[],
): string | null {
  if (!candidates.length) return null
  const preferred = candidates.filter(c =>
    AUX_TYPE_PREFERRED_KEYWORDS.some(kw => c.auxType.includes(kw)),
  )
  const pool = [...(preferred.length ? preferred : candidates)]
  pool.sort((a, b) =>
    Math.abs(b.absAmount) - Math.abs(a.absAmount)
    || b.rowCount - a.rowCount
    || (a.auxType < b.auxType ? 1 : a.auxType > b.auxType ? -1 : 0),
  )
  return pool[0].auxType
}

/**
 * 从辅助余额表匹配某往来单位的精确期末余额。
 *
 * 匹配优先级：①精确相等 ②双向包含（两侧长度均 ≥4，防短名误命中）
 * 未命中返回 undefined（调用方回退汇总表 amount）。
 *
 * 🔴 **同一单位跨子科目 + 跨维度组合要全部求和，不能只取第一条**（2026-08-04 实测）：
 * 端点改前缀匹配后，一个单位可能在多个子科目各有余额（实测 2202 有单位横跨
 * `2202.01/.02/.03/.97/.98` **5 个子科目**，且只有 `.98` 带金额），
 * 替代程序的「期末余额」应为全部之和；原实现用 `.find()` 只拿第一条 → 少算。
 *
 * 🔴 **不得在前端按 `(accountCode, auxName)` 去重**（曾一度这么写，实测证伪）：
 * 同一 `(科目码, 单位名)` 的多行**不是重复行**，而是**不同辅助维度组合**——
 * 实测 `2202.02` 某客户在 active dataset 内有 4 行，`aux_dimensions_raw` 分别是
 * `客户+成本中心:采购部` / `客户+成本中心:渝北总店` / `客户+成本中心:长寿美丽泽京店`
 * / `客户+成本中心+集团内外`，金额 `2,601,247.80 / 268,355.69 / 0 / 0`，
 * 合计 2,869,603.49。按 `科目码|单位名` 去重会只留一条 → **丢钱**。
 *
 * 数据集版本冗余（同一行存在 `dataset_id` 为 NULL 与 active 两份）**已由后端
 * `get_active_filter` 处理**（实测该单位 8 行 → 4 行、`1123` 364 行 → 182 行），
 * 前端再去重是重复且有害的。
 *
 * @param accountPrefix 可选科目码前缀限定（如 '1123' 预付 / '2202' 应付）
 */
export function matchAuxBalance(
  entityName: string,
  auxRows: readonly AuxBalanceRow[],
  accountPrefix?: string,
): number | undefined {
  if (!entityName || !auxRows?.length) return undefined

  const name = entityName.trim()
  if (name.length < 2) return undefined

  const scoped = accountPrefix
    ? auxRows.filter(r => String(r.accountCode || '').startsWith(accountPrefix))
    : auxRows

  /**
   * 跨子科目 / 跨维度组合求和 —— **不去重**。
   * 数据集版本冗余已由后端 `get_active_filter` 消除；这里每一行都是一个独立的
   * 辅助维度组合，去重会丢钱（见上方 docstring 的实测数据）。
   */
  const sumAll = (rows: readonly AuxBalanceRow[]): number => {
    let total = 0
    for (const r of rows) total += Number(r.closingBalance) || 0
    return Math.round(total * 100) / 100
  }

  // ① 精确匹配（全部同名行求和）
  const exact = scoped.filter(r => String(r.auxName || '').trim() === name)
  if (exact.length) return sumAll(exact)

  // ② 双向包含（最短长度 ≥4，宁漏勿误）
  //    🔴 只认**唯一**的 aux 单位名 —— 包含匹配可能命中多个不同单位
  //    （如「重庆和平药房连锁有限责任公司」会同时包含总公司与其多家分公司），
  //    把它们的余额加在一起就是把别人的钱算进本单位。多义时返回 undefined
  //    回退汇总表发函金额（宁缺勿造）。
  if (name.length >= 4) {
    const hits = scoped.filter(r => {
      const aux = String(r.auxName || '').trim()
      return aux.length >= 4 && (aux.includes(name) || name.includes(aux))
    })
    const distinctNames = new Set(hits.map(r => String(r.auxName || '').trim()))
    if (distinctNames.size === 1) return sumAll(hits)
  }

  return undefined
}

/**
 * 拉取某科目的辅助余额（往来单位维度）。
 *
 * 复用平台既有端点（G8/G9/G10 同款）：
 *   `GET /api/projects/{projectId}/ledger/aux-balance/{accountCode}?year=`
 *
 * 多维度并存时按 `pickAuxType` 锁定单一维度（**先关键词、再余额、再行数**，与后端
 * `four_table/aux_aggregation.pick_aux_type` 同源）。
 * 失败一律返回 `[]`（fail-open，不阻断带入主流程）。
 *
 * 🔴 `api`（`@/services/apiProxy`）**直接返回业务数据**，不是 AxiosResponse ——
 * 本函数原写 `const { data } = await api.get(...)`，而该端点返回的是**数组**，
 * 数组没有 `data` 属性 → `data === undefined` → `raw = []` → 恒返回 `[]`。
 * 浏览器实测（2026-08-04）：同一 URL `api.get` 返回 182 元素数组，而解构出的
 * `data` 是 `undefined` → F0-5/F0-6 的 aux 精确余额路径静默失效、期末余额回退
 * 汇总表发函金额。这与 Task 20.1 抓到的「http 与 apiProxy 形态错配」同族。
 * 判据：用 `api` 就直接拿返回值；用 `http`（`@/utils/http`）才需要 `.data`。
 */
export async function fetchAuxBalances(
  projectId: string,
  accountCode: string,
  year?: number,
): Promise<AuxBalanceRow[]> {
  if (!projectId?.trim() || !accountCode?.trim()) return []
  try {
    const { resolveAuditYearNumber } = await import('../../composables/workpaperAuditYear')
    const y = year
      ?? resolveAuditYearNumber(undefined, new Date().getFullYear() - 1)
      ?? (new Date().getFullYear() - 1)

    // 🔴 `api.get` 返回业务数据本体（此处为数组），禁写 `const { data } = ...`
    const payload = await api.get<any>(
      `/api/projects/${projectId}/ledger/aux-balance/${accountCode}`,
      { params: { year: y }, _silent: true } as any,
    )
    const raw: any[] = Array.isArray(payload)
      ? payload
      : ((payload as any)?.data ?? (payload as any)?.items ?? (payload as any)?.rows ?? [])
    if (!raw.length) return []

    // 先按 aux_type 分组，再用 pickAuxType 锁定**单一**维度
    // （辅助维度冗余存储，禁平铺全求和；选维度规则与后端 pick_aux_type 同源）
    const byType = new Map<string, any[]>()
    for (const r of raw) {
      const t = String(r.aux_type ?? r.auxType ?? r.dim_type ?? '未分类').trim() || '未分类'
      if (!byType.has(t)) byType.set(t, [])
      byType.get(t)!.push(r)
    }
    const chosen = pickAuxType(
      [...byType.entries()].map(([auxType, rows]) => ({
        auxType,
        rowCount: rows.length,
        absAmount: rows.reduce(
          (s, r) => s + Math.abs(Number(r.closing_balance ?? r.closingBalance ?? 0) || 0),
          0,
        ),
      })),
    )
    const best: any[] = chosen ? (byType.get(chosen) ?? []) : []

    return best.map(r => ({
      auxName: String(r.aux_name ?? r.auxName ?? '').trim(),
      accountCode: String(r.account_code ?? r.accountCode ?? accountCode).trim(),
      closingBalance: Number(r.closing_balance ?? r.closingBalance ?? 0) || 0,
    })).filter(r => r.auxName)
  } catch {
    return []
  }
}

/**
 * 映射为替代程序公司行的通用字段。
 *
 * @param auxRows 可选辅助余额行；命中该单位时 `closing_balance` 用 aux 精确值，
 *                否则回退汇总表 `amount`（发函金额）
 * @param accountPrefix 可选科目码前缀（限定 aux 匹配范围）
 */
export function mapSummaryToAlternativeCompany(
  r: SummaryRow,
  defaultItemName = '',
  auxRows?: readonly AuxBalanceRow[],
  accountPrefix?: string,
): {
  entity_name: string
  confirm_index?: string
  _source: 'auto'
  balance: { item_name: string; closing_balance: number }
  /** 余额取数来源（供 UI 溯源；aux = 辅助余额精确值 / summary = 汇总表发函金额） */
  _balance_source: 'aux' | 'summary'
} {
  const entityName = r.entity_name || ''
  const auxAmount = auxRows?.length
    ? matchAuxBalance(entityName, auxRows, accountPrefix)
    : undefined

  return {
    entity_name: entityName,
    confirm_index: r.confirm_index,
    _source: 'auto',
    balance: {
      item_name: r.account_type || defaultItemName,
      closing_balance: auxAmount ?? (Number(r.amount) || 0),
    },
    _balance_source: auxAmount != null ? 'aux' : 'summary',
  }
}

/**
 * 一键：取未回函并 map 为替代公司载荷
 * @returns null = 找不到汇总底稿；空数组 = 无未回函
 */
export async function importUnrepliedAsCompanies(
  projectId: string,
  summaryWpCode: string,
  options?: {
    accountTypes?: string[]
    defaultItemName?: string
    extraFilter?: (r: SummaryRow) => boolean
    /**
     * 可选：从辅助余额表取该科目的精确账面余额覆盖汇总表发函金额（R2.3）。
     * 传科目码（如 F0-5 预付账款 '1123'）即启用；取数失败 fail-open 回退发函金额。
     */
    auxAccountCode?: string
    /** 审计年度（aux 取数用；缺省由 `resolveAuditYearNumber` 推断） */
    auxYear?: number
  },
): Promise<{
  ok: true
  companies: ReturnType<typeof mapSummaryToAlternativeCompany>[]
  emptyReason?: string
  /** 有多少家用了 aux 精确余额（供 UI 提示「N 家已按辅助余额校准」） */
  auxMatchedCount?: number
}
  | { ok: false; reason: 'missing-project' | 'missing-summary' | 'error'; message: string }
> {
  if (!projectId?.trim()) {
    return { ok: false, reason: 'missing-project', message: '缺少项目上下文' }
  }
  try {
    const filters: Array<(r: SummaryRow) => boolean> = [defaultUnrepliedFilter]
    if (options?.accountTypes?.length) filters.push(accountTypeFilter(options.accountTypes))
    if (options?.extraFilter) filters.push(options.extraFilter)

    const result = await fetchConfirmationSummaryRows(projectId, summaryWpCode)
    if (!result) {
      return { ok: false, reason: 'missing-summary', message: `未找到 ${summaryWpCode} 函证结果汇总底稿` }
    }
    if (result.rows.length === 0) {
      return { ok: true, companies: [], emptyReason: `${summaryWpCode} 暂无函证数据` }
    }
    const matched = result.rows.filter(r => filters.every(f => f(r)))
    if (matched.length === 0) {
      return { ok: true, companies: [], emptyReason: `${summaryWpCode} 暂无符合条件的未回函项目` }
    }

    // 可选 aux 精确余额（fail-open：取不到就是空数组，回退发函金额）
    const auxRows = options?.auxAccountCode
      ? await fetchAuxBalances(projectId, options.auxAccountCode, options.auxYear)
      : []

    const companies = matched.map(r => mapSummaryToAlternativeCompany(
      r,
      options?.defaultItemName || '',
      auxRows,
      options?.auxAccountCode,
    ))
    const auxMatchedCount = companies.filter(c => c._balance_source === 'aux').length

    return {
      ok: true,
      companies,
      ...(auxMatchedCount > 0 ? { auxMatchedCount } : {}),
    }
  } catch (e: any) {
    if (e?.response?.status === 404) {
      return { ok: false, reason: 'missing-summary', message: `未找到 ${summaryWpCode} 函证结果汇总底稿` }
    }
    return { ok: false, reason: 'error', message: e?.message || '带入失败' }
  }
}

/**
 * 拉取同项目任意 confirmation htmlData（按 _format）
 * rows：优先 hd.rows，其次 hd.companies
 */
export async function fetchWorkpaperHtmlRows(
  projectId: string,
  wpCode: string,
  format: string,
  /** 可选：指定 sheet_name 定位（多 sheet 工作簿子 sheet 用） */
  sheetName?: string,
): Promise<{ wpId: string; rows: any[]; htmlData: any } | null> {
  if (!projectId?.trim() || !wpCode?.trim()) return null

  // 第一步：按 wpCode 查 wp_id
  let wpId: string | undefined
  const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
    params: { project_id: projectId, wp_code: wpCode },
    _silent: true,
  } as any)
  wpId = (idRes as any)?.wp_id as string | undefined

  // 回退：多 sheet 工作簿的子 sheet 不是独立 wp_code（如 E0-3 → 先查 E0）
  if (!wpId && wpCode.includes('-')) {
    const parentCode = wpCode.split('-')[0]
    const parentRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: parentCode },
      _silent: true,
    } as any)
    wpId = (parentRes as any)?.wp_id as string | undefined
  }
  if (!wpId) return null

  const cfg = await api.get<any>(`/api/workpapers/${wpId}/render-config`, { _silent: true } as any)
  const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []

  // 匹配策略：优先按 _format；若指定 sheetName 则同时按 sheet_name 定位
  for (const sheet of sheets) {
    const hd = sheet?.html_data ?? sheet?.htmlData
    if (!hd) continue

    // 策略 1：按 _format 匹配（专属组件载荷）
    if (hd._format === format) {
      const rows = Array.isArray(hd.rows)
        ? hd.rows
        : Array.isArray(hd.companies)
          ? hd.companies
          : []
      return { wpId, rows, htmlData: hd }
    }

    // 策略 2：按 sheet_name 匹配 + 从 grid 载荷提取行（d-form-table 兜底路径）
    if (sheetName && format === 'd-form-table') {
      const sn = sheet?.sheet_name ?? sheet?.name ?? ''
      if (sn === sheetName && hd.cells) {
        // grid 载荷：从 cells 矩阵提取行（跳过表头）
        const headerRows = hd.header_rows ?? 1
        const cells: any[][] = hd.cells ?? []

        // 列头防御：找第一行「非空值 ≥ 3」的作为真实表头
        // （strip_standard_header 可能未完全裁掉编制信息行）
        let headerIdx = headerRows - 1
        for (let probe = headerIdx; probe < Math.min(cells.length, headerIdx + 4); probe++) {
          const nonEmpty = (cells[probe] ?? []).filter((c: any) => c != null && c !== '').length
          if (nonEmpty >= 3) {
            headerIdx = probe
            break
          }
        }

        const headers = cells[headerIdx] ?? []
        const rows: any[] = []
        for (let i = headerIdx + 1; i < cells.length; i++) {
          const row = cells[i]
          if (!row || row.every((c: any) => c == null || c === '')) continue
          const obj: any = {}
          for (let j = 0; j < headers.length; j++) {
            if (headers[j]) obj[String(headers[j]).trim()] = row[j]
          }
          rows.push(obj)
        }
        if (rows.length > 0) {
          return { wpId, rows, htmlData: hd }
        }
      }
    }
  }
  return { wpId, rows: [], htmlData: null }
}

/** 从差异调节表（diff-reconcile-v1）取差异≠0 行 */
export async function fetchDiffReconcileNonZeroRows(
  projectId: string,
  diffWpCode: string,
): Promise<{ wpId: string; rows: any[] } | null> {
  const result = await fetchWorkpaperHtmlRows(projectId, diffWpCode, 'diff-reconcile-v1')
  if (!result) return null
  const rows = result.rows.filter((r) => {
    const diff = Number(r.difference)
    if (Number.isFinite(diff) && diff !== 0) return true
    const sent = Number(r.sent_amount) || 0
    const reply = Number(r.reply_amount) || 0
    return Math.round((sent - reply) * 100) / 100 !== 0
  })
  return { wpId: result.wpId, rows }
}
