/**
 * useK1PolicyCheck — K1-6 信用减值损失会计政策检查
 *
 * 对齐致同 K1-6：目标 → 程序 → (一)组合政策 → (二)历史损失 → (三)前瞻性 → (四)同业对比
 * → 审计说明 → 审计结论；组合划分须与 K1-7/K1-8 一致。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseK18Payload } from './useK1BadDebtCalcSheet'
import { K18_STORAGE_KEY } from './k1CrossHelpers'
import {
  K1_K2_AGING_LOSS_RATE_KEY,
  type K1K2AgingLossRateRow,
  type K16K18ComboConsistency,
  computeK16K18ComboConsistency,
  extractK18GroupNames,
  mergeCombosFromK18,
  applyK2RatesToK18Payload,
  pullK2RatesFromK18,
  parseK2AgingLossRates,
} from './k1PolicyCrossHelpers'

export interface K1PolicyCombo {
  id: string
  basis: string
  /** 损失率确定方法：账龄/迁徙率/单项等 */
  method: string
  remark: string
}

export interface K1PeerPolicyRow {
  id: string
  company: string
  policyText: string
  comparable: '' | '是' | '否' | '部分一致'
}

export const K1_DEFAULT_COMBO_BASES = [
  '押金和保证金',
  '应收关联公司款项',
  '应收代垫款项',
  '员工备用金',
] as const

export const K1_DEFAULT_AUDIT_PROCEDURES = [
  '检查信用减值损失会计政策的合理性，与前期是否一致，与同行业其他公司比较，关注会计政策或估计变更。',
  '根据实施上述程序的结果（包括将以前期间的估计与当期实际结果进行比较），考虑管理层判断是否存在偏向。',
].join('\n')

export const K1_LISTED_POLICY_EXAMPLES = [
  {
    company: '中国中铁',
    text: '依据信用风险特征将其他应收款划分为若干组合：组合1 应收押金和保证金；组合2 应收代垫款；组合3 应收其他款项。参考历史信用损失经验，结合当前状况及未来经济预测，通过违约风险敞口和未来12个月内或整个存续期预期信用损失率计算预期信用损失。',
  },
  {
    company: '海螺水泥',
    text: '对单项测试未发生减值的其他应收款，包括在具有类似信用风险特征的组合中再进行减值测试。组合1 除政府代垫款及银行委托理财产品以外的其他应收款；组合2 政府代垫款；组合3 银行委托理财产品。',
  },
  {
    company: '北辰实业',
    text: '组合1 应收押金、保证金及备用金；组合2 应收关联公司款项；组合3 应收少数股东款项；组合4 应收代垫款项；组合5 应收其他款项。通过违约风险敞口和未来12个月内或整个存续期预期信用损失率计算预期信用损失。',
  },
  {
    company: '拉夏贝尔',
    text: '对较低信用风险金融工具假设信用风险自初始确认后未显著增加，按12个月内预期信用损失计量。组合：押金和保证金；员工备用金及其他；应收子公司款项；应收股利款；应收定期存款利息。',
  },
  {
    company: '上海医药',
    text: '组合一 账龄；组合二 关联方股利；组合三 利息及银行承兑汇票；组合四 保证金(含押金)及其他应收供应商款项；组合五 应收合并范围内公司款项。',
  },
  {
    company: '上海电气',
    text: '存在减值客观证据的单独进行减值测试计提单项减值准备。其余按组合：组合1 押金和保证金；组合2 员工备用金；组合3 其他。参考历史信用损失经验结合前瞻性预测计算预期信用损失。',
  },
] as const

export const K1_POLICY_CONCLUSION_TEMPLATES: Record<string, string> = {
  A: '被审计单位其他应收款减值会计政策及估计符合企业会计准则规定，能够反映实际业务情况，与同行业相比无重大差异，且一贯执行。',
  B: '除上述需关注事项外，被审计单位其他应收款减值会计政策及估计总体符合企业会计准则规定，且一贯执行。',
  C: '被审计单位其他应收款减值会计政策/估计存在重大不当或管理层偏向，需进一步调整或扩大审计程序。',
}

const KEYS = {
  combos: 'K1-6-combos',
  policyDesc: 'K1-6-policy-desc',
  procedures: 'K1-6-procedures',
  historical: 'K1-6-historical',
  forward: 'K1-6-forward',
  priorYear: 'K1-6-prior-year',
  peer: 'K1-6-peer',
  peerRows: 'K1-6-peer-rows',
  auditNote: 'K1-6-audit-note',
  conclusion: 'K1-6-conclusion',
  conclusionOption: 'K1-6-conclusion-option',
} as const

