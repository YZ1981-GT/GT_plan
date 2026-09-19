/**
 * useI3Adjustment — I3-3 商誉调整分录汇总
 *
 * 对齐源 xlsx「商誉调整分录汇总表 I3-3」：
 * 调整事项说明 / 类别(账项·报表·其他) / 报表项目 / 科目名称 / 附注项目 /
 * 借方调整金额 / 贷方调整金额 / 索引 / 备注
 *
 * 联动：
 * - EventBus adjustment:created → I3-1 审定表 AJE/RJE（1711 净额）
 * - 中央调整分录模块双向同步（含 1711 的分录组）
 * - a13:push-misstatement（账项调整）
 * - 可从 I3-6 商誉减值草稿生成分录
 */
import {
  ref,
  computed,
  watch,
  type Ref,
  type ComputedRef,
} from 'vue'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'

export type I3AdjCategory = '账项调整' | '报表调整' | '其他'

export interface I3AdjustmentRow {
  rowId: string
  seq: number
  description: string
  category: I3AdjCategory | string
  entryType: 'AJE' | 'RJE' | ''
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 被投资单位（供 I3-1 精确匹配 AJE） */
  investee: string
  /** 兼容旧字段 */
  summary?: string
  debit?: number
  credit?: number
  sourceGroupId?: string
}

const ROWS_KEY = 'I3-3-rows'
const NOTE_KEY = 'I3-3-audit-note'
const CONCLUSION_KEY = 'I3-3-audit-conclusion'
const AJE_NET_KEY = 'I3-3-aje-net'
const RJE_NET_KEY = 'I3-3-rje-net'
const WP_CODE = 'I3'
const BALANCE_TOLERANCE = 0.01

/** 中央模块：含这些科目前缀视为商誉相关 */
const I3_RELATED_PREFIXES = ['1711', '6701', '6115', '6602', '2221', '1002']

export const I3_CATEGORY_OPTIONS: readonly I3AdjCategory[] = ['账项调整', '报表调整', '其他']

export const I3_ADJ_ACCOUNT_OPTIONS = [
  { code: '1711', name: '商誉' },
  { code: '1711.01', name: '商誉减值准备' },
  { code: '6701', name: '资产减值损失' },
  { code: '6115', name: '资产处置收益' },
  { code: '6602', name: '管理费用' },
  { code: '2221', name: '应交税费' },
  { code: '1002', name: '银行存款' },
  { code: '2202', name: '应付账款' },
] as const

