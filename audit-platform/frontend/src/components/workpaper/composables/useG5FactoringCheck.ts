/**
 * useG5FactoringCheck — G5-7 长期应收款保理业务核查
 *
 * 对齐纸质底稿：
 *   （一）终止确认明细  （二）继续涉入明细  （三）CAS23 九步终止确认判断
 * 结论映射：终止确认 / 不终止确认（质押借款） / 按继续涉入程度确认
 */
import { ref, computed } from 'vue'
import { parseNum } from '@/composables/useG5FormulaEngine'
import { STEP_DEFS, type StepJudgment } from './useD2Derecognition'

export type { StepJudgment }
export { STEP_DEFS }

export type FactoringMethod = '有追索' | '无追索' | '其他'
/** 底稿归类：终止确认表 / 继续涉入表 / 未终止（质押借款，不入上两表） */
export type FactoringTreatment = 'derecognized' | 'continuing' | 'pledged' | ''

export type FactoringConclusion =
  | '终止确认'
  | '不终止确认（继续确认，作质押融资处理）'
  | '按继续涉入程度确认'
  | ''

export interface FactoringJudgmentStep {
  stepId: string
  title: string
  note: string
  judgment: StepJudgment
  userNote: string
}

export interface FactoringCheckRow {
  id: string
  seq: number
  /** 项目/债务人 */
  debtor: string
  factor: string
  amount: number
  method: FactoringMethod
  /** 转移方式文字（保理/ABS 等） */
  transferMethod: string
  derecognizedAmount: number
  gainLoss: number
  continuingAsset: number
  continuingLiability: number
  /** 主要合同条款摘要 */
  contractTerms: string
  /** 九步判断结论（CAS23） */
  judgmentConclusion: FactoringConclusion
  /** 分析结论文字 */
  analysisConclusion: string
  /** 兼容旧字段：是/否 */
  derecognition: '是' | '否'
  basis: string
  conclusion: string
  indexRef: string
  treatment: FactoringTreatment
  judgmentSteps: FactoringJudgmentStep[]
}

export const CONCLUSION_OPTIONS: Exclude<FactoringConclusion, ''>[] = [
  '终止确认',
  '不终止确认（继续确认，作质押融资处理）',
  '按继续涉入程度确认',
]

export function createJudgmentSteps(saved?: FactoringJudgmentStep[]): FactoringJudgmentStep[] {
  const byId = new Map((saved || []).map(s => [s.stepId, s]))
  return STEP_DEFS.map(d => {
    const prev = byId.get(d.stepId)
    return {
      stepId: d.stepId,
      title: d.title,
      note: d.note,
      judgment: (prev?.judgment || '') as StepJudgment,
      userNote: prev?.userNote || '',
    }
  })
}

/** CAS23 决策树建议结论（与 D2 一致，人工可改） */
export function suggestJudgmentConclusion(steps: FactoringJudgmentStep[]): FactoringConclusion {
  const j = (id: string) => steps.find(s => s.stepId === id)?.judgment || ''
  if (j('s3') === '符合') return '终止确认'
  if (j('s6') === '符合') return '终止确认'
  if (j('s7') === '符合') return '不终止确认（继续确认，作质押融资处理）'
  if (j('s8') === '符合') return '按继续涉入程度确认'
  if (j('s8') === '不符合' && (j('s6') === '不符合' || j('s7') === '不符合')) return '终止确认'
  if (j('s6') || j('s7') || j('s8')) return '不终止确认（继续确认，作质押融资处理）'
  return ''
}

export function conclusionToTreatment(c: FactoringConclusion | string): FactoringTreatment {
  if (c === '终止确认') return 'derecognized'
  if (typeof c === 'string' && c.startsWith('按继续涉入')) return 'continuing'
  if (typeof c === 'string' && (c.startsWith('不终止') || c.includes('质押'))) return 'pledged'
  return ''
}

export function emptyRow(partial?: Partial<FactoringCheckRow>): FactoringCheckRow {
  return {
    id: crypto.randomUUID(),
    seq: 0,
    debtor: '',
    factor: '',
    amount: 0,
    method: '有追索',
    transferMethod: '保理',
    derecognizedAmount: 0,
    gainLoss: 0,
    continuingAsset: 0,
    continuingLiability: 0,
    contractTerms: '',
    judgmentConclusion: '',
    analysisConclusion: '',
    derecognition: '否',
    basis: '',
    conclusion: '',
    indexRef: '',
    treatment: '',
    judgmentSteps: createJudgmentSteps(),
    ...partial,
  }
}

function migrateLegacyRow(raw: any, index: number): FactoringCheckRow {
  const judgmentSteps = createJudgmentSteps(raw?.judgmentSteps)
  let judgmentConclusion = (raw?.judgmentConclusion || '') as FactoringConclusion
  if (!judgmentConclusion && raw?.derecognition === '是') judgmentConclusion = '终止确认'
  if (!judgmentConclusion && raw?.conclusion) {
    const c = String(raw.conclusion)
    if (c.includes('继续涉入')) judgmentConclusion = '按继续涉入程度确认'
    else if (c.includes('不终止') || c.includes('质押')) {
      judgmentConclusion = '不终止确认（继续确认，作质押融资处理）'
    } else if (c.includes('终止确认') || raw?.derecognition === '是') {
      judgmentConclusion = '终止确认'
    }
  }
  let treatment = (raw?.treatment || '') as FactoringTreatment
  if (!treatment) treatment = conclusionToTreatment(judgmentConclusion)

  const amount = parseNum(raw?.amount)
  const derecognition: '是' | '否' =
    judgmentConclusion === '终止确认' || judgmentConclusion.startsWith('按继续涉入')
      ? '是'
      : (raw?.derecognition === '是' ? '是' : '否')

  return emptyRow({
    id: raw?.id || crypto.randomUUID(),
    seq: index + 1,
    debtor: raw?.debtor || raw?.itemName || '',
    factor: raw?.factor || '',
    amount,
    method: (raw?.method === '无追索' || raw?.method === '其他' ? raw.method : '有追索') as FactoringMethod,
    transferMethod: raw?.transferMethod || raw?.method || '保理',
    derecognizedAmount: parseNum(raw?.derecognizedAmount ?? (derecognition === '是' ? amount : 0)),
    gainLoss: parseNum(raw?.gainLoss),
    continuingAsset: parseNum(raw?.continuingAsset),
    continuingLiability: parseNum(raw?.continuingLiability),
    contractTerms: raw?.contractTerms || '',
    judgmentConclusion,
    analysisConclusion: raw?.analysisConclusion || raw?.conclusion || '',
    derecognition,
    basis: raw?.basis || '',
    conclusion: raw?.conclusion || judgmentConclusion,
    indexRef: raw?.indexRef || '',
    treatment,
    judgmentSteps,
  })
}

