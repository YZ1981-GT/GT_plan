/**
 * useJ1Detail — J1-2 明细表 composable
 *
 * 列结构(14列)：项目 | 期初(未审/AJE/RJE/审定) | 期末(未审/AJE/RJE/审定) | 附注(期初/增加/减少/期末)
 * 负债类：期末=期初+贷方(增加)-借方(减少)
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, type Ref } from 'vue'
import { calcLiabilityEndBalance, calcSubtotal, parseNum } from './useJ1FormulaEngine'

export interface DetailRow {
  id: string
  label: string
  category: string
  // 期初段
  beginUnadj: number
  beginAje: number
  beginRje: number
  beginAudited: number
  // 期末段
  endUnadj: number
  endAje: number
  endRje: number
  endAudited: number
  // 附注段（期初/增加/减少/期末）
  noteBegin: number
  noteIncrease: number
  noteDecrease: number
  noteEnd: number
}

export function useJ1Detail(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<DetailRow[]> = ref([])

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.detail_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => {
      const noteBegin = parseNum(r.note_begin as number)
      const noteIncrease = parseNum(r.note_increase as number)
      const noteDecrease = parseNum(r.note_decrease as number)
      return {
        id: String(r.id || ''),
        label: String(r.label || ''),
        category: String(r.category || ''),
        beginUnadj: parseNum(r.begin_unadj as number),
        beginAje: parseNum(r.begin_aje as number),
        beginRje: parseNum(r.begin_rje as number),
        beginAudited: parseNum(r.begin_audited as number),
        endUnadj: parseNum(r.end_unadj as number),
        endAje: parseNum(r.end_aje as number),
        endRje: parseNum(r.end_rje as number),
        endAudited: parseNum(r.end_audited as number),
        noteBegin,
        noteIncrease,
        noteDecrease,
        noteEnd: calcLiabilityEndBalance(noteBegin, noteIncrease, noteDecrease),
      }
    })
  }

  const totalEndAudited = computed(() => calcSubtotal(rows.value.map(r => r.endAudited)))
  const totalNoteEnd = computed(() => calcSubtotal(rows.value.map(r => r.noteEnd)))

  return { rows, initFromHtmlData, totalEndAudited, totalNoteEnd }
}
