/**
 * useF5MajorAdjustment — F5-8 主营业务成本账户中重大调整事项核查表
 *
 * 源表编制逻辑：
 *  本表是 F5-1 销售成本审定表的附表，核查营业成本账户中重大调整事项的理由是否充分。
 *  列：日期 | 凭证号 | 重大调整事项内容 | 借方 | 贷方 | 调整理由 | 理由是否充分
 *  提示：检查现金返利、实物返利是否冲减或调整存货/购货当期主营业务成本。
 *  与 F5-1 审定、F5-4 调整分录相互印证。
 * 抽凭回填 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：按分录指纹去重，行元数据 `_gt`
 * 随行 JSON 落库（spec voucher-identity-writeback-and-audit-phase 任务 11）。
 */
import { computed, ref, watch, onBeforeUnmount, type MaybeRefOrGetter, type Ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { parseNum, calcSubtotal } from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  metaOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem,
} from './shared/voucherCheckFill'

export interface UseF5MajorAdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  materiality?: Ref<number>
  /** 项目 id（抽凭回填按项目当前审计阶段标行阶段，年审阶段预审行只读） */
  projectId?: MaybeRefOrGetter<string | null | undefined>
}

export interface MajorAdjustmentRow {
  id: string
  date: string
  voucherNo: string
  itemContent: string
  debitAmount: number
  creditAmount: number
  /** 借方 − 贷方（展示/重要性判断） */
  netAmount: number
  adjustmentReason: string
  reasonAdequate: string
}

interface StoredMajorAdjustmentRow {
  id: string
  date: string
  voucherNo: string
  itemContent: string
  debitAmount: number
  creditAmount: number
  adjustmentReason: string
  reasonAdequate: string
}

const STORAGE_KEY = 'F5-8-rows'
const NOTE_KEY = 'F5-8-audit-note'
const CONCLUSION_KEY = 'F5-8-audit-conclusion'
const LEGACY_CONCLUSION_KEY = 'F5-8-conclusion'

/** 源表默认空白行数（R14–R29） */
export const F5_MAJOR_ADJ_DEFAULT_ROWS = 16

export const F5_MAJOR_ADJ_ADEQUACY_OPTIONS = ['充分', '不充分', '待补充', '不适用'] as const

