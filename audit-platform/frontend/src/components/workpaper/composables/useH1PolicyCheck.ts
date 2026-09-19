/**
 * useH1PolicyCheck — H1-5 会计政策估计检查 composable
 *
 * 编制逻辑对齐致同 Excel 模板 H1-5：
 *   CAS4 六段落定性评价
 *   + 表A 本企业折旧参数及五维判断（可从 H1-2 带入）
 *   + 表B 同行业对标（偏离预警 + 行业模板）
 *   + 表C 估计变更原估计（上期底稿/H1-12 带入 + 影响金额）
 *   + 交叉校验 / 完成度闸门 / 导入导出包
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Requirements: 6.1-6.7
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { readH12BranchRows } from './h1H12BranchKeys'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PolicySection {
  key: string
  title: string
  description: string
  actualPolicy: string
  evaluation: string
  conclusion: 'Y' | 'N' | 'NA' | ''
  explanationIfN: string
}

export type YnNa = 'Y' | 'N' | 'NA' | ''

export interface DepParamRow {
  rowId: string
  category: string
  depMethod: string
  usefulLifeMin: number
  usefulLifeMax: number
  salvageRate: number
  meetsStandards: YnNa
  matchesEconomicBenefit: YnNa
  reasonableVsPeers: YnNa
  hasChange: YnNa
  changeReasonable: YnNa
  isReasonable: 'Y' | 'N' | ''
  remark: string
  /** 来自 H1-2 的资产笔数（带入后展示） */
  detailCount?: number
  /** 与 H1-2 参数是否不一致 */
  mismatchDetail?: boolean
}

export interface PeerCompany {
  peerId: string
  name: string
  source: string
}

export interface PeerCell {
  usefulLife: string
  depMethod: string
  salvageRate: number | null
}

export interface PeerPolicyRow {
  category: string
  values: Record<string, PeerCell>
}

export interface PriorEstimateRow {
  category: string
  usefulLife: string
  depMethod: string
  salvageRate: number | null
  /** 对当期折旧/损益影响金额 */
  impactAmount: number | null
  /** 来源标记 */
  source: '' | 'prior-year' | 'h1-12' | 'manual'
}

export interface PeerRange {
  category: string
  lifeMin: number | null
  lifeMax: number | null
  salvageMin: number | null
  salvageMax: number | null
  sampleCount: number
  label: string
}

export interface PeerDeviation {
  category: string
  field: 'usefulLife' | 'salvageRate'
  message: string
  requiresRemark: boolean
}

export interface CompletenessItem {
  id: string
  ok: boolean
  label: string
  hint: string
}

export interface CrossCheckIssue {
  id: string
  severity: 'warn' | 'error'
  message: string
}

export interface IndustryTemplate {
  id: string
  label: string
  peers: Array<{
    name: string
    source: string
    /** category → cell */
    policies: Record<string, PeerCell>
  }>
}

export interface H15ExportPack {
  version: 1
  exportedAt: string
  sections: PolicySection[]
  depParams: DepParamRow[]
  peers: { companies: PeerCompany[]; policies: PeerPolicyRow[] }
  priorEstimates: PriorEstimateRow[]
  auditNote: string
  auditConclusion?: string
}

export interface SyncFromDetailResult {
  added: number
  refreshed: number
  categories: string[]
}

export interface PriorYearPullResult {
  filled: number
  markedChange: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-5'

export const DEFAULT_CATEGORIES = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

export const DEP_METHOD_OPTIONS = ['直线法', '双倍余额递减法', '年数总和法', '工作量法'] as const

export const YN_OPTIONS: { label: string; value: YnNa }[] = [
  { label: 'Y', value: 'Y' },
  { label: 'N', value: 'N' },
  { label: 'NA', value: 'NA' },
]

/** 行业同业模板（示意数据，项目组须按实际年报替换） */
export const INDUSTRY_TEMPLATES: IndustryTemplate[] = [
  {
    id: 'manufacturing',
    label: '制造业（示意）',
    peers: [
      {
        name: '同业A（制造业）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '20-40', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '4-5', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
          其他设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
        },
      },
      {
        name: '同业B（制造业）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '20-50', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '5-12', depMethod: '直线法', salvageRate: 3 },
          运输设备: { usefulLife: '5-8', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 0 },
          其他设备: { usefulLife: '3-10', depMethod: '直线法', salvageRate: 5 },
        },
      },
      {
        name: '同业C（制造业）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '15-40', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '8-10', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '4-6', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
          其他设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
        },
      },
    ],
  },
  {
    id: 'realestate',
    label: '房地产（示意）',
    peers: [
      {
        name: '同业A（房地产）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '20-40', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '5-8', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
          其他设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
        },
      },
      {
        name: '同业B（房地产）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '25-50', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '4-5', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 0 },
          其他设备: { usefulLife: '5-8', depMethod: '直线法', salvageRate: 5 },
        },
      },
      {
        name: '同业C（房地产）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '20-40', depMethod: '直线法', salvageRate: 0 },
          机器设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
          其他设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
        },
      },
    ],
  },
  {
    id: 'tech',
    label: '科技/软件（示意）',
    peers: [
      {
        name: '同业A（科技）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '20-40', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '4-5', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 0 },
          其他设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
        },
      },
      {
        name: '同业B（科技）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '20-50', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '3-10', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '4-5', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
          其他设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 0 },
        },
      },
      {
        name: '同业C（科技）',
        source: '示意·须替换为实际年报附注',
        policies: {
          房屋及建筑物: { usefulLife: '20-40', depMethod: '直线法', salvageRate: 5 },
          机器设备: { usefulLife: '5-10', depMethod: '直线法', salvageRate: 5 },
          运输设备: { usefulLife: '5', depMethod: '直线法', salvageRate: 5 },
          办公设备: { usefulLife: '3', depMethod: '直线法', salvageRate: 0 },
          其他设备: { usefulLife: '3-5', depMethod: '直线法', salvageRate: 5 },
        },
      },
    ],
  },
]

