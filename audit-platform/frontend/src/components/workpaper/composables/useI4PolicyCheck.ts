/**
 * useI4PolicyCheck — I4-4 长期待摊费用摊销政策检查
 * 对齐源 xlsx「摊销政策检查表 I4-4」：
 *   表A 被审计单位政策 + 五维判断
 *   表B 同行业对标（最多4家）
 *   表C 估计变更原估计
 * 并补充政策要点评价（受益模式/期限/资本化边界/变更）。
 */
import { ref, computed, watch, type Ref } from 'vue'
import {
  crossCheckPolicyVsAmort,
  buildAttentionRemarksFromIssues,
  significantDiffAmounts,
  type CrossCheckResult,
} from './i4PolicyAmortCrossCheck'
import {
  computePeerRanges,
  computePeerDeviations,
  suggestReasonableVsPeers,
  suggestReasonableYForInRange,
  categoriesNeedingPeerRemark,
} from './i4PolicyPeerRange'
import { buildI4AmortSupplementDraft } from './useI4Adjustment'
import { recommendPeerIndustry, type IndustryHint } from './i4PolicyIndustryHint'
import {
  checkLeaseShorterRule,
  checkPolicyVsLeaseByCategory,
  type LeaseShorterResult,
} from './i4PolicyLeaseShorter'

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
  benefitPeriod: string
  amortMethod: string
  meetsStandards: Yn
  matchesBenefitPattern: Yn
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
  benefitPeriod: string
  amortMethod: string
}

export interface PeerPolicyRow {
  category: string
  cells: Record<string, PeerCell>
}

export interface PriorEstimateRow {
  rowId: string
  category: string
  benefitPeriod: string
  amortMethod: string
  impactAmount: number | null
  remark: string
}

export const DEFAULT_CATEGORIES = [
  '装修费',
  '开办费',
  '租赁改良',
  '低值易耗品',
  '其他',
]

export const AMORT_METHOD_OPTIONS = ['直线法', '工作量法', '其他']

export const CAS_CHECK_DEFS: Omit<CasCheckItem, 'actualPolicy' | 'evaluation' | 'conclusion' | 'explanationIfNo'>[] = [
  {
    key: 'amort-method',
    label: '摊销方法与受益模式',
    casRef: '长期待摊费用应按受益期间系统摊销；方法应反映费用受益模式。受益均匀分布通常用直线法，与产出相关可用工作量法。',
  },
  {
    key: 'benefit-period',
    label: '受益期限确定',
    casRef: '装修/租赁改良：不超过租赁期与预计使用年限孰短。开办费：按受益期合理估计（关注税会差异）。其他：合同约定或预计受益年限，无约定时审慎估计且不宜过长。',
  },
  {
    key: 'capitalize-boundary',
    label: '资本化与费用化边界',
    casRef: '仅将符合长期待摊确认条件的支出资本化；日常修理、期间费用不得计入长期待摊。关注跨期确认与重分类至固定资产/无形资产。',
  },
  {
    key: 'amort-start',
    label: '摊销起始时点',
    casRef: '自达到可使用/开始受益之日起摊销；提前终止、到期清算时剩余净值应一次性计入当期损益。',
  },
  {
    key: 'estimate-change',
    label: '会计估计变更（CAS28）',
    casRef: 'CAS28：受益期限变更属会计估计变更，采用未来适用法；摊销方法变更通常亦按估计变更处理。须披露变更内容、原因及影响金额。',
  },
]

export interface IndustryTemplate {
  id: string
  label: string
  peers: { name: string; source: string }[]
  policies: Record<string, Array<{ benefitPeriod: string; amortMethod: string }>>
}

