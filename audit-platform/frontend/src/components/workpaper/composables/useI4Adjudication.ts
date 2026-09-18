/**
 * useI4Adjudication — I4-1 长期待摊费用审定表
 *
 * 对齐 Excel：未审滚动 → 账项调整 → 审定；行自 I4-2 带入；AJE/RJE 自 I4-3；
 * 本期摊销可自 I4-6/I4-7；与 TB 1801 / I4-2 勾稽；上期审定比较。
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useI4CrossSheet } from './useI4CrossSheet'
import {
  type I4AdjudicationRowModel,
  type I4AdjudicationCrossCheck,
  emptyI4AdjudicationRow,
  normalizeI4AdjudicationRow,
  summarizeI4Adjudication,
  seedI4AdjudicationFromDetail,
  applyAjeFromI43,
  applyAmortFromI46,
  buildI4AdjudicationCrossCheck,
  buildI4ExcelLeadSummary,
  buildI4CategorySummary,
  buildI4AdjudicationConclusionDraft,
  validateI4AdjudicationSave,
  recalcI4AdjudicationRow,
  formatI4VarianceRate,
  I4_ADJ_ROWS_KEY,
  I4_ADJ_NOTE_KEY,
  I4_ADJ_CONCLUSION_KEY,
  I4_ADJ_MATTERS_KEY,
  I4_CONCLUSION_OPTIONS,
} from './i4AdjudicationModel'

export type I4AdjudicationRow = I4AdjudicationRowModel
export { formatI4VarianceRate, I4_CONCLUSION_OPTIONS }

export interface I4DifferenceRow {
  label: string
  accountCode: string
  audited: number
  tbAmount: number
  difference: number
}

export interface I4ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

const ITEM_PREFIX = 'I4-adj'
const ACCOUNT_CODE_1801 = '1801'

const DEFAULT_CATEGORIES = ['装修费', '开办费', '租赁改良', '技术转让费', '其他']

function safeParseRows(raw: unknown): any[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch {
      return []
    }
  }
  return []
}

export function useI4Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, I4ChecklistItem>>,
  options?: {
    tbUnadjusted1801?: Ref<number>
    tbAudited1801?: Ref<number>
    tbPriorAudited1801?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I4AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const significantMatters = ref('')

  const {
    detailTotals,
    detailRowsRaw,
    adjustmentRowsRaw,
    amortizationRowsRaw,
  } = useI4CrossSheet(allResponses as Ref<Map<string, any>>)

  function _loadRows(): void {
    const data = _getJson(I4_ADJ_ROWS_KEY) ?? _getJson(`${ITEM_PREFIX}-rows`)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(normalizeI4AdjudicationRow)
    } else {
      rows.value = DEFAULT_CATEGORIES.map((cat) => emptyI4AdjudicationRow({ projectName: cat }))
    }
    auditNote.value = _getString(I4_ADJ_NOTE_KEY) || _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(I4_ADJ_CONCLUSION_KEY) || _getString(`${ITEM_PREFIX}-audit-conclusion`)
    significantMatters.value = _getString(I4_ADJ_MATTERS_KEY) || _getString(`${ITEM_PREFIX}-significant-matters`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    if (typeof raw !== 'string') return raw
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  const computedRows = computed(() => rows.value.map(recalcI4AdjudicationRow))

  const subtotals = computed(() => summarizeI4Adjudication(computedRows.value))

  const excelLead = computed(() => buildI4ExcelLeadSummary(computedRows.value))

  const categorySummary = computed(() =>
    buildI4CategorySummary(computedRows.value, detailRowsRaw.value),
  )

  const crossCheck = computed<I4AdjudicationCrossCheck>(() =>
    buildI4AdjudicationCrossCheck(computedRows.value, detailTotals.value as any),
  )

  const reconciliationStatus = computed<'balanced' | 'mismatch'>(() =>
    computedRows.value.some((r) => r.hasError) ? 'mismatch' : 'balanced',
  )

  const hasAjeApprox = computed(() => computedRows.value.some((r) => r.ajeApprox))

  const tbUnadjusted = computed(() => options?.tbUnadjusted1801?.value ?? 0)

  const tbDifference = computed(() => subtotals.value.audited - tbUnadjusted.value)

  const differenceRows = computed<I4DifferenceRow[]>(() => [{
    label: '长期待摊费用(1801)',
    accountCode: ACCOUNT_CODE_1801,
    audited: subtotals.value.audited,
    tbAmount: tbUnadjusted.value,
    difference: tbDifference.value,
  }])

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(I4_ADJ_ROWS_KEY, rows.value)
    save(`${ITEM_PREFIX}-rows`, rows.value)
  }

  async function addRow(): Promise<void> {
    try {
      const { value: projectName } = await ElMessageBox.prompt(
        '请输入长期待摊费用项目名称',
        '新增待摊项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '项目名称不能为空',
        },
      )
      if (!projectName) return
      rows.value.push(emptyI4AdjudicationRow({ projectName: projectName.trim() }))
      _persist()
      ElMessage.success(`已添加：${projectName}`)
    } catch {
      /* cancel */
    }
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    const removed = rows.value.splice(idx, 1)[0]
    _persist()
    ElMessage.info(`已删除：${removed.projectName}`)
  }

  function updateCell(
    rowId: string,
    field: keyof I4AdjudicationRowModel,
    value: number | string,
  ): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || row.isEditable === false) return
    ;(row as any)[field] = value
    if (field === 'aje' || field === 'rje') row.ajeApprox = false
    const next = recalcI4AdjudicationRow(row)
    Object.assign(row, next)
    _persist()
  }

  function seedFromI42(): void {
    const detail = detailRowsRaw.value.length
      ? detailRowsRaw.value
      : safeParseRows(_getJson('I4-2-rows'))
    if (!detail.length) {
      ElMessage.warning('I4-2 明细暂无数据，请先编制明细表')
      return
    }
    rows.value = seedI4AdjudicationFromDetail(detail, rows.value)
    _persist()
    ElMessage.success(`已从 I4-2 带入 ${rows.value.length} 行（保留已有 AJE/RJE）`)
  }

  function syncFromI43(): void {
    const adj = adjustmentRowsRaw.value.length
      ? adjustmentRowsRaw.value
      : safeParseRows(_getJson('I4-3-rows'))
    const result = applyAjeFromI43(rows.value, adj)
    rows.value = result.rows
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      ElMessage.info('I4-3 无 1801 相关调整可同步')
      return
    }
    ElMessage.success(
      result.approx
        ? `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（含近似分摊，请复核）`
        : `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（精确匹配 ${result.matchedByName}）`,
    )
  }

  function syncAmortFromI46(): void {
    const amort = amortizationRowsRaw.value.length
      ? amortizationRowsRaw.value
      : [
          ...safeParseRows(_getJson('I4-6-rows')),
          ...safeParseRows(_getJson('I4-7-rows')),
        ]
    if (!amort.length) {
      ElMessage.warning('I4-6/I4-7 暂无摊销测算数据')
      return
    }
    rows.value = applyAmortFromI46(rows.value, amort)
    _persist()
    ElMessage.success('已从摊销测算同步本期摊销')
  }

  function applyTbData(tbUnadjustedTotal?: number): void {
    const total = tbUnadjustedTotal ?? tbUnadjusted.value
    if (!rows.value.length) return
    if (rows.value.length === 1) {
      rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], unadjusted: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.endBalance) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI4AdjudicationRow({ ...r, unadjusted: amt, ajeApprox: rows.value.length > 1 })
        })
      } else {
        rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], unadjusted: total })
      }
    }
    _persist()
    ElMessage.success('已写入 TB 未审数')
  }

  /** 从上期 TB / 比较期字段写入 priorAudited */
  function applyPriorFromTb(priorTotal?: number): void {
    const total = priorTotal ?? options?.tbPriorAudited1801?.value ?? 0
    if (!(Math.abs(total) > 0.005)) {
      ElMessage.warning('暂无上期审定/比较期数据（TB prior_* 字段）')
      return
    }
    if (rows.value.length === 1) {
      rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], priorAudited: total })
    } else {
      const base = rows.value.map((r) => Math.abs(r.beginBalance) || Math.abs(r.unadjusted) || 0)
      const sum = base.reduce((a, b) => a + b, 0)
      if (sum > 0) {
        let left = total
        rows.value = rows.value.map((r, i) => {
          const isLast = i === rows.value.length - 1
          const amt = isLast ? Math.round(left * 100) / 100 : Math.round((total * base[i] / sum) * 100) / 100
          left = Math.round((left - amt) * 100) / 100
          return recalcI4AdjudicationRow({ ...r, priorAudited: amt })
        })
      } else {
        rows.value[0] = recalcI4AdjudicationRow({ ...rows.value[0], priorAudited: total })
      }
    }
    _persist()
    ElMessage.success('已写入上期审定')
  }

  function fillConclusionDraft(): void {
    auditConclusion.value = buildI4AdjudicationConclusionDraft({
      sampleCount: rows.value.length,
      auditedTotal: subtotals.value.audited,
      tbDiff: tbDifference.value,
      hasAje: rows.value.some((r) => Math.abs(r.aje) + Math.abs(r.rje) > 0.005),
      crossWarning: crossCheck.value.hasWarning,
    })
    saveConclusion(auditConclusion.value)
  }

  function applyConclusionTemplate(key: string): void {
    const t = I4_CONCLUSION_OPTIONS.find((x) => x.key === key)
    if (!t) return
    auditConclusion.value = t.text
    saveConclusion(t.text)
  }

  // ─── 显式发布门状态（防重复提交，供发布按钮 :loading 绑定） ─────────────────
  const publishing = ref(false)

  /** 发布下游联动事件（仅 emit，不写 TB）。 */
  function _emitAdjudicated(): void {
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'I4',
        accountCodes: [ACCOUNT_CODE_1801],
        auditedTotal: subtotals.value.audited,
      },
    }))
  }

  /**
   * 保存审定表（普通保存动作，不写 TB）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 1。
   * 此前保存后**自动** PUT 旧端点回写 trial_balance(1801) → 违反 Req 1。现只保存 + emit；
   * TB 回写收敛为用户显式确认动作（publishToTb）。
   */
  async function writeback(force = false): Promise<{ ok: boolean; message?: string }> {
    const gate = validateI4AdjudicationSave({
      rows: computedRows.value,
      tbDiff: tbDifference.value,
      force,
    })
    if (!gate.ok) {
      const msg = gate.blockers.join('；')
      ElMessage.error(msg)
      return { ok: false, message: msg }
    }
    if (gate.warnings.length) {
      ElMessage.warning(gate.warnings[0])
    }

    _persist()
    const auditedTotal = subtotals.value.audited
    options?.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    _emitAdjudicated()
    return { ok: true }
  }

  // ─── 显式发布到试算表（显式确认门，复刻 D2/D4-1 范式） ────────────────────────

  /**
   * 确认发布审定数到试算表（科目 1801 长期待摊费用）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 13 / Req 2。
   * 二次确认（中文）→ 保存明细 → `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （审定表 sheet 名 I4-1 + writeback_rows 预算行 1801 balance）。用户取消 → 无副作用。
   */
  async function publishToTb(): Promise<void> {
    if (publishing.value) return

    try {
      await ElMessageBox.confirm(
        '发布后将把长期待摊费用审定数（科目 1801）写入试算表（trial_balance），'
        + '并触发报表/错报评价等下游重算。确认发布？',
        '发布到试算表确认',
        { confirmButtonText: '确认发布', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return // 用户取消 → 无任何副作用
    }

    if (!wpId.value) {
      ElMessage.error('缺少底稿标识，无法发布')
      return
    }

    // 先保存明细（普通保存，不写 TB）；被 gate 阻断则不发布
    const saved = await writeback(false)
    if (!saved.ok) return

    publishing.value = true
    try {
      const resp: any = await api.post(
        `/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`,
        {
          // sheet 名固定含审定表子码 I4-1，后端 extract_determination_wp_code 据此解出 I4-1
          sheet_name: '审定表I4-1',
          writeback_rows: [
            { account_code: ACCOUNT_CODE_1801, audited_amount: subtotals.value.audited, amount_kind: 'balance' },
          ],
        },
      )
      ElMessage.success(resp?.message || '已发布到试算表')
      _emitAdjudicated()
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || err?.message || '发布失败，请重试')
    } finally {
      publishing.value = false
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(I4_ADJ_NOTE_KEY, note)
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(I4_ADJ_CONCLUSION_KEY, conclusion)
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function saveSignificantMatters(text: string): void {
    significantMatters.value = text
    options?.onSave?.(I4_ADJ_MATTERS_KEY, text)
    options?.onSave?.(`${ITEM_PREFIX}-significant-matters`, text)
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  function _onAdjChanged(): void {
    ElNotification({
      title: 'I4-3 调整已更新',
      message: '审定表 AJE/RJE 可能需同步，请点击「从 I4-3 同步调整」',
      type: 'warning',
      duration: 8000,
    })
  }

  onMounted(() => {
    window.addEventListener('i4:adjustments-changed', _onAdjChanged)
  })
  onUnmounted(() => {
    window.removeEventListener('i4:adjustments-changed', _onAdjChanged)
  })

  return {
    rows: computedRows,
    auditNote,
    auditConclusion,
    significantMatters,
    subtotals,
    excelLead,
    categorySummary,
    crossCheck,
    reconciliationStatus,
    hasAjeApprox,
    tbUnadjusted,
    tbDifference,
    differenceRows,
    addRow,
    removeRow,
    updateCell,
    seedFromI42,
    syncFromI43,
    syncAmortFromI46,
    applyTbData,
    applyPriorFromTb,
    applyAdjustments: (adjustments: { 项目: string; AJE: number; RJE: number }[]) => {
      // 兼容旧调用：按项目名写入
      for (const adj of adjustments) {
        const row = rows.value.find((r) => r.projectName === adj.项目)
        if (!row) continue
        row.aje = adj.AJE
        row.rje = adj.RJE
        row.ajeApprox = false
        Object.assign(row, recalcI4AdjudicationRow(row))
      }
      _persist()
    },
    fillConclusionDraft,
    applyConclusionTemplate,
    writeback,
    // 显式发布到试算表（二次确认门）
    publishToTb,
    publishing,
    saveNote,
    saveConclusion,
    saveSignificantMatters,
  }
}

export default useI4Adjudication
