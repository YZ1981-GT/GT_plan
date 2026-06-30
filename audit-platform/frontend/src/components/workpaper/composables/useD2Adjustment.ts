/**
 * useD2Adjustment — 调整分录D2-4核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 6.1
 *
 * 职责：
 * - AdjustmentEntry 类型定义（10列）
 * - entries reactive（从 D2-entry-rows JSON remark加载）
 * - debitTotal / creditTotal computed（SUM各列）
 * - isBalanced computed（Math.abs(debit - credit) < 0.005 容差）
 * - balanceDiff computed（debit - credit）
 * - addEntry() / removeEntry(rowId) 动态行管理
 * - updateEntry + debounce 2s 保存（选择类即时保存）
 * - publishAdjustment() — EventBus 'adjustment:created'
 * - pushToA13(rowIds) — EventBus 推送选中分录到 A13 错报汇总
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { parseNum } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdjustmentEntry {
  rowId: string
  description: string          // 调整事项说明
  entryType: 'AJE' | 'RJE'   // 类别
  reportItem: string           // 报表项目
  accountName: string          // 科目名称
  noteItem: string             // 附注项目
  debitAmount: number          // 借方调整金额
  creditAmount: number         // 贷方调整金额
  indexRef: string             // 索引
  remark: string               // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** allResponses Map 中存储调整分录行数据的 key */
const STORAGE_KEY = 'D2-entry-rows'

/** 借贷平衡容差（避免浮点精度问题） */
const BALANCE_TOLERANCE = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成简易唯一ID */
function generateRowId(): string {
  return `adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/** 创建空调整分录行 */
function createEmptyEntry(): AdjustmentEntry {
  return {
    rowId: generateRowId(),
    description: '',
    entryType: 'AJE',
    reportItem: '',
    accountName: '',
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: '',
    remark: '',
  }
}

/**
 * 解析JSON remark为分录数组
 */
function parseEntries(jsonStr: string | null | undefined): AdjustmentEntry[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      description: raw.description || '',
      entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
      reportItem: raw.reportItem || '',
      accountName: raw.accountName || '',
      noteItem: raw.noteItem || '',
      debitAmount: parseNum(raw.debitAmount),
      creditAmount: parseNum(raw.creditAmount),
      indexRef: raw.indexRef || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Adjustment(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const entries = ref<AdjustmentEntry[]>([])
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadEntries(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    entries.value = parseEntries(resp?.remark)
  }

  // Watch allResponses for initial load
  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      // Only reload on initial (empty state)
      if (entries.value.length === 0) {
        loadEntries()
      }
    },
    { immediate: true }
  )

  // ─── Computed: Totals ──────────────────────────────────────────────────

  /** 借方合计 = SUM all entries debitAmount */
  const debitTotal: ComputedRef<number> = computed(() => {
    return entries.value.reduce((sum, e) => sum + parseNum(e.debitAmount), 0)
  })

  /** 贷方合计 = SUM all entries creditAmount */
  const creditTotal: ComputedRef<number> = computed(() => {
    return entries.value.reduce((sum, e) => sum + parseNum(e.creditAmount), 0)
  })

  /** 借贷差额 = debit - credit */
  const balanceDiff: ComputedRef<number> = computed(() => {
    return debitTotal.value - creditTotal.value
  })

  /** 是否平衡（容差0.005以内视为平衡） */
  const isBalanced: ComputedRef<boolean> = computed(() => {
    return Math.abs(balanceDiff.value) < BALANCE_TOLERANCE
  })

  // ─── Row Management ────────────────────────────────────────────────────

  /**
   * 新增一行空白调整分录
   */
  function addEntry(): void {
    if (isReadonly.value) return
    entries.value.push(createEmptyEntry())
    debounceSave()
  }

  /**
   * 删除指定分录行
   */
  function removeEntry(rowId: string): void {
    if (isReadonly.value) return
    const idx = entries.value.findIndex(e => e.rowId === rowId)
    if (idx === -1) return
    entries.value.splice(idx, 1)
    immediatelySave()
  }

  // ─── Update Entry ──────────────────────────────────────────────────────

  /**
   * 编辑分录字段
   * - 选择类字段（entryType dropdown）立即保存
   * - 文本/金额类字段 debounce 2s 保存
   */
  function updateEntry(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const entry = entries.value.find(e => e.rowId === rowId)
    if (!entry) return

    const key = field as keyof AdjustmentEntry
    if (key === 'rowId') return // Cannot change rowId

    if (key === 'debitAmount' || key === 'creditAmount') {
      ;(entry as any)[key] = parseNum(value)
    } else {
      ;(entry as any)[key] = value
    }

    // 选择类字段（entryType）立即保存；其他字段 debounce
    if (key === 'entryType') {
      immediatelySave()
    } else {
      debounceSave()
    }
  }

  // ─── EventBus: publishAdjustment ───────────────────────────────────────

  /**
   * 发布 'adjustment:created' 事件
   * payload: { wpCode:'D2', entryType, amount, description, debitAccount, creditAccount }
   *
   * 取最近一条分录的信息作为事件payload
   * 如需发布全部分录，外部循环调用或传 rowIds 参数
   */
  function publishAdjustment(): void {
    // Publish all current entries info
    for (const entry of entries.value) {
      if (entry.debitAmount === 0 && entry.creditAmount === 0) continue
      const payload = {
        wpCode: 'D2',
        entryType: entry.entryType,
        amount: Math.max(entry.debitAmount, entry.creditAmount),
        description: entry.description,
        debitAccount: entry.accountName,
        creditAccount: entry.accountName,
      }
      try {
        window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
      } catch {
        // silent
      }
    }
  }

  // ─── EventBus: pushToA13 ───────────────────────────────────────────────

  /**
   * 推送选中分录到 A13 错报汇总
   * 发布 window CustomEvent 'a13:push-misstatement'
   */
  function pushToA13(rowIds: string[]): void {
    const selected = entries.value.filter(e => rowIds.includes(e.rowId))
    if (selected.length === 0) return

    const misstatements = selected.map(entry => ({
      wpCode: 'D2',
      entryType: entry.entryType,
      description: entry.description,
      reportItem: entry.reportItem,
      accountName: entry.accountName,
      debitAmount: entry.debitAmount,
      creditAmount: entry.creditAmount,
      indexRef: entry.indexRef,
    }))

    try {
      window.dispatchEvent(new CustomEvent('a13:push-misstatement', {
        detail: { items: misstatements },
      }))
    } catch {
      // silent
    }
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function serialize(): string {
    return JSON.stringify(entries.value)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function immediatelySave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = null
    flushSave()
  }

  function flushSave(): void {
    const json = serialize()
    // Update allResponses Map
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    // Dispatch save event
    dispatchSaveEvent(json)
  }

  /**
   * 触发保存事件（CustomEvent 'd2:save-items'，由 useD2FormData 监听处理）
   */
  function dispatchSaveEvent(json: string): void {
    try {
      const items = [{
        item_id: STORAGE_KEY,
        conclusion: null,
        remark: json,
      }]
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 分录数据
    entries,

    // 合计与平衡
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,

    // EventBus 发布
    publishAdjustment,
    pushToA13,

    // 工具方法（供外部/测试使用）
    loadEntries,
    serialize,
  }
}

export default useD2Adjustment
