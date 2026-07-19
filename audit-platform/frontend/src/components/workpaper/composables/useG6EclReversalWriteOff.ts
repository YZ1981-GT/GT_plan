/**
 * useG6EclReversalWriteOff — G6-14 转回（收回）/核销检查（对齐 Excel 双表）
 */
import { ref, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { isReversalValid, calcSumColumn, parseNum } from '@/composables/useG6EclFormulaEngine'
import type {
  G6ReversalRow,
  G6WriteOffRow,
  ReversalWriteOffData,
  ReversalWriteOffRow,
} from './useG6EclFormData'

export interface ReversalSummary {
  totalReversalAmount: number
  totalAccumulatedProvision: number
  invalidCount: number
}

export interface WriteOffSummary {
  totalWriteOffAmount: number
  relatedPartyCount: number
  unreasonableCount: number
}

export interface ReversalWriteOffGate {
  invalidReversals: number
  relatedPartyWriteOffs: number
  relatedMissingAnalysis: number
  unreasonableReversals: number
  unreasonableWriteOffs: number
  ready: boolean
}

export function createEmptyReversal(
  partial: Partial<G6ReversalRow> & Pick<G6ReversalRow, 'id' | 'seq' | 'unitName'>,
): G6ReversalRow {
  return {
    reversalReason: '',
    recoveryMethod: '',
    originalBasis: '',
    reversalAmount: 0,
    accumulatedProvision: 0,
    reasonAnalysis: '',
    isReasonable: '',
    indexRef: '',
    kind: '转回',
    ...partial,
  }
}

export function createEmptyWriteOff(
  partial: Partial<G6WriteOffRow> & Pick<G6WriteOffRow, 'id' | 'seq' | 'unitName'>,
): G6WriteOffRow {
  return {
    writeOffType: '',
    writeOffAmount: 0,
    writeOffReason: '',
    writeOffProcedure: '',
    isRelatedParty: false,
    reasonAnalysis: '',
    isReasonable: '',
    indexRef: '',
    ...partial,
  }
}

/** 旧单表 → 双表迁移 */
export function migrateReversalWriteOff(raw: any): ReversalWriteOffData {
  if (!raw) {
    return { schemaVersion: 2, reversals: [], writeOffs: [], conclusion: '' }
  }
  if (raw.schemaVersion >= 2 || (Array.isArray(raw.reversals) || Array.isArray(raw.writeOffs))) {
    return {
      schemaVersion: 2,
      reversals: (raw.reversals || []).map((r: any, i: number) =>
        createEmptyReversal({
          id: String(r.id || `rev-${i}`),
          seq: i + 1,
          unitName: String(r.unitName || r.investProject || ''),
          reversalReason: String(r.reversalReason || r.reason || ''),
          recoveryMethod: String(r.recoveryMethod || ''),
          originalBasis: String(r.originalBasis || ''),
          reversalAmount: parseNum(r.reversalAmount ?? r.amount),
          accumulatedProvision: parseNum(r.accumulatedProvision),
          reasonAnalysis: String(r.reasonAnalysis || ''),
          isReasonable: (r.isReasonable || r.reasonConclusion || '') as G6ReversalRow['isReasonable'],
          indexRef: String(r.indexRef || ''),
          kind: r.kind === '收回' || r.type === '收回' ? '收回' : '转回',
        }),
      ),
      writeOffs: (raw.writeOffs || []).map((r: any, i: number) =>
        createEmptyWriteOff({
          id: String(r.id || `wo-${i}`),
          seq: i + 1,
          unitName: String(r.unitName || r.investProject || ''),
          writeOffType: String(r.writeOffType || ''),
          writeOffAmount: parseNum(r.writeOffAmount ?? r.amount),
          writeOffReason: String(r.writeOffReason || r.reason || ''),
          writeOffProcedure: String(r.writeOffProcedure || r.approvalProcedure || ''),
          isRelatedParty: Boolean(r.isRelatedParty),
          reasonAnalysis: String(r.reasonAnalysis || ''),
          isReasonable: (r.isReasonable || r.reasonConclusion || '') as G6WriteOffRow['isReasonable'],
          indexRef: String(r.indexRef || ''),
        }),
      ),
      conclusion: String(raw.conclusion || ''),
    }
  }

  // 旧 rows: type 分流
  const legacy: ReversalWriteOffRow[] = Array.isArray(raw.rows) ? raw.rows : []
  const reversals: G6ReversalRow[] = []
  const writeOffs: G6WriteOffRow[] = []
  for (const r of legacy) {
    if (r.type === '核销') {
      writeOffs.push(createEmptyWriteOff({
        id: r.id || `wo-${writeOffs.length}`,
        seq: writeOffs.length + 1,
        unitName: r.investProject || '',
        writeOffAmount: parseNum(r.amount),
        writeOffReason: r.reason || '',
        writeOffProcedure: r.approvalProcedure || '',
        isReasonable: (r.reasonConclusion || '') as G6WriteOffRow['isReasonable'],
        indexRef: r.indexRef || '',
      }))
    } else {
      reversals.push(createEmptyReversal({
        id: r.id || `rev-${reversals.length}`,
        seq: reversals.length + 1,
        unitName: r.investProject || '',
        reversalReason: r.reason || '',
        reversalAmount: parseNum(r.amount),
        isReasonable: (r.reasonConclusion || '') as G6ReversalRow['isReasonable'],
        indexRef: r.indexRef || '',
        kind: r.type === '收回' ? '收回' : '转回',
      }))
    }
  }
  return {
    schemaVersion: 2,
    reversals,
    writeOffs,
    conclusion: String(raw.conclusion || ''),
  }
}

export function useG6EclReversalWriteOff() {
  const reversals = ref<G6ReversalRow[]>([])
  const writeOffs = ref<G6WriteOffRow[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const activeRowIndex = ref(0)
  const conclusion = ref('')

  function isRowValid(row: G6ReversalRow): boolean {
    return isReversalValid(row.reversalAmount, row.accumulatedProvision)
  }

  function getReversalError(row: G6ReversalRow): string | null {
    if (!isRowValid(row)) return '转回/收回金额超过累计已计提减值准备'
    return null
  }

  function isRelatedPartyRow(row: G6WriteOffRow): boolean {
    return row.isRelatedParty === true
  }

  const reversalSummary = computed<ReversalSummary>(() => ({
    totalReversalAmount: calcSumColumn(reversals.value.map(r => r.reversalAmount)),
    totalAccumulatedProvision: calcSumColumn(reversals.value.map(r => r.accumulatedProvision)),
    invalidCount: reversals.value.filter(r => !isRowValid(r)).length,
  }))

  const writeOffSummary = computed<WriteOffSummary>(() => ({
    totalWriteOffAmount: calcSumColumn(writeOffs.value.map(r => r.writeOffAmount)),
    relatedPartyCount: writeOffs.value.filter(r => r.isRelatedParty).length,
    unreasonableCount: writeOffs.value.filter(r => r.isReasonable === '不合理').length,
  }))

  const gate = computed<ReversalWriteOffGate>(() => {
    const invalidReversals = reversals.value.filter(r => !isRowValid(r)).length
    const relatedPartyWriteOffs = writeOffs.value.filter(r => r.isRelatedParty).length
    const relatedMissingAnalysis = writeOffs.value.filter(
      r => r.isRelatedParty && !String(r.reasonAnalysis || '').trim(),
    ).length
    const unreasonableReversals = reversals.value.filter(r => r.isReasonable === '不合理').length
    const unreasonableWriteOffs = writeOffs.value.filter(r => r.isReasonable === '不合理').length
    return {
      invalidReversals,
      relatedPartyWriteOffs,
      relatedMissingAnalysis,
      unreasonableReversals,
      unreasonableWriteOffs,
      ready:
        invalidReversals === 0
        && relatedMissingAnalysis === 0
        && unreasonableReversals === 0
        && unreasonableWriteOffs === 0,
    }
  })

  async function addReversalRow(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt('请输入单位名称/投资项目', '新增转回（收回）行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValidator: (v) => (v?.trim() ? true : '名称不能为空'),
      })
      if (!value?.trim()) return
      reversals.value.push(createEmptyReversal({
        id: crypto.randomUUID(),
        seq: reversals.value.length + 1,
        unitName: value.trim(),
        isReasonable: '合理',
      }))
      activeRowIndex.value = reversals.value.length - 1
    } catch { /* cancel */ }
  }

  async function addWriteOffRow(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt('请输入单位名称/投资项目', '新增核销行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValidator: (v) => (v?.trim() ? true : '名称不能为空'),
      })
      if (!value?.trim()) return
      writeOffs.value.push(createEmptyWriteOff({
        id: crypto.randomUUID(),
        seq: writeOffs.value.length + 1,
        unitName: value.trim(),
        isReasonable: '合理',
      }))
      activeRowIndex.value = writeOffs.value.length - 1
    } catch { /* cancel */ }
  }

  function removeReversalRow(id: string): void {
    reversals.value = reversals.value.filter(r => r.id !== id)
    reversals.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function removeWriteOffRow(id: string): void {
    writeOffs.value = writeOffs.value.filter(r => r.id !== id)
    writeOffs.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function loadData(data: ReversalWriteOffData | null | undefined): void {
    const migrated = migrateReversalWriteOff(data)
    reversals.value = migrated.reversals
    writeOffs.value = migrated.writeOffs
    conclusion.value = migrated.conclusion
  }

  function toJSON(): ReversalWriteOffData {
    return {
      schemaVersion: 2,
      reversals: reversals.value.map(r => ({ ...r })),
      writeOffs: writeOffs.value.map(r => ({ ...r })),
      conclusion: conclusion.value,
    }
  }

  return {
    reversals,
    writeOffs,
    activeTab,
    activeRowIndex,
    conclusion,
    reversalSummary,
    writeOffSummary,
    gate,
    isRowValid,
    getReversalError,
    isRelatedPartyRow,
    addReversalRow,
    addWriteOffRow,
    removeReversalRow,
    removeWriteOffRow,
    loadData,
    toJSON,
  }
}

export default useG6EclReversalWriteOff
