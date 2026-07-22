/**
 * useG10Adjustment — G10-3 调整分录（按分项回写 G10-1 (三) 行）
 *
 * 编制逻辑（对齐 Excel「调整分录汇总 G10-3」）：
 * 1. 登记 2101 相关 AJE/RJE，整表借贷须平衡
 * 2. FVTPL 公允变动通常成对：Dr/Cr 6101 ↔ Cr/Dr 2101（负债上升贷 2101）
 * 3. 仅汇总 2101 科目贷−借净额，按「回写行」分项写入 G10-1 (三) 期末账项调整
 * 4. 未指定回写行时按负债类型/摘要关键词自动推断
 * 5. G10-5 推送差异、中央调整分录模块双向同步
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G10_ACCOUNT_CODE, G10_LIABILITY_TYPE_OPTIONS } from './g10Constants'
import {
  G10_ADJ_ROWS_KEY,
  aggregateG10AdjustmentAjeRjeByRow,
  calcG10AdjustmentNet,
  summarizeG10Adjustment,
} from './g10AdjStorage'
import { commitG10AdjustmentWriteback } from './g10CrossHelpers'
import { G10_ADJUDICATION_WRITEBACK_OPTIONS, isG10AccountCode } from './g10AccountMatch'
import { parseNum, calcSubtotal, isDebitCreditBalanced } from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { api } from '@/services/apiProxy'
import { adjustments as adjPaths } from '@/services/apiPaths/accounting'
import { eventBus } from '@/utils/eventBus'
import {
  isG10ClassificationAdjDraft,
  markClassificationDraftsConfirmed,
  G10_CLASSIFICATION_DRAFT_REVIEWED_EVENT,
  isPendingG10ClassificationAdjDraft,
} from './g10ClassificationCross'
import { isFromG105 } from './g10AdjSource'
import {
  buildG10AdjustmentProcedureSummary,
  G10A_ADJUSTMENT_MARK_KEY,
  G10A_ADJUSTMENT_PROGRAM_NOS,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'

export interface G10AdjustmentRow {
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
  indexRef: string
  liabilityType: string
  adjudicationRowKey: string
  /** 来自/已推送至中央调整模块时的 entry_group_id */
  sourceGroupId?: string
  /** G10-4 分类检查来源行 id */
  classificationSourceId?: string
  /** G10-4 草稿复核状态 */
  draftReviewStatus?: 'pending' | 'confirmed'
}

/** 交易性金融负债常用对方科目 */
export const G10_ADJ_ACCOUNT_OPTIONS: { code: string; name: string }[] = [
  { code: G10_ACCOUNT_CODE, name: '交易性金融负债' },
  { code: '6101', name: '公允价值变动损益' },
  { code: '6603', name: '财务费用—利息费用' },
  { code: '6111', name: '投资收益' },
  { code: '1002', name: '银行存款' },
  { code: '2202', name: '应付账款' },
  { code: '2501', name: '其他流动负债' },
  { code: '4104', name: '利润分配—未分配利润' },
]

const ITEM_ID_ROWS = 'G10-aje-rows'
const G10_RELATED_PREFIXES = [G10_ACCOUNT_CODE, '2102', '6101', '6603', '6111']