function generateRowId(): string {
  return `i3-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function parseAmt(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function entryTypeFromCategory(category: string): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

export function categoryFromLegacy(raw: any): I3AdjCategory {
  const c = String(raw?.category ?? '')
  if (c === '报表调整' || c === '账项调整' || c === '其他') return c
  if (raw?.entryType === 'RJE') return '报表调整'
  return '账项调整'
}

function isGoodwillAccount(code: string): boolean {
  return String(code || '').startsWith('1711')
}

function isI3RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return I3_RELATED_PREFIXES.some((p) => c.startsWith(p))
}

function reportItemForAccount(code: string): string {
  if (isGoodwillAccount(code)) return '商誉'
  if (String(code).startsWith('6701')) return '资产减值损失'
  return ''
}

export function buildI3ImpairmentDraftLines(opts: {
  cguName: string
  goodwillImpairment: number
  indexRef?: string
  investee?: string
  /** 贷方科目，默认 1711 商誉；可改为商誉减值准备科目 */
  creditAccountCode?: string
  creditAccountName?: string
}): I3AdjustmentRow[] {
  const amt = Math.round((opts.goodwillImpairment || 0) * 100) / 100
  if (amt <= 0.005) return []
  const desc = `计提商誉减值-${opts.cguName || '未命名CGU'}`
  const idx = opts.indexRef || 'I3-6'
  const creditCode = opts.creditAccountCode || '1711'
  const known = I3_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === creditCode)
  const creditName = opts.creditAccountName || known?.name || '商誉'
  const investee = String(opts.investee || '').trim()
  return [
    {
      rowId: generateRowId(),
      seq: 1,
      description: desc,
      investee,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '资产减值损失',
      accountCode: '6701',
      accountName: '资产减值损失',
      noteItem: '商誉',
      debitAmount: amt,
      creditAmount: 0,
      indexRef: idx,
      remark: '由 I3-6 减值草稿生成；商誉减值一经确认不得转回',
    },
    {
      rowId: generateRowId(),
      seq: 2,
      description: desc,
      investee,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: '商誉',
      accountCode: creditCode,
      accountName: creditName,
      noteItem: '商誉',
      debitAmount: 0,
      creditAmount: amt,
      indexRef: idx,
      remark: creditCode.startsWith('1711')
        ? '贷记商誉（或商誉减值准备，按被审计单位科目体系调整）'
        : `贷记 ${creditCode} ${creditName}`,
    },
  ]
}

export function useI3Adjustment(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const isReadonly = params.isReadonly ?? ref(false)

  const rows = ref<I3AdjustmentRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const lastPushMsg = ref('')

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
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
    const item = allResponses.value.get(itemId)
    return String(item?.remark ?? item?.conclusion ?? '')
  }

  function _normalizeRow(raw: any, idx: number): I3AdjustmentRow {
    const category = categoryFromLegacy(raw)
    const entryType = entryTypeFromCategory(category)
    const accountCode = String(raw.accountCode ?? '')
    const known = I3_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    const debitAmount = parseAmt(raw.debitAmount ?? raw.debit)
    const creditAmount = parseAmt(raw.creditAmount ?? raw.credit)
    const description = String(raw.description ?? raw.summary ?? '')
    return {
      rowId: raw.rowId || generateRowId(),
      seq: idx + 1,
      description,
      category,
      entryType,
      reportItem: String(raw.reportItem ?? reportItemForAccount(accountCode)),
      accountCode,
      accountName: String(raw.accountName || known?.name || ''),
      noteItem: String(raw.noteItem ?? ''),
      debitAmount,
      creditAmount,
      indexRef: String(raw.indexRef ?? raw.refIndex ?? ''),
      remark: String(raw.remark ?? ''),
      investee: String(raw.investee ?? raw.projectName ?? ''),
      summary: description,
      debit: debitAmount,
      credit: creditAmount,
      sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    }
  }

  function _toPersistShape(list: I3AdjustmentRow[]) {
    return list.map((r, i) => ({
      ...r,
      seq: i + 1,
      debit: r.debitAmount,
      credit: r.creditAmount,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      summary: r.description,
      entryType: entryTypeFromCategory(String(r.category)),
    }))
  }

  function load(): void {
    const parsed = _getJson(ROWS_KEY)
    if (Array.isArray(parsed)) {
      rows.value = parsed.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  const debitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const creditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const groupBalanceIssues = computed(() => {
    const groups = new Map<string, {
      key: string
      description: string
      entryType: string
      debit: number
      credit: number
      rowCount: number
    }>()
    for (const r of rows.value) {
      const et = r.entryType || entryTypeFromCategory(String(r.category))
      const desc = String(r.description || '').trim() || r.rowId
      const key = `${et}||${desc}`
      const g = groups.get(key) || {
        key, description: desc, entryType: et, debit: 0, credit: 0, rowCount: 0,
      }
      g.debit += r.debitAmount
      g.credit += r.creditAmount
      g.rowCount += 1
      groups.set(key, g)
    }
    return [...groups.values()]
      .map((g) => {
        const diff = g.debit - g.credit
        return { ...g, diff, isBalanced: Math.abs(diff) < BALANCE_TOLERANCE }
      })
      .filter((g) =>
        !g.isBalanced && (Math.abs(g.debit) > 0.005 || Math.abs(g.credit) > 0.005),
      )
  })

  function _netsFromList(list: I3AdjustmentRow[]) {
    let ajeNet = 0
    let rjeNet = 0
    let gwAje = 0
    let gwRje = 0
    for (const r of list) {
      const net = r.debitAmount - r.creditAmount
      const isRje = r.category === '报表调整' || r.entryType === 'RJE'
      if (isRje) rjeNet += net
      else ajeNet += net
      if (isGoodwillAccount(r.accountCode)) {
        if (isRje) gwRje += net
        else gwAje += net
      }
    }
    return { ajeNet, rjeNet, gwAje, gwRje }
  }

  const ajeNet = computed(() => _netsFromList(rows.value).ajeNet)
  const rjeNet = computed(() => _netsFromList(rows.value).rjeNet)
  const goodwillAjeNet = computed(() => _netsFromList(rows.value).gwAje)
  const goodwillRjeNet = computed(() => _netsFromList(rows.value).gwRje)

  function _writeNets(n: ReturnType<typeof _netsFromList>) {
    if (!onSave) return
    onSave(AJE_NET_KEY, n.gwAje)
    onSave(RJE_NET_KEY, n.gwRje)
    for (const [key, val] of [[AJE_NET_KEY, n.gwAje], [RJE_NET_KEY, n.gwRje]] as const) {
      const existing = allResponses.value.get(key) || { item_id: key, conclusion: null, remark: null }
      allResponses.value.set(key, { ...existing, item_id: key, remark: String(val) })
    }
  }

  function _persist(list?: I3AdjustmentRow[]): void {
    if (!onSave) return
    const next = list ?? rows.value
    const shaped = _toPersistShape(next)
    const normalized = shaped.map((r, i) => _normalizeRow(r, i))
    rows.value = normalized
    onSave(ROWS_KEY, shaped)
    const existing = allResponses.value.get(ROWS_KEY) || { item_id: ROWS_KEY, conclusion: null, remark: null }
    allResponses.value.set(ROWS_KEY, {
      ...existing,
      item_id: ROWS_KEY,
      remark: JSON.stringify(shaped),
    })
    _writeNets(_netsFromList(normalized))
  }

  function addRow(partial?: Partial<I3AdjustmentRow>): void {
    if (isReadonly.value) return
    const category = (partial?.category as I3AdjCategory) || '账项调整'
    const accountCode = partial?.accountCode || '1711'
    const known = I3_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === accountCode)
    rows.value.push(_normalizeRow({
      rowId: generateRowId(),
      description: partial?.description || '',
      investee: partial?.investee || '',
      category,
      entryType: entryTypeFromCategory(category),
      reportItem: partial?.reportItem || reportItemForAccount(accountCode),
      accountCode,
      accountName: partial?.accountName || known?.name || '商誉',
      noteItem: partial?.noteItem || '商誉',
      debitAmount: partial?.debitAmount ?? 0,
      creditAmount: partial?.creditAmount ?? 0,
      indexRef: partial?.indexRef || '',
      remark: partial?.remark || '',
    }, rows.value.length))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (field === 'category') {
      row.category = String(value ?? '账项调整')
      row.entryType = entryTypeFromCategory(String(row.category))
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const known = I3_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === row.accountCode)
      if (known) row.accountName = known.name
      if (!row.reportItem) row.reportItem = reportItemForAccount(row.accountCode)
    } else if (field === 'description' || field === 'summary') {
      row.description = String(value ?? '')
    } else if (field in row) {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function publishAdjustment(): void {
    const nets = _netsFromList(rows.value)
    const payload = {
      wp_code: WP_CODE,
      wpCode: WP_CODE,
      source: 'I3-3',
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      isBalanced: isBalanced.value,
      ajeNet: nets.gwAje,
      rjeNet: nets.gwRje,
      totalAje: nets.ajeNet,
      totalRje: nets.rjeNet,
    }
    try {
      eventBus.emit('adjustment:created', {
        wpCode: WP_CODE,
        entryType: 'AJE',
        amount: Math.abs(nets.gwAje),
        accountCode: '1711',
        accountName: '商誉',
        description: `I3-3 商誉账项净额 ${nets.gwAje}`,
        ...payload,
      } as any)
      window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
    } catch {
      /* silent */
    }
  }

  function saveNote(): void {
    if (!onSave) return
    onSave(NOTE_KEY, auditNote.value)
  }

  function saveConclusion(): void {
    if (!onSave) return
    onSave(CONCLUSION_KEY, auditConclusion.value)
  }

  function saveAndSync(): void {
    _persist()
    saveNote()
    saveConclusion()
    publishAdjustment()
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
      indexRef: r.indexRef || 'I3-3',
    }))
    try {
      eventBus.emit('a13:push-misstatement', {
        items,
        wpCode: WP_CODE,
        source: 'I3-3',
        timestamp: Date.now(),
      })
      window.dispatchEvent(new CustomEvent('a13:push-misstatement', {
        detail: { wpCode: WP_CODE, source: 'I3-3', entries: items },
      }))
      lastPushMsg.value = `已推送 ${targets.length} 行至 A13`
    } catch {
      lastPushMsg.value = '推送失败'
    }
  }

  function resolveAuditYear(): number | null {
    const prop = params.auditYear?.value
    if (prop != null && Number.isFinite(Number(prop)) && Number(prop) >= 1900) {
      return Number(prop)
    }
    return null
  }

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    if (!isBalanced.value) {
      lastSyncMsg.value = '借贷不平衡，无法推送至调整分录模块'
      return 0
    }
    const year = resolveAuditYear() ?? new Date().getFullYear()
    const pending = rows.value.filter(
      (r) =>
        !r.sourceGroupId
        && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) {
      lastSyncMsg.value = '无可推送分录（可能已同步或未填金额）'
      return 0
    }

    const groups = new Map<string, I3AdjustmentRow[]>()
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
            description: `[I3] ${lines[0].description || '商誉调整'}`,
            line_items: lines.map((r) => ({
              standard_account_code: r.accountCode || '1711',
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
      const skipped = groupBalanceIssues.value.length
      lastSyncMsg.value = skipped
        ? `已推送 ${pushed} 笔；另有 ${skipped} 组「调整事项」组内不平衡已跳过`
        : `已推送 ${pushed} 笔至调整分录模块`
    } else if (groupBalanceIssues.value.length) {
      lastSyncMsg.value = `无可推送：有 ${groupBalanceIssues.value.length} 组「调整事项」组内借贷不平衡`
    }
    return pushed
  }

  async function syncFromAdjustmentModule(): Promise<number> {
    const projectId = params.projectId.value
    if (!projectId || isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = resolveAuditYear() ?? new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: I3AdjustmentRow[] = []
      const existingGroupIds = new Set(
        rows.value.map((r) => r.sourceGroupId).filter(Boolean) as string[],
      )

      for (const item of items) {
        const lines = item.line_items || item.lines || []
        const hasRelated = lines.some((li: any) =>
          isI3RelatedAccount(li.standard_account_code || li.account_code),
        )
        if (!hasRelated) continue
        const hasCore = lines.some((li: any) =>
          isGoodwillAccount(String(li.standard_account_code || li.account_code || '')),
        )
        if (!hasCore) continue

        const groupId = String(item.entry_group_id || item.id || '')
        if (groupId && existingGroupIds.has(groupId)) continue

        const et = String(item.adjustment_type || item.type || '').toLowerCase().includes('rje')
          ? 'RJE'
          : 'AJE'
        const desc = String(item.description || item.adjustment_no || '调整分录模块同步').replace(
          /^\[I3\]\s*/,
          '',
        )
        for (const li of lines) {
          const code = String(li.standard_account_code || li.account_code || '')
          imported.push(_normalizeRow({
            description: desc,
            category: et === 'RJE' ? '报表调整' : '账项调整',
            entryType: et,
            accountCode: code,
            accountName: li.account_name || '',
            debitAmount: parseAmt(li.debit_amount ?? li.debit),
            creditAmount: parseAmt(li.credit_amount ?? li.credit),
            indexRef: '调整分录模块',
            remark: '来自调整分录模块',
            sourceGroupId: groupId || undefined,
            reportItem: reportItemForAccount(code),
            noteItem: '商誉',
          }, imported.length))
        }
      }

      if (!imported.length) {
        lastSyncMsg.value = '调整分录模块中无含 1711 商誉的相关分录'
        return 0
      }
      _persist([...rows.value, ...imported])
      publishAdjustment()
      lastSyncMsg.value = `已从模块同步 ${imported.length} 行`
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败'
      return 0
    } finally {
      syncing.value = false
    }
  }

  /** 从 I3-6 商誉减值结果生成草稿分录（跳过已有同说明） */
  function seedFromI36(opts?: {
    creditAccountCode?: string
    creditAccountName?: string
  }): number {
    if (isReadonly.value) return 0
    const raw = _getJson('I3-6-rows')
    if (!Array.isArray(raw) || !raw.length) {
      lastSyncMsg.value = 'I3-6 暂无减值测试行'
      return 0
    }
    // I3-2 按 CGU → 被投资单位（唯一时自动填入，便于回写明细）
    const detail = _getJson('I3-2-rows')
    const byCgu = new Map<string, string[]>()
    if (Array.isArray(detail)) {
      for (const r of detail) {
        const cgu = String(r?.cguName || '').trim()
        const inv = String(r?.investee || '').trim()
        if (!cgu || !inv) continue
        if (!byCgu.has(cgu)) byCgu.set(cgu, [])
        if (!byCgu.get(cgu)!.includes(inv)) byCgu.get(cgu)!.push(inv)
      }
    }
    const existingDesc = new Set(
      rows.value.map((r) => String(r.description || '').trim()).filter(Boolean),
    )
    const toAdd: I3AdjustmentRow[] = []
    for (const cgu of raw) {
      const amt = parseAmt(cgu.consolidatedGwImpairment ?? cgu.goodwillImpairment)
      if (amt <= 0.005) continue
      const name = String(cgu.cguName || '未命名CGU')
      const desc = `计提商誉减值-${name}`
      if (existingDesc.has(desc)) continue
      const invList = byCgu.get(name) || []
      const investee = invList.length === 1 ? invList[0] : ''
      toAdd.push(...buildI3ImpairmentDraftLines({
        cguName: name,
        goodwillImpairment: amt,
        investee,
        indexRef: 'I3-6',
        creditAccountCode: opts?.creditAccountCode,
        creditAccountName: opts?.creditAccountName,
      }))
    }
    if (!toAdd.length) {
      lastSyncMsg.value = '无新增减值草稿（可能已生成或 I3-6 无商誉减值）'
      return 0
    }
    _persist([...rows.value, ...toAdd])
    const filled = toAdd.filter((r) => r.investee).length
    lastSyncMsg.value = `已从 I3-6 生成 ${toAdd.length} 行减值调整草稿`
      + (filled ? `（其中 ${filled} 行已自动带入被投资单位）` : '（请手工填写被投资单位以便回写 I3-2）')
    return toAdd.length
  }

  const investeeOptions = computed(() => {
    const detail = _getJson('I3-2-rows')
    const set = new Set<string>()
    if (Array.isArray(detail)) {
      for (const r of detail) {
        const inv = String(r?.investee || '').trim()
        if (inv) set.add(inv)
      }
    }
    for (const r of rows.value) {
      const inv = String(r.investee || '').trim()
      if (inv) set.add(inv)
    }
    return [...set].sort()
  })

  return {
    rows,
    auditNote,
    auditConclusion,
    syncing,
    lastSyncMsg,
    lastPushMsg,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    groupBalanceIssues,
    ajeNet,
    rjeNet,
    goodwillAjeNet,
    goodwillRjeNet,
    investeeOptions,
    categoryOptions: I3_CATEGORY_OPTIONS,
    accountOptions: I3_ADJ_ACCOUNT_OPTIONS,
    addRow,
    removeRow,
    updateCell,
    saveNote,
    saveConclusion,
    saveAndSync,
    publishAdjustment,
    pushToA13,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    seedFromI36,
    load,
  }
}

export default useI3Adjustment
