/**
 * useJ1IndustryCompare — J1-5 同行业对比分析表 composable（对齐源模板4区块）
 *
 * 区块1：本公司薪酬总览（按岗位：生产/管理/销售 + 动态行）
 * 区块2：社保人数核对（左工资人数 vs 右社保人数）
 * 区块3：同行业对比——生产人员
 * 区块4：同行业对比——销管研
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, type Ref } from 'vue'
import { parseNum, calcChangeRate } from './useJ1FormulaEngine'

// ─── Types ────────────────────────────────────────────────────────────────

export interface CompanyDeptRow {
  id: string
  dept: string              // 部门/岗位
  curHeadcount: number      // 本期人数
  curTotal: number          // 本期总额
  curAvg: number            // 本期人均(公式)
  priorHeadcount: number    // 上期人数
  priorTotal: number        // 上期总额
  priorAvg: number          // 上期人均(公式)
  revenueRatio: number      // 占收入比(公式)
  avgChangeRate: number     // 人均变动率(公式)
  industryAvg: number       // 行业人均
  industryDiff: number      // 与行业差异(公式)
  analysis: string          // 异常分析说明
}

export interface SocialSecurityRow {
  label: string
  count: number
}

export interface IndustryPeerRow {
  id: string
  company: string
  headcount: number
  laborCost: number
  mainLaborCost: number  // 主营业务成本中人工成本
  avgWage: number        // 公式=laborCost/headcount
  revenue: number
  totalCost: number
  mainCost: number
  perCapitaOutput: number // 公式=revenue/headcount
  costRatio: number       // 公式=laborCost/totalCost
  mainBizRatio: number    // 公式=mainLaborCost/mainCost
}

export interface IndustryPeerSMRRow {
  id: string
  company: string
  salesCount: number
  salesCost: number
  salesAvg: number       // 公式
  mgmtCount: number
  mgmtCost: number
  mgmtAvg: number       // 公式
  rdCount: number
  rdCost: number
  rdAvg: number          // 公式
}

// ─── Storage Keys ─────────────────────────────────────────────────────────

const KEYS = {
  companyDept: 'J1-5-company-dept',
  revenue: 'J1-5-revenue',
  socialLeft: 'J1-5-social-left',
  socialRight: 'J1-5-social-right',
  peerProduction: 'J1-5-peer-production',
  peerSMR: 'J1-5-peer-smr',
  peers: 'J1-5-peers',
  note: 'J1-5-note',
  conclusion: 'J1-5-conclusion',
}

// ─── Composable ───────────────────────────────────────────────────────────

export interface UseJ1IndustryOptions {
  allResponses: Ref<Map<string, any>>
  saveImmediate: (items: Array<any>) => Promise<void>
  isReadonly: Ref<boolean>
}

export function useJ1IndustryCompare(options: UseJ1IndustryOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── 营业收入 ──────────────────────────────────────────────────────
  const revenue = ref(parseNum(allResponses.value.get(KEYS.revenue)?.remark))

  // ─── 区块1：公司薪酬总览 ──────────────────────────────────────────
  const companyDeptRows = ref<CompanyDeptRow[]>([])

  function recalcDeptRow(r: CompanyDeptRow): CompanyDeptRow {
    const curAvg = r.curHeadcount === 0 ? 0 : r.curTotal / r.curHeadcount
    const priorAvg = r.priorHeadcount === 0 ? 0 : r.priorTotal / r.priorHeadcount
    const revenueRatio = revenue.value === 0 ? 0 : (r.curTotal / revenue.value) * 100
    const avgChangeRate = calcChangeRate(curAvg, priorAvg)
    const industryDiff = r.industryAvg === 0 ? 0 : ((curAvg - r.industryAvg) / r.industryAvg) * 100
    return { ...r, curAvg, priorAvg, revenueRatio, avgChangeRate, industryDiff }
  }

  const DEFAULT_DEPTS = ['生产人员', '管理人员', '销售人员']

  function loadCompanyDept() {
    const raw = allResponses.value.get(KEYS.companyDept)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length > 0) {
          companyDeptRows.value = parsed.map((r: any) => recalcDeptRow({
            id: r.id || genId(), dept: r.dept || '',
            curHeadcount: parseNum(r.curHeadcount), curTotal: parseNum(r.curTotal), curAvg: 0,
            priorHeadcount: parseNum(r.priorHeadcount), priorTotal: parseNum(r.priorTotal), priorAvg: 0,
            revenueRatio: 0, avgChangeRate: 0,
            industryAvg: parseNum(r.industryAvg), industryDiff: 0,
            analysis: r.analysis || '',
          }))
          return
        }
      } catch {}
    }
    companyDeptRows.value = DEFAULT_DEPTS.map(dept => recalcDeptRow({
      id: genId(), dept, curHeadcount: 0, curTotal: 0, curAvg: 0,
      priorHeadcount: 0, priorTotal: 0, priorAvg: 0,
      revenueRatio: 0, avgChangeRate: 0, industryAvg: 0, industryDiff: 0, analysis: '',
    }))
  }
  loadCompanyDept()

  const companyTotal = computed<CompanyDeptRow>(() => {
    const rows = companyDeptRows.value
    const t: CompanyDeptRow = {
      id: 'total', dept: '合计',
      curHeadcount: rows.reduce((s, r) => s + r.curHeadcount, 0),
      curTotal: rows.reduce((s, r) => s + r.curTotal, 0), curAvg: 0,
      priorHeadcount: rows.reduce((s, r) => s + r.priorHeadcount, 0),
      priorTotal: rows.reduce((s, r) => s + r.priorTotal, 0), priorAvg: 0,
      revenueRatio: 0, avgChangeRate: 0, industryAvg: 0, industryDiff: 0, analysis: '',
    }
    return recalcDeptRow(t)
  })

  // ─── 区块2：社保人数核对 ──────────────────────────────────────────
  const socialLeft = ref<SocialSecurityRow[]>([])
  const socialRight = ref<SocialSecurityRow[]>([])

  const DEFAULT_LEFT = [
    { label: '公司发放工资人数', count: 0 },
    { label: '扣除不上交社保费人数（注：在合法试用期内的职工）', count: 0 },
  ]
  const DEFAULT_RIGHT = [
    { label: '上交城镇保险人数', count: 0 },
    { label: '上交小城镇保险人数', count: 0 },
    { label: '上交农业保险人数', count: 0 },
    { label: '上交综合保险人数', count: 0 },
  ]

  function loadSocial() {
    const rawL = allResponses.value.get(KEYS.socialLeft)?.remark
    const rawR = allResponses.value.get(KEYS.socialRight)?.remark
    socialLeft.value = rawL ? (JSON.parse(rawL) || DEFAULT_LEFT) : DEFAULT_LEFT.map(r => ({ ...r }))
    socialRight.value = rawR ? (JSON.parse(rawR) || DEFAULT_RIGHT) : DEFAULT_RIGHT.map(r => ({ ...r }))
  }
  loadSocial()

  const socialLeftTotal = computed(() => {
    const rows = socialLeft.value
    if (rows.length === 0) return 0
    return rows[0].count - rows.slice(1).reduce((s, r) => s + r.count, 0)
  })
  const socialRightTotal = computed(() => socialRight.value.reduce((s, r) => s + r.count, 0))
  const socialDiff = computed(() => socialLeftTotal.value - socialRightTotal.value)

  // ─── 区块3&4：同行业对比 ──────────────────────────────────────────
  const peerCompanies = ref<string[]>([])
  const peerProductionRows = ref<IndustryPeerRow[]>([])
  const peerSMRRows = ref<IndustryPeerSMRRow[]>([])

  function loadPeers() {
    const rawPeers = allResponses.value.get(KEYS.peers)?.remark
    peerCompanies.value = rawPeers ? JSON.parse(rawPeers) : ['A', 'B', 'C', 'D']

    const rawProd = allResponses.value.get(KEYS.peerProduction)?.remark
    if (rawProd) {
      try { peerProductionRows.value = JSON.parse(rawProd).map(recalcProdRow) } catch { initProdRows() }
    } else { initProdRows() }

    const rawSMR = allResponses.value.get(KEYS.peerSMR)?.remark
    if (rawSMR) {
      try { peerSMRRows.value = JSON.parse(rawSMR).map(recalcSMRRow) } catch { initSMRRows() }
    } else { initSMRRows() }
  }

  function initProdRows() {
    peerProductionRows.value = peerCompanies.value.map(c => recalcProdRow({
      id: genId(), company: c, headcount: 0, laborCost: 0, mainLaborCost: 0, avgWage: 0,
      revenue: 0, totalCost: 0, mainCost: 0, perCapitaOutput: 0, costRatio: 0, mainBizRatio: 0,
    }))
  }
  function initSMRRows() {
    peerSMRRows.value = peerCompanies.value.map(c => recalcSMRRow({
      id: genId(), company: c,
      salesCount: 0, salesCost: 0, salesAvg: 0,
      mgmtCount: 0, mgmtCost: 0, mgmtAvg: 0,
      rdCount: 0, rdCost: 0, rdAvg: 0,
    }))
  }
  loadPeers()

  function recalcProdRow(r: any): IndustryPeerRow {
    const headcount = parseNum(r.headcount)
    const laborCost = parseNum(r.laborCost)
    const mainLaborCost = parseNum(r.mainLaborCost)
    const rev = parseNum(r.revenue)
    const totalCost = parseNum(r.totalCost)
    const mainCost = parseNum(r.mainCost)
    return {
      id: r.id || genId(), company: r.company || '',
      headcount, laborCost, mainLaborCost,
      avgWage: headcount === 0 ? 0 : laborCost / headcount,
      revenue: rev, totalCost, mainCost,
      perCapitaOutput: headcount === 0 ? 0 : rev / headcount,
      costRatio: totalCost === 0 ? 0 : (laborCost / totalCost) * 100,
      mainBizRatio: mainCost === 0 ? 0 : (mainLaborCost / mainCost) * 100,
    }
  }

  function recalcSMRRow(r: any): IndustryPeerSMRRow {
    return {
      id: r.id || genId(), company: r.company || '',
      salesCount: parseNum(r.salesCount), salesCost: parseNum(r.salesCost),
      salesAvg: parseNum(r.salesCount) === 0 ? 0 : parseNum(r.salesCost) / parseNum(r.salesCount),
      mgmtCount: parseNum(r.mgmtCount), mgmtCost: parseNum(r.mgmtCost),
      mgmtAvg: parseNum(r.mgmtCount) === 0 ? 0 : parseNum(r.mgmtCost) / parseNum(r.mgmtCount),
      rdCount: parseNum(r.rdCount), rdCost: parseNum(r.rdCost),
      rdAvg: parseNum(r.rdCount) === 0 ? 0 : parseNum(r.rdCost) / parseNum(r.rdCount),
    }
  }

  // 同行业平均（computed）
  const peerProdAvg = computed<IndustryPeerRow>(() => {
    const rows = peerProductionRows.value
    if (rows.length === 0) return recalcProdRow({ company: '同行业平均' })
    const n = rows.length
    return recalcProdRow({
      company: '同行业平均',
      headcount: rows.reduce((s, r) => s + r.headcount, 0) / n,
      laborCost: rows.reduce((s, r) => s + r.laborCost, 0) / n,
      mainLaborCost: rows.reduce((s, r) => s + r.mainLaborCost, 0) / n,
      revenue: rows.reduce((s, r) => s + r.revenue, 0) / n,
      totalCost: rows.reduce((s, r) => s + r.totalCost, 0) / n,
      mainCost: rows.reduce((s, r) => s + r.mainCost, 0) / n,
    })
  })

  const peerSMRAvg = computed<IndustryPeerSMRRow>(() => {
    const rows = peerSMRRows.value
    if (rows.length === 0) return recalcSMRRow({ company: '同行业平均' })
    const n = rows.length
    return recalcSMRRow({
      company: '同行业平均',
      salesCount: rows.reduce((s, r) => s + r.salesCount, 0) / n,
      salesCost: rows.reduce((s, r) => s + r.salesCost, 0) / n,
      mgmtCount: rows.reduce((s, r) => s + r.mgmtCount, 0) / n,
      mgmtCost: rows.reduce((s, r) => s + r.mgmtCost, 0) / n,
      rdCount: rows.reduce((s, r) => s + r.rdCount, 0) / n,
      rdCost: rows.reduce((s, r) => s + r.rdCost, 0) / n,
    })
  })

  // ─── 可比公司管理 ──────────────────────────────────────────────────
  function addPeer(name: string) {
    if (isReadonly.value || peerCompanies.value.includes(name)) return
    peerCompanies.value = [...peerCompanies.value, name]
    peerProductionRows.value.push(recalcProdRow({ id: genId(), company: name }))
    peerSMRRows.value.push(recalcSMRRow({ id: genId(), company: name }))
    scheduleSave()
  }

  function removePeer(name: string) {
    if (isReadonly.value) return
    peerCompanies.value = peerCompanies.value.filter(p => p !== name)
    peerProductionRows.value = peerProductionRows.value.filter(r => r.company !== name)
    peerSMRRows.value = peerSMRRows.value.filter(r => r.company !== name)
    scheduleSave()
  }

  // ─── Save ──────────────────────────────────────────────────────────
  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleSave() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(persist, 1500)
  }

  function persist() {
    const USER_DEPT_FIELDS = ['id', 'dept', 'curHeadcount', 'curTotal', 'priorHeadcount', 'priorTotal', 'industryAvg', 'analysis']
    const items = [
      { item_id: KEYS.companyDept, conclusion: null, remark: JSON.stringify(companyDeptRows.value.map(r => {
        const obj: any = {}; USER_DEPT_FIELDS.forEach(f => { obj[f] = (r as any)[f] }); return obj
      })) },
      { item_id: KEYS.revenue, conclusion: null, remark: String(revenue.value) },
      { item_id: KEYS.socialLeft, conclusion: null, remark: JSON.stringify(socialLeft.value) },
      { item_id: KEYS.socialRight, conclusion: null, remark: JSON.stringify(socialRight.value) },
      { item_id: KEYS.peers, conclusion: null, remark: JSON.stringify(peerCompanies.value) },
      { item_id: KEYS.peerProduction, conclusion: null, remark: JSON.stringify(peerProductionRows.value) },
      { item_id: KEYS.peerSMR, conclusion: null, remark: JSON.stringify(peerSMRRows.value) },
    ]
    items.forEach(it => allResponses.value.set(it.item_id, it))
    saveImmediate(items).catch(() => {})
  }

  function updateDeptCell(rowId: string, field: string, value: any) {
    if (isReadonly.value) return
    const idx = companyDeptRows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    const row = { ...companyDeptRows.value[idx], [field]: typeof value === 'string' ? value : parseNum(value) }
    companyDeptRows.value[idx] = recalcDeptRow(row as CompanyDeptRow)
    scheduleSave()
  }

  function updateProdCell(rowId: string, field: string, value: number) {
    if (isReadonly.value) return
    const idx = peerProductionRows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    const row = { ...peerProductionRows.value[idx], [field]: parseNum(value) }
    peerProductionRows.value[idx] = recalcProdRow(row)
    scheduleSave()
  }

  function updateSMRCell(rowId: string, field: string, value: number) {
    if (isReadonly.value) return
    const idx = peerSMRRows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    const row = { ...peerSMRRows.value[idx], [field]: parseNum(value) }
    peerSMRRows.value[idx] = recalcSMRRow(row)
    scheduleSave()
  }

  // ─── 审计说明/结论 ─────────────────────────────────────────────────
  const auditNote = ref(allResponses.value.get(KEYS.note)?.remark || '')
  const auditConclusion = ref(allResponses.value.get(KEYS.conclusion)?.remark || '')

  function saveOpinion() {
    if (isReadonly.value) return
    const items = [
      { item_id: KEYS.note, conclusion: null, remark: auditNote.value },
      { item_id: KEYS.conclusion, conclusion: null, remark: auditConclusion.value },
    ]
    items.forEach(it => allResponses.value.set(it.item_id, it))
    saveImmediate(items).catch(() => {})
  }

  // ─── Helpers ───────────────────────────────────────────────────────
  function genId(): string { return `j1i-${Date.now()}-${Math.random().toString(36).slice(2, 6)}` }

  return {
    revenue, companyDeptRows, companyTotal, socialLeft, socialRight,
    socialLeftTotal, socialRightTotal, socialDiff,
    peerCompanies, peerProductionRows, peerSMRRows, peerProdAvg, peerSMRAvg,
    auditNote, auditConclusion,
    updateDeptCell, updateProdCell, updateSMRCell,
    addPeer, removePeer, scheduleSave, saveOpinion,
  }
}
