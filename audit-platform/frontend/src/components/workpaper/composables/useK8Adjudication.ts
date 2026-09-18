/**
 * useK8Adjudication — K8-1 审定表逻辑（29行×12列，73公式，损益类！取发生额）
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Task: 3.4
 * Requirements: 2.1-2.7, 7.1-7.4, 9.1-9.2
 *
 * 职责：
 * - 管理审定表行数据（费用明细项目）
 * - 每行: { projectName, unadjusted, aje, rje, audited, priorAmount, yoyChange }
 * - 使用 calcAuditedAmount / calcIncomeStatementOccurrence / calcYoYChangeAmount / calcSubtotal
 * - 合计行计算 + 与K8-2明细交叉验证
 * - TB回写（6601发生额！）+ 发布 'substantive:adjudicated' EventBus事件
 *
 * 科目：6601销售费用（**损益类！取发生额**）
 * ⚠️ 损益类！从tb_ledger取借方发生额累计，非tb_balance期末余额
 *
 * Item IDs: "K8-1-row-{idx}-{field}"
 */
import { ref, computed, watch, nextTick, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSubtotal,
  calcYoYChangeAmount,
} from './useK8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K8AdjRow {
  rowKey: string
  /** 费用项目名称 */
  projectName: string
  /** 本期未审数（从tb_ledger取发生额） */
  unadjustedDebit: number
  /** 本期贷方发生（红冲） */
  unadjustedCredit: number
  /** 本期未审数（净额：借方-贷方，公式列） */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 上期审定数 */
  priorAmount: number
  /** 同比变动额（公式：审定-上期审定） */
  yoyChange: number
  /** 同比变动率（公式：变动额/|上期|） */
  yoyChangeRate: number | null
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

export interface K8AdjSubtotalRow {
  label: string
  unadjustedDebit: number
  unadjustedCredit: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  priorAmount: number
  yoyChange: number
  yoyChangeRate: number | null
}

export interface K8AdjPrefillRow {
  name: string
  unadjustedDebit: number
  unadjustedCredit: number
}

export interface UseK8AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  /** tb_balance 6601 明细子科目预填（无持久化行时据此建行，对齐 K9 审定表预填铁律） */
  prefill?: Ref<K8AdjPrefillRow[]>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'K8-1'
const ROWS_KEY = `${ITEM_PREFIX}-rows`
const ACCOUNT_CODE_6601 = '6601'
/** 变动率高亮阈值(±30%) */
const CHANGE_RATE_THRESHOLD = 0.3