/** 示意性行业模板（便于起步；实务应以年报附注核实） */
export const INDUSTRY_TEMPLATES: IndustryTemplate[] = [
  {
    id: 'retail',
    label: '零售/连锁（示意）',
    peers: [
      { name: '永辉超市', source: '年报附注·长期待摊费用' },
      { name: '红旗连锁', source: '年报附注·长期待摊费用' },
      { name: '家家悦', source: '年报附注·长期待摊费用' },
      { name: '步步高', source: '年报附注·长期待摊费用' },
    ],
    policies: {
      装修费: [
        { benefitPeriod: '3-5年/租赁期孰短', amortMethod: '直线法' },
        { benefitPeriod: '租赁期', amortMethod: '直线法' },
        { benefitPeriod: '3-5年', amortMethod: '直线法' },
        { benefitPeriod: '租赁期孰短', amortMethod: '直线法' },
      ],
      租赁改良: [
        { benefitPeriod: '租赁期', amortMethod: '直线法' },
        { benefitPeriod: '租赁期', amortMethod: '直线法' },
        { benefitPeriod: '租赁剩余期限', amortMethod: '直线法' },
        { benefitPeriod: '租赁期', amortMethod: '直线法' },
      ],
    },
  },
  {
    id: 'manufacturing',
    label: '制造业（示意）',
    peers: [
      { name: '三一重工', source: '年报附注·长期待摊费用' },
      { name: '中联重科', source: '年报附注·长期待摊费用' },
      { name: '海螺水泥', source: '年报附注·长期待摊费用' },
      { name: '徐工机械', source: '年报附注·长期待摊费用' },
    ],
    policies: {
      装修费: [
        { benefitPeriod: '5年', amortMethod: '直线法' },
        { benefitPeriod: '3-5年', amortMethod: '直线法' },
        { benefitPeriod: '5年', amortMethod: '直线法' },
        { benefitPeriod: '3-10年', amortMethod: '直线法' },
      ],
      开办费: [
        { benefitPeriod: '3-5年', amortMethod: '直线法' },
        { benefitPeriod: '5年', amortMethod: '直线法' },
        { benefitPeriod: '3年', amortMethod: '直线法' },
        { benefitPeriod: '5年', amortMethod: '直线法' },
      ],
      其他: [
        { benefitPeriod: '受益期', amortMethod: '直线法/工作量法' },
        { benefitPeriod: '受益期', amortMethod: '直线法' },
        { benefitPeriod: '受益期', amortMethod: '直线法' },
        { benefitPeriod: '受益期', amortMethod: '直线法' },
      ],
    },
  },
  {
    id: 'property',
    label: '物业/商业地产（示意）',
    peers: [
      { name: '万科企业', source: '年报附注·长期待摊费用' },
      { name: '保利发展', source: '年报附注·长期待摊费用' },
      { name: '华润置地', source: '年报附注·长期待摊费用' },
      { name: '龙湖集团', source: '年报附注·长期待摊费用' },
    ],
    policies: {
      装修费: [
        { benefitPeriod: '租赁期/3-5年孰短', amortMethod: '直线法' },
        { benefitPeriod: '租赁期孰短', amortMethod: '直线法' },
        { benefitPeriod: '租赁期', amortMethod: '直线法' },
        { benefitPeriod: '3-5年', amortMethod: '直线法' },
      ],
      租赁改良: [
        { benefitPeriod: '租赁剩余期限', amortMethod: '直线法' },
        { benefitPeriod: '租赁期', amortMethod: '直线法' },
        { benefitPeriod: '租赁期', amortMethod: '直线法' },
        { benefitPeriod: '租赁期孰短', amortMethod: '直线法' },
      ],
    },
  },
]

const ITEM_CAS = 'I4-4-cas-items'
const ITEM_PARAMS = 'I4-4-policy-params'
const ITEM_PEERS = 'I4-4-peer-companies'
const ITEM_PEER_POLICIES = 'I4-4-peer-policies'
const ITEM_PRIORS = 'I4-4-prior-estimates'
const ITEM_NOTE = 'I4-4-audit-note'
const ITEM_CONCLUSION = 'I4-4-overall-conclusion'

/** 旧版自由文本键（迁移兼容） */
const LEGACY_METHOD = 'I4-4-amortization-method'
const LEGACY_PERIOD = 'I4-4-benefit-period'
const LEGACY_CHANGE = 'I4-4-change-treatment'
const LEGACY_CONCLUSION = 'I4-4-conclusion'
const LEGACY_AUDIT_CONCLUSION = 'I4-policycheck-audit-conclusion'

function _id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function _emptyParam(category = ''): PolicyParamRow {
  return {
    rowId: _id('p'),
    category,
    benefitPeriod: '',
    amortMethod: '直线法',
    meetsStandards: '',
    matchesBenefitPattern: '',
    reasonableVsPeers: '',
    hasChange: '',
    changeReasonable: '',
    remark: '',
  }
}