function newId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

function emptyCombo(basis = ''): K1PolicyCombo {
  return { id: newId('combo'), basis, method: '', remark: '' }
}

function seedCombos(): K1PolicyCombo[] {
  return K1_DEFAULT_COMBO_BASES.map((b) => emptyCombo(b))
}

function deserializeCombo(raw: any): K1PolicyCombo {
  return {
    id: String(raw?.id || newId('combo')),
    basis: String(raw?.basis ?? ''),
    method: String(raw?.method ?? ''),
    remark: String(raw?.remark ?? ''),
  }
}

function deserializePeerRow(raw: any): K1PeerPolicyRow {
  return {
    id: String(raw?.id || newId('peer')),
    company: String(raw?.company ?? ''),
    policyText: String(raw?.policyText ?? raw?.text ?? ''),
    comparable: raw?.comparable ?? '',
  }
}

export interface UseK1PolicyCheckOpts {
  allResponses: Ref<Map<string, any>>
}

export function useK1PolicyCheck(opts: UseK1PolicyCheckOpts) {
  const combos = ref<K1PolicyCombo[]>([])
  const peerRows = ref<K1PeerPolicyRow[]>([])
  const k2LossRates = ref<K1K2AgingLossRateRow[]>([])
  const policyDesc = ref('')
  const auditProcedures = ref(K1_DEFAULT_AUDIT_PROCEDURES)
  const historicalLoss = ref('')
  const forwardLooking = ref('')
  const priorYearPolicy = ref('')
  const peerComparison = ref('')
  const auditNote = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  function load(): void {
    const comboRaw = opts.allResponses.value.get(KEYS.combos)?.remark
    if (comboRaw) {
      try {
        const parsed = JSON.parse(comboRaw)
        combos.value = Array.isArray(parsed) ? parsed.map(deserializeCombo) : seedCombos()
      } catch {
        combos.value = seedCombos()
      }
    } else {
      combos.value = seedCombos()
    }

    policyDesc.value = opts.allResponses.value.get(KEYS.policyDesc)?.remark || ''
    auditProcedures.value = opts.allResponses.value.get(KEYS.procedures)?.remark || K1_DEFAULT_AUDIT_PROCEDURES
    historicalLoss.value = opts.allResponses.value.get(KEYS.historical)?.remark || ''
    forwardLooking.value = opts.allResponses.value.get(KEYS.forward)?.remark || ''
    priorYearPolicy.value = opts.allResponses.value.get(KEYS.priorYear)?.remark || ''
    peerComparison.value = opts.allResponses.value.get(KEYS.peer)?.remark || ''
    auditNote.value = opts.allResponses.value.get(KEYS.auditNote)?.remark || ''
    conclusion.value = opts.allResponses.value.get(KEYS.conclusion)?.remark || ''
    conclusionOption.value = opts.allResponses.value.get(KEYS.conclusionOption)?.remark || ''

    const peerRaw = opts.allResponses.value.get(KEYS.peerRows)?.remark
    if (peerRaw) {
      try {
        const parsed = JSON.parse(peerRaw)
        peerRows.value = Array.isArray(parsed) ? parsed.map(deserializePeerRow) : []
      } catch {
        peerRows.value = []
      }
    } else {
      peerRows.value = []
    }

    k2LossRates.value = parseK2AgingLossRates(opts.allResponses.value.get(K1_K2_AGING_LOSS_RATE_KEY)?.remark)
  }

  const k18Groups = computed(() => extractK18GroupNames(opts.allResponses.value))

  const k18ComboConsistency: ComputedRef<K16K18ComboConsistency> = computed(() =>
    computeK16K18ComboConsistency(
      combos.value.map((c) => c.basis),
      k18Groups.value,
    ),
  )

  const comboCount: ComputedRef<number> = computed(() =>
    combos.value.filter((c) => c.basis.trim()).length,
  )

  const completionScore: ComputedRef<{ done: number; total: number }> = computed(() => {
    const checks = [
      comboCount.value > 0,
      !!policyDesc.value.trim(),
      !!historicalLoss.value.trim(),
      !!forwardLooking.value.trim(),
      peerRows.value.some((r) => r.company && r.policyText) || !!peerComparison.value.trim(),
      !!auditNote.value.trim(),
      !!conclusion.value.trim(),
    ]
    return { done: checks.filter(Boolean).length, total: checks.length }
  })

  function addCombo(): void {
    combos.value = [...combos.value, emptyCombo()]
  }

  function removeCombo(id: string): void {
    combos.value = combos.value.filter((c) => c.id !== id)
  }

  function updateCombo(id: string, field: keyof K1PolicyCombo, value: string): void {
    const row = combos.value.find((c) => c.id === id)
    if (row) (row as any)[field] = value
  }

  function addPeerRow(company = '', policyText = ''): void {
    peerRows.value = [...peerRows.value, { id: newId('peer'), company, policyText, comparable: '' }]
  }

  function removePeerRow(id: string): void {
    peerRows.value = peerRows.value.filter((r) => r.id !== id)
  }

  function updateK2Rate(id: string, field: keyof K1K2AgingLossRateRow, value: string | number): void {
    const row = k2LossRates.value.find((r) => r.id === id)
    if (row) (row as any)[field] = value
  }

  function syncCombosFromK18(): { added: number; updated: number } {
    const result = mergeCombosFromK18(combos.value, k18Groups.value)
    combos.value = result.combos
    return { added: result.added, updated: result.updated }
  }

  function pullK2RatesFromK18Sheet(): number {
    const pulled = pullK2RatesFromK18(opts.allResponses.value, k18ComboConsistency.value.matched)
    let changed = 0
    k2LossRates.value = pulled
    return changed + pulled.filter((r) => r.historicalRate > 0).length
  }

  function pushK2RatesToK18(): { updatedCells: number; written: boolean } {
    const raw = opts.allResponses.value.get(K18_STORAGE_KEY)?.remark
    if (!raw) return { updatedCells: 0, written: false }
    const payload = parseK18Payload(raw)
    const { payload: next, updatedCells } = applyK2RatesToK18Payload(
      payload,
      k2LossRates.value,
      k18ComboConsistency.value.matched,
    )
    if (updatedCells <= 0) return { updatedCells: 0, written: false }
    const serialized = JSON.stringify(next)
    opts.allResponses.value.set(K18_STORAGE_KEY, { item_id: K18_STORAGE_KEY, remark: serialized })
    return { updatedCells, written: true }
  }

  function applyListedExample(company: string, text: string): void {
    const existing = peerRows.value.find((r) => r.company === company)
    if (existing) {
      existing.policyText = text
    } else {
      addPeerRow(company, text)
    }
    const addition = `【${company}】${text}`
    peerComparison.value = peerComparison.value.trim()
      ? `${peerComparison.value}\n${addition}`
      : addition
  }

  function buildSaveItems(): Array<{ item_id: string; conclusion: string | null; remark: string }> {
    return [
      { item_id: KEYS.combos, conclusion: null, remark: JSON.stringify(combos.value) },
      { item_id: KEYS.policyDesc, conclusion: null, remark: policyDesc.value },
      { item_id: KEYS.procedures, conclusion: null, remark: auditProcedures.value },
      { item_id: KEYS.historical, conclusion: null, remark: historicalLoss.value },
      { item_id: KEYS.forward, conclusion: null, remark: forwardLooking.value },
      { item_id: KEYS.priorYear, conclusion: null, remark: priorYearPolicy.value },
      { item_id: KEYS.peer, conclusion: null, remark: peerComparison.value },
      { item_id: KEYS.peerRows, conclusion: null, remark: JSON.stringify(peerRows.value) },
      { item_id: KEYS.auditNote, conclusion: null, remark: auditNote.value },
      { item_id: KEYS.conclusion, conclusion: conclusion.value, remark: conclusion.value },
      { item_id: KEYS.conclusionOption, conclusion: null, remark: conclusionOption.value },
      { item_id: K1_K2_AGING_LOSS_RATE_KEY, conclusion: null, remark: JSON.stringify(k2LossRates.value) },
    ]
  }

  watch(
    () => opts.allResponses.value.get(KEYS.combos)?.remark,
    () => {
      if (combos.value.length === 0) load()
    },
    { immediate: true },
  )

  return {
    combos,
    peerRows,
    k2LossRates,
    policyDesc,
    auditProcedures,
    historicalLoss,
    forwardLooking,
    priorYearPolicy,
    peerComparison,
    auditNote,
    conclusion,
    conclusionOption,
    comboCount,
    completionScore,
    k18ComboConsistency,
    load,
    addCombo,
    removeCombo,
    updateCombo,
    addPeerRow,
    removePeerRow,
    updateK2Rate,
    syncCombosFromK18,
    pullK2RatesFromK18Sheet,
    pushK2RatesToK18,
    applyListedExample,
    buildSaveItems,
  }
}