/** 默认费用明细项目（典型29行中的重要项目） */
const DEFAULT_PROJECTS = [
  '职工薪酬',
  '差旅费',
  '业务招待费',
  '广告宣传费',
  '运输费',
  '折旧及摊销',
  '租赁费',
  '办公费',
  '通讯费',
  '保险费',
  '会议费',
  '咨询服务费',
  '装卸费',
  '包装费',
  '售后服务费',
  '其他',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function calcChangeRate(current: number, prior: number): number | null {
  const pri = parseNum(prior)
  if (pri === 0) return null
  return (parseNum(current) - pri) / Math.abs(pri)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK8Adjudication(params: UseK8AdjudicationParams) {
  const { allResponses, projectId, wpId, isReadonly, prefill, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K8AdjRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isChanged = ref(false)
  /** 是否已从预填 seed 并落库一次（避免重复/循环 persist） */
  const hasSeededPrefill = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map(_normalizeRow)
    } else if (prefill?.value && prefill.value.length > 0) {
      // 无持久化行 → 从 tb_balance 6601 明细子科目预填
      rows.value = prefill.value.map((p) => _normalizeRow({
        projectName: p.name,
        unadjustedDebit: p.unadjustedDebit,
        unadjustedCredit: p.unadjustedCredit,
        isEditable: true,
      }))
      // 预填落库：首次 seed 后一次性持久化行 + 审定合计，
      // 让附注自动取数/TB 勾稽在用户动手前即有数（seed 的是 TB 真实发生额，非臆造）。
      if (!hasSeededPrefill.value && onSave && !isReadonly?.value) {
        hasSeededPrefill.value = true
        void nextTick(() => {
          _persist()
          onSave(`${ITEM_PREFIX}-audited-total`, totalRow.value.audited)
        })
      }
    } else {
      rows.value = _buildDefaultRows()
    }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): K8AdjRow {
    const unadjustedDebit = parseNum(raw.unadjustedDebit)
    const unadjustedCredit = parseNum(raw.unadjustedCredit)
    const unadjusted = calcIncomeStatementOccurrence(unadjustedDebit, unadjustedCredit)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorAmount = parseNum(raw.priorAmount)
    const yoyChange = calcYoYChangeAmount(audited, priorAmount)
    const yoyChangeRate = calcChangeRate(audited, priorAmount)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      unadjustedDebit,
      unadjustedCredit,
      unadjusted,
      aje,
      rje,
      audited,
      priorAmount,
      yoyChange,
      yoyChangeRate,
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  function _buildDefaultRows(): K8AdjRow[] {
    return DEFAULT_PROJECTS.map((name) => ({
      rowKey: `row-${name}`,
      projectName: name,
      unadjustedDebit: 0,
      unadjustedCredit: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      priorAmount: 0,
      yoyChange: 0,
      yoyChangeRate: null,
      remark: '',
      isEditable: true,
    }))
  }

  // ─── Computed: 带公式列完整行 ──────────────────────────────────────────────

  const computedRows: ComputedRef<K8AdjRow[]> = computed(() => {
    return rows.value.map((row) => {
      const unadjusted = calcIncomeStatementOccurrence(row.unadjustedDebit, row.unadjustedCredit)
      const audited = calcAuditedAmount(unadjusted, row.aje, row.rje)
      const yoyChange = calcYoYChangeAmount(audited, row.priorAmount)
      const yoyChangeRate = calcChangeRate(audited, row.priorAmount)
      return { ...row, unadjusted, audited, yoyChange, yoyChangeRate }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<K8AdjSubtotalRow> = computed(() => {
    const detail = computedRows.value
    const unadjustedDebit = calcSubtotal(detail.map(r => r.unadjustedDebit))
    const unadjustedCredit = calcSubtotal(detail.map(r => r.unadjustedCredit))
    const unadjusted = calcIncomeStatementOccurrence(unadjustedDebit, unadjustedCredit)
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const priorAmount = calcSubtotal(detail.map(r => r.priorAmount))
    const yoyChange = calcYoYChangeAmount(audited, priorAmount)
    const yoyChangeRate = calcChangeRate(audited, priorAmount)
    return { label: '合  计', unadjustedDebit, unadjustedCredit, unadjusted, aje, rje, audited, priorAmount, yoyChange, yoyChangeRate }
  })

  // ─── 与K8-2明细合计交叉验证 ────────────────────────────────────────────────

  const detailCrossValidation: ComputedRef<{ diff: number; isBalanced: boolean }> = computed(() => {
    const adjTotal = totalRow.value.audited
    const detailTotalRaw = allResponses.value.get('K8-2-detail-audited-total')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    const diff = adjTotal - detailTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: keyof K8AdjRow, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K8AdjRow): void {
    row.unadjusted = calcIncomeStatementOccurrence(row.unadjustedDebit, row.unadjustedCredit)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.yoyChange = calcYoYChangeAmount(row.audited, row.priorAmount)
    row.yoyChangeRate = calcChangeRate(row.audited, row.priorAmount)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(projectName: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectName,
      unadjustedDebit: 0, unadjustedCredit: 0, unadjusted: 0,
      aje: 0, rje: 0, audited: 0,
      priorAmount: 0, yoyChange: 0, yoyChangeRate: null,
      remark: '', isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = rows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      isChanged.value = true
      _persist()
    }
  }

  // ─── 从 K8-2 明细带入（复现源模板 SUMIF：审定表各行取自明细表）───────────────
  /**
   * 源模板 K8-1 各行 = 明细表 K8-2 的 SUMIF（本期审定 Q / 上期审定 W）。
   * 一键按明细科目重建审定表行，填未审(=月度合计)/账项调整/重分类/上期审定。
   */
  function pullFromDetail(): { ok: boolean; message: string } {
    if (isReadonly?.value) return { ok: false, message: '只读模式' }
    const item = allResponses.value.get('K8-2-detail-rows')
    const raw = item?.remark ?? item?.conclusion
    let detail: any[] = []
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) detail = parsed
    } catch { /* ignore */ }
    if (!detail.length) return { ok: false, message: 'K8-2 明细表暂无数据，请先填写明细表' }

    rows.value = detail
      .filter((d: any) => (d.accountName || '').trim())
      .map((d: any) => {
        const months = Array.isArray(d.months) ? d.months.map((v: any) => parseNum(v)) : []
        const unadj = months.length ? calcSubtotal(months) : parseNum(d.unadjTotal)
        return _normalizeRow({
          rowKey: `row-${d.accountName}`,
          projectName: d.accountName,
          unadjustedDebit: unadj,
          unadjustedCredit: 0,
          aje: parseNum(d.aje),
          rje: parseNum(d.rje),
          priorAmount: parseNum(d.priorAmount),
          remark: d.crossRefIndex ? `勾稽：${d.crossRefIndex}` : '',
          isEditable: true,
        })
      })
    isChanged.value = true
    _persist()
    return { ok: true, message: `已从 K8-2 明细带入 ${rows.value.length} 个费用项目` }
  }

  // ─── TB回写 + EventBus（损益类发生额！）────────────────────────────────────

  /**
   * 发布审定发生额到试算表（显式发布门，损益类 occurrence 口径）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 7 / Req 1,2,6,8。
   * 此前 writeback() 直调旧端点 `PUT /projects/{pid}/trial-balance/writeback` 绕过确认门。
   * 现改为二次确认（中文）→ `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （writeback_rows 携带 6601 与前端已算审定发生额，amount_kind='occurrence'）。
   * 保留 substantive:adjudicated emit（附注刷新回归）。用户取消 → 无任何副作用。
   */
  async function writeback(): Promise<void> {
    if (isReadonly?.value) return

    try {
      await ElMessageBox.confirm(
        '发布后将把销售费用审定数（科目 6601，本期发生额）写入试算表（trial_balance），'
        + '并触发报表/错报评价等下游重算。确认发布？',
        '发布到试算表确认',
        { confirmButtonText: '确认发布', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return // 用户取消 → 无任何副作用（不 persist、不写 TB、不 emit）
    }

    _persist()
    const auditedTotal = totalRow.value.audited

    // 持久化审定合计（独立item_id，供CrossSheet+render策略回读）
    onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    if (!wpId.value) {
      ElMessage.error('缺少底稿标识，无法发布')
      return
    }

    // TB回写（科目6601，**发生额！** occurrence）
    try {
      const { api } = await import('@/services/apiProxy')
      const resp: any = await api.post(
        `/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`,
        {
          sheet_name: '审定表K8-1',
          writeback_rows: [
            { account_code: ACCOUNT_CODE_6601, audited_amount: auditedTotal, amount_kind: 'occurrence' },
          ],
        },
      )
      ElMessage.success(resp?.message || '已发布到试算表(6601发生额)')
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || err?.message || '发布失败，请重试')
      return
    }

    // 发布 'substantive:adjudicated' EventBus事件（mitt eventBus，附注组件 subscribe 刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'K8',
      accountCode: ACCOUNT_CODE_6601,
      auditedAmount: auditedTotal,
      timestamp: Date.now(),
    })

    isChanged.value = false
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    _persistAuditedByItem()
  }

  /**
   * 写 K8-1-audited-by-item（供附注上市/国企 applyAutoFill 消费）
   * 格式：{ [费用项目名]: { audited, prior } }
   * 修复此前"附注读 K8-1-audited-by-item 但审定表从不写→自动取数恒空"的死链。
   */
  function _persistAuditedByItem(): void {
    if (!onSave) return
    const byItem: Record<string, { audited: number; prior: number }> = {}
    for (const row of computedRows.value) {
      const name = (row.projectName || '').trim()
      if (!name) continue
      byItem[name] = { audited: row.audited, prior: row.priorAmount }
    }
    onSave(`${ITEM_PREFIX}-audited-by-item`, byItem)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── 全量重算 ──────────────────────────────────────────────────────────────

  function computeAll(): void {
    for (const row of rows.value) _recalcRow(row)
    _persist()
  }

  /** 获取审定合计（供外部CrossSheet/TB回写） */
  function getAuditedTotal(): number {
    return totalRow.value.audited
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch([allResponses, () => prefill?.value], () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    totalRow,
    auditNote,
    auditConclusion,
    isChanged,
    detailCrossValidation,
    updateCell,
    addRow,
    removeRow,
    pullFromDetail,
    writeback,
    computeAll,
    saveNote,
    saveConclusion,
    getAuditedTotal,
    initFromResponses,
  }
}

export default useK8Adjudication
