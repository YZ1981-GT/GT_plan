/**
 * useI1PolicyCheck — I1-4 无形资产摊销/减值政策检查
 * 对齐源 xlsx「无形资产摊销政策检查表 I1-4」：
 *   表A 被审计单位政策 + 五维判断
 *   表B 同行业对标（最多4家）
 *   表C 估计变更原估计
 * 并保留 CAS6/CAS8 段落评价（Req 5）。
 */
import { ref, computed, watch, type Ref } from 'vue'

export type Yn = '' | 'Y' | 'N' | 'NA'
export type CasConclusion = '' | '是' | '否' | '不适用'

export interface CasCheckItem {
  key: string
  label: string
  casRef: string
  actualPolicy: string
  evaluation: string
  conclusion: CasConclusion
  explanationIfNo: string
}

export interface PolicyParamRow {
  rowId: string
  category: string
  usefulLife: string
  amortMethod: string
  meetsStandards: Yn
  matchesEconomicBenefit: Yn
  reasonableVsPeers: Yn
  hasChange: Yn
  changeReasonable: Yn
  remark: string
  detailCount?: number
}

export interface PeerCompany {
  peerId: string
  name: string
  source: string
}

export interface PeerCell {
  usefulLife: string
  amortMethod: string
}

export interface PeerPolicyRow {
  category: string
  cells: Record<string, PeerCell>
}

export interface PriorEstimateRow {
  rowId: string
  category: string
  usefulLife: string
  amortMethod: string
  impactAmount: number | null
  remark: string
}

export const DEFAULT_CATEGORIES = [
  '土地使用权',
  '专利权',
  '非专利技术',
  '商标权',
  '著作权',
  '软件',
  '特许权',
  '数据资源',
  '其他',
]

export const AMORT_METHOD_OPTIONS = ['直线法', '产量法', '年数总和法', '不摊销（寿命不确定）', '其他']

export const CAS_CHECK_DEFS: Omit<CasCheckItem, 'actualPolicy' | 'evaluation' | 'conclusion' | 'explanationIfNo'>[] = [
  {
    key: 'amort-method',
    label: '摊销方法',
    casRef: 'CAS6§19：摊销方法应反映经济利益预期消耗方式；无法可靠确定时应当采用直线法。',
  },
  {
    key: 'useful-life',
    label: '使用寿命确定',
    casRef: 'CAS6§11-15：判断寿命有限或不确定；有限者估计期限或产量等；不确定者每期末复核。',
  },
  {
    key: 'salvage-rate',
    label: '残值率确定',
    casRef: 'CAS6§16：残值通常为零，除非有第三方购买承诺或活跃市场残值信息。',
  },
  {
    key: 'impairment-indication',
    label: '减值迹象判断',
    casRef: 'CAS8§4-5：每年末评估减值迹象（技术陈旧/市场变化/法律限制/绩效低于预期等）。',
  },
  {
    key: 'impairment-test-frequency',
    label: '减值测试频率',
    casRef: 'CAS8§6：寿命不确定及尚未达到可使用状态的无形资产，无论是否存在迹象，每年至少测试一次。',
  },
  {
    key: 'amort-start-date',
    label: '摊销起始时点',
    casRef: 'CAS6§17：自达到预定用途之日起摊销；处置当月不再摊销。',
  },
  {
    key: 'amort-period-review',
    label: '摊销期限/方法复核',
    casRef: 'CAS6§21-22：至少每年末复核寿命与摊销方法；变更按会计估计变更（未来适用法）。',
  },
]

export interface IndustryTemplate {
  id: string
  label: string
  peers: { name: string; source: string }[]
  /** category → peerIndex → { usefulLife, amortMethod } */
  policies: Record<string, Array<{ usefulLife: string; amortMethod: string }>>
}

