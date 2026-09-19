/**
 * useD7LongTerm — D7-5 账龄1年以上检查（8列）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 10.1
 * Requirements: 10.1-10.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum, calcSubtotal } from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'
import type { DetailRow } from './useD7Detail'
import { useAgingConfig } from '@/composables/useAgingConfig'

/** ">1年" 段判定阈值（天）：dayFrom ≥ 366 视为账龄超过 1 年 */
const OVER_ONE_YEAR_DAY_FROM = 366

// ─── Types ───────────────────────────────────────────────────────────────────

export interface LongTermRow {
  rowId: string
  customerName: string       // 客户名称
  endBalance: number         // 期末余额
  aging: string              // 账龄
  businessDescription: string // 经济业务说明
  reason: string             // 未结转或未偿还的原因
  auditDateTransfer: number  // 至审计日结转或偿还金额
  plan: string               // 处理计划
  disposalConclusion: string // 处置结论
  remark: string             // 备注
}

/** 处置结论枚举 */
export const D7_DISPOSAL_CONCLUSIONS = [
  '应确认收入',
  '应退回',
  '正常挂账',
  '应转营业外收入',
  '待确定',
] as const

export interface UseD7LongTermOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'D7-5-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `lt-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): LongTermRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): LongTermRow {
  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    endBalance: parseNum(raw.endBalance),
    aging: raw.aging || '',
    businessDescription: raw.businessDescription || '',
    reason: raw.reason || '',
    auditDateTransfer: parseNum(raw.auditDateTransfer),
    plan: raw.plan || '',
    disposalConclusion: raw.disposalConclusion || '',
    remark: raw.remark || '',
  }
}

function createEmptyRow(): LongTermRow {
  return {
    rowId: generateRowId(),
    customerName: '', endBalance: 0, aging: '',
    businessDescription: '', reason: '',
    auditDateTransfer: 0, plan: '', disposalConclusion: '', remark: '',
  }
}

/** 单行"超过1年"段之和（期末审定账龄 nested keyed），按传入 overKeys 动态求和 */
function sumOverOneYear(row: any, overKeys: string[]): number {
  const audited = (row?.agingAudited ?? {}) as Record<string, number>
  return overKeys.reduce((sum, k) => sum + parseNum(audited[k]), 0)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7LongTerm(options: UseD7LongTermOptions) {
  const { allResponses, debouncedSave, projectId } = options

  // ─── Aging Config Integration (subject='D7', 2-period) ──────────────
  const { segments } = useAgingConfig(projectId, 'D7')

  /** 账龄超 1 年的段 key（dayFrom ≥ 366，按项目配置动态判定，不硬编码 4 段）Req 5.1/5.4 */
  const overOneYearKeys = computed<string[]>(() =>
    segments.value.filter(s => s.dayFrom >= OVER_ONE_YEAR_DAY_FROM).map(s => s.key),
  )

  // ─── Reactive rows ───────────────────────────────────────────────────

  const rows = ref<LongTermRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  // ─── Total Row ───────────────────────────────────────────────────────

  const totalRow: ComputedRef<{ endBalance: number; auditDateTransfer: number }> = computed(() => ({
    endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    auditDateTransfer: calcSubtotal(rows.value.map(r => r.auditDateTransfer)),
  }))

  // ─── Add/Remove/Update ───────────────────────────────────────────────

  function addRow(): void {
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    rows.value = rows.value.map(r => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (field === 'endBalance' || field === 'auditDateTransfer') {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    })
    persistRows()
  }

  // ─── Import from D7-2 (filter aging > 1 year) ───────────────────────

  function importFromD72(): void {
    const d7DetailJson = allResponses.value.get('D7-2-rows')?.remark
    if (!d7DetailJson) {
      ElMessage.info('D7-2明细表暂无数据')
      return
    }

    let detailRows: DetailRow[] = []
    try { detailRows = JSON.parse(d7DetailJson) } catch { return }

    // 超过1年段：账龄配置中 dayFrom >= 366 的段（不硬编码 4 段，Req 5.1/5.4）
    const overKeys = overOneYearKeys.value
    const segLabelByKey = new Map(segments.value.map(s => [s.key, s.label]))

    // 筛选期末审定账龄中"超过1年"段之和 > 0 的明细行（Req 5.2）
    const longTermRows = detailRows.filter((r: any) => sumOverOneYear(r, overKeys) > 0)

    if (longTermRows.length === 0) {
      ElMessage.info('未找到账龄超过1年的客户')
      return
    }

    // Dedup by customer name
    const existingNames = new Set(rows.value.map(r => r.customerName))
    const newRows: LongTermRow[] = longTermRows
      .filter((r: any) => !existingNames.has(r.companyName || r.contractName))
      .map((r: any) => {
        // 账龄 label 取占比最大的"超过1年"段 label（Req 5.3）
        const audited = (r.agingAudited ?? {}) as Record<string, number>
        let topKey = overKeys[0] || ''
        let topAmt = -Infinity
        for (const k of overKeys) {
          const amt = parseNum(audited[k])
          if (amt > topAmt) { topAmt = amt; topKey = k }
        }
        const aging = segLabelByKey.get(topKey) || topKey || '1年以上'

        return normalizeRow({
          rowId: generateRowId(),
          customerName: r.companyName || r.contractName || '',
          endBalance: parseNum(r.endAudited),
          aging,
        })
      })

    if (newRows.length > 0) {
      rows.value = [...rows.value, ...newRows]
      persistRows()
      ElMessage.success(`从D7-2导入${newRows.length}个账龄超过1年的客户`)
    } else {
      ElMessage.info('所有超1年客户已存在')
    }
  }

  // ─── D7-2 账龄>1年合计（供 D7-5↔D7-2 勾稽，按 segment 动态判定） ─────
  // 单一动态来源，供消费组件勾稽校验复用，避免在 .vue 中硬编码 endAging2+3+4。

  const d72LongTermTotal = computed<number>(() => {
    const jsonStr = allResponses.value.get('D7-2-rows')?.remark
    if (!jsonStr) return 0
    let detailRows: any[] = []
    try {
      const parsed = JSON.parse(jsonStr)
      detailRows = Array.isArray(parsed) ? parsed : []
    } catch {
      return 0
    }
    const overKeys = overOneYearKeys.value
    return detailRows.reduce((sum, r) => sum + sumOverOneYear(r, overKeys), 0)
  })

  // ─── Disposal Summary (处置结论统计) ───────────────────────────────

  const disposalSummary = computed(() => {
    const counts: Record<string, number> = {}
    for (const row of rows.value) {
      if (row.disposalConclusion) {
        counts[row.disposalConclusion] = (counts[row.disposalConclusion] || 0) + 1
      }
    }
    return counts
  })

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(allResponses, (map) => {
    auditNotes.value.explanation = map.get('D7-5-note-explanation')?.remark || ''
    auditNotes.value.conclusion = map.get('D7-5-note-conclusion')?.remark || ''
  }, { immediate: true })

  watch(() => auditNotes.value.explanation, (v) => debouncedSave('D7-5-note-explanation', { remark: v }))
  watch(() => auditNotes.value.conclusion, (v) => debouncedSave('D7-5-note-conclusion', { remark: v }))

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    disposalSummary,
    overOneYearKeys,
    d72LongTermTotal,
    addRow,
    removeRow,
    updateCell,
    importFromD72,
    auditNotes,
  }
}

export default useD7LongTerm
