/**
 * useI2Adjudication — I2-1 开发支出审定表
 * 对齐源表期初/期末「未审·调整·审定」+ TB差异 + I2-2/I2-3 取数 + 事件发布
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type I2AdjudicationRow,
  type I2AdjudicationSummary,
  I2_ADJ_ROWS_KEY,
  I2_ADJ_NOTE_KEY,
  I2_ADJ_CONCLUSION_KEY,
  emptyI2AdjudicationRow,
  normalizeI2AdjudicationRow,
  recalcI2AdjudicationRow,
  summarizeI2Adjudication,
  seedAdjudicationFromI22,
  applyAjeFromI23,
  serializeI2AdjudicationRow,
  formatChangeRate,
  safeParseArray,
  readText,
} from './i2AdjudicationModel'
import type { I2TbData } from './useI2FormData'

export type { I2AdjudicationRow as AdjudicationRow, I2AdjudicationSummary }
export { formatChangeRate }

export function useI2Adjudication(params: {
  allResponses: Ref<Map<string, any>>
  tbData: Ref<I2TbData>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  onAfterSave?: (summary: I2AdjudicationSummary) => void | Promise<void>
}) {
  const { allResponses, tbData, saveResponses, onAfterSave } = params

  const rows = ref<I2AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function load() {
    const map = allResponses.value
    rows.value = safeParseArray(map.get(I2_ADJ_ROWS_KEY)).map(normalizeI2AdjudicationRow)
    auditNote.value = readText(map.get(I2_ADJ_NOTE_KEY))
    auditConclusion.value = readText(map.get(I2_ADJ_CONCLUSION_KEY))
  }

  watch(allResponses, () => load(), { immediate: true })

  const summary: ComputedRef<I2AdjudicationSummary> = computed(() => summarizeI2Adjudication(rows.value))

  const totalRow = computed(() => emptyI2AdjudicationRow({
    projectName: '合计',
    beginUnadj: summary.value.beginUnadj,
    beginAdj: summary.value.beginAdj,
    endUnadj: summary.value.endUnadj,
    endAdj: summary.value.endAdj,
    increaseCapitalized: summary.value.increaseCapitalized,
    decreaseTransfer: summary.value.decreaseTransfer,
    decreaseExpense: summary.value.decreaseExpense,
  }))

  const tbRow = computed(() => emptyI2AdjudicationRow({
    projectName: 'TB数据',
    beginUnadj: 0,
    endUnadj: tbData.value.unadjusted1717 || tbData.value.audited1717 || 0,
    endAdj: (tbData.value.aje1717 || 0) + (tbData.value.rje1717 || 0),
  }))

  /** 差异 = 合计期末审定 − TB期末审定（或未审+调整） */
  const tbDiff = computed(() => {
    const tbAudited = Math.abs(tbData.value.audited1717) > 0.005
      ? tbData.value.audited1717
      : (tbData.value.unadjusted1717 + tbData.value.aje1717 + tbData.value.rje1717)
    return Math.round((summary.value.endAudited - tbAudited) * 100) / 100
  })

  const diffRow = computed(() => emptyI2AdjudicationRow({
    projectName: '差异',
    endUnadj: Math.round((summary.value.endUnadj - (tbData.value.unadjusted1717 || 0)) * 100) / 100,
    endAdj: 0,
    beginUnadj: 0,
  }))

  // 覆盖 diffRow 的 endAudited 展示用
  const displayDiffEndAudited = computed(() => tbDiff.value)

  const hasTbDiff = computed(() => Math.abs(tbDiff.value) > 0.01)

  function addRow(projectName: string) {
    if (!projectName?.trim()) return
    rows.value.push(emptyI2AdjudicationRow({ projectName: projectName.trim() }))
  }

  function removeRow(rowId: string) {
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
  }

  function updateRow(rowId: string, field: keyof I2AdjudicationRow, value: number | string) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const numericFields = [
      'beginUnadj', 'beginAdj', 'endUnadj', 'endAdj',
      'increaseCapitalized', 'decreaseTransfer', 'decreaseExpense',
    ]
    if (numericFields.includes(field as string)) {
      ;(row as any)[field] = Number(value) || 0
      // 手工改期末调整 → 视为已复核，清除近似标记
      if (field === 'endAdj') row.ajeApprox = false
    } else if (field === 'projectName' || field === 'reasonAnalysis') {
      ;(row as any)[field] = String(value ?? '')
    } else {
      return
    }
    recalcI2AdjudicationRow(row)
  }

  const hasAjeApprox = computed(() => rows.value.some((r) => r.ajeApprox))

  function seedFromDetail(): { ok: boolean; message: string } {
    const detail = safeParseArray(allResponses.value.get('I2-2-rows'))
    const seeded = seedAdjudicationFromI22(detail)
    if (!seeded.length) return { ok: false, message: '暂无 I2-2 明细可供带入' }
    // 按项目名合并
    const byName = new Map(rows.value.map((r) => [r.projectName.trim(), r]))
    let n = 0
    for (const s of seeded) {
      const prev = byName.get(s.projectName.trim())
      if (prev) {
        prev.beginUnadj = s.beginUnadj
        prev.endUnadj = s.endUnadj || prev.endUnadj
        prev.increaseCapitalized = s.increaseCapitalized
        prev.decreaseTransfer = s.decreaseTransfer
        prev.decreaseExpense = s.decreaseExpense
        recalcI2AdjudicationRow(prev)
      } else {
        rows.value.push(s)
        byName.set(s.projectName.trim(), s)
      }
      n++
    }
    return { ok: true, message: `已从 I2-2 带入/更新 ${n} 个项目` }
  }

  function syncAjeFromI23(): { ok: boolean; message: string; approx?: boolean } {
    const adj = safeParseArray(allResponses.value.get('I2-3-rows'))
    if (!adj.length) return { ok: false, message: '暂无 I2-3 调整分录' }
    if (!rows.value.length) return { ok: false, message: '请先维护项目行再同步调整' }
    const { rows: next, applied, approx, matchedByName } = applyAjeFromI23(rows.value, adj)
    rows.value = next
    const parts = [`已写入期末调整至 ${applied} 行`]
    if (matchedByName) parts.push(`其中按项目名精确匹配 ${matchedByName} 笔`)
    if (approx) parts.push('其余按期末未审占比分摊（近似，须人工复核）')
    return { ok: true, message: parts.join('；'), approx }
  }

  function applyTbToUnadj() {
    const tb = tbData.value.unadjusted1717
    if (Math.abs(tb) < 0.005) return { ok: false, message: 'TB 未审数为 0' }
    if (!rows.value.length) {
      rows.value.push(emptyI2AdjudicationRow({
        projectName: '开发支出',
        endUnadj: tb,
        endAdj: (tbData.value.aje1717 || 0) + (tbData.value.rje1717 || 0),
      }))
      return { ok: true, message: '已用 TB 创建开发支出汇总行' }
    }
    if (rows.value.length === 1) {
      rows.value[0].endUnadj = tb
      rows.value[0].endAdj = (tbData.value.aje1717 || 0) + (tbData.value.rje1717 || 0)
      recalcI2AdjudicationRow(rows.value[0])
      return { ok: true, message: '已将 TB 未审/调整写入唯一项目行' }
    }
    return { ok: false, message: '多项目时请用「从 I2-2 带入」，TB 仅作合计勾稽' }
  }

  async function save(): Promise<void> {
    await saveResponses('I2-1', {
      [I2_ADJ_ROWS_KEY]: JSON.stringify(rows.value.map(serializeI2AdjudicationRow)),
      [I2_ADJ_NOTE_KEY]: auditNote.value,
      [I2_ADJ_CONCLUSION_KEY]: auditConclusion.value,
    })
    await onAfterSave?.(summary.value)

    // 发布审定事件 → 附注/跨底稿
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'I2',
        accountCode: '1717',
        adjudicatedAmount: summary.value.endAudited,
        beginAudited: summary.value.beginAudited,
        transferToIntangible: summary.value.decreaseTransfer,
      },
    }))
    if (summary.value.decreaseTransfer > 0.005) {
      window.dispatchEvent(new CustomEvent('development:capitalized-to-intangible', {
        detail: {
          wpCode: 'I2',
          transferAmount: summary.value.decreaseTransfer,
        },
      }))
    }
  }

  async function saveAuditField(kind: 'note' | 'conclusion', val: string) {
    if (kind === 'note') {
      auditNote.value = val
      await saveResponses('I2-1', { [I2_ADJ_NOTE_KEY]: val })
    } else {
      auditConclusion.value = val
      await saveResponses('I2-1', { [I2_ADJ_CONCLUSION_KEY]: val })
    }
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    summary,
    totalRow,
    tbRow,
    diffRow,
    tbDiff,
    displayDiffEndAudited,
    hasTbDiff,
    hasAjeApprox,
    addRow,
    removeRow,
    updateRow,
    seedFromDetail,
    syncAjeFromI23,
    applyTbToUnadj,
    save,
    saveAuditField,
    load,
  }
}

export default useI2Adjudication
