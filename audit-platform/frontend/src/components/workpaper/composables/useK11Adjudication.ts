/**
 * useK11Adjudication — K11-1 审定表逻辑（37行×12列，61公式，损益类！取发生额）
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 * Task: 3.4
 * Requirements: 2~6 全部
 *
 * 职责：
 * - 管理审定表行数据（按资产类别分行，37行）
 * - 每行（对齐源模板12列）: { projectName, 上期数[priorUnadjusted/priorAdjustment/priorAudited], 本期数[currentOccurrence/aje/rje/audited], yoyChange/yoyChangeRate, sourceWp, remark(原因分析) }
 * - 使用 calcAuditedAmount / calcIncomeStatementOccurrence / calcSubtotal
 * - 合计行计算 + 与K11-2明细交叉验证
 * - TB回写（6701发生额！）+ 发布 'substantive:adjudicated' EventBus事件
 * - GtIndexChip跳转源底稿(F2/H1/I1/I3/H2/G7/H4/H8/H3)
 *
 * 科目：6701资产减值损失（**损益类！取发生额**）
 * ⚠️ 损益类！从tb_ledger取借方发生额累计，非tb_balance期末余额
 *
 * Item IDs: "K11-1-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSubtotal,
} from './useK11FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K11AdjRow {
  rowKey: string
  /** 资产类别/减值项目名称 */
  projectName: string
  // ── 上期数（源模板：未审数/账项调整/审定数） ──
  /** 上期未审数 */
  priorUnadjusted: number
  /** 上期账项调整 */
  priorAdjustment: number
  /** 上期审定数（公式：上期未审+上期账项调整） */
  priorAudited: number
  // ── 本期数（源模板：未审数/账项调整/审定数；本平台账项调整细分为AJE+RJE） ──
  /** 本期未审数（=本期发生额，借方发生-贷方发生，从tb_ledger） */
  currentOccurrence: number
  /** 未审数（=本期发生额，公式列别名） */
  unadjusted: number
  /** 本期账项调整 AJE */
  aje: number
  /** 本期重分类 RJE */
  rje: number
  /** 本期审定数（公式：未审+AJE+RJE） */
  audited: number
  // ── 本期审定数与上期审定数的比较 ──
  /** 变动额（公式：本期审定-上期审定） */
  yoyChange: number
  /** 变动率（公式：变动额/|上期审定|） */
  yoyChangeRate: number | null
  /** 来源底稿编码（如 F2/H1/I1/I3 等） */
  sourceWp: string
  /** 原因分析（源模板末列，字段名保持 remark 向后兼容） */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
  /** 是否为合计行 */
  isTotalRow: boolean
}

export interface K11AdjSubtotalRow {
  label: string
  priorUnadjusted: number
  priorAdjustment: number
  priorAudited: number
  currentOccurrence: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  yoyChange: number
  yoyChangeRate: number | null
}

export interface UseK11AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'K11-1'
const ROWS_KEY = `${ITEM_PREFIX}-rows`
const ACCOUNT_CODE_6701 = '6701'

/** 来源底稿映射（sourceWp codes） */
export const SOURCE_WP_CODES = ['F2', 'H1', 'I1', 'I2', 'I3', 'H2', 'G7', 'H4', 'H8', 'H3'] as const

/**
 * 默认审定表资产类别行 —— P1 对齐源模板 K11-1 canonical 18 项
 * （合同资产/存货跌价/合同取得成本/合同履约成本/持有待售/其他权益工具投资/
 *  其他非流动金融资产/长期股权投资/投资性房地产/固定资产/工程物资/在建工程/
 *  生产性生物资产/油气资产/使用权资产/无形资产/商誉/其他），项目名用"损失"后缀对齐源模板。
 * sourceWp 仅对有清晰单一减值源底稿的项目设置，其余留空。
 */
