/**
 * useD4Disclosure.ts — D4 营业收入附注披露 composable
 *
 * 双版本(listed/soe)共用逻辑：
 * - Section 1: 营业收入和营业成本（跨sheet取数 D4-1审定/D4-2明细/M循环成本）
 * - Section 2: 合同收入分解（按商品类型/服务类型/地区/时段，动态行）
 * - Section 3: 前五大客户收入（动态行+自动占比）
 * - Section 4(listed): 合同资产/负债变动说明
 * - Section 5(soe): 分产品/分地区收入
 *
 * 持久化：checklist_responses batch API，item_id前缀 D4-disc-{variant}-
 * 跨sheet读取：从allResponses map读D4-1/D4-2审定数
 * EventBus: disclosure:note-text-updated 双向同步附注模块
 */
import { ref, computed, watch, onBeforeUnmount, onMounted, inject, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type DisclosureVariant = 'listed' | 'soe'

export interface RevenueRow {
  rowId: string
  category: string
  currentRevenue: number
  priorRevenue: number
  currentCost: number
  priorCost: number
}

export interface ContractRevenueRow {
  rowId: string
  category: string
  currentAmount: number
  priorAmount: number
}

export interface Top5CustomerRow {
  rowId: string
  rank: number
  name: string
  amount: number
  proportion: number
  isRelatedParty: boolean
}

export interface ProductRegionRow {
  rowId: string
  dimension: string
  type: '产品' | '地区' | '时段'
  currentAmount: number
  priorAmount: number
}

export interface ContractBalanceRow {
  rowId: string
  item: string
  endBalance: number
  beginBalance: number
  changeAmount: number
  reason: string
}

export interface UseD4DisclosureOptions {
  allResponses: Ref<Map<string, any>>
  wpId: Ref<string>
  projectId: Ref<string>
  variant: DisclosureVariant
  saveBatch: (items: Array<{ item_id: string; conclusion: string | null; remark: string }>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const DISCLOSURE_GUIDANCE: Record<string, string[]> = {
  section1: [
    '处置投资性房地产（无论采用公允价值模式计量还是成本模式计量）的收入，在"其他业务收入"列示，相应结转成本至"其他业务成本"。',
    '单项的投资性房地产的处置，无论是直接出售还是先划分为持有待售资产再出售，处置损益均计入"其他业务收入/成本"，不计入"资产处置损益"。',
    '在停工停产期间继续计提固定资产折旧和无形资产摊销，并根据用途计入相关资产的成本或当期损益。例如，企业因需求不足而停产或因事故而停工检修等，相关生产设备应当继续计提折旧，并计入营业成本。',
    '披露本公司前期已经履行(或部分履行)的履约义务在本期调整的收入金额及原因。',
  ],
  section2: [
    '按主要产品类型或行业划分收入和成本，应与企业内部管理报告的分类保持一致。',
    '示例类别：消费品/汽车/能源/建筑服务等。',
  ],
  section3: [
    '按主要经营地区划分收入和成本，不适用的可删除此节。',
    '示例地区：东北/华北/西北/华东/华南等。',
  ],
  section4: [
    '在确定对收入进行分解的类别时，企业应当考虑：①财务报表之外披露的收入信息；②管理层为评价经营分部财务业绩所定期复核的信息；③企业或使用者用于评价财务业绩或作出资源分配决策的信息。',
    '可采用的分解类别包括但不限于：商品类型、经营地区、市场或客户类型、合同类型（固定造价/成本加成）、商品转让时间（时点/时段）、合同期限（长期/短期）、销售渠道（直销/经销商）等。',
    '租赁收入需单独披露。',
    '需区分"在某一时点确认"和"在某一时段确认"的收入。',
  ],
  section5: [
    '披露与履约义务相关的信息，包括：履行时间、重要的支付条款、企业承诺转让的商品的性质（包括说明企业是否作为代理人）、预期将退还给客户的款项等类似义务、质量保证的类型及相关义务等。',
  ],
  section6: [
    '披露分摊至本期末尚未履行(或部分未履行)履约义务的交易价格总额。',
    '披露上述金额确认为收入的预计时间（可采用定量的时间段或定性说明）。',
    '说明是否存在任何对价金额未纳入交易价格（如因可变对价限制要求而未计入的部分）。',
    '简化操作方法适用条件：一是原预计合同期限不超过一年；二是企业有权发出账单且账单金额能代表已履约部分价值。采用简化方法的应提供定性说明。',
  ],
  section7: [
    '披露重大合同变更或重大交易价格调整相关的信息、会计处理方法及对收入的影响金额。',
  ],
  section8: [
    '试运行销售收入（上市公司适用）：披露试运行期间的销售收入及相关会计处理。',
  ],
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genRowId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseArray<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch { return [] }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4Disclosure(options: UseD4DisclosureOptions) {
  const { allResponses, wpId, projectId, variant, saveBatch, isReadonly } = options
  const prefix = `D4-disc-${variant}-`
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // 审计年度（由主入口 provide('d4AuditYear')），回退"当前年-1"
  const injectedAuditYear = inject<Ref<number> | null>('d4AuditYear', null)
  function resolveAuditYear(): number {
    const y = injectedAuditYear?.value
    return y && y > 0 ? y : new Date().getFullYear() - 1
  }

  // ─── Persistence helpers ─────────────────────────────────────────────
  function getResp(key: string): string | null {
    const resp = allResponses.value.get(prefix + key)
    return resp?.remark ?? null
  }

  function persist(key: string, value: string): void {
    if (isReadonly.value) return
    const itemId = prefix + key
    const item = { item_id: itemId, conclusion: null, remark: value }
    allResponses.value.set(itemId, item)
    saveBatch([item])
  }

  // ─── Key constants (hoisted for use in refreshFromTb) ──────────────────
  const SECTION2_KEY = 'section2-rows'
  const SECTION3_KEY = 'section3-rows'
  const SECTION4_KEY = 'section4-rows'

  // ─── Cross-Sheet Data: 一键刷新从TB取数 ───────────────────────────────
  const isRefreshing = ref(false)
  const lastRefreshTime = ref<string>('')

  // TB审定数缓存(存checklist_responses持久化)
  const TB_CACHE_KEY = 'tb-balances'
  const tbBalances = ref<{
    revenue_6001: number
    revenue_6051: number
    cost_6401: number
    cost_6402: number
    prior_revenue_6001: number
    prior_revenue_6051: number
    prior_cost_6401: number
    prior_cost_6402: number
  }>({
    revenue_6001: 0, revenue_6051: 0, cost_6401: 0, cost_6402: 0,
    prior_revenue_6001: 0, prior_revenue_6051: 0, prior_cost_6401: 0, prior_cost_6402: 0,
  })

  // 从allResponses加载缓存的TB数据
  function loadTbCache() {
    const cached = getResp(TB_CACHE_KEY)
    if (cached) {
      try {
        const parsed = JSON.parse(cached)
        tbBalances.value = { ...tbBalances.value, ...parsed }
        lastRefreshTime.value = parsed._refreshTime || ''
      } catch { /* silent */ }
    }
  }
  watch(() => allResponses.value.get(prefix + TB_CACHE_KEY)?.remark, loadTbCache, { immediate: true })

  // 首次加载：如果没有缓存数据则自动刷新
  onMounted(() => {
    if (!lastRefreshTime.value) {
      refreshFromTb()
    }
  })

  // 一键刷新：调后端auto-data端点从TB取最新审定数
  async function refreshFromTb(): Promise<void> {
    if (isRefreshing.value) return
    isRefreshing.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const projectYear = resolveAuditYear()

      // 1. 从TB取收入/成本审定数
      const res = await http.get(`/api/projects/${projectId.value}/auto-data/d4_analysis_indicators`, {
        params: { year: projectYear },
        _silent: true,
      } as any)
      const data = res.data?.data ?? res.data
      if (data?.balances) {
        tbBalances.value.revenue_6001 = parseNum(data.balances.revenue_6001)
        tbBalances.value.revenue_6051 = parseNum(data.balances.revenue_6051)
        tbBalances.value.cost_6401 = parseNum(data.balances.cost_6401)
        tbBalances.value.cost_6402 = parseNum(data.balances.cost_6402)
      }
      // 上期
      const priorRes = await http.get(`/api/projects/${projectId.value}/auto-data/d4_analysis_indicators`, {
        params: { year: projectYear - 1 },
        _silent: true,
      } as any)
      const priorData = priorRes.data?.data ?? priorRes.data
      if (priorData?.balances) {
        tbBalances.value.prior_revenue_6001 = parseNum(priorData.balances.revenue_6001)
        tbBalances.value.prior_revenue_6051 = parseNum(priorData.balances.revenue_6051)
        tbBalances.value.prior_cost_6401 = parseNum(priorData.balances.cost_6401)
        tbBalances.value.prior_cost_6402 = parseNum(priorData.balances.cost_6402)
      }

      // 2. 从D4-2明细表按产品汇总 → 填充Section 2(按产品类型)
      const d4_2_resp = allResponses.value.get('D4-2-rows')
      if (d4_2_resp?.remark && section2Rows.value.length === 0) {
        try {
          const rows = JSON.parse(d4_2_resp.remark)
          if (Array.isArray(rows) && rows.length > 0) {
            const productRows = rows.map((r: any) => ({
              rowId: `s2-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
              category: r.productName || r.name || '',
              currentAmount: (() => {
                const months = Array.isArray(r.months) ? r.months.map(parseNum) : []
                return months.reduce((s: number, v: number) => s + v, 0) + parseNum(r.auditAdjustment)
              })(),
              priorAmount: parseNum(r.priorAudited),
            })).filter((r: any) => r.category)
            if (productRows.length > 0) {
              section2Rows.value = productRows
              persist(SECTION2_KEY, JSON.stringify(productRows))
            }
          }
        } catch { /* silent */ }
      }

      // 3. 从D4-3其他收入 → 追加到Section 2
      const d4_3_resp = allResponses.value.get('D4-3-rows')
      if (d4_3_resp?.remark) {
        try {
          const rows = JSON.parse(d4_3_resp.remark)
          if (Array.isArray(rows) && rows.length > 0) {
            const existingCategories = new Set(section2Rows.value.map(r => r.category))
            const otherRows = rows.filter((r: any) => {
              const name = r.name || r.productName || ''
              return name && !existingCategories.has(name)
            }).map((r: any) => ({
              rowId: `s2-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
              category: r.name || r.productName || '其他业务',
              currentAmount: parseNum(r.currentUnadjusted) + parseNum(r.currentAdjustment),
              priorAmount: parseNum(r.priorAudited),
            }))
            if (otherRows.length > 0) {
              section2Rows.value = [...section2Rows.value, ...otherRows]
              persist(SECTION2_KEY, JSON.stringify(section2Rows.value))
            }
          }
        } catch { /* silent */ }
      }

      // 持久化TB缓存
      lastRefreshTime.value = new Date().toISOString()
      persist(TB_CACHE_KEY, JSON.stringify({ ...tbBalances.value, _refreshTime: lastRefreshTime.value }))
    } catch { /* silent - TB可能还没数据 */ }
    finally { isRefreshing.value = false }
  }

  // ─── Section 1 computed: 收入/成本全从TB审定数取 ──────────────────────
  // 数据源优先级：TB缓存 > 0(待刷新)
  // 公式：主营收入=TB.6001审定数, 其他收入=TB.6051审定数
  //       主营成本=TB.6401审定数, 其他成本=TB.6402审定数
  //       毛利=收入-成本（自动计算）
  const crossSheetRevenue = computed(() => ({
    mainRevenue: tbBalances.value.revenue_6001,
    priorMainRevenue: tbBalances.value.prior_revenue_6001,
    otherRevenue: tbBalances.value.revenue_6051,
    priorOtherRevenue: tbBalances.value.prior_revenue_6051,
    totalRevenue: tbBalances.value.revenue_6001 + tbBalances.value.revenue_6051,
    priorTotalRevenue: tbBalances.value.prior_revenue_6001 + tbBalances.value.prior_revenue_6051,
  }))

  // 成本直接从TB缓存取(科目6401主营成本+6402其他成本)
  const crossSheetCost = computed(() => ({
    mainCost: tbBalances.value.cost_6401,
    otherCost: tbBalances.value.cost_6402,
    priorMainCost: tbBalances.value.prior_cost_6401,
    priorOtherCost: tbBalances.value.prior_cost_6402,
  }))

  // ─── Section 1: 营业收入和营业成本 ───────────────────────────────────
  // 公式链：
  //   主营收入 = TB.6001.audited_amount
  //   其他收入 = TB.6051.audited_amount
  //   主营成本 = TB.6401.audited_amount
  //   其他成本 = TB.6402.audited_amount
  //   毛利 = 收入 - 成本 (自动计算,不可编辑)
  //   毛利率 = 毛利 / 收入 × 100%
  const section1Data = computed<RevenueRow[]>(() => [
    {
      rowId: 's1-main',
      category: '主营业务',
      currentRevenue: crossSheetRevenue.value.mainRevenue,
      priorRevenue: crossSheetRevenue.value.priorMainRevenue,
      currentCost: crossSheetCost.value.mainCost,
      priorCost: crossSheetCost.value.priorMainCost,
    },
    {
      rowId: 's1-other',
      category: '其他业务',
      currentRevenue: crossSheetRevenue.value.otherRevenue,
      priorRevenue: crossSheetRevenue.value.priorOtherRevenue,
      currentCost: crossSheetCost.value.otherCost,
      priorCost: crossSheetCost.value.priorOtherCost,
    },
  ])

  const section1Total = computed<RevenueRow>(() => ({
    rowId: '__total__',
    category: '合计',
    currentRevenue: crossSheetRevenue.value.totalRevenue,
    priorRevenue: crossSheetRevenue.value.priorTotalRevenue,
    currentCost: crossSheetCost.value.mainCost + crossSheetCost.value.otherCost,
    priorCost: crossSheetCost.value.priorMainCost + crossSheetCost.value.priorOtherCost,
  }))

  // 毛利率(自动计算)
  const grossMarginRate = computed(() => {
    const rev = crossSheetRevenue.value.totalRevenue
    const cost = crossSheetCost.value.mainCost + crossSheetCost.value.otherCost
    return rev > 0 ? ((rev - cost) / rev * 100) : 0
  })

  const priorGrossMarginRate = computed(() => {
    const rev = crossSheetRevenue.value.priorTotalRevenue
    const cost = crossSheetCost.value.priorMainCost + crossSheetCost.value.priorOtherCost
    return rev > 0 ? ((rev - cost) / rev * 100) : 0
  })

  // ─── Section 2: 合同收入分解（动态行） ────────────────────────────────
  const section2Rows = ref<ContractRevenueRow[]>([])

  function loadSection2() {
    const rows = safeParseArray<ContractRevenueRow>(getResp(SECTION2_KEY))
    section2Rows.value = rows.map(r => ({
      rowId: r.rowId || genRowId('s2'),
      category: r.category || '',
      currentAmount: parseNum(r.currentAmount),
      priorAmount: parseNum(r.priorAmount),
    }))
  }

  watch(() => allResponses.value.get(prefix + SECTION2_KEY)?.remark, loadSection2, { immediate: true })

  const section2Total = computed(() => ({
    currentAmount: calcSubtotal(section2Rows.value.map(r => r.currentAmount)),
    priorAmount: calcSubtotal(section2Rows.value.map(r => r.priorAmount)),
  }))

  function addSection2Row(): void {
    if (isReadonly.value) return
    section2Rows.value.push({ rowId: genRowId('s2'), category: '', currentAmount: 0, priorAmount: 0 })
    persist(SECTION2_KEY, JSON.stringify(section2Rows.value))
  }

  function removeSection2Row(rowId: string): void {
    if (isReadonly.value) return
    section2Rows.value = section2Rows.value.filter(r => r.rowId !== rowId)
    persist(SECTION2_KEY, JSON.stringify(section2Rows.value))
  }

  function updateSection2(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = section2Rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    ;(section2Rows.value[idx] as any)[field] = field === 'category' ? value : parseNum(value)
    persist(SECTION2_KEY, JSON.stringify(section2Rows.value))
  }

  // ─── Section 3: 前五大客户收入（动态行） ──────────────────────────────
  const section3Rows = ref<Top5CustomerRow[]>([])

  function loadSection3() {
    const rows = safeParseArray<Top5CustomerRow>(getResp(SECTION3_KEY))
    section3Rows.value = rows.map((r, i) => ({
      rowId: r.rowId || genRowId('s3'),
      rank: i + 1,
      name: r.name || '',
      amount: parseNum(r.amount),
      proportion: parseNum(r.proportion),
      isRelatedParty: !!r.isRelatedParty,
    }))
  }

  watch(() => allResponses.value.get(prefix + SECTION3_KEY)?.remark, loadSection3, { immediate: true })

  const section3Total = computed(() => {
    const totalAmt = calcSubtotal(section3Rows.value.map(r => r.amount))
    const totalRevenue = crossSheetRevenue.value.totalRevenue
    return {
      amount: totalAmt,
      proportion: totalRevenue > 0 ? (totalAmt / totalRevenue * 100) : 0,
    }
  })

  function addSection3Row(): void {
    if (isReadonly.value) return
    section3Rows.value.push({
      rowId: genRowId('s3'),
      rank: section3Rows.value.length + 1,
      name: '',
      amount: 0,
      proportion: 0,
      isRelatedParty: false,
    })
    persist(SECTION3_KEY, JSON.stringify(section3Rows.value))
  }

  function removeSection3Row(rowId: string): void {
    if (isReadonly.value) return
    section3Rows.value = section3Rows.value.filter(r => r.rowId !== rowId)
    // 重排rank
    section3Rows.value.forEach((r, i) => { r.rank = i + 1 })
    persist(SECTION3_KEY, JSON.stringify(section3Rows.value))
  }

  function updateSection3(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = section3Rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    if (field === 'isRelatedParty') {
      section3Rows.value[idx].isRelatedParty = !!value
    } else if (field === 'name') {
      section3Rows.value[idx].name = value
    } else {
      section3Rows.value[idx].amount = parseNum(value)
      // 重算占比
      const totalRevenue = crossSheetRevenue.value.totalRevenue
      section3Rows.value[idx].proportion = totalRevenue > 0
        ? (parseNum(value) / totalRevenue * 100) : 0
    }
    persist(SECTION3_KEY, JSON.stringify(section3Rows.value))
  }

  // ─── Section 4: 合同资产/负债变动(listed) 或 分产品分地区(soe) ────────
  const section4Rows = ref<(ContractBalanceRow | ProductRegionRow)[]>([])

  function loadSection4() {
    const rows = safeParseArray<any>(getResp(SECTION4_KEY))
    if (variant === 'listed') {
      section4Rows.value = rows.map((r: any) => ({
        rowId: r.rowId || genRowId('s4'),
        item: r.item || '',
        endBalance: parseNum(r.endBalance),
        beginBalance: parseNum(r.beginBalance),
        changeAmount: parseNum(r.changeAmount),
        reason: r.reason || '',
      }))
    } else {
      section4Rows.value = rows.map((r: any) => ({
        rowId: r.rowId || genRowId('s4'),
        dimension: r.dimension || '',
        type: r.type || '产品',
        currentAmount: parseNum(r.currentAmount),
        priorAmount: parseNum(r.priorAmount),
      }))
    }
  }

  watch(() => allResponses.value.get(prefix + SECTION4_KEY)?.remark, loadSection4, { immediate: true })

  const section4Total = computed(() => {
    if (variant === 'listed') {
      const rows = section4Rows.value as ContractBalanceRow[]
      return {
        endBalance: calcSubtotal(rows.map(r => r.endBalance)),
        beginBalance: calcSubtotal(rows.map(r => r.beginBalance)),
        changeAmount: calcSubtotal(rows.map(r => r.changeAmount)),
      }
    } else {
      const rows = section4Rows.value as ProductRegionRow[]
      return {
        currentAmount: calcSubtotal(rows.map(r => r.currentAmount)),
        priorAmount: calcSubtotal(rows.map(r => r.priorAmount)),
      }
    }
  })

  function addSection4Row(type?: '产品' | '地区' | '时段'): void {
    if (isReadonly.value) return
    if (variant === 'listed') {
      (section4Rows.value as ContractBalanceRow[]).push({
        rowId: genRowId('s4'), item: '', endBalance: 0, beginBalance: 0, changeAmount: 0, reason: '',
      })
    } else {
      (section4Rows.value as ProductRegionRow[]).push({
        rowId: genRowId('s4'), dimension: '', type: type || '产品', currentAmount: 0, priorAmount: 0,
      })
    }
    persist(SECTION4_KEY, JSON.stringify(section4Rows.value))
  }

  function removeSection4Row(rowId: string): void {
    if (isReadonly.value) return
    section4Rows.value = section4Rows.value.filter(r => r.rowId !== rowId)
    persist(SECTION4_KEY, JSON.stringify(section4Rows.value))
  }

  function updateSection4(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = section4Rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const numFields = ['endBalance', 'beginBalance', 'changeAmount', 'currentAmount', 'priorAmount']
    ;(section4Rows.value[idx] as any)[field] = numFields.includes(field) ? parseNum(value) : value
    // 自动计算changeAmount
    if (variant === 'listed' && (field === 'endBalance' || field === 'beginBalance')) {
      const row = section4Rows.value[idx] as ContractBalanceRow
      row.changeAmount = row.endBalance - row.beginBalance
    }
    persist(SECTION4_KEY, JSON.stringify(section4Rows.value))
  }

  // ─── Notes (per section) ─────────────────────────────────────────────
  const noteTexts = ref<Record<string, string>>({})

  function loadNotes() {
    for (const key of ['note-1', 'note-2', 'note-3', 'note-4', 'note-5', 'note-6', 'note-7', 'note-8', 'note-main']) {
      const resp = allResponses.value.get(prefix + key)
      noteTexts.value[key] = resp?.remark || ''
    }
  }

  // 初始化notes
  watch(() => allResponses.value.size, loadNotes, { immediate: true })

  function updateNote(key: string, value: string): void {
    noteTexts.value[key] = value
    persist(key, value)
    // EventBus: 同步附注模块
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { wpCode: 'D4', section: `${variant}-${key}`, text: value },
      }))
    } catch { /* silent */ }
  }

  // ─── EventBus: 监听附注模块更新 ─────────────────────────────────────
  const noteUpdateHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'D4' && detail?.section?.startsWith(`${variant}-`)) {
      const key = detail.section.replace(`${variant}-`, '')
      if (noteTexts.value[key] !== undefined) {
        noteTexts.value[key] = detail.text || ''
      }
    }
  }
  window.addEventListener('note:section-updated', noteUpdateHandler)
  eventListeners.push({ event: 'note:section-updated', handler: noteUpdateHandler })

  // ─── Lifecycle cleanup ───────────────────────────────────────────────
  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────
  return {
    // Cross-sheet
    crossSheetRevenue,
    crossSheetCost,
    // Refresh
    isRefreshing,
    lastRefreshTime,
    refreshFromTb,
    // Section 1
    section1Data,
    section1Total,
    grossMarginRate,
    priorGrossMarginRate,
    // Section 2
    section2Rows,
    section2Total,
    addSection2Row,
    removeSection2Row,
    updateSection2,
    // Section 3
    section3Rows,
    section3Total,
    addSection3Row,
    removeSection3Row,
    updateSection3,
    // Section 4
    section4Rows: section4Rows as Ref<any[]>,
    section4Total,
    addSection4Row,
    removeSection4Row,
    updateSection4,
    // Notes
    noteTexts,
    updateNote,
    // Metadata
    prefix,
    variant,
  }
}