const SECTION_DEFINITIONS: Omit<PolicySection, 'actualPolicy' | 'evaluation' | 'conclusion' | 'explanationIfN'>[] = [
  { key: 'recognition', title: '(1) 固定资产确认条件', description: 'CAS4第3条：与该固定资产有关的经济利益很可能流入企业；该固定资产的成本能够可靠地计量。' },
  { key: 'classification', title: '(2) 固定资产分类与使用年限', description: 'CAS4第14-15条：企业应当根据固定资产的性质和使用情况，合理确定固定资产的使用寿命；至少于每年年度终了复核。' },
  { key: 'depreciation', title: '(3) 折旧方法与残值率', description: 'CAS4第17-19条：可选用年限平均法、工作量法、双倍余额递减法、年数总和法。预计净残值不得随意变更；变更属会计估计变更，采用未来适用法。' },
  { key: 'subsequent', title: '(4) 后续支出资本化/费用化', description: 'CAS4第6-7条：符合确认条件的后续支出计入固定资产成本；不符合的计入当期损益。' },
  { key: 'impairment', title: '(5) 减值政策', description: 'CAS8第4-5条：资产减值迹象判断标准、可收回金额确定方法、资产组划分；减值一经确认不得转回。' },
  { key: 'disposal', title: '(6) 处置确认', description: 'CAS4第22-23条：固定资产满足下列条件之一时予以终止确认：处于处置状态/预期通过使用或处置不能产生经济利益。' },
]

function _emptyPeerCell(): PeerCell {
  return { usefulLife: '', depMethod: '', salvageRate: null }
}

function _newPeerId(i: number): string {
  return `peer-${i}`
}

function _parseLifeNums(text: string): number[] {
  const m = String(text || '').match(/(\d+(?:\.\d+)?)/g)
  return m ? m.map(Number).filter((n) => Number.isFinite(n)) : []
}

function _mode(values: string[]): string {
  const counts = new Map<string, number>()
  for (const v of values) {
    if (!v) continue
    counts.set(v, (counts.get(v) || 0) + 1)
  }
  let best = ''
  let bestN = 0
  for (const [k, n] of counts) {
    if (n > bestN) {
      best = k
      bestN = n
    }
  }
  return best
}