function genId(): string {
  return `g10a-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function reseq(list: G10AdjustmentRow[]): G10AdjustmentRow[] {
  return list.map((r, i) => ({ ...r, seq: i + 1 }))
}

function isG10RelatedAccount(code: string): boolean {
  const c = String(code || '').trim()
  if (isG10AccountCode(c)) return true
  return G10_RELATED_PREFIXES.some((p) => c === p || c.startsWith(p))
}

function entryTypeFromModule(t: string | undefined): 'AJE' | 'RJE' {
  const text = String(t || '').toLowerCase()
  if (text.includes('rje') || text.includes('报表') || text.includes('重分类')) return 'RJE'
  return 'AJE'
}

export function createEmptyG10AdjustmentRow(): G10AdjustmentRow {
  return {
    rowId: genId(),
    seq: 1,
    entryType: 'AJE',
    date: '',
    summary: '',
    accountCode: G10_ACCOUNT_CODE,
    accountName: '交易性金融负债',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '',
    remark: '',
    indexRef: '',
    liabilityType: '',
    adjudicationRowKey: '',
  }
}

function normalize(raw: any, idx = 0): G10AdjustmentRow {
  const code = String(raw.accountCode ?? G10_ACCOUNT_CODE).trim() || G10_ACCOUNT_CODE
  const known = G10_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === code)
  return {
    rowId: raw.rowId || raw.id || genId(),
    seq: raw.seq ?? idx + 1,
    entryType: raw.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: raw.date || '',
    summary: raw.summary || raw.description || '',
    accountCode: code,
    accountName: (raw.accountName ?? known?.name ?? '').trim() || known?.name || '交易性金融负债',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    preparedBy: raw.preparedBy || '',
    remark: raw.remark || '',
    indexRef: raw.indexRef || raw.index || '',
    liabilityType: raw.liabilityType || '',
    adjudicationRowKey: raw.adjudicationRowKey || '',
    sourceGroupId: raw.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    classificationSourceId: raw.classificationSourceId ? String(raw.classificationSourceId) : undefined,
    draftReviewStatus: raw.draftReviewStatus === 'confirmed' ? 'confirmed' : raw.draftReviewStatus === 'pending' ? 'pending' : undefined,
  }
}

export function useG10Adjustment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
}) {
  const rows = ref<G10AdjustmentRow[]>([])
  const syncing = ref(false)
  const lastSyncMsg = ref('')
  const procedureMarking = ref(false)

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_ADJUSTMENT_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_ADJUSTMENT_MARK_KEY)?.conclusion === 'completed',
  )

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => {
      if (!json) { rows.value = []; return }
      try {
        const parsed = JSON.parse(json)
        rows.value = Array.isArray(parsed) ? reseq(parsed.map(normalize)) : []
      } catch {
        rows.value = []
      }
    },
    { immediate: true },
  )

  function persist(list = rows.value): void {
    const next = reseq(list)
    rows.value = next
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(next) })
    syncWriteback(next)
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() =>
    isDebitCreditBalanced(rows.value.map((r) => r.debitAmount), rows.value.map((r) => r.creditAmount)),
  )
  const adjustmentNet = computed(() => calcG10AdjustmentNet(rows.value))
  const writebackPreview = computed(() => aggregateG10AdjustmentAjeRjeByRow(rows.value))
  const summary = computed(() => summarizeG10Adjustment(rows.value))

  function syncWriteback(list = rows.value): void {
    const wb = aggregateG10AdjustmentAjeRjeByRow(list)
    commitG10AdjustmentWriteback(opts.allResponses.value, opts.debouncedSave, wb)
  }

  function addRow(): void {
    if (opts.isReadonly.value) return
    persist([...rows.value, { ...createEmptyG10AdjustmentRow(), seq: rows.value.length + 1, date: todayIso() }])
  }

  async function addFvPlPair(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value: summaryText } = await ElMessageBox.prompt(
        '请输入摘要（将生成 2101 ↔ 6101 成对分录）',
        '新增公允变动分录组（FVTPL）',
        { inputPlaceholder: '如：调整××衍生负债期末公允价值' },
      )
      const summary = (summaryText ?? '').trim()
      if (!summary) return

      const { value: amtRaw } = await ElMessageBox.prompt(
        '请输入金额（正数=负债公允价值上升；负数=下降）',
        '公允变动金额',
        { inputPlaceholder: '如 100000 或 -50000', inputValue: '0' },
      )
      const amt = parseNum(amtRaw)
      if (Math.abs(amt) < 0.01) return

      const isIncrease = amt > 0
      const abs = Math.abs(amt)
      const date = todayIso()
      const base = rows.value.length
      const pair: G10AdjustmentRow[] = [
        {
          rowId: genId(),
          seq: base + 1,
          entryType: 'AJE',
          date,
          summary,
          accountCode: '6101',
          accountName: '公允价值变动损益',
          debitAmount: isIncrease ? abs : 0,
          creditAmount: isIncrease ? 0 : abs,
          preparedBy: '',
          remark: '手工公允变动分录组(FVTPL)',
          indexRef: 'G10-5',
          liabilityType: '',
          adjudicationRowKey: '',
        },
        {
          rowId: genId(),
          seq: base + 2,
          entryType: 'AJE',
          date,
          summary,
          accountCode: G10_ACCOUNT_CODE,
          accountName: '交易性金融负债',
          debitAmount: isIncrease ? 0 : abs,
          creditAmount: isIncrease ? abs : 0,
          preparedBy: '',
          remark: '手工公允变动分录组(FVTPL)',
          indexRef: 'G10-5',
          liabilityType: '',
          adjudicationRowKey: '',
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
      persist(rows.value.filter((r) => r.rowId !== rowId))
    } catch { /* cancelled */ }
  }

  function updateRow(rowId: string, patch: Partial<G10AdjustmentRow>): void {
    if (opts.isReadonly.value) return
    const list = rows.value.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, ...patch }
      if (patch.accountCode != null) {
        const known = G10_ADJ_ACCOUNT_OPTIONS.find((o) => o.code === patch.accountCode)
        if (known && (!patch.accountName || patch.accountName === r.accountName)) {
          next.accountName = known.name
        }
      }
      return normalize(next, r.seq - 1)
    })
    persist(list)
  }

  async function pushToAdjustmentModule(): Promise<number> {
    const projectId = opts.projectId?.value
    if (!projectId || opts.isReadonly.value) return 0
    if (!isBalanced.value) return 0
    const year = Number(opts.auditYear?.value)
    if (!Number.isFinite(year) || year < 1900) return 0

    const pending = rows.value.filter(
      (r) => !r.sourceGroupId && (Math.abs(r.debitAmount) > 0.005 || Math.abs(r.creditAmount) > 0.005),
    )
    if (!pending.length) return 0

    const groups = new Map<string, G10AdjustmentRow[]>()
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
          description: `[G10] ${lines[0].summary || '交易性金融负债调整'}`,
          line_items: lines.map((r) => ({
            standard_account_code: r.accountCode || G10_ACCOUNT_CODE,
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

      const imported: G10AdjustmentRow[] = []
      for (const item of items) {
        const lines = item.line_items || item.lines || []
        if (!lines.some((li: any) => isG10RelatedAccount(li.standard_account_code || li.account_code))) continue
        const groupId = String(item.entry_group_id || item.id || '')
        for (const li of lines) {
          const accountCode = String(li.standard_account_code || li.account_code || '')
          imported.push(normalize({
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
      persist([...manual, ...imported])
      lastSyncMsg.value = imported.length
        ? `已同步 ${imported.length} 行`
        : '集中模块中无 2101/6101 等相关分录'
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
    persist(rows.value)
    const pushed = await pushToAdjustmentModule()
    return { ok: true, pushed }
  }

  /** 标记 G10-4 重分类草稿为已复核（清除高亮） */
  function confirmClassificationDrafts(options?: {
    sourceIds?: string[]
    summaries?: string[]
    allPending?: boolean
  }): number {
    if (opts.isReadonly.value) return 0
    const before = rows.value.filter((r) => isG10ClassificationAdjDraft(r) && r.draftReviewStatus !== 'confirmed').length
    const next = markClassificationDraftsConfirmed(rows.value, options)
    const after = next.filter((r) => isG10ClassificationAdjDraft(r) && r.draftReviewStatus !== 'confirmed').length
    const changed = before - after
    if (changed <= 0) return 0
    persist(next)
    try {
      window.dispatchEvent(new CustomEvent(G10_CLASSIFICATION_DRAFT_REVIEWED_EVENT))
    } catch { /* silent */ }
    return changed
  }

  function onModuleUpdated() {
    if (!opts.isReadonly.value && opts.projectId?.value) void syncFromAdjustmentModule()
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    const meaningful = rows.value.filter((r) =>
      Math.abs(parseNum(r.debitAmount)) > 0.005
      || Math.abs(parseNum(r.creditAmount)) > 0.005
      || String(r.summary || '').trim(),
    )
    if (!meaningful.length) {
      ElMessage.warning('请先登记 G10-3 调整分录（或从 G10-5 等推送）')
      return -1
    }
    const pendingG104 = rows.value.filter(isPendingG10ClassificationAdjDraft).length
    if (!isBalanced.value) {
      try {
        await ElMessageBox.confirm(
          `调整分录借贷未平衡（差额 ${balanceDiff.value.toFixed(2)}），是否仍标记 G10A 调整程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    } else if (pendingG104 > 0) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${pendingG104} 行 G10-4 重分类草稿待复核，是否仍标记 G10A 调整程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    const fromG105 = rows.value.filter(isFromG105).length
    const fromG104 = rows.value.filter(isG10ClassificationAdjDraft).length
    const writebackRows = Object.values(writebackPreview.value.byRow).filter((wb) =>
      Math.abs(parseNum(wb.closingAje)) > 0.005 || Math.abs(parseNum(wb.closingRje)) > 0.005,
    ).length

    procedureMarking.value = true
    try {
      const s = summary.value
      const execSummary = buildG10AdjustmentProcedureSummary({
        rowCount: s.rowCount,
        ajeCount: s.ajeCount,
        rjeCount: s.rjeCount,
        balanced: isBalanced.value,
        net2101: s.net2101,
        fvPlNet: s.fvPlNet,
        writebackRows,
        fromG105,
        fromG104,
        pendingG104,
      })
      const n = await markG10AProcedureSteps({
        projectId: pid,
        programNos: [...G10A_ADJUSTMENT_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G10-3/G10-5/G10-1',
        executionSummary: execSummary,
      })
      opts.debouncedSave(G10A_ADJUSTMENT_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary: execSummary,
          programNos: [...G10A_ADJUSTMENT_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_ADJUSTMENT_PROGRAM_NOS].join('/')}（调整/公允损益）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } catch {
      ElMessage.error('回填 G10A 失败，请稍后重试')
      return -1
    } finally {
      procedureMarking.value = false
    }
  }

  onMounted(() => {
    eventBus.on('adjustment:updated', onModuleUpdated)
  })
  onBeforeUnmount(() => {
    eventBus.off('adjustment:updated', onModuleUpdated)
  })

  return {
    rows,
    debitTotal,
    creditTotal,
    balanceDiff,
    isBalanced,
    adjustmentNet,
    writebackPreview,
    summary,
    syncing,
    lastSyncMsg,
    writebackOptions: G10_ADJUDICATION_WRITEBACK_OPTIONS,
    liabilityTypeOptions: G10_LIABILITY_TYPE_OPTIONS,
    addRow,
    addFvPlPair,
    removeRow,
    updateRow,
    syncWriteback,
    pushToAdjustmentModule,
    syncFromAdjustmentModule,
    confirmAndPush,
    confirmClassificationDrafts,
    markProcedureComplete,
    procedureMarked,
    procedureMarking,
    ITEM_ID_ROWS,
  }
}
