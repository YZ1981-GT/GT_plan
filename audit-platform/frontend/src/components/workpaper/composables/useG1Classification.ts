/**
 * useG1Classification - G1-9 分类适当性检查（2区段Tab）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.3
 *
 * Responsibilities:
 * - 2区段Tab（SPPI测试11列 / 业务模式判定10列），区段间行同步
 * - SPPI通过/不通过下拉 + 最终分类下拉(FVTPL/FVOCI/AC)
 * - 动态行增删 + loadAll/persistAll
 *
 * Requirements: 11.1~11.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ChecklistResponse } from './useF1FormData'

// --- Types ---

/** SPPI 通过/不通过 */
export type SppiResult = 'pass' | 'fail' | ''

/** 最终分类 */
export type FinalClassification = 'FVTPL' | 'FVOCI' | 'AC' | ''

export const G1_SPPI_RESULT_OPTIONS = [
  { value: 'pass', label: '通过' },
  { value: 'fail', label: '不通过' },
] as const

export const G1_FINAL_CLASS_OPTIONS = [
  { value: 'FVTPL', label: 'FVTPL（以公允价值计量且变动计入当期损益）' },
  { value: 'FVOCI', label: 'FVOCI（以公允价值计量且变动计入其他综合收益）' },
  { value: 'AC', label: 'AC（以摊余成本计量）' },
] as const

/**
 * G1-9 分类适当性行（21列 = SPPI测试11列 + 业务模式判定10列，共用投资项目）
 */
export interface G1ClassificationRow {
  id: string
  seq: number
  investItem: string // 投资项目（两区段共用）
  // --- SPPI测试区段（11列，含投资项目）---
  contractTerms: string // 合同条款
  basicLendingArrangement: string // 基本借贷安排
  solelyPrincipalInterest: string // 仅为本金和利息
  prepaymentFeature: string // 提前还款特征
  creditRisk: string // 信用风险
  leverageFeature: string // 杠杆特征
  nonStandardFeature: string // 非标准特征
  sppiResult: SppiResult // SPPI通过/不通过（下拉）
  sppiAuditEval: string // 审计评价
  sppiRemark: string // 备注
  // --- 业务模式判定区段（10列，含投资项目）---
  managementObjective: string // 管理目标
  portfolioManagement: string // 资产组合管理方式
  compensationMechanism: string // 报酬机制
  saleFrequencyScale: string // 出售频率/规模
  saleReason: string // 出售原因
  matchHoldCollect: string // 是否符合持有收取
  matchCollectAndSell: string // 是否符合既收取又出售
  finalClassification: FinalClassification // 最终分类（下拉）
  bizAuditEval: string // 审计评价
}

export interface G1ClassificationColumn {
  prop: keyof G1ClassificationRow
  label: string
  width: number
  type: 'text' | 'sppi-select' | 'class-select'
}

/** SPPI测试区段列（11列） */
export const G1_SPPI_COLUMNS: G1ClassificationColumn[] = [
  { prop: 'investItem', label: '投资项目', width: 160, type: 'text' },
  { prop: 'contractTerms', label: '合同条款', width: 160, type: 'text' },
  { prop: 'basicLendingArrangement', label: '基本借贷安排', width: 140, type: 'text' },
  { prop: 'solelyPrincipalInterest', label: '仅为本金和利息', width: 140, type: 'text' },
  { prop: 'prepaymentFeature', label: '提前还款特征', width: 140, type: 'text' },
  { prop: 'creditRisk', label: '信用风险', width: 130, type: 'text' },
  { prop: 'leverageFeature', label: '杠杆特征', width: 130, type: 'text' },
  { prop: 'nonStandardFeature', label: '非标准特征', width: 130, type: 'text' },
  { prop: 'sppiResult', label: 'SPPI通过/不通过', width: 140, type: 'sppi-select' },
  { prop: 'sppiAuditEval', label: '审计评价', width: 160, type: 'text' },
  { prop: 'sppiRemark', label: '备注', width: 140, type: 'text' },
]

/** 业务模式判定区段列（10列） */
export const G1_BIZMODEL_COLUMNS: G1ClassificationColumn[] = [
  { prop: 'investItem', label: '投资项目', width: 160, type: 'text' },
  { prop: 'managementObjective', label: '管理目标', width: 140, type: 'text' },
  { prop: 'portfolioManagement', label: '资产组合管理方式', width: 150, type: 'text' },
  { prop: 'compensationMechanism', label: '报酬机制', width: 130, type: 'text' },
  { prop: 'saleFrequencyScale', label: '出售频率/规模', width: 140, type: 'text' },
  { prop: 'saleReason', label: '出售原因', width: 140, type: 'text' },
  { prop: 'matchHoldCollect', label: '是否符合持有收取', width: 150, type: 'text' },
  { prop: 'matchCollectAndSell', label: '是否符合既收取又出售', width: 170, type: 'text' },
  { prop: 'finalClassification', label: '最终分类', width: 160, type: 'class-select' },
  { prop: 'bizAuditEval', label: '审计评价', width: 160, type: 'text' },
]

const DATA_KEY = 'G1-9-rows'
const CONCLUSION_KEY = 'G1-9-conclusion'

// --- Helpers ---

function emptyRow(id: string, seq: number): G1ClassificationRow {
  return {
    id,
    seq,
    investItem: '',
    contractTerms: '',
    basicLendingArrangement: '',
    solelyPrincipalInterest: '',
    prepaymentFeature: '',
    creditRisk: '',
    leverageFeature: '',
    nonStandardFeature: '',
    sppiResult: '',
    sppiAuditEval: '',
    sppiRemark: '',
    managementObjective: '',
    portfolioManagement: '',
    compensationMechanism: '',
    saleFrequencyScale: '',
    saleReason: '',
    matchHoldCollect: '',
    matchCollectAndSell: '',
    finalClassification: '',
    bizAuditEval: '',
  }
}

function loadRows(map: Map<string, ChecklistResponse>): G1ClassificationRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [emptyRow('1', 1)]
  try {
    const parsed = JSON.parse(raw) as Partial<G1ClassificationRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyRow('1', 1)]
    return parsed.map((p, i) => ({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [emptyRow('1', 1)]
  }
}

// --- Composable ---

export function useG1Classification(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1ClassificationRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  /** SPPI 统计：通过/不通过笔数 */
  const stats = computed(() => {
    const pass = rows.value.filter((r) => r.sppiResult === 'pass').length
    const fail = rows.value.filter((r) => r.sppiResult === 'fail').length
    const fvtpl = rows.value.filter((r) => r.finalClassification === 'FVTPL').length
    const fvoci = rows.value.filter((r) => r.finalClassification === 'FVOCI').length
    const ac = rows.value.filter((r) => r.finalClassification === 'AC').length
    return { pass, fail, fvtpl, fvoci, ac }
  })

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1ClassificationRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增分类检查行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '投资项目名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [...rows.value, { ...emptyRow(`row-${Date.now()}`, seq), investItem: value }]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  return {
    sppiColumns: G1_SPPI_COLUMNS,
    bizModelColumns: G1_BIZMODEL_COLUMNS,
    sppiResultOptions: G1_SPPI_RESULT_OPTIONS,
    finalClassOptions: G1_FINAL_CLASS_OPTIONS,
    rows,
    auditConclusion,
    stats,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1Classification
