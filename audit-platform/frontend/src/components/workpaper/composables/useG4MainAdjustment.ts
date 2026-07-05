/**
 * useG4MainAdjustment — G4-3 调整分录汇总（22行×10列）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 5.3
 * Requirements: 6.1~6.5
 *
 * 功能：
 * - 22行×10列数据管理（AdjustmentEntry）
 * - isDebitCreditBalanced 实时借贷平衡校验
 * - 保存时汇总 AJE/RJE 金额回写 G4-1 审定表（closingAJE/closingRJE）
 * - 动态行增删（ElMessageBox.prompt 输入摘要）
 *
 * 比照 useF3Adjustment / useG14Adjustment
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, isDebitCreditBalanced } from '@/composables/useG4MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ═══ 数据模型 ═══

export interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

/** 按科目汇总的 AJE/RJE 金额，用于回写 G4-1 审定表 */
export interface AdjustmentSummary {
  accountCode: string
  ajeNet: number   // AJE借方 - AJE贷方
  rjeNet: number   // RJE借方 - RJE贷方
}

// ═══ 常量 ═══

const STORAGE_KEY = 'G4-3-rows'
const MAX_ROWS = 100

/** 债权投资常用科目 */
export const G4_BOND_ACCOUNTS = [
  { code: '1501', name: '债权投资——成本' },
  { code: '150101', name: '债权投资——利息调整' },
  { code: '150102', name: '债权投资——应计利息' },
  { code: '1502', name: '债权投资减值准备' },
  { code: '6011', name: '利息收入' },
  { code: '1012', name: '银行存款' },
  { code: '1101', name: '应收利息' },
] as const

// ═══ 工具函数 ═══

