/**
 * useG9Adjustment — G9-3 调整分录（AJE/RJE 回写 G9-1）
 *
 * 编制逻辑：
 * 1. 登记 1504 相关 AJE/RJE，整表借贷须平衡
 * 2. FVTPL 公允变动通常成对：Dr/Cr 1504 ↔ 6101；FVOCI 可用 4002
 * 3. 仅汇总科目代码以 1504 开头的借−贷净额，分 AJE/RJE 回写 G9-1「fvtpl_1」
 * 4. 可与中央调整分录模块双向同步（1504/6101/4002 等）
 * 5. G9-4 推送差异、截止测试填入均复用本表持久化与回写
 */
import { computed, ref, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G9_ACCOUNT_CODE } from './g9Constants'
import {
  aggregateG9AdjustmentAjeRje,
  applyG9AdjustmentWriteback,
  calcG9AdjustmentNet,
  parseG9AdjStore,
  summarizeG9Adjustment,
} from './g9AdjStorage'
import { mapCutoffToG9Adjustment, mergeByFillMode } from './gCycleCutoffFill'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import { parseNum, isDebitCreditBalanced } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'

export interface G9AdjustmentEntry {
  rowId: string
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
  /** 来自/已推送至中央调整模块时的 entry_group_id */
  sourceGroupId?: string
}

/** 其他非流动金融资产常用对方科目 */
export const G9_ADJ_ACCOUNT_OPTIONS: { code: string; name: string }[] = [
  { code: G9_ACCOUNT_CODE, name: '其他非流动金融资产' },
  { code: '6101', name: '公允价值变动损益' },
  { code: '4002', name: '其他综合收益' },
  { code: '6111', name: '投资收益' },
  { code: '6701', name: '资产减值损失' },
  { code: '1002', name: '银行存款' },
  { code: '1221', name: '其他应收款' },
  { code: '4104', name: '利润分配—未分配利润' },
]

const ITEM_ID_ROWS = 'G9-adjustment-rows'
const ITEM_ID_ADJ_ROWS = 'G9-adj-rows'
export const G9_AJE_ADJ_OVERLAY_ID = 'G9-aje-adj-overlay'

const G9_RELATED_PREFIXES = [G9_ACCOUNT_CODE, '1510', '1504', '6101', '4002', '6111', '6701']