const DEFAULT_PROJECTS: Array<{ name: string; sourceWp: string }> = [
  { name: '合同资产减值损失', sourceWp: 'D6' },
  { name: '存货跌价损失', sourceWp: 'F2' },
  { name: '合同取得成本减值损失', sourceWp: '' },
  { name: '合同履约成本减值损失', sourceWp: '' },
  { name: '持有待售资产减值损失', sourceWp: 'K6' },
  { name: '其他权益工具投资减值损失', sourceWp: '' },
  { name: '其他非流动金融资产减值损失', sourceWp: '' },
  { name: '长期股权投资减值损失', sourceWp: 'G7' },
  { name: '投资性房地产减值损失', sourceWp: 'H3' },
  { name: '固定资产减值损失', sourceWp: 'H1' },
  { name: '工程物资减值损失', sourceWp: 'H4' },
  { name: '在建工程减值损失', sourceWp: 'H2' },
  { name: '生产性生物资产减值损失', sourceWp: 'H5' },
  { name: '油气资产减值损失', sourceWp: 'H7' },
  { name: '使用权资产减值损失', sourceWp: 'H8' },
  { name: '无形资产减值损失', sourceWp: 'I1' },
  { name: '商誉减值损失', sourceWp: 'I3' },
  { name: '其他', sourceWp: '' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function calcChangeRate(current: number, prior: number): number | null {
  const pri = parseNum(prior)
  if (pri === 0) return null
  return (parseNum(current) - pri) / Math.abs(pri)
}

/**
 * 归一化减值资产类别名（审定表↔附注披露跨表匹配用）。
 * 去掉"减值/准备/损失/资产"及空白 → 共同资产词干。
 * 例："存货跌价准备"/"存货跌价损失"→"存货跌价"；
 *     "固定资产减值准备"/"固定资产减值损失"→"固定"；
 *     "商誉减值准备"/"商誉减值损失"→"商誉"。
 */
export function normalizeImpairmentCategory(name: string): string {
  return String(name || '')
    .replace(/减值/g, '')
    .replace(/准备/g, '')
    .replace(/损失/g, '')
    .replace(/资产/g, '')
    .replace(/\s/g, '')
    .trim()
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK11Adjudication(params: UseK11AdjudicationParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K11AdjRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map(_normalizeRow)
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

  function _normalizeRow(raw: any): K11AdjRow {
    // 上期数：迁移旧字段 priorOccurrence → priorUnadjusted（旧数据无上期账项调整）
    const priorUnadjusted = parseNum(raw.priorUnadjusted ?? raw.priorOccurrence)
    const priorAdjustment = parseNum(raw.priorAdjustment)
    const priorAudited = priorUnadjusted + priorAdjustment
    // 本期数
    const currentOccurrence = parseNum(raw.currentOccurrence)
    const unadjusted = currentOccurrence
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    // 比较：本期审定 vs 上期审定
    const yoyChange = audited - priorAudited
    const yoyChangeRate = calcChangeRate(audited, priorAudited)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      priorUnadjusted,
      priorAdjustment,
      priorAudited,
      currentOccurrence,
      unadjusted,
      aje,
      rje,
      audited,
      yoyChange,
      yoyChangeRate,
      sourceWp: raw.sourceWp ?? '',
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
      isTotalRow: raw.isTotalRow ?? false,
    }
  }

  function _buildDefaultRows(): K11AdjRow[] {
    return DEFAULT_PROJECTS.map((item) => ({
      rowKey: `row-${item.name}`,
      projectName: item.name,
      priorUnadjusted: 0,
      priorAdjustment: 0,
      priorAudited: 0,
      currentOccurrence: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      yoyChange: 0,
      yoyChangeRate: null,
      sourceWp: item.sourceWp,
      remark: '',
      isEditable: true,
      isTotalRow: false,
    }))
  }

  // ─── Computed: 带公式列完整行 ──────────────────────────────────────────────

  const computedRows: ComputedRef<K11AdjRow[]> = computed(() => {
    return rows.value.map((row) => {
      const priorAudited = row.priorUnadjusted + row.priorAdjustment
      const unadjusted = row.currentOccurrence
      const audited = calcAuditedAmount(unadjusted, row.aje, row.rje)
      const yoyChange = audited - priorAudited
      const yoyChangeRate = calcChangeRate(audited, priorAudited)
      return { ...row, priorAudited, unadjusted, audited, yoyChange, yoyChangeRate }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow: ComputedRef<K11AdjSubtotalRow> = computed(() => {
    const detail = computedRows.value
    const priorUnadjusted = calcSubtotal(detail.map(r => r.priorUnadjusted))
    const priorAdjustment = calcSubtotal(detail.map(r => r.priorAdjustment))
    const priorAudited = priorUnadjusted + priorAdjustment
    const currentOccurrence = calcSubtotal(detail.map(r => r.currentOccurrence))
    const unadjusted = currentOccurrence
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const yoyChange = audited - priorAudited
    const yoyChangeRate = calcChangeRate(audited, priorAudited)
    return { label: '合  计', priorUnadjusted, priorAdjustment, priorAudited, currentOccurrence, unadjusted, aje, rje, audited, yoyChange, yoyChangeRate }
  })

  // ─── 与K11-2明细合计交叉验证 ────────────────────────────────────────────────

  const detailCrossValidation: ComputedRef<{ diff: number; isBalanced: boolean }> = computed(() => {
    const adjTotal = totalRow.value.audited
    const detailTotalRaw = allResponses.value.get('K11-2-total-occurrence')
    const detailTotal = parseNum(detailTotalRaw?.remark ?? detailTotalRaw?.conclusion ?? 0)
    const diff = adjTotal - detailTotal
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── 与K11-3调整分录合计勾稽（K11-3→K11-1 联动可见，不双重累加）────────────

  const adjustmentReconcile: ComputedRef<{
    ajeFromEntries: number
    rjeFromEntries: number
    ajeInTable: number
    rjeInTable: number
    ajeDiff: number
    rjeDiff: number
    hasK113: boolean
    isMatch: boolean
  }> = computed(() => {
    const ajeItem = allResponses.value.get('K11-1-aje-total')
    const rjeItem = allResponses.value.get('K11-1-rje-total')
    const ajeFromEntries = parseNum(ajeItem?.remark ?? ajeItem?.conclusion ?? 0)
    const rjeFromEntries = parseNum(rjeItem?.remark ?? rjeItem?.conclusion ?? 0)
    const ajeInTable = totalRow.value.aje
    const rjeInTable = totalRow.value.rje
    const ajeDiff = ajeInTable - ajeFromEntries
    const rjeDiff = rjeInTable - rjeFromEntries
    const hasK113 = !!ajeItem || !!rjeItem
    return {
      ajeFromEntries,
      rjeFromEntries,
      ajeInTable,
      rjeInTable,
      ajeDiff,
      rjeDiff,
      hasK113,
      isMatch: Math.abs(ajeDiff) < 0.01 && Math.abs(rjeDiff) < 0.01,
    }
  })

  // ─── GtIndexChip数据（源底稿跳转） ────────────────────────────────────────

  const sourceChipData: ComputedRef<Array<{ rowKey: string; sourceWp: string; label: string }>> = computed(() => {
    return computedRows.value
      .filter(r => r.sourceWp)
      .map(r => ({
        rowKey: r.rowKey,
        sourceWp: r.sourceWp,
        label: `${r.sourceWp} ${r.projectName}`,
      }))
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: keyof K11AdjRow, value: number | string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K11AdjRow): void {
    row.priorAudited = row.priorUnadjusted + row.priorAdjustment
    row.unadjusted = row.currentOccurrence
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.yoyChange = row.audited - row.priorAudited
    row.yoyChangeRate = calcChangeRate(row.audited, row.priorAudited)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(projectName: string, sourceWp: string = ''): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      projectName,
      priorUnadjusted: 0,
      priorAdjustment: 0,
      priorAudited: 0,
      currentOccurrence: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      yoyChange: 0,
      yoyChangeRate: null,
      sourceWp,
      remark: '',
      isEditable: true,
      isTotalRow: false,
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

  // ─── TB回写 + EventBus（损益类发生额！）────────────────────────────────────

  async function writeback(): Promise<void> {
    _persist()
    const auditedTotal = totalRow.value.audited

    // 持久化审定合计（独立item_id，供CrossSheet+render策略回读）
    onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    // TB回写（科目6701，**发生额！**）
    if (projectId.value) {
      try {
        const { default: http } = await import('@/utils/http')
        await http.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_6701,
          audited_amount: auditedTotal,
          is_occurrence: true, // 损益类标记
        })
        ElMessage.success('审定发生额已回写试算表(6701)')
      } catch {
        ElMessage.warning('审定发生额回写失败，请手动确认')
      }
    }

    // 发布 'substantive:adjudicated' EventBus事件（附注组件 subscribe 刷新）
    eventBus.emit('substantive:adjudicated', {
      wpCode: 'K11',
      accountCode: ACCOUNT_CODE_6701,
      auditedAmount: auditedTotal,
      timestamp: Date.now(),
    })

    isChanged.value = false
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 供附注披露自动取数（按归一化资产类别键写 audited-by-category，修复死链）
    onSave('K11-1-audited-by-category', _buildAuditedByCategory())
  }

  /**
   * 构建 audited-by-category（附注披露 applyAutoFill 消费）。
   * 键=归一化资产类别；值含本期审定发生额(currentProvision)/上期(priorAmount)。
   * K11-1 只有净发生额，故 currentReversal=0（本期发生额=净额，与源模板"附注引用审定数"一致）。
   */
  function _buildAuditedByCategory(): Record<string, {
    currentProvision: number
    currentReversal: number
    priorAmount: number
    occurrence: number
  }> {
    const out: Record<string, { currentProvision: number; currentReversal: number; priorAmount: number; occurrence: number }> = {}
    // 直接从 raw rows.value 计算（_persist 同步调用，rows 已被 _recalcRow 更新）；
    // 不依赖 computedRows 的惰性求值时序，保证 persist 时取到最新值。
    for (const row of rows.value) {
      if (!row.projectName) continue
      const key = normalizeImpairmentCategory(row.projectName)
      if (!key) continue
      const audited = calcAuditedAmount(row.currentOccurrence, row.aje, row.rje)
      const priorAudited = parseNum(row.priorUnadjusted) + parseNum(row.priorAdjustment)
      out[key] = {
        currentProvision: audited,
        currentReversal: 0,
        priorAmount: priorAudited,
        occurrence: audited,
      }
    }
    return out
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function getAuditedTotal(): number {
    return totalRow.value.audited
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    totalRow,
    auditNote,
    auditConclusion,
    isChanged,
    detailCrossValidation,
    adjustmentReconcile,
    sourceChipData,
    updateCell,
    addRow,
    removeRow,
    writeback,
    saveNote,
    saveConclusion,
    getAuditedTotal,
    initFromResponses,
  }
}

export default useK11Adjudication
