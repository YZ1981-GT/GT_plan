/**
 * useH1Adjustment — H1-3 固定资产调整分录汇总
 *
 * 编制逻辑（对齐 Excel「固定资产调整分录汇总表 H1-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目名称 /
 *    附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注
 * 2. 数字化增强：科目代码（TB/审定映射）、借贷平衡、推送 A13
 * 3. 「账项调整」→ entryType=AJE 影响审定数；「报表调整」→ RJE 仅列报；「其他」按 AJE
 * 4. 兼容旧存档：adjustType/AJE|RJE、debit/credit、reference、summary
 * 5. 持久化 H1-3-rows；publish adjustment:created → H1-1；a13:push-misstatement → A13
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Req 4.1-4.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H1AdjCategory = '账项调整' | '报表调整' | '其他'

export interface H1AdjustmentRow {
  rowId: string
  seq: number
  /** 调整事项说明（Excel A 列） */
  description: string
  /** 类别：账项调整 / 报表调整 / 其他（Excel B 列） */
  category: H1AdjCategory | string
  /** 派生：账项/其他→AJE，报表→RJE（供 H1-1 / A13） */
  entryType: 'AJE' | 'RJE' | ''
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** @deprecated 旧摘要，读档并入 description */
  summary?: string
  /** @deprecated 对方科目，保留兼容导入 */
  counterAccount?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-3'
const WP_CODE = 'H1'
const BALANCE_TOLERANCE = 0.01

export const H1_CATEGORY_OPTIONS: readonly H1AdjCategory[] = ['账项调整', '报表调整', '其他']

/** 固定资产及相关对方科目（录入下拉） */
export const H1_ADJ_ACCOUNT_OPTIONS = [
  { code: '1601', name: '固定资产' },
  { code: '1602', name: '累计折旧' },
  { code: '1603', name: '固定资产减值准备' },
  { code: '1604', name: '在建工程' },
  { code: '1605', name: '工程物资' },
  { code: '1606', name: '固定资产清理' },
  { code: '5301', name: '营业外支出' },
  { code: '6301', name: '营业外收入' },
  { code: '5602', name: '管理费用' },
  { code: '5001', name: '生产成本' },
  { code: '5101', name: '制造费用' },
  { code: '1002', name: '银行存款' },
  { code: '2202', name: '应付账款' },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `h1a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function categoryFromLegacy(raw: {
  category?: string
  entryType?: string
  adjustType?: string
}): H1AdjCategory {
  const cat = String(raw.category || '').trim()
  if ((H1_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat as H1AdjCategory
  if (cat === '重分类调整') return '报表调整'
  const legacy = String(raw.entryType || raw.adjustType || '').toUpperCase()
  if (legacy === 'RJE' || cat.includes('报表') || cat.includes('重分类')) return '报表调整'
  if (cat.includes('其他')) return '其他'
  return '账项调整'
}

export function entryTypeFromCategory(category: string): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

function parseAmt(v: unknown): number {
  if (v == null || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Adjustment(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  const rows = ref<H1AdjustmentRow[]>([])
  const lastPushMsg = ref('')

  function _loadRows(): void {
    const item = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    const raw = item?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
    } catch { rows.value = [] }
  }

  function _normalizeRow(raw: any, idx: number): H1AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const description = String(raw.description || raw.summary || '').trim()
    const code = String(raw.accountCode ?? '').trim()
    const known = H1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
    return {
      rowId: raw.rowId ?? generateRowId(),
      seq: raw.seq ?? idx + 1,
      description,
      category,
      entryType,
      reportItem: raw.reportItem ?? '固定资产',
      accountCode: code,
      accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '',
      noteItem: raw.noteItem ?? '',
      debitAmount: parseAmt(raw.debitAmount ?? raw.debit),
      creditAmount: parseAmt(raw.creditAmount ?? raw.credit),
      indexRef: String(raw.indexRef ?? raw.reference ?? '').trim(),
      remark: raw.remark ?? '',
      summary: raw.summary,
      counterAccount: raw.counterAccount ?? raw.contraAccount ?? '',
    }
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const isBalanced = computed(() => Math.abs(debitTotal.value - creditTotal.value) < BALANCE_TOLERANCE)
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)

  /** 账项调整净额（借−贷，资产增加为正） */
  const ajeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /** 报表调整净额（不回写审定损益口径，仅列报） */
  const rjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  function addRow(): void {
    rows.value.push({
      rowId: generateRowId(),
      seq: rows.value.length + 1,
      description: '',
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '固定资产',
      accountCode: '1601',
      accountName: '固定资产',
      noteItem: '',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: 'H1-3',
      remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: keyof H1AdjustmentRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'category') {
      row.entryType = entryTypeFromCategory(String(value))
    }
    if (field === 'accountCode') {
      const known = H1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(value))
      if (known && !row.accountName) row.accountName = known.name
      if (known) row.accountName = known.name
    }
    _persist()
  }

  function updateRow(rowId: string, patch: Partial<H1AdjustmentRow>): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    if (patch.category != null) {
      row.entryType = entryTypeFromCategory(String(patch.category))
    }
    if (patch.accountCode != null) {
      const known = H1_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(patch.accountCode))
      if (known) row.accountName = known.name
    }
    _persist()
  }

  function publishAdjustment(): void {
    const payload = {
      wp_code: WP_CODE,
      wpCode: WP_CODE,
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
      totalAje: ajeNet.value,
      totalRje: rjeNet.value,
    }
    options?.onPublishEvent?.('adjustment:created', payload)
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(ajeNet.value),
        accountCode: '1601',
        accountName: '固定资产',
        description: `H1-3 账项净额 ${ajeNet.value}`,
        ...payload,
      } as any)
    } catch { /* silent */ }
  }

  function pushToA13(rowIds?: string[]): void {
    const targets = rowIds?.length
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value.filter((r) => r.category !== '报表调整' && (r.debitAmount || r.creditAmount))
    if (!targets.length) {
      lastPushMsg.value = '无可推送行（报表调整默认不推，或未填金额）'
      return
    }
    const items = targets.map((r) => ({
      wpCode: WP_CODE,
      entryType: entryTypeFromCategory(String(r.category)),
      description: r.description,
      reportItem: r.reportItem,
      accountCode: r.accountCode,
      accountName: r.accountName,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      indexRef: r.indexRef || 'H1-3',
    }))
    options?.onPublishEvent?.('adjustment:push-to-a13', { wp_code: WP_CODE, entries: items })
    try {
      eventBus.emit('a13:push-misstatement', {
        items,
        wpCode: WP_CODE,
        timestamp: Date.now(),
      })
      lastPushMsg.value = `已推送 ${targets.length} 行至 A13`
    } catch {
      lastPushMsg.value = '推送失败'
    }
  }

  function _persist(): void {
    // H1-1 跨表同步走 allResponses Map（onSave 乐观写入）；EventBus 仅在显式 publish/push 时派发
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows,
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    ajeNet,
    rjeNet,
    lastPushMsg,
    categoryOptions: H1_CATEGORY_OPTIONS,
    accountOptions: H1_ADJ_ACCOUNT_OPTIONS,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    publishAdjustment,
    pushToA13,
  }
}

export default useH1Adjustment