/** 示意性行业模板（便于起步；实务应以年报附注核实） */
export const INDUSTRY_TEMPLATES: IndustryTemplate[] = [
  {
    id: 'software',
    label: '软件/互联网（示意）',
    peers: [
      { name: '用友网络', source: '年报附注·无形资产' },
      { name: '金山办公', source: '年报附注·无形资产' },
      { name: '石基信息', source: '年报附注·无形资产' },
      { name: '恒生电子', source: '年报附注·无形资产' },
    ],
    policies: {
      软件: [
        { usefulLife: '2-10年', amortMethod: '直线法' },
        { usefulLife: '3-10年', amortMethod: '直线法' },
        { usefulLife: '2-5年', amortMethod: '直线法' },
        { usefulLife: '3-10年', amortMethod: '直线法' },
      ],
      土地使用权: [
        { usefulLife: '50年', amortMethod: '直线法' },
        { usefulLife: '50年', amortMethod: '直线法' },
        { usefulLife: '40-50年', amortMethod: '直线法' },
        { usefulLife: '50年', amortMethod: '直线法' },
      ],
      专利权: [
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
      ],
    },
  },
  {
    id: 'pharma',
    label: '医药（示意）',
    peers: [
      { name: '恒瑞医药', source: '年报附注·无形资产' },
      { name: '复星医药', source: '年报附注·无形资产' },
      { name: '华东医药', source: '年报附注·无形资产' },
      { name: '华润三九', source: '年报附注·无形资产' },
    ],
    policies: {
      专利权: [
        { usefulLife: '10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '10年', amortMethod: '直线法' },
        { usefulLife: '10年', amortMethod: '直线法' },
      ],
      非专利技术: [
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
      ],
      土地使用权: [
        { usefulLife: '30-50年', amortMethod: '直线法' },
        { usefulLife: '40-50年', amortMethod: '直线法' },
        { usefulLife: '50年', amortMethod: '直线法' },
        { usefulLife: '50年', amortMethod: '直线法' },
      ],
      商标权: [
        { usefulLife: '10年', amortMethod: '直线法' },
        { usefulLife: '10年', amortMethod: '直线法' },
        { usefulLife: '10年', amortMethod: '直线法' },
        { usefulLife: '10年', amortMethod: '直线法' },
      ],
    },
  },
  {
    id: 'manufacturing',
    label: '制造业（示意）',
    peers: [
      { name: '三一重工', source: '年报附注·无形资产' },
      { name: '中联重科', source: '年报附注·无形资产' },
      { name: '海螺水泥', source: '年报附注·无形资产' },
      { name: '中国中铁', source: '年报附注·无形资产' },
    ],
    policies: {
      土地使用权: [
        { usefulLife: '50年', amortMethod: '直线法' },
        { usefulLife: '50年', amortMethod: '直线法' },
        { usefulLife: '50年', amortMethod: '直线法' },
        { usefulLife: '50年', amortMethod: '直线法' },
      ],
      软件: [
        { usefulLife: '2-10年', amortMethod: '直线法' },
        { usefulLife: '3-10年', amortMethod: '直线法' },
        { usefulLife: '2-5年', amortMethod: '直线法' },
        { usefulLife: '3-5年', amortMethod: '直线法' },
      ],
      专利权: [
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
        { usefulLife: '10年', amortMethod: '直线法' },
        { usefulLife: '5-10年', amortMethod: '直线法' },
      ],
    },
  },
]

const ITEM_CAS = 'I1-4-cas-items'
const ITEM_PARAMS = 'I1-4-policy-params'
const ITEM_PEERS = 'I1-4-peer-companies'
const ITEM_PEER_POLICIES = 'I1-4-peer-policies'
const ITEM_PRIORS = 'I1-4-prior-estimates'
const ITEM_NOTE = 'I1-4-audit-note'
const ITEM_CONCLUSION = 'I1-4-overall-conclusion'

function _id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function _emptyParam(category = ''): PolicyParamRow {
  return {
    rowId: _id('p'),
    category,
    usefulLife: '',
    amortMethod: '直线法',
    meetsStandards: '',
    matchesEconomicBenefit: '',
    reasonableVsPeers: '',
    hasChange: '',
    changeReasonable: '',
    remark: '',
  }
}

function _emptyPeerCell(): PeerCell {
  return { usefulLife: '', amortMethod: '' }
}

function _defaultPeers(): PeerCompany[] {
  return [1, 2, 3, 4].map((i) => ({
    peerId: `peer-${i}`,
    name: '',
    source: '',
  }))
}

function _parseJson<T>(raw: any, fallback: T): T {
  if (raw == null) return fallback
  try {
    const v = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (v && typeof v === 'object' && ('remark' in v || 'conclusion' in v)) {
      const inner = (v as any).remark ?? (v as any).conclusion
      if (typeof inner === 'string') {
        try { return JSON.parse(inner) as T } catch { return (inner as T) ?? fallback }
      }
      if (inner != null && typeof inner !== 'string') return inner as T
    }
    return v as T
  } catch {
    return fallback
  }
}

function _responseText(raw: any): string {
  if (raw == null) return ''
  if (typeof raw === 'string') return raw
  return String(raw.remark ?? raw.conclusion ?? raw.text ?? '')
}

/** 从 I1-2 明细聚合类别及寿命众数（简易） */
export function aggregateCategoriesFromDetail(rows: any[]): Array<{
  category: string
  usefulLife: string
  amortMethod: string
  detailCount: number
}> {
  const map = new Map<string, { lives: string[]; methods: string[]; count: number }>()
  for (const item of rows) {
    const cat = String(item.category ?? item.assetCategory ?? '其他').trim() || '其他'
    let lifeStr = ''
    if (item.usefulLifeMonths != null && Number(item.usefulLifeMonths) > 0) {
      const months = Number(item.usefulLifeMonths)
      const years = Math.round((months / 12) * 10) / 10
      lifeStr = `${years}年`
    } else if (item.usefulLifeYears != null && Number(item.usefulLifeYears) > 0) {
      lifeStr = `${Number(item.usefulLifeYears)}年`
    } else if (item.usefulLife != null && Number(item.usefulLife) > 0) {
      const n = Number(item.usefulLife)
      // 无单位字段时：>100 视为月，否则视为年
      lifeStr = n > 100 ? `${Math.round((n / 12) * 10) / 10}年` : `${n}年`
    }
    const method = String(item.amortMethod ?? item.depreciationMethod ?? '直线法')
    const cur = map.get(cat) ?? { lives: [], methods: [], count: 0 }
    if (lifeStr) cur.lives.push(lifeStr)
    if (method) cur.methods.push(method)
    cur.count++
    map.set(cat, cur)
  }
  return [...map.entries()].map(([category, v]) => {
    const usefulLife = modeOf(v.lives) || ''
    const amortMethod = modeOf(v.methods) || '直线法'
    return { category, usefulLife, amortMethod, detailCount: v.count }
  })
}

function modeOf(arr: string[]): string {
  if (!arr.length) return ''
  const freq = new Map<string, number>()
  for (const x of arr) freq.set(x, (freq.get(x) ?? 0) + 1)
  return [...freq.entries()].sort((a, b) => b[1] - a[1])[0][0]
}

export function useI1PolicyCheck(
  allResponses: Ref<Map<string, any>>,
  options?: { onSave?: (itemId: string, value: any) => void },
) {
  const casItems = ref<CasCheckItem[]>(
    CAS_CHECK_DEFS.map((d) => ({
      ...d,
      actualPolicy: '',
      evaluation: '',
      conclusion: '' as CasConclusion,
      explanationIfNo: '',
    })),
  )
  const policyParams = ref<PolicyParamRow[]>(DEFAULT_CATEGORIES.map((c) => _emptyParam(c)))
  const peerCompanies = ref<PeerCompany[]>(_defaultPeers())
  const peerPolicies = ref<PeerPolicyRow[]>([])
  const priorEstimates = ref<PriorEstimateRow[]>([])
  const auditNote = ref('')
  const overallConclusion = ref('')

  function _ensurePeerRows() {
    const cats = policyParams.value.map((r) => r.category).filter(Boolean)
    const existing = new Map(peerPolicies.value.map((r) => [r.category, r]))
    peerPolicies.value = cats.map((category) => {
      const prev = existing.get(category)
      const cells: Record<string, PeerCell> = {}
      for (const p of peerCompanies.value) {
        cells[p.peerId] = prev?.cells?.[p.peerId] ?? _emptyPeerCell()
      }
      return { category, cells }
    })
  }

  function load() {
    const map = allResponses.value
    if (!map) return

    const casRaw = _parseJson<any[]>(map.get(ITEM_CAS), null as any)
    if (Array.isArray(casRaw) && casRaw.length) {
      const byKey = new Map(casRaw.map((x: any) => [x.key, x]))
      casItems.value = CAS_CHECK_DEFS.map((d) => {
        const s = byKey.get(d.key)
        return {
          ...d,
          actualPolicy: s?.actualPolicy ?? '',
          evaluation: s?.evaluation ?? '',
          conclusion: (s?.conclusion ?? '') as CasConclusion,
          explanationIfNo: s?.explanationIfNo ?? '',
        }
      })
    } else {
      // 兼容旧版逐项 I1-4-{key} 存储
      casItems.value = CAS_CHECK_DEFS.map((d) => {
        const saved = map.get(`I1-4-${d.key}`)
        const data = _parseJson<any>(saved, {})
        return {
          ...d,
          actualPolicy: data.actualPolicy ?? '',
          evaluation: data.evaluation ?? '',
          conclusion: (data.conclusion ?? '') as CasConclusion,
          explanationIfNo: data.explanationIfNo ?? '',
        }
      })
    }

    const params = _parseJson<PolicyParamRow[]>(map.get(ITEM_PARAMS), null as any)
    if (Array.isArray(params) && params.length) {
      policyParams.value = params.map((p) => ({ ..._emptyParam(), ...p, rowId: p.rowId || _id('p') }))
    }

    const peers = _parseJson<PeerCompany[]>(map.get(ITEM_PEERS), null as any)
    if (Array.isArray(peers) && peers.length) {
      peerCompanies.value = peers.slice(0, 4).map((p, i) => ({
        peerId: p.peerId || `peer-${i + 1}`,
        name: p.name ?? '',
        source: p.source ?? '',
      }))
      while (peerCompanies.value.length < 4) {
        peerCompanies.value.push({ peerId: `peer-${peerCompanies.value.length + 1}`, name: '', source: '' })
      }
    }

    const peerPol = _parseJson<PeerPolicyRow[]>(map.get(ITEM_PEER_POLICIES), null as any)
    if (Array.isArray(peerPol)) peerPolicies.value = peerPol
    _ensurePeerRows()

    const priors = _parseJson<PriorEstimateRow[]>(map.get(ITEM_PRIORS), null as any)
    if (Array.isArray(priors)) priorEstimates.value = priors

    auditNote.value = _responseText(map.get(ITEM_NOTE))
    overallConclusion.value = _responseText(map.get(ITEM_CONCLUSION))
  }

  function persistCas() {
    options?.onSave?.(ITEM_CAS, casItems.value)
  }
  function persistParams() {
    options?.onSave?.(ITEM_PARAMS, policyParams.value)
    _ensurePeerRows()
    options?.onSave?.(ITEM_PEER_POLICIES, peerPolicies.value)
    syncPriorsFromChanges()
  }
  function persistPeers() {
    options?.onSave?.(ITEM_PEERS, peerCompanies.value)
    _ensurePeerRows()
    options?.onSave?.(ITEM_PEER_POLICIES, peerPolicies.value)
  }
  function persistPriors() {
    options?.onSave?.(ITEM_PRIORS, priorEstimates.value)
  }
  function persistNote() {
    options?.onSave?.(ITEM_NOTE, auditNote.value)
  }
  function persistConclusion() {
    options?.onSave?.(ITEM_CONCLUSION, overallConclusion.value)
  }

  function syncPriorsFromChanges() {
    const changed = policyParams.value.filter((r) => r.hasChange === 'Y')
    const existing = new Map(priorEstimates.value.map((p) => [p.category, p]))
    priorEstimates.value = changed.map((r) => {
      const prev = existing.get(r.category)
      return prev ?? {
        rowId: _id('prior'),
        category: r.category,
        usefulLife: '',
        amortMethod: '',
        impactAmount: null,
        remark: '',
      }
    })
    persistPriors()
  }

  const showPriorEstimates = computed(() => policyParams.value.some((r) => r.hasChange === 'Y'))

  const hasAnyChange = computed(() => showPriorEstimates.value)
  const changedCategories = computed(() =>
    policyParams.value
      .filter((r) => r.hasChange === 'Y' && r.category)
      .map((r) => r.category),
  )

  const lastAppliedTemplateLabel = ref('')

  const casCompleted = computed(() =>
    casItems.value.filter((i) => !!i.conclusion && (i.conclusion !== '否' || !!i.explanationIfNo)).length,
  )

  const paramsJudged = computed(() =>
    policyParams.value.filter((r) =>
      r.category && r.meetsStandards && r.matchesEconomicBenefit && r.reasonableVsPeers && r.hasChange
      && (r.hasChange !== 'Y' || r.changeReasonable),
    ).length,
  )

  const completeness = computed(() => {
    const checks = [
      {
        id: 'cas',
        label: 'CAS段落评价已完成',
        ok: casCompleted.value === casItems.value.length,
        hint: `${casCompleted.value}/${casItems.value.length}`,
      },
      {
        id: 'params',
        label: '表A五维判断已填',
        ok: paramsJudged.value >= Math.min(1, policyParams.value.filter((r) => r.category).length)
          && paramsJudged.value === policyParams.value.filter((r) => r.category).length,
        hint: `${paramsJudged.value}/${policyParams.value.filter((r) => r.category).length}`,
      },
      {
        id: 'peers',
        label: '表B至少填写1家同业及来源',
        ok: peerCompanies.value.some((p) => p.name && p.source),
        hint: peerCompanies.value.filter((p) => p.name).length + '家',
      },
      {
        id: 'priors',
        label: '有变更时表C已填原估计',
        ok: !hasAnyChange.value || priorEstimates.value.every((p) => p.usefulLife || p.amortMethod),
        hint: hasAnyChange.value ? `${priorEstimates.value.length}行` : '无变更',
      },
      {
        id: 'conclusion',
        label: '审计结论已填写',
        ok: overallConclusion.value.trim().length >= 8,
        hint: overallConclusion.value ? '已填' : '未填',
      },
    ]
    return checks
  })

  const completionProgress = computed(() => {
    const list = completeness.value
    if (!list.length) return 0
    return Math.round((list.filter((c) => c.ok).length / list.length) * 100)
  })

  const completenessOk = computed(() => completeness.value.every((c) => c.ok))

  const negativeJudgments = computed(() =>
    policyParams.value.filter((r) =>
      r.meetsStandards === 'N'
      || r.matchesEconomicBenefit === 'N'
      || r.reasonableVsPeers === 'N'
      || r.changeReasonable === 'N',
    ),
  )

  function addParamRow(category = '') {
    policyParams.value.push(_emptyParam(category))
    persistParams()
  }

  function removeParamRow(rowId: string) {
    policyParams.value = policyParams.value.filter((r) => r.rowId !== rowId)
    persistParams()
  }

  function syncFromDetail(detailRows: any[]) {
    const agg = aggregateCategoriesFromDetail(detailRows)
    if (!agg.length) return 0
    const byCat = new Map(policyParams.value.map((r) => [r.category, r]))
    const next: PolicyParamRow[] = []
    for (const a of agg) {
      const prev = byCat.get(a.category)
      if (prev) {
        prev.usefulLife = a.usefulLife || prev.usefulLife
        prev.amortMethod = a.amortMethod || prev.amortMethod
        prev.detailCount = a.detailCount
        next.push(prev)
      } else {
        next.push({
          ..._emptyParam(a.category),
          usefulLife: a.usefulLife,
          amortMethod: a.amortMethod,
          detailCount: a.detailCount,
        })
      }
    }
    // 保留手工新增但明细中没有的类别
    for (const r of policyParams.value) {
      if (r.category && !agg.some((a) => a.category === r.category)) next.push(r)
    }
    policyParams.value = next
    persistParams()
    return agg.length
  }

  function applyIndustryTemplate(templateId: string) {
    const tpl = INDUSTRY_TEMPLATES.find((t) => t.id === templateId)
    if (!tpl) return
    lastAppliedTemplateLabel.value = tpl.label
    peerCompanies.value = tpl.peers.map((p, i) => ({
      peerId: `peer-${i + 1}`,
      name: p.name,
      source: String(p.source || '').includes('示意')
        ? p.source
        : `示意·${p.source || '行业模板'}`,
    }))
    const cats = [...new Set([
      ...policyParams.value.map((r) => r.category).filter(Boolean),
      ...Object.keys(tpl.policies),
    ])]
    peerPolicies.value = cats.map((category) => {
      const cells: Record<string, PeerCell> = {}
      const list = tpl.policies[category] ?? []
      peerCompanies.value.forEach((p, i) => {
        cells[p.peerId] = {
          usefulLife: list[i]?.usefulLife ?? '',
          amortMethod: list[i]?.amortMethod ?? '',
        }
      })
      return { category, cells }
    })
    // 确保表A有对应类别
    for (const cat of Object.keys(tpl.policies)) {
      if (!policyParams.value.some((r) => r.category === cat)) {
        policyParams.value.push(_emptyParam(cat))
      }
    }
    persistPeers()
    persistParams()
  }

  function updatePeerCell(category: string, peerId: string, field: keyof PeerCell, value: string) {
    const row = peerPolicies.value.find((r) => r.category === category)
    if (!row) return
    if (!row.cells[peerId]) row.cells[peerId] = _emptyPeerCell()
    row.cells[peerId][field] = value
    options?.onSave?.(ITEM_PEER_POLICIES, peerPolicies.value)
  }

  function suggestConclusionTemplate(): string {
    const neg = negativeJudgments.value.length
    const changed = hasAnyChange.value
    if (neg === 0 && !changed) {
      return 'A、经检查，被审计单位无形资产摊销及减值相关会计政策/估计符合CAS6、CAS8要求，与实际经营及同行业比较未见重大不合理，前后期一贯，可确认。'
    }
    if (neg === 0 && changed) {
      return 'B、本期存在会计估计变更，已按未来适用法处理并记录原估计及影响；除下列事项外，摊销/减值政策未见异常：……'
    }
    return 'C、下列类别政策/估计判断为不合理或与准则不符，需进一步评估错报影响并考虑调整/披露：……'
  }

  watch(allResponses, load, { immediate: true })

  return {
    casItems,
    policyParams,
    peerCompanies,
    peerPolicies,
    priorEstimates,
    auditNote,
    overallConclusion,
    showPriorEstimates,
    hasAnyChange,
    changedCategories,
    lastAppliedTemplateLabel,
    completeness,
    completionProgress,
    completenessOk,
    negativeJudgments,
    AMORT_METHOD_OPTIONS,
    INDUSTRY_TEMPLATES,
    persistCas,
    persistParams,
    persistPeers,
    persistPriors,
    persistNote,
    persistConclusion,
    addParamRow,
    removeParamRow,
    syncFromDetail,
    applyIndustryTemplate,
    updatePeerCell,
    suggestConclusionTemplate,
    load,
  }
}

export default useI1PolicyCheck
