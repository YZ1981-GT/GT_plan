/**
 * useH2Adjustment — H2-3 在建工程调整分录汇总
 *
 * 编制逻辑（对齐 Excel「在建工程调整分录汇总表 H2-3」）：
 * 1. 列：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 /
 *    附注项目 / 借方调整金额 / 贷方调整金额 / 索引 / 备注
 * 2. 「账项调整」→ AJE 影响审定数；「报表调整」→ RJE 仅列报；「其他」按 AJE
 * 3. 仅列示与在建工程相关的审计调整；完整分录通常多行（1604 + 对方科目）且整表借贷平衡
 * 4. 索引交叉引用来源底稿（H2-5/8/9/15 等）；H2-9/H2-15 可推送自动草稿
 * 5. 与中央调整分录模块双向同步（含 1604 的完整分录组）；可推送 A13；1604 净额可回写 H2-1
 * 6. 兼容旧存档：entryType AJE|RJE、debit/credit、summary、date、reason
 */
import {
  ref,
  computed,
  watch,
  onMounted,
  onBeforeUnmount,
  getCurrentInstance,
  type Ref,
  type ComputedRef,
} from 'vue'
import { isBalanced as checkBalanced, calcSubtotal } from './useH2FormulaEngine'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H2AdjCategory = '账项调整' | '报表调整' | '其他'