function generateId(): string {
  return `g4adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyEntry(seq: number, summary = ''): AdjustmentEntry {
  return {
    id: generateId(),
    seq,
    entryType: 'AJE',
    date: '',
    summary,
    accountCode: '1501',
    accountName: '债权投资——成本',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '',
    remark: '',
  }
}

function normalizeEntry(raw: any, idx: number): AdjustmentEntry {
  return {
    id: raw.id || raw.rowId || generateId(),
    seq: raw.seq ?? idx + 1,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date || '',
    summary: raw.summary || '',
    accountCode: raw.accountCode || '1501',
    accountName: raw.accountName || '债权投资——成本',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy || raw.preparer || '',
    remark: raw.remark || '',
  }
}

function parseEntries(json: string | null | undefined): AdjustmentEntry[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeEntry)
  } catch {
    return []
  }
}

// ═══ 接口定义 ═══

export interface UseG4MainAdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean> | ComputedRef<boolean>
  /** 回写回调：保存时将 AJE/RJE 汇总按科目回写 G4-1 审定表 */
  onWritebackG4_1?: (summaries: AdjustmentSummary[]) => void
}

// ═══ Composable 主体 ═══

export function useG4MainAdjustment(options: UseG4MainAdjustmentOptions) {
  const { allResponses, isReadonly, onWritebackG4_1 } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 响应式数据 ───
  const entries = ref<AdjustmentEntry[]>([])

  // ─── 从存储加载 ───
  function loadEntries(): void {
    const stored = parseEntries(allResponses.value.get(STORAGE_KEY)?.remark)
    entries.value = stored.length > 0 ? stored : [createEmptyEntry(1)]
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => { if (entries.value.length === 0) loadEntries() },
    { immediate: true },
  )

  // ─── 计算属性 ───
  const totalDebits = computed(() =>
    entries.value.reduce((sum, e) => sum + parseNum(e.debitAmount), 0),
  )

  const totalCredits = computed(() =>
    entries.value.reduce((sum, e) => sum + parseNum(e.creditAmount), 0),
  )

  const balanceDiff = computed(() => totalDebits.value - totalCredits.value)

  const isBalanced = computed(() =>
    isDebitCreditBalanced(
      entries.value.map((e) => e.debitAmount),
      entries.value.map((e) => e.creditAmount),
    ),
  )

  // ─── 持久化 ───
  function persist(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(entries.value),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) {
      window.dispatchEvent(new CustomEvent('g4:save-items', { detail: { items: [item] } }))
    }
  }

  // ─── 动态行管理 ───

  /**
   * 新增调整分录行 — 必须通过 ElMessageBox.prompt 输入摘要确认后创建
   */
  async function addEntry(): Promise<void> {
    if (readonly.value) return
    if (entries.value.length >= MAX_ROWS) return

    try {
      const { value: summary } = await ElMessageBox.prompt(
        '请输入调整分录摘要',
        '新增调整分录',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：冲回多计利息收入',
          inputValidator: (val: string) => {
            if (!val || !val.trim()) return '摘要不能为空'
            return true
          },
          inputErrorMessage: '请输入有效的摘要内容',
        },
      )
      if (!summary || !summary.trim()) return

      const newEntry = createEmptyEntry(entries.value.length + 1, summary.trim())
      entries.value = [...entries.value, newEntry]
      persist()
    } catch {
      // 用户取消 — 不做任何操作
    }
  }

  /**
   * 删除指定行（至少保留1行）
   */
  function removeEntry(id: string): void {
    if (readonly.value) return
    if (entries.value.length <= 1) return

    const idx = entries.value.findIndex((e) => e.id === id)
    if (idx === -1) return

    const next = entries.value.filter((e) => e.id !== id)
    next.forEach((e, i) => { e.seq = i + 1 })
    entries.value = next
    persist()
  }

  /**
   * 更新单元格
   */
  function updateCell(id: string, field: keyof AdjustmentEntry, value: unknown): void {
    if (readonly.value) return
    const idx = entries.value.findIndex((e) => e.id === id)
    if (idx === -1) return

    const row = { ...entries.value[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') {
      row[field] = parseNum(value)
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const acc = G4_BOND_ACCOUNTS.find((a) => a.code === row.accountCode)
      if (acc) row.accountName = acc.name
    } else if (field === 'accountName') {
      row.accountName = String(value ?? '')
      const acc = G4_BOND_ACCOUNTS.find((a) => a.name === row.accountName)
      if (acc) row.accountCode = acc.code
    } else if (field === 'seq' || field === 'id') {
      // seq/id 不可手动修改
      return
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    const next = [...entries.value]
    next[idx] = row
    entries.value = next
    persist()
  }

  // ─── 汇总回写 G4-1 审定表 ───

  /**
   * 按科目代码汇总 AJE/RJE 净额（借方-贷方），回写 G4-1 审定表
   */
  function aggregateForWriteback(): AdjustmentSummary[] {
    const map = new Map<string, { ajeNet: number; rjeNet: number }>()

    for (const entry of entries.value) {
      if (entry.debitAmount === 0 && entry.creditAmount === 0) continue
      const key = entry.accountCode || '1501'
      if (!map.has(key)) map.set(key, { ajeNet: 0, rjeNet: 0 })
      const bucket = map.get(key)!
      const net = parseNum(entry.debitAmount) - parseNum(entry.creditAmount)
      if (entry.entryType === 'AJE') {
        bucket.ajeNet += net
      } else {
        bucket.rjeNet += net
      }
    }

    return Array.from(map.entries()).map(([accountCode, amounts]) => ({
      accountCode,
      ajeNet: amounts.ajeNet,
      rjeNet: amounts.rjeNet,
    }))
  }

  /**
   * 保存并回写 G4-1 审定表
   * 调用 onWritebackG4_1 callback 将汇总数据传递给审定表更新
   */
  function saveAndWriteback(): void {
    // 立即持久化
    persist()
    // 立即 flush（不等待 debounce）
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
    flushSave()

    // 汇总并回写 G4-1
    const summaries = aggregateForWriteback()
    if (onWritebackG4_1) {
      onWritebackG4_1(summaries)
    }

    // 同时通过 CustomEvent 广播，以便其他组件监听
    window.dispatchEvent(new CustomEvent('g4:adjustment-writeback', {
      detail: { summaries },
    }))
  }

  // ─── 生命周期清理 ───
  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    // 数据
    entries,
    // 计算属性
    totalDebits,
    totalCredits,
    balanceDiff,
    isBalanced,
    // 行操作
    addEntry,
    removeEntry,
    updateCell,
    // 保存 & 回写
    saveAndWriteback,
    aggregateForWriteback,
    // 常量
    accountOptions: G4_BOND_ACCOUNTS,
    STORAGE_KEY,
  }
}

export default useG4MainAdjustment
