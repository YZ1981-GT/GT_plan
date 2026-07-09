/**
 * useJ1Adjudication — J1 应付职工薪酬 审定表 composable
 *
 * 科目：2211应付职工薪酬（贷方/负债类）
 * J1-1审定表：57个公式覆盖短期薪酬/离职后福利/辞退福利/其他长期 四大分类
 *
 * 列结构（3组×相同结构）：
 *   项目名称 | 期初数(未审/调整/审定) | 期末数(未审/调整/审定) | 变动比较(额/率) | 原因分析
 *
 * 分类分组：
 * 1. 短期薪酬：工资/社保/公积金/福利费/工会经费/教育经费/非货币
 * 2. 离职后福利-设定提存：养老/失业/年金
 * 3. 辞退福利
 * 4. 一年内到期的其他长期
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 2.2-2.6, 3.2
 */
import { ref, computed, type Ref } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcChangeDiff,
  calcChangeRate,
  calcSubtotal,
  parseNum,
} from './useJ1FormulaEngine'

export interface AdjudicationRow {
  id: string
  label: string
  category: 'short_term' | 'post_employment' | 'severance' | 'other_long_term'
  // 期初
  beginUnadj: number
  beginAje: number
  beginAudited: number
  // 期末
  endUnadj: number
  endAje: number
  endAudited: number
  // 变动
  changeDiff: number
  changeRate: number
  // 原因分析
  analysis: string
}

export interface AdjudicationGroup {
  category: string
  label: string
  rows: AdjudicationRow[]
  subtotal: AdjudicationRow
}

const CATEGORIES = [
  { key: 'short_term', label: '（1）短期薪酬' },
  { key: 'post_employment', label: '（2）离职后福利-设定提存计划' },
  { key: 'severance', label: '（3）辞退福利' },
  { key: 'other_long_term', label: '（4）一年内到期的其他长期职工福利' },
] as const

export function useJ1Adjudication(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<AdjudicationRow[]> = ref([])
  const isInitialized = ref(false)

  // ── 初始化 ────────────────────────────────────────────────────────────────

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.adjudication_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map((r) => {
      const beginUnadj = parseNum(r.begin_unadj as number)
      const beginAje = parseNum(r.begin_aje as number)
      const beginAudited = calcAuditedAmount(beginUnadj, beginAje, 0)
      const endUnadj = parseNum(r.end_unadj as number)
      const endAje = parseNum(r.end_aje as number)
      const endAudited = calcAuditedAmount(endUnadj, endAje, 0)
      const changeDiff = calcChangeDiff(endAudited, beginAudited)
      const changeRate = calcChangeRate(endAudited, beginAudited)

      return {
        id: String(r.id || ''),
        label: String(r.label || ''),
        category: (r.category || 'short_term') as AdjudicationRow['category'],
        beginUnadj,
        beginAje,
        beginAudited,
        endUnadj,
        endAje,
        endAudited,
        changeDiff,
        changeRate,
        analysis: String(r.analysis || ''),
      }
    })
    isInitialized.value = true
  }

  // ── 按分类分组 ────────────────────────────────────────────────────────────

  const groups: Ref<AdjudicationGroup[]> = computed(() =>
    CATEGORIES.map(cat => {
      const catRows = rows.value.filter(r => r.category === cat.key)
      const subtotal: AdjudicationRow = {
        id: `subtotal-${cat.key}`,
        label: `${cat.label}小计`,
        category: cat.key as AdjudicationRow['category'],
        beginUnadj: calcSubtotal(catRows.map(r => r.beginUnadj)),
        beginAje: calcSubtotal(catRows.map(r => r.beginAje)),
        beginAudited: calcSubtotal(catRows.map(r => r.beginAudited)),
        endUnadj: calcSubtotal(catRows.map(r => r.endUnadj)),
        endAje: calcSubtotal(catRows.map(r => r.endAje)),
        endAudited: calcSubtotal(catRows.map(r => r.endAudited)),
        changeDiff: calcSubtotal(catRows.map(r => r.changeDiff)),
        changeRate: 0, // 小计行不算变动率
        analysis: '',
      }
      // 重新计算小计变动率
      subtotal.changeRate = calcChangeRate(subtotal.endAudited, subtotal.beginAudited)
      return { category: cat.key, label: cat.label, rows: catRows, subtotal }
    }),
  ) as unknown as Ref<AdjudicationGroup[]>

  // ── 合计行 ────────────────────────────────────────────────────────────────

  const grandTotal = computed(() => {
    const allRows = rows.value
    const endAudited = calcSubtotal(allRows.map(r => r.endAudited))
    const beginAudited = calcSubtotal(allRows.map(r => r.beginAudited))
    return {
      beginAudited,
      endAudited,
      changeDiff: calcChangeDiff(endAudited, beginAudited),
      changeRate: calcChangeRate(endAudited, beginAudited),
    }
  })

  // ── 更新单行 ──────────────────────────────────────────────────────────────

  function updateRow(id: string, field: keyof AdjudicationRow, value: unknown) {
    const row = rows.value.find(r => r.id === id)
    if (!row) return
    ;(row as Record<string, unknown>)[field] = value
    // 重算公式链
    row.beginAudited = calcAuditedAmount(row.beginUnadj, row.beginAje, 0)
    row.endAudited = calcAuditedAmount(row.endUnadj, row.endAje, 0)
    row.changeDiff = calcChangeDiff(row.endAudited, row.beginAudited)
    row.changeRate = calcChangeRate(row.endAudited, row.beginAudited)
  }

  return {
    rows,
    groups,
    grandTotal,
    isInitialized,
    initFromHtmlData,
    updateRow,
  }
}