function newId(): string {
  return `f5ma-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyF5MajorAdjRow(): StoredMajorAdjustmentRow {
  return {
    id: newId(),
    date: '',
    voucherNo: '',
    itemContent: '',
    debitAmount: 0,
    creditAmount: 0,
    adjustmentReason: '',
    reasonAdequate: '',
  }
}

export function defaultF5MajorAdjRows(): StoredMajorAdjustmentRow[] {
  return Array.from({ length: F5_MAJOR_ADJ_DEFAULT_ROWS }, () => emptyF5MajorAdjRow())
}

export function migrateF5MajorAdjRows(jsonStr: string | null | undefined): StoredMajorAdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => {
      let debit = parseNum(r?.debitAmount ?? r?.debit)
      let credit = parseNum(r?.creditAmount ?? r?.credit)
      // 旧单金额模型 → 正数记借方，负数记贷方
      const single = r?.adjustmentAmount ?? r?.adjustAmount
      if (debit === 0 && credit === 0 && single != null) {
        const amt = parseNum(single)
        if (amt >= 0) debit = amt
        else credit = Math.abs(amt)
      }
      const reasonParts = [
        String(r?.adjustmentReason ?? r?.adjustReason ?? ''),
        String(r?.approvalBasis ?? ''),
      ].filter((s) => s.trim())
      return withRowMeta({
        id: String(r?.id ?? r?.rowId ?? `f5ma-migrated-${i}`),
        date: String(r?.date ?? r?.adjustmentDate ?? r?.adjustDate ?? ''),
        voucherNo: String(r?.voucherNo ?? ''),
        itemContent: String(
          r?.itemContent ?? r?.adjustmentItem ?? r?.adjustItem ?? r?.content ?? '',
        ),
        debitAmount: debit,
        creditAmount: credit,
        adjustmentReason: reasonParts.join('；') || String(r?.adjustmentReason ?? ''),
        reasonAdequate: String(
          r?.reasonAdequate ?? r?.auditEvaluation ?? r?.adequate ?? '',
        ),
      }, r)
    })
  } catch {
    return []
  }
}

/** 空白占位行：没有行元数据，日期、凭证号、事项、金额、理由都没填 */
export function isBlankF5MajorAdjRow(r: StoredMajorAdjustmentRow): boolean {
  return !metaOf(r) && !r.debitAmount && !r.creditAmount
    && [r.date, r.voucherNo, r.itemContent, r.adjustmentReason, r.reasonAdequate].every((v) => !String(v ?? '').trim())
}

/** 共享回填函数的待写入项 → 调整事项行：金额在样本自己的借贷栏；事项缺省取摘要 */
export function mapPreparedToF5MajorAdjRow(item: PreparedItem): StoredMajorAdjustmentRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null }
  return {
    ...emptyF5MajorAdjRow(),
    date: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    itemContent: s.summary || '重大成本调整',
    debitAmount: parseNum(item.debitAmount),
    creditAmount: parseNum(item.creditAmount),
  }
}

/** 行上已填调整理由或理由是否充分（替换与撤销抽凭时据此先确认） */
export function hasF5MajorAdjContent(r: StoredMajorAdjustmentRow): boolean {
  return [r.adjustmentReason, r.reasonAdequate].some((v) => String(v ?? '').trim() !== '')
}

export function computeF5MajorAdjRow(stored: StoredMajorAdjustmentRow): MajorAdjustmentRow {
  return {
    ...stored,
    netAmount: stored.debitAmount - stored.creditAmount,
  }
}

export function useF5MajorAdjustment(options: UseF5MajorAdjustmentOptions) {
  const { allResponses, isReadonly, materiality } = options
  const readonly = isReadonly ?? ref(false)
  const materialityRef = materiality ?? ref(0)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedRows = ref<StoredMajorAdjustmentRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  /**
   * 抽凭回填用的表：写入时去掉空白占位行（表初始有 16 行空行，原实现表全空时整表替换），
   * 表空了补回默认空白行（同删行）
   */
  const fillTable = computed<StoredMajorAdjustmentRow[]>({
    get: () => storedRows.value,
    set: (list) => {
      const kept = list.filter((r) => !!metaOf(r) || !isBlankF5MajorAdjRow(r))
      storedRows.value = kept.length ? kept : defaultF5MajorAdjRows()
    },
  })
  // 抽凭回填 / 撤销 / 年审阶段预审行只读：共享回填函数
  const voucherFill = useVoucherCheckFill<StoredMajorAdjustmentRow>({
    projectId: options.projectId ?? null,
    tables: fillTable,
    mapSampleToRow: (item) => mapPreparedToF5MajorAdjRow(item),
    persist: () => persist(),
    hasUserContent: hasF5MajorAdjContent,
    readonly: () => readonly.value,
  })
  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedId(id: string): boolean {
    const row = storedRows.value.find((r) => r.id === id)
    return !!row && voucherFill.isRowLocked(row)
  }

  function rawJson(): string | null | undefined {
    return allResponses.value.get(STORAGE_KEY)?.remark
  }

  function loadRows(): void {
    const migrated = migrateF5MajorAdjRows(rawJson())
    storedRows.value = migrated.length ? migrated : defaultF5MajorAdjRows()
    voucherFill.markLoaded()
  }

  watch(() => rawJson(), (raw) => {
    if (raw && raw === lastPersisted) return
    loadRows()
  }, { immediate: true })

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark
        ?? allResponses.value.get(LEGACY_CONCLUSION_KEY)?.remark,
    ],
    ([note, conclusion]) => {
      auditNote.value = typeof note === 'string' ? note : ''
      auditConclusion.value = typeof conclusion === 'string' ? conclusion : ''
    },
    { immediate: true },
  )

  const rows: ComputedRef<MajorAdjustmentRow[]> = computed(() =>
    storedRows.value.map(computeF5MajorAdjRow),
  )

  const totalDebit = computed(() => calcSubtotal(storedRows.value.map((r) => r.debitAmount)))
  const totalCredit = computed(() => calcSubtotal(storedRows.value.map((r) => r.creditAmount)))
  const filledCount = computed(() =>
    storedRows.value.filter((r) =>
      r.itemContent.trim() || r.voucherNo.trim() || r.debitAmount || r.creditAmount,
    ).length,
  )

  const inadequateCount = computed(() =>
    rows.value.filter((r) => {
      if (!r.itemContent.trim() && !r.debitAmount && !r.creditAmount) return false
      const a = r.reasonAdequate.trim()
      return !a || a === '不充分' || a === '待补充'
    }).length,
  )

  function exceedsMateriality(row: MajorAdjustmentRow): boolean {
    const m = materialityRef.value
    if (m <= 0) return false
    return Math.abs(row.netAmount) > m || Math.max(row.debitAmount, row.creditAmount) > m
  }

  const exceedCount = computed(() => rows.value.filter(exceedsMateriality).length)

  function persist(): void {
    const json = JSON.stringify(voucherFill.guardPersist(storedRows.value))
    lastPersisted = json
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items } }))
      // EventBus 通知审定表/披露刷新（与其余循环对齐）
      eventBus.emit('adjustment:created', { wpCode: 'F5', timestamp: Date.now() })
    }
  }

  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value || lockedId(id)) return
    const row = storedRows.value.find((r) => r.id === id)
    if (!row) return
    if (key === 'debitAmount' || key === 'creditAmount') {
      ;(row as any)[key] = parseNum(value)
    } else if ([
      'date', 'voucherNo', 'itemContent', 'adjustmentReason', 'reasonAdequate',
    ].includes(key)) {
      ;(row as any)[key] = String(value ?? '')
    }
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    storedRows.value.push(emptyF5MajorAdjRow())
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value || lockedId(id)) return
    const next = storedRows.value.filter((r) => r.id !== id)
    storedRows.value = next.length ? next : defaultF5MajorAdjRows()
    persist()
  }

  /**
   * 抽凭引擎回填：一个对方科目一行（后端配对），金额在样本自己的借贷栏，按分录指纹去重；
   * 「替换本阶段抽凭行」只删本阶段抽凭填入的行（原实现表全空才替换、否则不去重追加，已删除）
   */
  function onEngineFilled(payload: EngineFilledPayload) {
    return voucherFill.onEngineFilled(payload)
  }

  function isRowHighlighted(row: MajorAdjustmentRow): boolean {
    if (exceedsMateriality(row)) return true
    const a = row.reasonAdequate.trim()
    if ((row.itemContent.trim() || row.debitAmount || row.creditAmount)
      && (!a || a === '不充分' || a === '待补充')) {
      return true
    }
    return false
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    totalDebit,
    totalCredit,
    filledCount,
    inadequateCount,
    exceedCount,
    auditNote,
    auditConclusion,
    updateCell,
    addRow,
    removeRow,
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled,
    onAttachImported: (samples: FillSample[]) => voucherFill.onAttachImported(samples),
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    exceedsMateriality,
    isRowHighlighted,
    saveAuditNote,
    saveAuditConclusion,
    loadRows,
  }
}

export default useF5MajorAdjustment