function genId(): string {
  return `g9a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function isG9RelatedAccount(code: string): boolean {
  const c = String(code || '')
  return G9_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function normalizeEntry(raw: any, idx: number): G9AdjustmentEntry {
  const code = String(raw.accountCode ?? G9_ACCOUNT_CODE).trim() || G9_ACCOUNT_CODE
  const known = G9_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
  return {
    rowId: raw.rowId || raw.id || genId(),
    seq: raw.seq ?? idx + 1,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date ?? '',
    summary: raw.summary ?? '',
    accountCode: code,
    accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '其他非流动金融资产',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy ?? '',
    remark: raw.remark ?? '',
    sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
  }
}

function parseRows(json: string | null | undefined): G9AdjustmentEntry[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr.map(normalizeEntry) : []
  } catch {
    return []
  }
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

export function useG9Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
  applyAdjustmentToAdjudication?: (aje: number, rje: number) => void
}) {
  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))
  const syncing = ref(false)
  const lastSyncMsg = ref('')

  const balanceOk = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )

  const balanceDiff = computed(() => {
    const d = rows.value.reduce((s, r) => s + parseNum(r.debitAmount), 0)
    const c = rows.value.reduce((s, r) => s + parseNum(r.creditAmount), 0)
    return d - c
  })

  const adjustmentNet = computed(() => calcG9AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateG9AdjustmentAjeRje(rows.value))
  const summary = computed(() => summarizeG9Adjustment(rows.value))

  function persist(list: G9AdjustmentEntry[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
    syncWriteback(list)
  }

  function syncWriteback(list = rows.value): void {
    const wb = aggregateG9AdjustmentAjeRje(list)
    opts.debouncedSave(G9_AJE_ADJ_OVERLAY_ID, { remark: JSON.stringify(wb) })

    const store = parseG9AdjStore(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark)
    const patched = applyG9AdjustmentWriteback(store, wb)
    opts.debouncedSave(ITEM_ID_ADJ_ROWS, { remark: JSON.stringify(patched) })

    opts.applyAdjustmentToAdjudication?.(wb.closingAje, wb.closingRje)
    try {
      window.dispatchEvent(new CustomEvent('g9:adjustment-writeback', { detail: wb }))
    } catch { /* silent */ }
  }

  function updateRow(rowId: string, patch: Partial<G9AdjustmentEntry>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if (patch.accountCode != null) {
        const known = G9_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === patch.accountCode)
        if (known && (!patch.accountName || patch.accountName === r.accountName)) {
          next.accountName = known.name
        }
      }
      return normalizeEntry(next, r.seq - 1)
    })
    persist(list)
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入摘要', '新增调整分录', {
        inputPlaceholder: '如：调整××产品公允价值变动',
      })
      const summaryText = (value ?? '').trim()
      if (!summaryText) return
      persist([
        ...rows.value,
        {
          rowId: genId(),
          seq: rows.value.length + 1,
          entryType: 'AJE',
          date: todayIso(),
          summary: summaryText,
          accountCode: G9_ACCOUNT_CODE,
          accountName: '其他非流动金融资产',
          debitAmount: 0,
          creditAmount: 0,
          preparedBy: '',
          remark: '',
        },
      ])
    } catch { /* cancelled */ }
  }

  /** FVTPL：1504 ↔ 6101 成对分录 */
  async function addFvPlPair(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value: summaryText } = await ElMessageBox.prompt(
        '请输入摘要（将生成 1504 ↔ 6101 成对分录）',
        '新增公允变动分录组（FVTPL）',
        { inputPlaceholder: '如：调整××产品期末公允价值' },
      )
      const summary = (summaryText ?? '').trim()
      if (!summary) return

      const { value: amtRaw } = await ElMessageBox.prompt(
        '请输入金额（正数=公允价值上升；负数=下降）',
        '公允变动金额',
        { inputPlaceholder: '如 100000 或 -50000', inputValue: '0' },
      )
      const amt = parseNum(amtRaw)
      if (Math.abs(amt) < 0.01) return

      const isIncrease = amt > 0
      const abs = Math.abs(amt)
      const date = todayIso()
      const base = rows.value.length
      const pair: G9AdjustmentEntry[] = [
        {
          rowId: genId(),
          seq: base + 1,
          entryType: 'AJE',
          date,
          summary,
          accountCode: G9_ACCOUNT_CODE,
          accountName: '其他非流动金融资产',
          debitAmount: isIncrease ? abs : 0,
          creditAmount: isIncrease ? 0 : abs,
          preparedBy: '',
          remark: '手工公允变动分录组(FVTPL)',
        },
        {
          rowId: genId(),
          seq: base + 2,
          entryType: 'AJE',
          date,
          summary: `${summary}（公允变动）`,
          accountCode: '6101',
          accountName: '公允价值变动损益',
          debitAmount: isIncrease ? 0 : abs,
          creditAmount: isIncrease ? abs : 0,
          preparedBy: '',
          remark: '手工公允变动分录组(FVTPL)',
        },
      ]
      persist([...rows.value, ...pair])
    } catch { /* cancelled */ }
  }

  /** FVOCI：1504 ↔ 4002 成对分录 */
  async function addFvOciPair(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value: summaryText } = await ElMessageBox.prompt(
        '请输入摘要（将生成 1504 ↔ 4002 成对分录）',
        '新增公允变动分录组（FVOCI）',
        { inputPlaceholder: '如：调整××产品计入 OCI 的公允变动' },
      )
      const summary = (summaryText ?? '').trim()
      if (!summary) return

      const { value: amtRaw } = await ElMessageBox.prompt(
        '请输入金额（正数=公允价值上升；负数=下降）',
        '公允变动金额',
        { inputPlaceholder: '如 100000 或 -50000', inputValue: '0' },
      )
      const amt = parseNum(amtRaw)
      if (Math.abs(amt) < 0.01) return

      const isIncrease = amt > 0
      const abs = Math.abs(amt)
      const date = todayIso()
      const base = rows.value.length
      const pair: G9AdjustmentEntry[] = [
        {
          rowId: genId(),
          seq: base + 1,
          entryType: 'AJE',
          date,
          summary,
          accountCode: G9_ACCOUNT_CODE,
          accountName: '其他非流动金融资产',
          debitAmount: isIncrease ? abs : 0,
          creditAmount: isIncrease ? 0 : abs,
          preparedBy: '',
          remark: '手工公允变动分录组(FVOCI)',
        },
        {
          rowId: genId(),
          seq: base + 2,
          entryType: 'AJE',
          date,
          summary: `${summary}（OCI）`,
          accountCode: '4002',
          accountName: '其他综合收益',
          debitAmount: isIncrease ? 0 : abs,
          creditAmount: isIncrease ? abs : 0,
          preparedBy: '',
          remark: '手工公允变动分录组(FVOCI)',
        },
      ]
      persist([...rows.value, ...pair])
    } catch { /* cancelled */ }
  }

  async function removeRow(rowId: string): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      persist(rows.value.filter((r) => r.rowId !== rowId).map((r, i) => ({ ...r, seq: i + 1 })))
    } catch { /* cancelled */ }
  }

  function applyCutoffResults(samples: ExtractedVoucher[], fillMode: FillMode): void {
    if (opts.isReadonly.value || !samples.length) return
    const base = rows.value.length
    const mapped = samples.map((v, i) => mapCutoffToG9Adjustment(v, base + i + 1))
    const merged = mergeByFillMode(rows.value, mapped, fillMode, (r) => r.remark || `${r.summary}|${r.debitAmount}`)
    persist(merged.map((r, i) => ({ ...r, seq: i + 1 })))
  }

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) return 0
    if (!balanceOk.value) return 0
    const year = Number(opts.auditYear?.value)
    if (!Number.isFinite(year) || year < 1900) return 0

    const pending = rows.value.filter(
      (r) => !r.sourceGroupId && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) return 0

    const groups = new Map<string, G9AdjustmentEntry[]>()
    for (const row of pending) {
      const key = `${row.entryType}||${row.summary || row.rowId}`
      groups.set(key, [...(groups.get(key) || []), row])
    }

    let pushed = 0
    let list = [...rows.value]
    for (const lines of groups.values()) {
      const debit = lines.reduce((s, r) => s + r.debitAmount, 0)
      const credit = lines.reduce((s, r) => s + r.creditAmount, 0)
      if (Math.abs(debit - credit) >= 0.01) continue
      try {
        const res: any = await api.post(adjPaths.create(projectId), {
          adjustment_type: lines[0].entryType === 'RJE' ? 'rje' : 'aje',
          year,
          company_code: 'default',
          description: `[G9] ${lines[0].summary || '其他非流动金融资产调整'}`,
          line_items: lines.map((r) => ({
            standard_account_code: r.accountCode || G9_ACCOUNT_CODE,
            account_name: r.accountName || undefined,
            debit_amount: r.debitAmount,
            credit_amount: r.creditAmount,
          })),
        }, { _silent: true } as any)
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
      persist(list)
      eventBus.emit('adjustment:updated')
    }
    return pushed
  }

  async function syncFromAdjustmentModule(): Promise<number> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) return 0
    syncing.value = true
    lastSyncMsg.value = ''
    try {
      const year = Number(opts.auditYear?.value) || new Date().getFullYear()
      const res: any = await api.get(adjPaths.list(projectId), {
        params: { year, page: 1, page_size: 200 },
        _silent: true,
      } as any)
      const items = res?.data?.data?.items ?? res?.data?.items ?? res?.items ?? []
      if (!Array.isArray(items)) {
        lastSyncMsg.value = '未获取到调整分录'
        return 0
      }

      const imported: G9AdjustmentEntry[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        if (!lines.some((li: any) => isG9RelatedAccount(li.standard_account_code || li.account_code))) continue
        const groupId = String(item.entry_group_id || item.id || '')
        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          imported.push(normalizeEntry({
            rowId: `${groupId}-${imported.length}`,
            summary: item.description || item.adjustment_no || '调整分录模块同步',
            entryType: entryTypeFromModule(item.adjustment_type || item.type),
            date: todayIso(),
            accountCode,
            accountName: li.account_name || accountCode,
            debitAmount: li.debit_amount,
            creditAmount: li.credit_amount,
            preparedBy: '',
            remark: '来自调整分录模块',
            sourceGroupId: groupId,
          }, imported.length))
        }
      }
      const manual = rows.value.filter((r) => !r.sourceGroupId)
      persist([...manual, ...imported].map((r, i) => ({ ...r, seq: i + 1 })))
      lastSyncMsg.value = imported.length
        ? `已同步 ${imported.length} 行`
        : '集中模块中无 1504/6101/4002 等相关分录'
      return imported.length
    } catch {
      lastSyncMsg.value = '同步失败，请稍后重试'
      return 0
    } finally {
      syncing.value = false
    }
  }

  async function confirmAndPush(): Promise<{ ok: boolean; pushed: number }> {
    if (!balanceOk.value) return { ok: false, pushed: 0 }
    persist(rows.value)
    const pushed = await pushToAdjustmentModule()
    return { ok: true, pushed }
  }

  function onModuleUpdated() {
    if (!opts.isReadonly.value && opts.projectId?.value) void syncFromAdjustmentModule()
  }

  onMounted(() => {
    eventBus.on('adjustment:updated', onModuleUpdated)
  })
  onBeforeUnmount(() => {
    eventBus.off('adjustment:updated', onModuleUpdated)
  })

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    () => { /* rows computed */ },
    { immediate: true },
  )

  return {
    rows,
    balanceOk,
    balanceDiff,
    adjustmentNet,
    writebackPreview,
    summary,
    syncing,
    lastSyncMsg,
    updateRow,
    addRow,
    addFvPlPair,
    addFvOciPair,
    removeRow,
    syncWriteback,
    applyCutoffResults,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    confirmAndPush,
  }
}