/** 按判断结论同步归类与兼容字段 */
export function applyConclusionToRow(row: FactoringCheckRow, conclusion: FactoringConclusion): void {
  row.judgmentConclusion = conclusion
  row.treatment = conclusionToTreatment(conclusion)
  row.conclusion = conclusion || row.conclusion
  if (conclusion === '终止确认') {
    row.derecognition = '是'
    if (!row.derecognizedAmount && row.amount) row.derecognizedAmount = row.amount
  } else if (conclusion.startsWith('按继续涉入')) {
    row.derecognition = '是'
  } else if (conclusion) {
    row.derecognition = '否'
    row.derecognizedAmount = 0
  }
}

export function buildJudgmentSummary(row: FactoringCheckRow): string {
  const lines = row.judgmentSteps
    .filter(s => s.judgment)
    .map(s => `${s.title}：${s.judgment}${s.userNote ? `（${s.userNote}）` : ''}`)
  const concl = row.judgmentConclusion || suggestJudgmentConclusion(row.judgmentSteps) || '待定'
  return `保理终止确认判断（${row.debtor || '未命名'}·9步）：\n${lines.join('\n')}\n结论：${concl}`
}

export function useG5FactoringCheck() {
  const rows = ref<FactoringCheckRow[]>([])
  const conclusion = ref('')

  const derecognizedRows = computed(() =>
    rows.value.filter(r => r.treatment === 'derecognized' || (!r.treatment && r.derecognition === '是' && !String(r.judgmentConclusion).startsWith('按继续涉入'))),
  )
  const continuingRows = computed(() =>
    rows.value.filter(r => r.treatment === 'continuing' || String(r.judgmentConclusion).startsWith('按继续涉入')),
  )
  const pledgedRows = computed(() =>
    rows.value.filter(r => r.treatment === 'pledged' || String(r.judgmentConclusion).startsWith('不终止')),
  )
  const pendingRows = computed(() =>
    rows.value.filter(r => !r.treatment && !r.judgmentConclusion && r.derecognition !== '是'),
  )

  const totals = computed(() => ({
    amount: rows.value.reduce((s, r) => s + parseNum(r.amount), 0),
    derecognized: rows.value
      .filter(r => r.treatment === 'derecognized' || r.judgmentConclusion === '终止确认')
      .reduce((s, r) => s + parseNum(r.derecognizedAmount || r.amount), 0),
    continuingAsset: continuingRows.value.reduce((s, r) => s + parseNum(r.continuingAsset), 0),
    continuingLiability: continuingRows.value.reduce((s, r) => s + parseNum(r.continuingLiability), 0),
    notDerecognized: rows.value
      .filter(r => r.treatment === 'pledged' || r.derecognition === '否')
      .reduce((s, r) => s + parseNum(r.amount), 0),
  }))

  /** 有追索 + 终止确认 / 继续涉入 = 高风险警示 */
  const warningRows = computed(() =>
    rows.value.filter(r =>
      r.method === '有追索'
      && (r.judgmentConclusion === '终止确认' || r.treatment === 'derecognized' || (r.derecognition === '是' && r.treatment !== 'continuing')),
    ),
  )

  function renumber(): void {
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function addRow(seed?: Partial<FactoringCheckRow>): FactoringCheckRow {
    const row = emptyRow({ ...seed, seq: rows.value.length + 1 })
    rows.value.push(row)
    renumber()
    return row
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    renumber()
  }

  function updateRow(id: string, patch: Partial<FactoringCheckRow>): void {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    Object.assign(row, patch)
    if (patch.judgmentConclusion !== undefined) {
      applyConclusionToRow(row, patch.judgmentConclusion as FactoringConclusion)
    }
    if (patch.judgmentSteps) {
      const suggested = suggestJudgmentConclusion(row.judgmentSteps)
      if (suggested && !row.judgmentConclusion) applyConclusionToRow(row, suggested)
      row.basis = buildJudgmentSummary(row)
    }
  }

  function upsertRow(next: FactoringCheckRow): void {
    const idx = rows.value.findIndex(r => r.id === next.id)
    if (idx >= 0) rows.value[idx] = next
    else rows.value.push(next)
    renumber()
  }

  function loadRows(data: FactoringCheckRow[] | any[]): void {
    rows.value = (data || []).map((r, i) => migrateLegacyRow(r, i))
  }

  return {
    rows,
    conclusion,
    derecognizedRows,
    continuingRows,
    pledgedRows,
    pendingRows,
    totals,
    warningRows,
    addRow,
    removeRow,
    updateRow,
    upsertRow,
    loadRows,
    CONCLUSION_OPTIONS,
  }
}