function _median(nums: number[]): number | null {
  if (!nums.length) return null
  const s = [...nums].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1PolicyCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  const sections = ref<PolicySection[]>([])
  const depParams = ref<DepParamRow[]>([])
  const peerCompanies = ref<PeerCompany[]>([])
  const peerPolicies = ref<PeerPolicyRow[]>([])
  const priorEstimates = ref<PriorEstimateRow[]>([])
  const auditNote = ref('')

  function _loadData(): void {
    const sectData = _getJson(`${ITEM_PREFIX}-sections`)
    if (Array.isArray(sectData) && sectData.length > 0) {
      sections.value = sectData.map(_normalizePolicySection)
    } else {
      sections.value = SECTION_DEFINITIONS.map((def) => ({
        ...def,
        actualPolicy: '',
        evaluation: '',
        conclusion: '' as const,
        explanationIfN: '',
      }))
    }

    const paramData = _getJson(`${ITEM_PREFIX}-dep-params`)
    if (Array.isArray(paramData) && paramData.length > 0) {
      depParams.value = paramData.map(_normalizeDepParam)
    } else {
      depParams.value = _buildDefaultDepParams()
    }

    const peersData = _getJson(`${ITEM_PREFIX}-peers`)
    if (peersData && Array.isArray(peersData.companies) && peersData.companies.length > 0) {
      peerCompanies.value = peersData.companies.map(_normalizePeerCompany)
      peerPolicies.value = Array.isArray(peersData.policies)
        ? peersData.policies.map((r: any) => _normalizePeerPolicyRow(r, peerCompanies.value))
        : _buildDefaultPeerPolicies(peerCompanies.value)
    } else {
      peerCompanies.value = _buildDefaultPeers()
      peerPolicies.value = _buildDefaultPeerPolicies(peerCompanies.value)
    }

    const priorData = _getJson(`${ITEM_PREFIX}-prior-estimates`)
    if (Array.isArray(priorData) && priorData.length > 0) {
      priorEstimates.value = priorData.map(_normalizePriorEstimate)
    } else {
      priorEstimates.value = []
    }

    const noteItem = allResponses.value.get(`${ITEM_PREFIX}-audit-note`)
    auditNote.value = (noteItem?.remark as string) || ''

    _refreshDetailMismatchFlags()
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  function _normalizePolicySection(raw: any): PolicySection {
    const def = SECTION_DEFINITIONS.find((d) => d.key === raw.key)
    return {
      key: raw.key ?? '',
      title: raw.title || def?.title || '',
      description: raw.description || def?.description || '',
      actualPolicy: raw.actualPolicy ?? '',
      evaluation: raw.evaluation ?? '',
      conclusion: raw.conclusion ?? '',
      explanationIfN: raw.explanationIfN ?? '',
    }
  }

  function _normalizeDepParam(raw: any): DepParamRow {
    return {
      rowId: raw.rowId ?? `dp-${Math.random().toString(36).slice(2, 8)}`,
      category: raw.category ?? '',
      depMethod: raw.depMethod ?? '直线法',
      usefulLifeMin: Number(raw.usefulLifeMin) || 0,
      usefulLifeMax: Number(raw.usefulLifeMax) || 0,
      salvageRate: Number(raw.salvageRate) || 0,
      meetsStandards: raw.meetsStandards ?? '',
      matchesEconomicBenefit: raw.matchesEconomicBenefit ?? '',
      reasonableVsPeers: raw.reasonableVsPeers ?? '',
      hasChange: raw.hasChange ?? '',
      changeReasonable: raw.changeReasonable ?? '',
      isReasonable: raw.isReasonable ?? '',
      remark: raw.remark ?? '',
      detailCount: raw.detailCount,
      mismatchDetail: raw.mismatchDetail,
    }
  }

  function _emptyDepRow(category = ''): DepParamRow {
    return {
      rowId: `dp-${category || Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      category,
      depMethod: '直线法',
      usefulLifeMin: 0,
      usefulLifeMax: 0,
      salvageRate: 0,
      meetsStandards: '',
      matchesEconomicBenefit: '',
      reasonableVsPeers: '',
      hasChange: '',
      changeReasonable: '',
      isReasonable: '',
      remark: '',
    }
  }

  function _buildDefaultDepParams(): DepParamRow[] {
    return DEFAULT_CATEGORIES.map((cat) => _emptyDepRow(cat))
  }

  function _normalizePeerCompany(raw: any, idx = 0): PeerCompany {
    return {
      peerId: raw.peerId || _newPeerId(idx + 1),
      name: raw.name ?? '',
      source: raw.source ?? '',
    }
  }

  function _buildDefaultPeers(): PeerCompany[] {
    return [1, 2, 3].map((i) => ({ peerId: _newPeerId(i), name: '', source: '' }))
  }

  function _normalizePeerPolicyRow(raw: any, peers: PeerCompany[]): PeerPolicyRow {
    const values: Record<string, PeerCell> = {}
    for (const p of peers) {
      const cell = raw.values?.[p.peerId] ?? {}
      values[p.peerId] = {
        usefulLife: cell.usefulLife ?? '',
        depMethod: cell.depMethod ?? '',
        salvageRate: cell.salvageRate == null || cell.salvageRate === '' ? null : Number(cell.salvageRate),
      }
    }
    return { category: raw.category ?? '', values }
  }

  function _buildDefaultPeerPolicies(peers: PeerCompany[], cats?: string[]): PeerPolicyRow[] {
    const categories = cats?.length ? cats : [...DEFAULT_CATEGORIES]
    return categories.map((cat) => {
      const values: Record<string, PeerCell> = {}
      for (const p of peers) values[p.peerId] = _emptyPeerCell()
      return { category: cat, values }
    })
  }

  function _normalizePriorEstimate(raw: any): PriorEstimateRow {
    return {
      category: raw.category ?? '',
      usefulLife: raw.usefulLife ?? '',
      depMethod: raw.depMethod ?? '',
      salvageRate: raw.salvageRate == null || raw.salvageRate === '' ? null : Number(raw.salvageRate),
      impactAmount: raw.impactAmount == null || raw.impactAmount === '' ? null : Number(raw.impactAmount),
      source: raw.source || '',
    }
  }

  function _emptyPrior(category: string): PriorEstimateRow {
    return { category, usefulLife: '', depMethod: '', salvageRate: null, impactAmount: null, source: '' }
  }

  // ─── H1-2 / H1-12 parsers ─────────────────────────────────────────────────

  function _parseDetailRows(): any[] {
    const item = allResponses.value.get('H1-2-rows')
    if (!item?.remark) return []
    try {
      const parsed = typeof item.remark === 'string' ? JSON.parse(item.remark) : item.remark
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  function _parseH12Rows(): any[] {
    return readH12BranchRows(allResponses.value).rows
  }

  function _aggregateDetailByCategory(detail: any[]): Map<string, {
    usefulLifeMin: number
    usefulLifeMax: number
    salvageRate: number
    depMethod: string
    count: number
  }> {
    const map = new Map<string, {
      lives: number[]
      salvages: number[]
      methods: string[]
      count: number
    }>()
    for (const d of detail) {
      const cat = String(d.category || '').trim()
      if (!cat) continue
      const life = Number(d.usefulLife) || 0
      let salvage = Number(d.salvageRate) || 0
      if (salvage > 0 && salvage < 1) salvage = salvage * 100
      const method = String(d.depMethod || '直线法')
      const bucket = map.get(cat) || { lives: [], salvages: [], methods: [], count: 0 }
      if (life > 0) bucket.lives.push(life)
      if (salvage >= 0) bucket.salvages.push(salvage)
      bucket.methods.push(method)
      bucket.count += 1
      map.set(cat, bucket)
    }
    const out = new Map<string, {
      usefulLifeMin: number
      usefulLifeMax: number
      salvageRate: number
      depMethod: string
      count: number
    }>()
    for (const [cat, b] of map) {
      out.set(cat, {
        usefulLifeMin: b.lives.length ? Math.min(...b.lives) : 0,
        usefulLifeMax: b.lives.length ? Math.max(...b.lives) : 0,
        salvageRate: _median(b.salvages) ?? 0,
        depMethod: _mode(b.methods) || '直线法',
        count: b.count,
      })
    }
    return out
  }

  function _refreshDetailMismatchFlags(): void {
    const agg = _aggregateDetailByCategory(_parseDetailRows())
    for (const row of depParams.value) {
      const hit = agg.get(row.category)
      row.detailCount = hit?.count
      if (!hit) {
        row.mismatchDetail = agg.size > 0
        continue
      }
      const lifeOk =
        (!row.usefulLifeMin && !row.usefulLifeMax) ||
        (row.usefulLifeMin === hit.usefulLifeMin && row.usefulLifeMax === hit.usefulLifeMax) ||
        (row.usefulLifeMin <= hit.usefulLifeMax && row.usefulLifeMax >= hit.usefulLifeMin)
      const salvageOk = Math.abs((row.salvageRate || 0) - (hit.salvageRate || 0)) <= 1
      const methodOk = !row.depMethod || row.depMethod === hit.depMethod
      row.mismatchDetail = !(lifeOk && salvageOk && methodOk)
    }
  }

  /** 从 H1-2 按类别汇总带入表A参数 */
  function syncFromDetail(opts?: { replace?: boolean }): SyncFromDetailResult {
    const agg = _aggregateDetailByCategory(_parseDetailRows())
    const categories = [...agg.keys()]
    if (!categories.length) {
      return { added: 0, refreshed: 0, categories: [] }
    }

    let added = 0
    let refreshed = 0

    if (opts?.replace) {
      depParams.value = categories.map((cat) => {
        const a = agg.get(cat)!
        const row = _emptyDepRow(cat)
        row.usefulLifeMin = a.usefulLifeMin
        row.usefulLifeMax = a.usefulLifeMax
        row.salvageRate = Math.round(a.salvageRate * 100) / 100
        row.depMethod = a.depMethod
        row.detailCount = a.count
        row.mismatchDetail = false
        return row
      })
      added = categories.length
      _syncPeerCategories()
      _persistParams()
      return { added, refreshed: 0, categories }
    }

    const byCat = new Map(depParams.value.map((r) => [r.category, r]))
    for (const cat of categories) {
      const a = agg.get(cat)!
      const hit = byCat.get(cat)
      if (hit) {
        hit.usefulLifeMin = a.usefulLifeMin
        hit.usefulLifeMax = a.usefulLifeMax
        hit.salvageRate = Math.round(a.salvageRate * 100) / 100
        hit.depMethod = a.depMethod
        hit.detailCount = a.count
        hit.mismatchDetail = false
        refreshed += 1
      } else {
        const row = _emptyDepRow(cat)
        row.usefulLifeMin = a.usefulLifeMin
        row.usefulLifeMax = a.usefulLifeMax
        row.salvageRate = Math.round(a.salvageRate * 100) / 100
        row.depMethod = a.depMethod
        row.detailCount = a.count
        depParams.value.push(row)
        added += 1
      }
    }
    _syncPeerCategories()
    _persistParams()
    return { added, refreshed, categories }
  }

  function _syncPeerCategories(): void {
    const cats = depParams.value.map((r) => r.category).filter(Boolean)
    const existing = new Map(peerPolicies.value.map((r) => [r.category, r]))
    peerPolicies.value = cats.map((cat) => {
      if (existing.has(cat)) return existing.get(cat)!
      const values: Record<string, PeerCell> = {}
      for (const p of peerCompanies.value) values[p.peerId] = _emptyPeerCell()
      return { category: cat, values }
    })
    _persistPeers()
  }

  /**
   * 从上期底稿 checklist-responses 带入原估计：
   * - 对比上年 dep-params，参数变化的类别自动标记 hasChange=Y 并填表C
   * - 若上年已有 prior-estimates 亦可回填空字段
   */
  function applyPriorYearResponses(items: any[]): PriorYearPullResult {
    const list = Array.isArray(items) ? items : []
    const find = (id: string) => list.find((x: any) => (x.item_id || x.itemId) === id)
    const parseRemark = (item: any) => {
      const raw = item?.remark ?? item?.value
      if (!raw) return null
      if (typeof raw === 'object') return raw
      try { return JSON.parse(raw) } catch { return null }
    }

    const priorParams: any[] = parseRemark(find(`${ITEM_PREFIX}-dep-params`)) || []
    const priorPriors: any[] = parseRemark(find(`${ITEM_PREFIX}-prior-estimates`)) || []
    const priorByCat = new Map<string, any>(
      (Array.isArray(priorParams) ? priorParams : []).map((r: any) => [String(r.category || ''), r]),
    )

    let filled = 0
    let markedChange = 0

    for (const row of depParams.value) {
      const prev = priorByCat.get(row.category)
      if (!prev) continue
      const prevLifeMin = Number(prev.usefulLifeMin) || 0
      const prevLifeMax = Number(prev.usefulLifeMax) || 0
      const prevSalvage = Number(prev.salvageRate) || 0
      const prevMethod = String(prev.depMethod || '')
      const lifeChanged =
        (row.usefulLifeMin || row.usefulLifeMax) &&
        (row.usefulLifeMin !== prevLifeMin || row.usefulLifeMax !== prevLifeMax)
      const salvageChanged = Math.abs((row.salvageRate || 0) - prevSalvage) > 0.01
      const methodChanged = row.depMethod && prevMethod && row.depMethod !== prevMethod

      if (lifeChanged || salvageChanged || methodChanged) {
        if (row.hasChange !== 'Y') {
          row.hasChange = 'Y'
          markedChange += 1
        }
        const lifeText =
          prevLifeMin && prevLifeMax && prevLifeMin !== prevLifeMax
            ? `${prevLifeMin}–${prevLifeMax}`
            : String(prevLifeMax || prevLifeMin || prev.usefulLife || '')
        _upsertPrior(row.category, {
          usefulLife: lifeText,
          depMethod: prevMethod,
          salvageRate: prevSalvage,
          source: 'prior-year',
        })
        filled += 1
      }
    }

    for (const p of Array.isArray(priorPriors) ? priorPriors : []) {
      const cat = String(p.category || '')
      if (!cat) continue
      const existing = priorEstimates.value.find((r) => r.category === cat)
      if (existing && !existing.usefulLife && !existing.depMethod) {
        existing.usefulLife = p.usefulLife || existing.usefulLife
        existing.depMethod = p.depMethod || existing.depMethod
        existing.salvageRate = p.salvageRate ?? existing.salvageRate
        existing.source = existing.source || 'prior-year'
        filled += 1
      }
    }

    _syncPriorEstimatesFromChanges()
    _persistParams()
    return { filled, markedChange }
  }

  /** 从 H1-12 估计变更字段回填表C */
  function syncPriorsFromH12(): number {
    const rows = _parseH12Rows().filter((r) => r.estimateChangeDate || r.usefulLifeBefore || r.salvageRateBefore)
    if (!rows.length) return 0
    const byCat = new Map<string, any[]>()
    for (const r of rows) {
      const cat = String(r.category || '').trim()
      if (!cat) continue
      if (!byCat.has(cat)) byCat.set(cat, [])
      byCat.get(cat)!.push(r)
    }
    let n = 0
    for (const [cat, list] of byCat) {
      const sample = list[0]
      const lifeBefore = sample.usefulLifeBefore ?? sample.usefulLife
      let salvageBefore = sample.salvageRateBefore ?? sample.salvageRate
      if (salvageBefore != null && Number(salvageBefore) > 0 && Number(salvageBefore) < 1) {
        salvageBefore = Number(salvageBefore) * 100
      }
      const depRow = depParams.value.find((r) => r.category === cat)
      if (depRow && depRow.hasChange !== 'Y') {
        depRow.hasChange = 'Y'
      }
      _upsertPrior(cat, {
        usefulLife: lifeBefore != null ? String(lifeBefore) : '',
        depMethod: sample.depMethod || '',
        salvageRate: salvageBefore == null ? null : Number(salvageBefore),
        source: 'h1-12',
      })
      n += 1
    }
    _syncPriorEstimatesFromChanges()
    _persistParams()
    return n
  }

  function _upsertPrior(category: string, patch: Partial<PriorEstimateRow>): void {
    let row = priorEstimates.value.find((r) => r.category === category)
    if (!row) {
      row = _emptyPrior(category)
      priorEstimates.value.push(row)
    }
    if (patch.usefulLife != null && (!row.usefulLife || patch.source === 'prior-year' || patch.source === 'h1-12')) {
      row.usefulLife = patch.usefulLife
    }
    if (patch.depMethod != null && (!row.depMethod || patch.source)) row.depMethod = patch.depMethod
    if (patch.salvageRate !== undefined && (row.salvageRate == null || patch.source)) {
      row.salvageRate = patch.salvageRate
    }
    if (patch.impactAmount !== undefined) row.impactAmount = patch.impactAmount
    if (patch.source) row.source = patch.source
  }

  /** 应用行业同业模板到表B */
  function applyIndustryTemplate(templateId: string): boolean {
    const tpl = INDUSTRY_TEMPLATES.find((t) => t.id === templateId)
    if (!tpl) return false
    peerCompanies.value = tpl.peers.map((p, i) => ({
      peerId: _newPeerId(i + 1),
      name: p.name,
      source: p.source,
    }))
    const cats = depParams.value.map((r) => r.category).filter(Boolean)
    const catList = cats.length ? cats : [...DEFAULT_CATEGORIES]
    peerPolicies.value = catList.map((cat) => {
      const values: Record<string, PeerCell> = {}
      tpl.peers.forEach((p, i) => {
        const peerId = _newPeerId(i + 1)
        values[peerId] = { ...(p.policies[cat] || _emptyPeerCell()) }
      })
      return { category: cat, values }
    })
    _persistPeers()
    return true
  }

  /** 根据同业区间自动建议「同业合理」判断（空字段才填） */
  function suggestJudgmentsFromPeers(): number {
    let n = 0
    const devSet = new Set(peerDeviations.value.map((d) => d.category))
    for (const row of depParams.value) {
      if (row.reasonableVsPeers) continue
      const range = peerRanges.value.find((r) => r.category === row.category)
      if (!range || range.sampleCount < 1) continue
      if (devSet.has(row.category)) {
        row.reasonableVsPeers = 'N'
        if (!row.remark?.trim()) {
          row.remark = `同业偏离：${peerDeviations.value.filter((d) => d.category === row.category).map((d) => d.message).join('；')}`
        }
      } else {
        row.reasonableVsPeers = 'Y'
      }
      _autoOverallReasonable(row)
      n += 1
    }
    if (n) _persistParams()
    return n
  }

  // ─── Computed: peers / deviations / completeness ───────────────────────────

  const categoriesWithChange = computed(() =>
    depParams.value.filter((r) => r.hasChange === 'Y').map((r) => r.category),
  )

  const showPriorEstimates = computed(() => categoriesWithChange.value.length > 0)

  const hasAnyChange = computed(() => categoriesWithChange.value.length > 0)

  const peerRanges = computed((): PeerRange[] => {
    return peerPolicies.value.map((row) => {
      const lives: number[] = []
      const salvages: number[] = []
      for (const cell of Object.values(row.values)) {
        lives.push(..._parseLifeNums(cell.usefulLife))
        if (cell.salvageRate != null && cell.salvageRate !== ('' as any)) {
          salvages.push(Number(cell.salvageRate))
        }
      }
      const lifeMin = lives.length ? Math.min(...lives) : null
      const lifeMax = lives.length ? Math.max(...lives) : null
      const salvageMin = salvages.length ? Math.min(...salvages) : null
      const salvageMax = salvages.length ? Math.max(...salvages) : null
      let label = ''
      if (lifeMin != null && lifeMax != null) label += `年限${lifeMin}–${lifeMax}`
      if (salvageMin != null && salvageMax != null) {
        label += (label ? '，' : '') + `残值${salvageMin}–${salvageMax}%`
      }
      return {
        category: row.category,
        lifeMin,
        lifeMax,
        salvageMin,
        salvageMax,
        sampleCount: lives.length + salvages.length,
        label,
      }
    })
  })

  const peerLifeHints = computed(() => {
    const hints: Record<string, string> = {}
    for (const r of peerRanges.value) {
      if (r.label) hints[r.category] = r.label
    }
    return hints
  })

  const peerDeviations = computed((): PeerDeviation[] => {
    const out: PeerDeviation[] = []
    for (const row of depParams.value) {
      const range = peerRanges.value.find((r) => r.category === row.category)
      if (!range || range.sampleCount < 1) continue
      const clientMin = row.usefulLifeMin || row.usefulLifeMax
      const clientMax = row.usefulLifeMax || row.usefulLifeMin
      if (range.lifeMin != null && range.lifeMax != null && clientMin && clientMax) {
        if (clientMax < range.lifeMin || clientMin > range.lifeMax) {
          out.push({
            category: row.category,
            field: 'usefulLife',
            message: `${row.category}年限${clientMin}–${clientMax}超出同业${range.lifeMin}–${range.lifeMax}`,
            requiresRemark: true,
          })
        }
      }
      if (range.salvageMin != null && range.salvageMax != null && row.salvageRate != null) {
        if (row.salvageRate < range.salvageMin - 0.5 || row.salvageRate > range.salvageMax + 0.5) {
          out.push({
            category: row.category,
            field: 'salvageRate',
            message: `${row.category}残值率${row.salvageRate}%超出同业${range.salvageMin}–${range.salvageMax}%`,
            requiresRemark: true,
          })
        }
      }
    }
    return out
  })

  const categoriesNeedingDeviationRemark = computed(() => {
    const set = new Set<string>()
    for (const d of peerDeviations.value) {
      const row = depParams.value.find((r) => r.category === d.category)
      if (row && !row.remark?.trim()) set.add(d.category)
    }
    return [...set]
  })

  const crossCheckIssues = computed((): CrossCheckIssue[] => {
    const issues: CrossCheckIssue[] = []
    const depSection = sections.value.find((s) => s.key === 'depreciation')
    const classSection = sections.value.find((s) => s.key === 'classification')
    const hasUnreasonable = depParams.value.some((r) => r.isReasonable === 'N')
    const hasChange = hasAnyChange.value

    if (depSection?.conclusion === 'Y' && hasUnreasonable) {
      issues.push({
        id: 'dep-y-vs-table-n',
        severity: 'error',
        message: '段落(3)结论为Y，但表A存在「综合合理=N」的类别，请复核一致性',
      })
    }
    if (depSection?.conclusion === 'Y' && hasChange && !priorEstimates.value.some((p) => p.usefulLife || p.depMethod)) {
      issues.push({
        id: 'dep-y-missing-prior',
        severity: 'warn',
        message: '存在估计变更但表C原估计未填写完整',
      })
    }
    if (classSection?.conclusion === 'Y' && depParams.value.some((r) => r.mismatchDetail)) {
      issues.push({
        id: 'class-vs-h12',
        severity: 'warn',
        message: '表A参数与 H1-2 明细汇总不一致（已标黄），请核对分类与使用年限',
      })
    }
    if (hasChange) {
      issues.push({
        id: 'link-s3',
        severity: 'warn',
        message: '本期存在会计估计变更，请同步执行 S3-2 估计变更程序并勾稽附注披露',
      })
    }
    for (const cat of categoriesNeedingDeviationRemark.value) {
      issues.push({
        id: `dev-remark-${cat}`,
        severity: 'error',
        message: `${cat} 偏离同业区间，须在表A备注说明原因`,
      })
    }
    return issues
  })

  function _sectionDone(s: PolicySection): boolean {
    if (!s.conclusion) return false
    if (s.conclusion === 'N' && !s.explanationIfN?.trim()) return false
    return true
  }

  function _depRowDone(r: DepParamRow): boolean {
    if (!r.category) return false
    if (!r.depMethod || (!r.usefulLifeMin && !r.usefulLifeMax)) return false
    if (!r.meetsStandards || !r.matchesEconomicBenefit || !r.reasonableVsPeers || !r.hasChange) return false
    if (r.hasChange === 'Y' && !r.changeReasonable) return false
    if (!r.isReasonable) return false
    if (categoriesNeedingDeviationRemark.value.includes(r.category)) return false
    if (r.hasChange === 'Y') {
      const prior = priorEstimates.value.find((p) => p.category === r.category)
      if (!prior?.usefulLife && !prior?.depMethod) return false
    }
    return true
  }

  const sectionCompletedCount = computed(() => sections.value.filter(_sectionDone).length)
  const depCompletedCount = computed(() => depParams.value.filter(_depRowDone).length)

  const completeness = computed((): CompletenessItem[] => {
    const items: CompletenessItem[] = [
      {
        id: 'sections',
        ok: sectionCompletedCount.value === sections.value.length,
        label: `CAS4段落 ${sectionCompletedCount.value}/${sections.value.length}`,
        hint: '每段须有结论；N 须填写原因',
      },
      {
        id: 'dep-params',
        ok: depCompletedCount.value === depParams.value.length && depParams.value.length > 0,
        label: `表A参数判断 ${depCompletedCount.value}/${depParams.value.length}`,
        hint: '五维判断+综合合理；同业偏离须备注；变更须填表C',
      },
      {
        id: 'peers',
        ok: peerCompanies.value.some((p) => p.name.trim()) && peerPolicies.value.some((r) =>
          Object.values(r.values).some((c) => c.usefulLife || c.depMethod || c.salvageRate != null),
        ),
        label: '表B同业对标已填',
        hint: '至少一家同业公司及政策参数，并注明信息来源',
      },
      {
        id: 'peer-source',
        ok: !peerCompanies.value.some((p) => p.name.trim() && !p.source.trim()),
        label: '同业信息来源齐全',
        hint: '已填名称的同业公司须注明年报附注等来源',
      },
      {
        id: 'cross',
        ok: !crossCheckIssues.value.some((i) => i.severity === 'error'),
        label: '无阻断性交叉校验问题',
        hint: crossCheckIssues.value.filter((i) => i.severity === 'error').map((i) => i.message).join('；') || '通过',
      },
      {
        id: 'note',
        ok: !!auditNote.value?.trim(),
        label: '审计说明已填写',
        hint: '记录同业选取、重大判断与变更影响',
      },
    ]
    if (hasAnyChange.value) {
      const priorsOk = categoriesWithChange.value.every((cat) => {
        const p = priorEstimates.value.find((x) => x.category === cat)
        return !!(p?.usefulLife || p?.depMethod)
      })
      items.push({
        id: 'prior',
        ok: priorsOk,
        label: '表C原估计已填',
        hint: '存在变更的类别须列示变更前参数',
      })
    }
    return items
  })

  const completenessOk = computed(() => completeness.value.every((c) => c.ok))

  const gateBlockers = computed(() =>
    completeness.value.filter((c) => !c.ok).map((c) => `${c.label}：${c.hint}`),
  )

  const completionProgress = computed(() => {
    const items = completeness.value
    if (!items.length) return 0
    const done = items.filter((c) => c.ok).length
    return Math.round((done / items.length) * 100)
  })

  const completedCount = computed(() => sectionCompletedCount.value)

  const h12ChangeHint = computed(() => {
    const n = _parseH12Rows().filter((r) => r.estimateChangeDate || r.usefulLifeBefore != null || r.salvageRateBefore != null).length
    return n > 0 ? `H1-12 有 ${n} 行含估计变更字段，可一键带入表C` : ''
  })

  // ─── Sync 表C ──────────────────────────────────────────────────────────────

  function _syncPriorEstimatesFromChanges(): void {
    const changed = categoriesWithChange.value
    const existing = new Map(priorEstimates.value.map((r) => [r.category, r]))
    priorEstimates.value = changed.map((cat) => existing.get(cat) ?? _emptyPrior(cat))
    _persistPriors()
  }

  // ─── Update ────────────────────────────────────────────────────────────────

  function updateSection(key: string, field: keyof PolicySection, value: any): void {
    const section = sections.value.find((s) => s.key === key)
    if (!section) return
    ;(section as any)[field] = value
    _persistSections()
  }

  function persistSections(): void {
    _persistSections()
  }

  function updateDepParam(rowId: string, field: keyof DepParamRow, value: any): void {
    const row = depParams.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'hasChange') {
      if (value !== 'Y') row.changeReasonable = ''
      _syncPriorEstimatesFromChanges()
    }
    if (['meetsStandards', 'matchesEconomicBenefit', 'reasonableVsPeers', 'hasChange', 'changeReasonable'].includes(field)) {
      _autoOverallReasonable(row)
    }
    if (['usefulLifeMin', 'usefulLifeMax', 'salvageRate', 'depMethod', 'category'].includes(field)) {
      _refreshDetailMismatchFlags()
    }
    _persistParams()
  }

  function persistDepParams(): void {
    _refreshDetailMismatchFlags()
    _persistParams()
  }

  function _autoOverallReasonable(row: DepParamRow): void {
    const checks: YnNa[] = [
      row.meetsStandards,
      row.matchesEconomicBenefit,
      row.reasonableVsPeers,
      row.hasChange === 'Y' ? row.changeReasonable : 'Y',
    ]
    if (checks.some((c) => !c)) return
    row.isReasonable = checks.some((c) => c === 'N') ? 'N' : 'Y'
  }

  function addDepParam(category = ''): void {
    depParams.value.push(_emptyDepRow(category))
    _syncPeerCategories()
    _persistParams()
  }

  function removeDepParam(rowId: string): void {
    const idx = depParams.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      depParams.value.splice(idx, 1)
      _syncPriorEstimatesFromChanges()
      _syncPeerCategories()
      _persistParams()
    }
  }

  function updatePeerCompany(peerId: string, field: keyof PeerCompany, value: string): void {
    const peer = peerCompanies.value.find((p) => p.peerId === peerId)
    if (!peer) return
    ;(peer as any)[field] = value
    _persistPeers()
  }

  function updatePeerCell(category: string, peerId: string, field: keyof PeerCell, value: any): void {
    const row = peerPolicies.value.find((r) => r.category === category)
    if (!row) return
    if (!row.values[peerId]) row.values[peerId] = _emptyPeerCell()
    ;(row.values[peerId] as any)[field] = value
    _persistPeers()
  }

  function persistPeers(): void {
    _persistPeers()
  }

  function updatePriorEstimate(category: string, field: keyof PriorEstimateRow, value: any): void {
    const row = priorEstimates.value.find((r) => r.category === category)
    if (!row) return
    ;(row as any)[field] = value
    if (field !== 'source') row.source = row.source || 'manual'
    _persistPriors()
  }

  function persistPriors(): void {
    _persistPriors()
  }

  function setAuditNote(text: string): void {
    auditNote.value = text
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, text)
  }

  // ─── Import / Export pack ──────────────────────────────────────────────────

  function buildExportPack(auditConclusion = ''): H15ExportPack {
    return {
      version: 1,
      exportedAt: new Date().toISOString(),
      sections: sections.value,
      depParams: depParams.value,
      peers: { companies: peerCompanies.value, policies: peerPolicies.value },
      priorEstimates: priorEstimates.value,
      auditNote: auditNote.value,
      auditConclusion,
    }
  }

  function importExportPack(pack: H15ExportPack | any): { ok: boolean; message: string } {
    if (!pack || pack.version !== 1) {
      return { ok: false, message: '无效的 H1-5 导出包（需要 version=1）' }
    }
    if (Array.isArray(pack.sections)) sections.value = pack.sections.map(_normalizePolicySection)
    if (Array.isArray(pack.depParams)) depParams.value = pack.depParams.map(_normalizeDepParam)
    if (pack.peers?.companies) {
      peerCompanies.value = pack.peers.companies.map(_normalizePeerCompany)
      peerPolicies.value = Array.isArray(pack.peers.policies)
        ? pack.peers.policies.map((r: any) => _normalizePeerPolicyRow(r, peerCompanies.value))
        : _buildDefaultPeerPolicies(peerCompanies.value)
    }
    if (Array.isArray(pack.priorEstimates)) {
      priorEstimates.value = pack.priorEstimates.map(_normalizePriorEstimate)
    }
    if (typeof pack.auditNote === 'string') {
      auditNote.value = pack.auditNote
      options?.onSave?.(`${ITEM_PREFIX}-audit-note`, pack.auditNote)
    }
    _persistSections()
    _persistParams()
    _persistPeers()
    _persistPriors()
    return { ok: true, message: '已导入 H1-5 数据包' }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistSections(): void {
    options?.onSave?.(`${ITEM_PREFIX}-sections`, sections.value)
  }

  function _persistParams(): void {
    options?.onSave?.(`${ITEM_PREFIX}-dep-params`, depParams.value)
  }

  function _persistPeers(): void {
    options?.onSave?.(`${ITEM_PREFIX}-peers`, {
      companies: peerCompanies.value,
      policies: peerPolicies.value,
    })
  }

  function _persistPriors(): void {
    options?.onSave?.(`${ITEM_PREFIX}-prior-estimates`, priorEstimates.value)
  }

  watch(allResponses, () => _loadData(), { immediate: true })

  return {
    sections,
    depParams,
    peerCompanies,
    peerPolicies,
    priorEstimates,
    auditNote,
    categoriesWithChange,
    showPriorEstimates,
    hasAnyChange,
    peerLifeHints,
    peerRanges,
    peerDeviations,
    categoriesNeedingDeviationRemark,
    crossCheckIssues,
    completeness,
    completenessOk,
    gateBlockers,
    completionProgress,
    completedCount,
    sectionCompletedCount,
    depCompletedCount,
    h12ChangeHint,
    updateSection,
    persistSections,
    updateDepParam,
    persistDepParams,
    addDepParam,
    removeDepParam,
    updatePeerCompany,
    updatePeerCell,
    persistPeers,
    updatePriorEstimate,
    persistPriors,
    setAuditNote,
    syncFromDetail,
    applyPriorYearResponses,
    syncPriorsFromH12,
    applyIndustryTemplate,
    suggestJudgmentsFromPeers,
    buildExportPack,
    importExportPack,
    SECTION_DEFINITIONS,
    DEP_METHOD_OPTIONS,
    YN_OPTIONS,
    INDUSTRY_TEMPLATES,
  }
}

export default useH1PolicyCheck