export interface H2AdjustmentRow {
  rowId: string
  seq: number
  /** 调整事项说明（Excel A 列） */
  description: string
  /** 类别：账项调整 / 报表调整 / 其他（Excel B 列） */
  category: H2AdjCategory | string
  /** 派生：账项/其他→AJE，报表→RJE（供 H2-1 / A13 / 中央模块） */
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
  contraAccount?: string
  /** 来自/已推送至中央调整模块时的 entry_group_id */
  sourceGroupId?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-3-rows'
const NOTE_KEY = 'H2-3-audit-note'
const WP_CODE = 'H2'
const BALANCE_TOLERANCE = 0.01
/** 中央模块同步：分录组内含这些科目前缀即视为在建工程相关 */
const H2_RELATED_PREFIXES = ['1604', '1601', '1605', '6701']

export const H2_CATEGORY_OPTIONS: readonly H2AdjCategory[] = ['账项调整', '报表调整', '其他']

/** 在建工程及相关对方科目（录入下拉） */
export const H2_ADJ_ACCOUNT_OPTIONS = [
  { code: '1604', name: '在建工程' },
  { code: '1601', name: '固定资产' },
  { code: '1605', name: '工程物资' },
  { code: '1602', name: '累计折旧' },
  { code: '6701', name: '资产减值损失' },
  { code: '6603', name: '财务费用' },
  { code: '2202', name: '应付账款' },
  { code: '1002', name: '银行存款' },
  { code: '5301', name: '营业外支出' },
  { code: '6301', name: '营业外收入' },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `h2a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function categoryFromLegacy(raw: {
  category?: string
  entryType?: string
  adjustType?: string
}): H2AdjCategory {
  const cat = String(raw.category || '').trim()
  if ((H2_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat as H2AdjCategory
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

function isH2RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return H2_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function isCipAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1604' || c.startsWith('1604')
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

function categoryFromEntryType(et: 'AJE' | 'RJE'): H2AdjCategory {
  return et === 'RJE' ? '报表调整' : '账项调整'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Adjustment(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const rows = ref<H2AdjustmentRow[]>([])
  const auditNote = ref('')
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const lastPushMsg = ref('')

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try {
      return typeof raw === 'string' ? JSON.parse(raw) : raw
    } catch {
      return null
    }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any, idx: number): H2AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const description = String(raw.description || raw.summary || raw.reason || '').trim()
    const code = String(raw.accountCode ?? '').trim()
    const known = H2_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
    return {
      rowId: raw.rowId ?? generateRowId(),
      seq: raw.seq ?? idx + 1,
      description,
      category,
      entryType,
      reportItem: raw.reportItem ?? '在建工程',
      accountCode: code,
      accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '',
      noteItem: raw.noteItem ?? '',
      debitAmount: parseAmt(raw.debitAmount ?? raw.debit),
      creditAmount: parseAmt(raw.creditAmount ?? raw.credit),
      indexRef: String(raw.indexRef ?? raw.reference ?? '').trim(),
      remark: raw.remark ?? '',
      summary: raw.summary,
      contraAccount: raw.contraAccount ?? raw.counterAccount ?? '',
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const debitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map((r) => r.debitAmount)),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map((r) => r.creditAmount)),
  )

  const isBalanced: ComputedRef<boolean> = computed(() =>
    checkBalanced(rows.value.map((r) => ({ debit: r.debitAmount, credit: r.creditAmount }))),
  )

  const balanceDiff: ComputedRef<number> = computed(() => debitTotal.value - creditTotal.value)

  /** 账项调整净额（全表，借−贷） */
  const ajeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /** 报表调整净额 */
  const rjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  /**
   * 科目 1604 账项净额（借−贷，资产增加为正）——供 H2-1 期末账项调整回写。
   * 减值准备贷方（1604）会使净额为负，符合审定净值口径。
   */
  const cipAjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isCipAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const cipRjeNet = computed(() => {
    let net = 0
    for (const r of rows.value) {
      if (r.category !== '报表调整' && r.entryType !== 'RJE') continue
      if (!isCipAccount(r.accountCode)) continue
      net += r.debitAmount - r.creditAmount
    }
    return net
  })

  const ajeTotals = computed(() => {
    const ajeRows = rows.value.filter((r) => r.category !== '报表调整' && r.entryType !== 'RJE')
    return {
      debit: calcSubtotal(ajeRows.map((r) => r.debitAmount)),
      credit: calcSubtotal(ajeRows.map((r) => r.creditAmount)),
    }
  })

  const rjeTotals = computed(() => {
    const rjeRows = rows.value.filter((r) => r.category === '报表调整' || r.entryType === 'RJE')
    return {
      debit: calcSubtotal(rjeRows.map((r) => r.debitAmount)),
      credit: calcSubtotal(rjeRows.map((r) => r.creditAmount)),
    }
  })

  const summary = computed(() => ({
    rowCount: rows.value.length,
    ajeCount: rows.value.filter((r) => r.category !== '报表调整' && r.entryType !== 'RJE').length,
    rjeCount: rows.value.filter((r) => r.category === '报表调整' || r.entryType === 'RJE').length,
    totalDebits: debitTotal.value,
    totalCredits: creditTotal.value,
    ajeNet: ajeNet.value,
    rjeNet: rjeNet.value,
    cipAjeNet: cipAjeNet.value,
    cipRjeNet: cipRjeNet.value,
  }))

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _toPersistShape(list: H2AdjustmentRow[]) {
    return list.map((r, i) => ({
      rowId: r.rowId,
      seq: i + 1,
      description: r.description,
      category: r.category,
      entryType: entryTypeFromCategory(String(r.category)),
      reportItem: r.reportItem,
      accountCode: r.accountCode,
      accountName: r.accountName,
      noteItem: r.noteItem,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      // 兼容 H2-9/H2-15 自动草稿及旧读档
      debit: r.debitAmount,
      credit: r.creditAmount,
      indexRef: r.indexRef,
      remark: r.remark,
      sourceGroupId: r.sourceGroupId,
      summary: r.summary || r.description,
      contraAccount: r.contraAccount,
    }))
  }

  function _persist(list?: H2AdjustmentRow[]): void {
    if (!options.onSave) return
    const next = list ?? rows.value
    const shaped = _toPersistShape(next)
    rows.value = shaped.map(_normalizeRow)
    options.onSave(ROWS_KEY, shaped)
    // 乐观写入 allResponses，供 H2-1 crossSheet 即时读取
    const existing = options.allResponses.value.get(ROWS_KEY) || {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: null,
    }
    options.allResponses.value.set(ROWS_KEY, {
      ...existing,
      item_id: ROWS_KEY,
      remark: JSON.stringify(shaped),
    })
  }

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value.push({
      rowId: generateRowId(),
      seq: rows.value.length + 1,
      description: '',
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '在建工程',
      accountCode: '1604',
      accountName: '在建工程',
      noteItem: '',
      debitAmount: 0,
      creditAmount: 0,
      indexRef: 'H2-3',
      remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: keyof H2AdjustmentRow | string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return

    if (field === 'debit' || field === 'debitAmount') {
      row.debitAmount = parseAmt(value)
    } else if (field === 'credit' || field === 'creditAmount') {
      row.creditAmount = parseAmt(value)
    } else if (field === 'category') {
      row.category = String(value)
      row.entryType = entryTypeFromCategory(String(value))
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
      row.category = categoryFromEntryType(row.entryType)
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const known = H2_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
    } else if (field in row) {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function updateRow(rowId: string, patch: Partial<H2AdjustmentRow>): void {
    if (options.isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    if (patch.category != null) {
      row.entryType = entryTypeFromCategory(String(patch.category))
    }
    if (patch.entryType != null && patch.category == null) {
      row.category = categoryFromEntryType(patch.entryType === 'RJE' ? 'RJE' : 'AJE')
    }
    if (patch.accountCode != null) {
      const known = H2_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === String(patch.accountCode))
      if (known) row.accountName = known.name
    }
    _persist()
  }

  // ─── H2-1 / EventBus ───────────────────────────────────────────────────────

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
      cipAjeNet: cipAjeNet.value,
      cipRjeNet: cipRjeNet.value,
      ajeTotals: ajeTotals.value,
      rjeTotals: rjeTotals.value,
    }
    options.onPublishEvent?.('adjustment:created', payload)
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(cipAjeNet.value),
        accountCode: '1604',
        accountName: '在建工程',
        description: `H2-3 在建工程账项净额 ${cipAjeNet.value}`,
        ...payload,
      } as any)
    } catch {
      /* silent */
    }
  }

  function pushToA13(rowIds?: string[]): void {
    const targets = rowIds?.length
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value.filter(
          (r) => r.category !== '报表调整' && (r.debitAmount || r.creditAmount),
        )
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
      debit: r.debitAmount,
      credit: r.creditAmount,
      indexRef: r.indexRef || 'H2-3',
    }))
    options.onPublishEvent?.('adjustment:push-to-a13', { wp_code: WP_CODE, entries: items })
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

  // ─── 中央调整分录模块双向同步 ──────────────────────────────────────────────

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = options.projectId.value
    if (!projectId || options.isReadonly.value) return 0
    if (!isBalanced.value) {
      lastSyncMsg.value = '借贷不平衡，无法推送至调整分录模块'
      return 0
    }
    const year = Number(options.auditYear?.value)
    if (!Number.isFinite(year) || year < 1900) {
      lastSyncMsg.value = '缺少审计年度，无法推送至调整分录模块'
      return 0
    }

    const pending = rows.value.filter(
      (r) =>
        !r.sourceGroupId &&
        (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) {
      lastSyncMsg.value = '无可推送分录（可能已同步或未填金额）'
      return 0
    }

    const groups = new Map<string, H2AdjustmentRow[]>()
    for (const row of pending) {
      const key = `${row.entryType || entryTypeFromCategory(String(row.category))}||${row.description || row.rowId}`
      groups.set(key, [...(groups.get(key) || []), row])
    }

    let pushed = 0
    let list = [...rows.value]
    for (const lines of groups.values()) {
      const debit = lines.reduce((s, r) => s + r.debitAmount, 0)
      const credit = lines.reduce((s, r) => s + r.creditAmount, 0)
      if (Math.abs(debit - credit) >= BALANCE_TOLERANCE) continue
      try {
        const et = entryTypeFromCategory(String(lines[0].category))
        const res: any = await api.post(
          adjPaths.create(projectId),
          {
            adjustment_type: et === 'RJE' ? 'rje' : 'aje',
            year,
            company_code: 'default',
            description: `[H2] ${lines[0].description || '在建工程调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '1604',
              account_name: r.accountName || undefined,
              debit_amount: r.debitAmount,
              credit_amount: r.creditAmount,
            })),
          },
          { _silent: true } as any,
        )
        const groupId = res?.entry_group_id ?? res?.data?.entry_group_id ?? res?.id
        if (!groupId) continue
        const id = String(groupId)
        list = list.map((r) =>
          lines.some((l) => l.rowId === r.rowId) ? { ...r, sourceGroupId: id } : r,
        )
        pushed++
      } catch {
        lastSyncMsg.value = '底稿已保存，但部分分录未能同步至集中模块'
      }
    }
    if (pushed > 0) {
      _persist(list)
      publishAdjustment()
      eventBus.emit('adjustment:updated')
      lastSyncMsg.value = `已推送 ${pushed} 笔至调整分录模块`
    }
    return pushed
  }

  async function syncFromAdjustmentModule(): Promise<number> {
    const projectId = options.projectId.value
    if (!projectId || options.isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = Number(options.auditYear?.value) || new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: H2AdjustmentRow[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        // 仅拉取含在建工程相关科目的完整分录组（避免单边失衡）
        const hasCip = lines.some((li: any) =>
          isH2RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasCip) continue
        // 进一步：组内须含 1604，否则可能是纯固定资产调整
        const has1604 = lines.some((li: any) =>
          isCipAccount(li.standard_account_code || li.account_code),
        )
        if (!has1604) continue

        const groupId = String(item.entry_group_id || item.id || '')
        const et = entryTypeFromModule(item.adjustment_type || item.type)
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[H2\]\s*/,
          '',
        )
        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          imported.push(
            _normalizeRow(
              {
                rowId: `${groupId}-${imported.length}`,
                description: desc,
                category: categoryFromEntryType(et),
                entryType: et,
                reportItem: isCipAccount(accountCode) ? '在建工程' : '',
                accountCode,
                accountName: li.account_name || accountCode,
                debitAmount: li.debit_amount,
                creditAmount: li.credit_amount,
                indexRef: '调整分录模块',
                remark: '来自调整分录模块',
                sourceGroupId: groupId,
              },
              imported.length,
            ),
          )
        }
      }

      const manual = rows.value.filter((r) => !r.sourceGroupId)
      _persist([...manual, ...imported])
      lastSyncMsg.value = imported.length
        ? `已同步 ${imported.length} 行`
        : '调整分录模块中无含 1604 的相关分录'
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败，请稍后重试'
      return 0
    } finally {
      syncing.value = false
    }
  }

  async function confirmAndPush(): Promise<{ ok: boolean; pushed: number }> {
    if (!isBalanced.value) return { ok: false, pushed: 0 }
    _persist()
    publishAdjustment()
    const pushed = await pushToAdjustmentModule()
    return { ok: true, pushed }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function onModuleUpdated() {
    if (!options.isReadonly.value && options.projectId.value) {
      void syncFromAdjustmentModule()
    }
  }

  // 单测等非组件上下文跳过生命周期注册
  if (getCurrentInstance()) {
    onMounted(() => {
      eventBus.on('adjustment:updated', onModuleUpdated)
    })
    onBeforeUnmount(() => {
      eventBus.off('adjustment:updated', onModuleUpdated)
    })
  }

  return {
    rows,
    auditNote,
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    ajeNet,
    rjeNet,
    cipAjeNet,
    cipRjeNet,
    ajeTotals,
    rjeTotals,
    summary,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    categoryOptions: H2_CATEGORY_OPTIONS,
    accountOptions: H2_ADJ_ACCOUNT_OPTIONS,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    publishAdjustment,
    pushToA13,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    confirmAndPush,
    saveNote,
    initFromAllResponses,
  }
}

export default useH2Adjustment