function _emptyPeerCell(): PeerCell {
  return { benefitPeriod: '', amortMethod: '' }
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

function modeOf(arr: string[]): string {
  if (!arr.length) return ''
  const freq = new Map<string, number>()
  for (const x of arr) freq.set(x, (freq.get(x) ?? 0) + 1)
  return [...freq.entries()].sort((a, b) => b[1] - a[1])[0][0]
}

/** 从 I4-2 明细按费用类型聚合受益期限众数与摊销方法 */
export function aggregateCategoriesFromI4Detail(rows: any[]): Array<{
  category: string
  benefitPeriod: string
  amortMethod: string
  detailCount: number
}> {
  const map = new Map<string, { periods: string[]; methods: string[]; count: number }>()
  for (const item of rows) {
    const cat = String(item.expenseType ?? item.category ?? item.accountCategory ?? '其他').trim() || '其他'
    let periodStr = ''
    const months = Number(item.totalMonths ?? item.benefitMonths ?? 0)
    if (months > 0) {
      const years = Math.round((months / 12) * 10) / 10
      periodStr = Number.isInteger(years) ? `${years}年` : `${years}年（${months}月）`
    } else if (item.benefitPeriod != null && String(item.benefitPeriod).trim()) {
      periodStr = String(item.benefitPeriod).trim()
    }
    const method = String(item.amortizationMethod ?? item.amortMethod ?? '直线法')
    const cur = map.get(cat) ?? { periods: [], methods: [], count: 0 }
    if (periodStr) cur.periods.push(periodStr)
    if (method) cur.methods.push(method)
    cur.count++
    map.set(cat, cur)
  }
  return [...map.entries()].map(([category, v]) => ({
    category,
    benefitPeriod: modeOf(v.periods) || '',
    amortMethod: modeOf(v.methods) || '直线法',
    detailCount: v.count,
  }))
}

export function useI4PolicyCheck(
  allResponses: Ref<Map<string, any>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
    projectContext?: Ref<Record<string, any> | null | undefined> | { value: Record<string, any> | null | undefined }
  },
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
  const lastAppliedTemplateLabel = ref('')

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

  function _migrateLegacy(map: Map<string, any>) {
    const parts: string[] = []
    const m = _responseText(map.get(LEGACY_METHOD))
    const p = _responseText(map.get(LEGACY_PERIOD))
    const c = _responseText(map.get(LEGACY_CHANGE))
    if (m) parts.push(`【摊销方法】\n${m}`)
    if (p) parts.push(`【受益期限】\n${p}`)
    if (c) parts.push(`【估计变更】\n${c}`)
    if (parts.length && !auditNote.value.trim()) {
      auditNote.value = parts.join('\n\n')
    }
    const legacyCon =
      _responseText(map.get(LEGACY_AUDIT_CONCLUSION))
      || _responseText(map.get(LEGACY_CONCLUSION))
    if (legacyCon && !overallConclusion.value.trim()) {
      overallConclusion.value = legacyCon
    }
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
    }

    const params = _parseJson<PolicyParamRow[]>(map.get(ITEM_PARAMS), null as any)
    if (Array.isArray(params) && params.length) {
      policyParams.value = params.map((p) => ({
        ..._emptyParam(),
        ...p,
        // 兼容误存 usefulLife 的旧数据
        benefitPeriod: p.benefitPeriod || (p as any).usefulLife || '',
        rowId: p.rowId || _id('p'),
      }))
    }

    const peers = _parseJson<PeerCompany[]>(map.get(ITEM_PEERS), null as any)
    if (Array.isArray(peers) && peers.length) {
      peerCompanies.value = peers.slice(0, 4).map((p, i) => ({
        peerId: p.peerId || `peer-${i + 1}`,
        name: p.name ?? '',
        source: p.source ?? '',
      }))
      while (peerCompanies.value.length < 4) {
        peerCompanies.value.push({
          peerId: `peer-${peerCompanies.value.length + 1}`,
          name: '',
          source: '',
        })
      }
    }

    const peerPol = _parseJson<PeerPolicyRow[]>(map.get(ITEM_PEER_POLICIES), null as any)
    if (Array.isArray(peerPol)) {
      peerPolicies.value = peerPol.map((r) => {
        const cells: Record<string, PeerCell> = {}
        for (const [pid, cell] of Object.entries(r.cells ?? {})) {
          cells[pid] = {
            benefitPeriod: cell.benefitPeriod || (cell as any).usefulLife || '',
            amortMethod: cell.amortMethod || '',
          }
        }
        return { category: r.category, cells }
      })
    }
    _ensurePeerRows()

    const priors = _parseJson<PriorEstimateRow[]>(map.get(ITEM_PRIORS), null as any)
    if (Array.isArray(priors)) {
      priorEstimates.value = priors.map((p) => ({
        ...p,
        benefitPeriod: p.benefitPeriod || (p as any).usefulLife || '',
        rowId: p.rowId || _id('prior'),
      }))
    }

    auditNote.value = _responseText(map.get(ITEM_NOTE))
    overallConclusion.value = _responseText(map.get(ITEM_CONCLUSION))

    // 无新结构数据时迁移旧自由文本
    if (!map.get(ITEM_PARAMS) && !map.get(ITEM_NOTE) && !map.get(ITEM_CONCLUSION)) {
      _migrateLegacy(map)
    }
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
        benefitPeriod: '',
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

  const casCompleted = computed(() =>
    casItems.value.filter((i) => !!i.conclusion && (i.conclusion !== '否' || !!i.explanationIfNo)).length,
  )

  const paramsJudged = computed(() =>
    policyParams.value.filter((r) =>
      r.category
      && r.meetsStandards
      && r.matchesBenefitPattern
      && r.reasonableVsPeers
      && r.hasChange
      && (r.hasChange !== 'Y' || r.changeReasonable),
    ).length,
  )

  function _parseRows(itemId: string): any[] {
    const raw = allResponses.value?.get(itemId)
    const text = raw?.remark ?? raw?.conclusion
    if (!text) return []
    try {
      const parsed = typeof text === 'string' ? JSON.parse(text) : text
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }

  /** 表A ↔ I4-6/I4-7 自动勾稽 */
  const amortCrossCheck = computed<CrossCheckResult>(() =>
    crossCheckPolicyVsAmort(
      policyParams.value,
      _parseRows('I4-6-rows'),
      _parseRows('I4-7-rows'),
    ),
  )

  const peerRanges = computed(() => computePeerRanges(peerPolicies.value))
  const peerDeviations = computed(() =>
    computePeerDeviations(policyParams.value, peerRanges.value),
  )
  const peerRemarkNeeded = computed(() =>
    categoriesNeedingPeerRemark(policyParams.value, peerDeviations.value),
  )
  const peerLifeHints = computed(() => {
    const hints: Record<string, string> = {}
    for (const r of peerRanges.value) {
      if (r.label) hints[r.category] = r.label
    }
    return hints
  })

  const industryHint = computed<IndustryHint>(() =>
    recommendPeerIndustry({
      projectContext: options?.projectContext?.value ?? null,
      detailRows: _parseRows('I4-2-rows'),
    }),
  )

  const leaseShorterCheck = computed<LeaseShorterResult>(() => {
    const policyPeriods: Record<string, string> = {}
    for (const r of policyParams.value) {
      if (r.category && r.benefitPeriod) policyPeriods[r.category] = r.benefitPeriod
    }
    const detail = _parseRows('I4-2-rows')
    const base = checkLeaseShorterRule(detail, policyPeriods)
    const policyIssues = checkPolicyVsLeaseByCategory(policyParams.value, detail)
    const byCategory = [...base.byCategory]
    for (const p of policyIssues) {
      const idx = byCategory.findIndex((c) => c.category === p.category)
      if (idx >= 0 && p.severity === 'error') {
        byCategory[idx] = p
      } else if (idx < 0) {
        byCategory.push(p)
      }
    }
    const errors = byCategory.filter((c) => c.severity === 'error')
    const ok = errors.length === 0
    return {
      ...base,
      byCategory,
      ok,
      summary: !base.items.length && !policyIssues.length
        ? base.summary
        : ok
          ? '租赁期孰短校验通过'
          : `孰短未通过：${errors.map((e) => e.category).join('、')}`,
    }
  })

  const COMPLETION_KEY = 'I4-4-completion'
  const COMPLETION_OK_KEY = 'I4-4-completion-ok'
  const COMPLETION_PROGRESS_KEY = 'I4-4-completion-progress'

  const sheetMarkedComplete = computed(() => {
    const item = allResponses.value?.get(COMPLETION_KEY)
    const c = String(item?.conclusion ?? item?.remark ?? '')
    return c === '已完成' || c === 'Y'
  })

  const completeness = computed(() => {
    const catCount = policyParams.value.filter((r) => r.category).length
    const cross = amortCrossCheck.value
    const hasAmortData = cross.aggs.length > 0
    const lease = leaseShorterCheck.value
    const hasLeaseItems = lease.items.length > 0 || lease.byCategory.some((c) => c.severity === 'error')
    return [
      {
        id: 'cas',
        label: '政策要点评价已完成',
        ok: casCompleted.value === casItems.value.length,
        hint: `${casCompleted.value}/${casItems.value.length}`,
      },
      {
        id: 'params',
        label: '表A五维判断已填',
        ok: catCount > 0 && paramsJudged.value === catCount,
        hint: `${paramsJudged.value}/${catCount}`,
      },
      {
        id: 'peers',
        label: '表B至少填写1家同业及来源',
        ok: peerCompanies.value.some((p) => p.name && p.source),
        hint: `${peerCompanies.value.filter((p) => p.name).length}家`,
      },
      {
        id: 'peer-remark',
        label: '同业偏离已备注',
        ok: peerRemarkNeeded.value.length === 0,
        hint: peerRemarkNeeded.value.length
          ? peerRemarkNeeded.value.join('、')
          : '无偏离或已说明',
      },
      {
        id: 'cross',
        label: '表A与I4-6/7勾稽无阻断项',
        ok: !hasAmortData || cross.ok,
        hint: hasAmortData ? cross.summary : '测算未就绪',
      },
      {
        id: 'lease',
        label: '装修/租赁改良孰短校验',
        ok: !hasLeaseItems || lease.ok,
        hint: lease.summary,
      },
      {
        id: 'priors',
        label: '有变更时表C已填原估计',
        ok: !hasAnyChange.value || priorEstimates.value.every((p) => p.benefitPeriod || p.amortMethod),
        hint: hasAnyChange.value ? `${priorEstimates.value.length}行` : '无变更',
      },
      {
        id: 'conclusion',
        label: '审计结论已填写',
        ok: overallConclusion.value.trim().length >= 8,
        hint: overallConclusion.value ? '已填' : '未填',
      },
    ]
  })

  const completionProgress = computed(() => {
    const list = completeness.value
    if (!list.length) return 0
    return Math.round((list.filter((c) => c.ok).length / list.length) * 100)
  })

  const completenessOk = computed(() => completeness.value.every((c) => c.ok))

  const canMarkComplete = computed(() => completenessOk.value)

  function persistCompletionMarker(forceOk?: boolean): void {
    if (!options?.onSave) return
    const ok = forceOk ?? completenessOk.value
    const progress = completionProgress.value
    options.onSave(COMPLETION_KEY, ok ? '已完成' : '进行中')
    options.onSave(COMPLETION_OK_KEY, ok ? 'Y' : 'N')
    options.onSave(COMPLETION_PROGRESS_KEY, String(progress))
    const map = allResponses.value
    if (map) {
      map.set(COMPLETION_KEY, {
        item_id: COMPLETION_KEY,
        conclusion: ok ? '已完成' : '进行中',
        remark: String(progress),
      })
      map.set(COMPLETION_OK_KEY, {
        item_id: COMPLETION_OK_KEY,
        conclusion: ok ? 'Y' : 'N',
        remark: ok ? 'Y' : 'N',
      })
      map.set(COMPLETION_PROGRESS_KEY, {
        item_id: COMPLETION_PROGRESS_KEY,
        conclusion: null,
        remark: String(progress),
      })
    }
  }

  /** 显式标记已完成；闸门未过则拒绝 */
  function markSheetComplete(): { ok: boolean; message: string } {
    if (!completenessOk.value) {
      return { ok: false, message: '完成度闸门未通过，不能标记为已完成' }
    }
    persistCompletionMarker(true)
    return { ok: true, message: '已标记 I4-4 为已完成' }
  }

  /** 取消已完成（改回进行中） */
  function unmarkSheetComplete(): void {
    persistCompletionMarker(false)
  }

  // 闸门从通过→不通过时，若已标记完成则自动降级为进行中
  watch(completenessOk, (ok) => {
    if (!ok && sheetMarkedComplete.value) {
      persistCompletionMarker(false)
    }
  })

  const negativeJudgments = computed(() =>
    policyParams.value.filter((r) =>
      r.meetsStandards === 'N'
      || r.matchesBenefitPattern === 'N'
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
    const agg = aggregateCategoriesFromI4Detail(detailRows)
    if (!agg.length) return 0
    const byCat = new Map(policyParams.value.map((r) => [r.category, r]))
    const next: PolicyParamRow[] = []
    for (const a of agg) {
      const prev = byCat.get(a.category)
      if (prev) {
        prev.benefitPeriod = a.benefitPeriod || prev.benefitPeriod
        prev.amortMethod = a.amortMethod || prev.amortMethod
        prev.detailCount = a.detailCount
        next.push(prev)
      } else {
        next.push({
          ..._emptyParam(a.category),
          benefitPeriod: a.benefitPeriod,
          amortMethod: a.amortMethod,
          detailCount: a.detailCount,
        })
      }
    }
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
          benefitPeriod: list[i]?.benefitPeriod ?? '',
          amortMethod: list[i]?.amortMethod ?? '',
        }
      })
      return { category, cells }
    })
    for (const cat of Object.keys(tpl.policies)) {
      if (!policyParams.value.some((r) => r.category === cat)) {
        policyParams.value.push(_emptyParam(cat))
      }
    }
    persistPeers()
    persistParams()
  }

  /**
   * 应用公开年报附注摘录库返回的同业数据（最多4家）
   */
  function applyPeerCatalog(payload: {
    label?: string
    peers: Array<{
      name: string
      source?: string
      stock_code?: string
      year?: number
      policies?: Record<string, { benefitPeriod?: string; amortMethod?: string }>
    }>
  }): number {
    const list = (payload.peers || []).slice(0, 4)
    if (!list.length) return 0
    lastAppliedTemplateLabel.value = payload.label
      ? `${payload.label}·年报库`
      : '公开年报附注摘录库'
    peerCompanies.value = list.map((p, i) => ({
      peerId: `peer-${i + 1}`,
      name: p.name,
      source: p.source
        || `公开年报附注摘录库${p.year ? `·${p.year}` : ''}${p.stock_code ? `·${p.stock_code}` : ''}`,
    }))
    while (peerCompanies.value.length < 4) {
      peerCompanies.value.push({
        peerId: `peer-${peerCompanies.value.length + 1}`,
        name: '',
        source: '',
      })
    }
    const policyCats = new Set<string>([
      ...policyParams.value.map((r) => r.category).filter(Boolean),
      ...list.flatMap((p) => Object.keys(p.policies || {})),
    ])
    peerPolicies.value = [...policyCats].map((category) => {
      const cells: Record<string, PeerCell> = {}
      peerCompanies.value.forEach((peer, i) => {
        const pol = list[i]?.policies?.[category]
        cells[peer.peerId] = {
          benefitPeriod: pol?.benefitPeriod ?? '',
          amortMethod: pol?.amortMethod ?? '',
        }
      })
      return { category, cells }
    })
    for (const cat of policyCats) {
      if (!policyParams.value.some((r) => r.category === cat)) {
        policyParams.value.push(_emptyParam(cat))
      }
    }
    persistPeers()
    persistParams()
    return list.length
  }

  /** 将测算众数回填到表A空白的期限/方法（不覆盖已填） */
  function syncBlankParamsFromAmort(): number {
    const aggs = amortCrossCheck.value.aggs
    if (!aggs.length) return 0
    let n = 0
    for (const a of aggs) {
      let row = policyParams.value.find((r) => r.category === a.category)
      if (!row) {
        row = _emptyParam(a.category)
        policyParams.value.push(row)
        n++
      }
      if (!row.amortMethod && a.amortMethod) {
        row.amortMethod = a.amortMethod.includes('/') ? a.amortMethod.split('/')[0] : a.amortMethod
        n++
      }
      if (!row.benefitPeriod && a.benefitPeriod && a.benefitPeriod !== '按工作量') {
        row.benefitPeriod = a.benefitPeriod
        n++
      }
      row.detailCount = a.itemCount
    }
    if (n) persistParams()
    return n
  }

  /** 根据表B区间自动建议「同业合理」Y/N（仅填空字段） */
  function suggestJudgmentsFromPeers(): number {
    const ranges = peerRanges.value.filter((r) => r.sampleCount > 0)
    if (!ranges.length) return 0
    const devs = peerDeviations.value
    let n = suggestReasonableVsPeers(policyParams.value, devs)
    n += suggestReasonableYForInRange(policyParams.value, ranges, devs)
    if (n) persistParams()
    return n
  }

  /**
   * 勾稽异常 → 表A标记关注：写入备注；方法/期限不一致时将「符合准则/受益模式」置空提示复核
   * （不强制改 Y→N，避免覆盖人工判断；仅追加备注）
   */
  function markCrossIssuesAsAttention(): number {
    const remarks = buildAttentionRemarksFromIssues(amortCrossCheck.value.issues)
    if (!remarks.size) return 0
    let n = 0
    for (const [cat, text] of remarks) {
      let row = policyParams.value.find((r) => r.category === cat)
      if (!row) {
        row = _emptyParam(cat)
        policyParams.value.push(row)
      }
      if (!row.remark?.includes('[勾稽')) {
        row.remark = row.remark?.trim() ? `${row.remark}；${text}` : text
        n++
      }
      // 重大差异且仍为 Y → 建议改为空以便复核
      const hasSig = amortCrossCheck.value.issues.some(
        (i) => i.category === cat && i.code === 'significant-diff' && i.severity === 'error',
      )
      if (hasSig && row.meetsStandards === 'Y') {
        row.meetsStandards = ''
        n++
      }
      if (hasSig && row.matchesBenefitPattern === 'Y') {
        row.matchesBenefitPattern = ''
        n++
      }
    }
    if (n) persistParams()
    return n
  }

  /**
   * 重大测算差异 → 写入 I4-3 补提摊销草稿（跳过已有同说明）
   * @returns 新增行数
   */
  function appendAdjDraftsFromCrossCheck(): number {
    const diffs = significantDiffAmounts(amortCrossCheck.value)
    if (!diffs.length) return 0
    const existing = _parseRows('I4-3-rows')
    const descs = new Set(existing.map((r: any) => String(r.description || '')))
    const toAdd: any[] = []
    for (const d of diffs) {
      const lines = buildI4AmortSupplementDraft({
        projectName: d.category,
        amount: d.amount,
        indexRef: d.source,
      })
      if (!lines.length) continue
      if (descs.has(lines[0].description)) continue
      for (const line of lines) {
        toAdd.push(line)
        descs.add(line.description)
      }
    }
    if (!toAdd.length) return 0
    const next = [...existing, ...toAdd]
    options?.onSave?.('I4-3-rows', next)
    const map = allResponses.value
    if (map) {
      map.set('I4-3-rows', {
        item_id: 'I4-3-rows',
        conclusion: null,
        remark: JSON.stringify(next),
      })
    }
    return toAdd.length
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
      return 'A、经检查，被审计单位长期待摊费用摊销政策与受益期限估计符合准则及受益模式，与同行业比较未见重大不合理，前后期一贯，可确认。'
    }
    if (neg === 0 && changed) {
      return 'B、本期存在会计估计变更，已按未来适用法处理并记录原估计及影响；除下列事项外，摊销政策未见异常：……'
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
    amortCrossCheck,
    peerRanges,
    peerDeviations,
    peerRemarkNeeded,
    peerLifeHints,
    industryHint,
    leaseShorterCheck,
    sheetMarkedComplete,
    canMarkComplete,
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
    persistCompletionMarker,
    markSheetComplete,
    unmarkSheetComplete,
    addParamRow,
    removeParamRow,
    syncFromDetail,
    applyIndustryTemplate,
    applyPeerCatalog,
    syncBlankParamsFromAmort,
    suggestJudgmentsFromPeers,
    markCrossIssuesAsAttention,
    appendAdjDraftsFromCrossCheck,
    updatePeerCell,
    suggestConclusionTemplate,
    load,
  }
}

export default useI4PolicyCheck
