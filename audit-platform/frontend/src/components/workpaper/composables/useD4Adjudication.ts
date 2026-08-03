/**
 * useD4Adjudication — D4-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/d4-four-table-extraction-and-disclosure-alignment/
 * Task: 4.2 (接 adjudication_prefill + dynamicAdjudicationRows 共享件 + previewSeedFromPrefill)
 *
 * 职责：
 * - 接后端 `adjudication_prefill`（html_data 输出，Task 2.1）
 * - 使用共享 `dynamicAdjudicationRows` 动态行基础设施（K2 范式）
 * - `previewSeedFromPrefill` 行为：
 *   ・新子科目自动插行
 *   ・已有行金额变化弹确认（可选「仅补空值」）
 *   ・手工/历史行永不覆盖（Req 3.4）
 * - 双区块（主营/其他）+ 小计/合计/TB核对/差异
 * - crossSheet 聚合（D4-2/D4-3/D4-4）
 * - EventBus 发布审定数（TB 回写 6001/6051）
 *
 * Requirements: 3.2, 3.4, 3.5
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { D4_MAIN_REVENUE_STANDARD, D4_OTHER_REVENUE_STANDARD, isMainRevenueCode, isOtherRevenueCode } from './d4AccountScope'
import { D4_ADJ_ROWS_SPEC, D4_ADJ_PREFIX } from './d4AdjudicationRows'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
} from './useD4FormulaEngine'
import {
  type DynamicAdjRow,
  type DynamicRowPrefillItem,
  type SeedFromPrefillResult,
  resolveInitialRows,
  serializeRows,
  deserializeRows,
  seedRowsFromPrefill,
  findRowForPrefill,
  findDuplicateLabel,
  appendManualRow,
  dropRow,
  renameRowLabel,
  rowsItemId,
  rowFieldItemId,
  readNum,
  readRaw,
  normalizeLabel,
} from './shared/dynamicAdjudicationRows'
import type { ChecklistResponse } from './useD4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 基础选项（兼容其他 D4 composable 的 `UseD4BaseOptions` 导入） */
export interface UseD4BaseOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface UseD4AdjudicationOptions extends UseD4BaseOptions {
  /** 后端 render 下发的 `adjudication_prefill`（html_data 顶层） */
  adjudicationPrefill?: Ref<DynamicRowPrefillItem[] | null | undefined>
  /** 保存字段值到 checklist_responses */
  saveField?: (itemId: string, value: { remark?: string; conclusion?: string | null }) => void
  /** 批量保存 */
  saveBatch?: (items: Array<{ item_id: string; remark?: string; conclusion?: string | null }>) => void
}

export interface AdjudicationRow {
  rowKey: string
  label: string
  isFixed: boolean
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number
  isFromCrossSheet: boolean
  isEditable: boolean
  /** 动态行对象（仅内部使用） */
  _dynamicRow?: DynamicAdjRow
}

export interface AdjudicationSection {
  sectionKey: 'main-revenue' | 'other-revenue'
  sectionLabel: string
  rows: AdjudicationRow[]
  subtotalRow: AdjudicationRow
}

/** previewSeedFromPrefill 的预览结果 */
export interface PrefillPreviewItem {
  label: string
  code?: string
  isNew: boolean
  currentValue: number
  prefillValue: number
  /** 该行是否有手工录入（手工永不覆盖） */
  isManual: boolean
  /** 该行金额是否有变化 */
  hasChange: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const BALANCE_TOLERANCE = 0.005

/**
 * 旧模型行清单 itemId（兼容迁移前的 `D4-1-adj-rows` JSON）。
 * 新模型使用共享件的 `{prefix}-rows` = `D4-1-rows`。
 */
const LEGACY_ADJ_STORAGE_KEY = 'D4-1-adj-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 从旧 JSON 格式迁移到动态行模型。
 * 旧格式 = `[{rowKey, label, sectionKey, currentUnadjusted, ...}]` 整行序列化。
 * 新格式 = `DynamicAdjRow[]` 清单 + per-field 键。
 */
function migrateLegacyD4Rows(
  responses: Map<string, unknown> | null | undefined,
): { rows: DynamicAdjRow[]; fieldValues: Record<string, string> } | null {
  const legacyResp = responses?.get(LEGACY_ADJ_STORAGE_KEY) as Record<string, unknown> | undefined
  const raw = legacyResp?.remark as string | undefined
  if (!raw) return null

  interface LegacyRow {
    rowKey: string
    label: string
    sectionKey: string
    currentUnadjusted?: number
    currentAje?: number
    currentRje?: number
    priorUnadjusted?: number
    priorAje?: number
    priorRje?: number
    isFromCrossSheet?: boolean
  }

  const legacyRows = safeParseRows<LegacyRow>(raw)
  if (legacyRows.length === 0) return null

  const dynamicRows: DynamicAdjRow[] = []
  const fieldValues: Record<string, string> = {}

  for (const lr of legacyRows) {
    if (!lr.rowKey || !lr.label) continue
    const row: DynamicAdjRow = {
      rowId: lr.rowKey,
      label: normalizeLabel(lr.label),
      source: lr.isFromCrossSheet ? 'tb' : 'manual',
    }
    dynamicRows.push(row)

    // 迁移金额值到 per-field 键
    const prefix = D4_ADJ_PREFIX
    if (lr.currentUnadjusted)
      fieldValues[`${prefix}-${lr.rowKey}-currentUnadjusted`] = String(lr.currentUnadjusted)
    if (lr.currentAje)
      fieldValues[`${prefix}-${lr.rowKey}-currentAje`] = String(lr.currentAje)
    if (lr.currentRje)
      fieldValues[`${prefix}-${lr.rowKey}-currentRje`] = String(lr.currentRje)
    if (lr.priorUnadjusted)
      fieldValues[`${prefix}-${lr.rowKey}-priorUnadjusted`] = String(lr.priorUnadjusted)
    if (lr.priorAje)
      fieldValues[`${prefix}-${lr.rowKey}-priorAje`] = String(lr.priorAje)
    if (lr.priorRje)
      fieldValues[`${prefix}-${lr.rowKey}-priorRje`] = String(lr.priorRje)
  }

  return { rows: dynamicRows, fieldValues }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4Adjudication(options: UseD4AdjudicationOptions) {
  const {
    wpId,
    projectId,
    allResponses,
    isReadonly,
    adjudicationPrefill,
    saveField,
    saveBatch,
  } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Dynamic rows state ──────────────────────────────────────────────

  const dynamicRows = ref<DynamicAdjRow[]>([])
  const hasPrefillData = computed(() => {
    const pf = adjudicationPrefill?.value
    return Array.isArray(pf) && pf.length > 0
  })

  // ─── Initialize rows (from responses or migration) ──────────────────

  function initRows(): void {
    const responses = allResponses.value

    // 1. 尝试从新模型读取（`D4-1-rows`）
    const newModelItemId = rowsItemId(D4_ADJ_ROWS_SPEC)
    const stored = readRaw(responses as Map<string, unknown>, newModelItemId)
    if (stored.trim()) {
      dynamicRows.value = deserializeRows(stored)
      return
    }

    // 2. 尝试从旧 JSON 模型迁移
    const migrated = migrateLegacyD4Rows(responses as Map<string, unknown>)
    if (migrated && migrated.rows.length > 0) {
      dynamicRows.value = migrated.rows
      // 持久化迁移结果
      persistRowList(migrated.rows)
      // 迁移字段值
      for (const [key, val] of Object.entries(migrated.fieldValues)) {
        responses.set(key, { item_id: key, conclusion: null, remark: val } as any)
      }
      return
    }

    // 3. 共享件的 resolveInitialRows（处理 legacyRows 迁移，D4 为空数组所以跳过）
    const resolved = resolveInitialRows(D4_ADJ_ROWS_SPEC, responses as Map<string, unknown>)
    dynamicRows.value = resolved.rows
    if (resolved.migrated) {
      persistRowList(resolved.rows)
    }
  }

  // 首次初始化
  initRows()

  // 监听 allResponses 变化时重新初始化（宿主保存后重建 allResponses）
  watch(allResponses, () => { initRows() }, { deep: false })

  // ─── Persist helpers ─────────────────────────────────────────────────

  function persistRowList(rows: DynamicAdjRow[]): void {
    const itemId = rowsItemId(D4_ADJ_ROWS_SPEC)
    const json = serializeRows(rows)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: json } as any)
    debounceSave()
  }

  function persistFieldValue(rowId: string, field: string, value: string | number): void {
    const itemId = rowFieldItemId(D4_ADJ_ROWS_SPEC, rowId, field)
    const strVal = String(value ?? 0)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: strVal } as any)
    debounceSave()
  }

  // ─── Read field value from responses ─────────────────────────────────

  function getRowFieldValue(rowId: string, field: string): number {
    const itemId = rowFieldItemId(D4_ADJ_ROWS_SPEC, rowId, field)
    return readNum(allResponses.value as Map<string, unknown>, itemId)
  }

  // ─── Seed from prefill (Req 3.5) ────────────────────────────────────

  /**
   * 从四表预填数据建行 + 填充金额。
   *
   * @param overwrite - 为 true 时覆盖四表行的已有值；为 false 时仅补空值。
   *                    **手工行（source='manual'）永不覆盖**（Req 3.4）。
   */
  function seedFromPrefill(opts: { overwrite: boolean } = { overwrite: false }): void {
    const prefill = adjudicationPrefill?.value
    if (!prefill || prefill.length === 0) return

    const result = seedRowsFromPrefill(
      D4_ADJ_ROWS_SPEC,
      prefill,
      dynamicRows.value,
      // D4 损益类：opening_balance = 上期发生额 → priorUnadjusted
      //           closing_balance = 本期发生额 → currentUnadjusted
      { opening: 'priorUnadjusted', closing: 'currentUnadjusted' },
    )

    // 更新行清单
    dynamicRows.value = result.rows
    persistRowList(result.rows)

    // 写入字段值（手工优先 / 仅补空值 按 overwrite 判定）
    for (const [itemId, val] of Object.entries(result.values)) {
      const rowId = extractRowIdFromItemId(itemId)
      const row = result.rows.find(r => r.rowId === rowId)

      // 🔴 手工行永不覆盖（Req 3.4）
      if (row?.source === 'manual') continue

      const existing = readNum(allResponses.value as Map<string, unknown>, itemId)
      if (!opts.overwrite && existing !== 0) continue // 仅补空值模式

      allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: val } as any)
    }

    debounceSave()
  }

  /**
   * 预览 seed 效果 —— 弹确认对话框（Req 3.5）。
   *
   * 行为：
   * - 新子科目 → 显示将要自动插入的行
   * - 已有行金额变化 → 显示变化明细，用户可选「全部覆盖」或「仅补空值」
   * - 手工行 → 显示「保持不变」
   */
  async function previewSeedFromPrefill(): Promise<void> {
    const prefill = adjudicationPrefill?.value
    if (!prefill || prefill.length === 0) return

    const preview: PrefillPreviewItem[] = []
    let hasNewRows = false
    let hasChanges = false

    for (const p of prefill) {
      const label = normalizeLabel(p.name)
      if (!label) continue

      const existingRow = findRowForPrefill(dynamicRows.value, p)
      const prefillValue = Number(p.closing_balance) || 0

      if (!existingRow) {
        // 新子科目 → 自动插行
        hasNewRows = true
        preview.push({
          label,
          code: p.code,
          isNew: true,
          currentValue: 0,
          prefillValue,
          isManual: false,
          hasChange: true,
        })
      } else {
        const currentValue = getRowFieldValue(existingRow.rowId, 'currentUnadjusted')
        const isManual = existingRow.source === 'manual'
        const changed = Math.abs(currentValue - prefillValue) > BALANCE_TOLERANCE

        preview.push({
          label,
          code: p.code,
          isNew: false,
          currentValue,
          prefillValue,
          isManual,
          hasChange: changed && !isManual,
        })

        if (changed && !isManual) hasChanges = true
      }
    }

    // 只有新行且无变化 → 直接插行，无需确认
    if (hasNewRows && !hasChanges) {
      seedFromPrefill({ overwrite: false })
      return
    }

    // 有变化 → 弹确认
    if (hasChanges) {
      const changedItems = preview.filter(p => p.hasChange && !p.isNew && !p.isManual)
      const newItems = preview.filter(p => p.isNew)

      let message = ''
      if (newItems.length > 0) {
        message += `<p><b>新增 ${newItems.length} 行：</b>${newItems.map(i => i.label).join('、')}</p>`
      }
      if (changedItems.length > 0) {
        message += `<p><b>${changedItems.length} 行金额有变化：</b></p><ul>`
        for (const item of changedItems.slice(0, 5)) {
          message += `<li>${item.label}：${item.currentValue.toFixed(2)} → ${item.prefillValue.toFixed(2)}</li>`
        }
        if (changedItems.length > 5) {
          message += `<li>…等共 ${changedItems.length} 项</li>`
        }
        message += '</ul>'
        message += '<p>手工录入的行将保持不变。</p>'
      }

      try {
        const action = await ElMessageBox.confirm(message, '四表取数预览', {
          dangerouslyUseHTMLString: true,
          confirmButtonText: '全部覆盖',
          cancelButtonText: '仅补空值',
          distinguishCancelAndClose: true,
          type: 'info',
        })
        // 确认 → 全部覆盖
        seedFromPrefill({ overwrite: true })
      } catch (action) {
        if (action === 'cancel') {
          // 取消 = 仅补空值
          seedFromPrefill({ overwrite: false })
        }
        // close = 关闭对话框，不做任何操作
      }
    }
  }

  // ─── Row operations (dynamic rows) ───────────────────────────────────

  function addRow(label: string, sectionKey: 'main-revenue' | 'other-revenue'): DynamicAdjRow | null {
    if (readonly.value) return null
    const normalized = normalizeLabel(label)
    if (!normalized) return null

    // 撞名检查
    if (findDuplicateLabel(dynamicRows.value, normalized)) return null

    const { rows, row } = appendManualRow(dynamicRows.value)
    // 设置行标签
    const updatedRows = rows.map(r => r.rowId === row.rowId ? { ...r, label: normalized } : r)
    dynamicRows.value = updatedRows
    persistRowList(updatedRows)
    return row
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    const result = dropRow(
      D4_ADJ_ROWS_SPEC,
      dynamicRows.value,
      allResponses.value as Map<string, unknown>,
      rowId,
    )
    dynamicRows.value = result.rows
    persistRowList(result.rows)

    // 清理字段键
    for (const removedId of result.removedItemIds) {
      allResponses.value.delete(removedId)
    }
    debounceSave()
  }

  function renameRow(rowId: string, newLabel: string): boolean {
    if (readonly.value) return false
    const normalized = normalizeLabel(newLabel)
    if (!normalized) return false

    // 撞名检查（排除自身）
    if (findDuplicateLabel(dynamicRows.value, normalized, rowId)) return false

    dynamicRows.value = renameRowLabel(dynamicRows.value, rowId, normalized)
    persistRowList(dynamicRows.value)
    return true
  }

  // ─── Audit note / conclusion ─────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── CrossSheet data (from allResponses D4-2/D4-3/D4-4) ─────────────

  const mainRevenueByProduct = computed<Record<string, { current: number; prior: number }>>(() => {
    const resp = allResponses.value.get('D4-2-rows')
    const rows = safeParseRows<any>(resp?.remark)
    const result: Record<string, { current: number; prior: number }> = {}
    for (const row of rows) {
      const product = row.product || '未命名'
      const months = Array.isArray(row.months) ? row.months.map(parseNum) : []
      const periodTotal = months.reduce((s: number, v: number) => s + v, 0)
      const audited = periodTotal + parseNum(row.auditAdjustment)
      const priorAudited = parseNum(row.priorUnadjusted) + parseNum(row.priorAdjustment)
      if (!result[product]) result[product] = { current: 0, prior: 0 }
      result[product].current += audited
      result[product].prior += priorAudited
    }
    return result
  })

  const otherRevenueByItem = computed<Record<string, { current: number; prior: number }>>(() => {
    const resp = allResponses.value.get('D4-3-rows')
    const rows = safeParseRows<any>(resp?.remark)
    const result: Record<string, { current: number; prior: number }> = {}
    for (const row of rows) {
      const item = row.item || '未命名'
      const currentAudited = parseNum(row.currentUnadjusted) + parseNum(row.currentAdjustment)
      const priorAudited = parseNum(row.priorUnadjusted) + parseNum(row.priorAdjustment)
      if (!result[item]) result[item] = { current: 0, prior: 0 }
      result[item].current += currentAudited
      result[item].prior += priorAudited
    }
    return result
  })

  const adjustmentTotals = computed(() => {
    const resp = allResponses.value.get('D4-4-rows')
    const rows = safeParseRows<any>(resp?.remark)
    let mainAje = 0, mainRje = 0, otherAje = 0, otherRje = 0
    for (const row of rows) {
      const code = row.accountName || row.accountCode || ''
      const amount = parseNum(row.debitAmount) - parseNum(row.creditAmount)
      const isMain = code.includes(D4_MAIN_REVENUE_STANDARD)
      const isOther = code.includes(D4_OTHER_REVENUE_STANDARD)
      if (isMain) {
        if (row.category === 'AJE' || row.entryType === 'AJE') mainAje += amount
        else mainRje += amount
      } else if (isOther) {
        if (row.category === 'AJE' || row.entryType === 'AJE') otherAje += amount
        else otherRje += amount
      }
    }
    return { mainAje, mainRje, otherAje, otherRje }
  })

  // ─── Sections computed (combining dynamic rows + crossSheet) ─────────

  const sections: ComputedRef<AdjudicationSection[]> = computed(() => {
    const rows = dynamicRows.value
    const adjTotals = adjustmentTotals.value

    // 按科目码分组（主营 6001 / 其他 6051）
    const mainRows: AdjudicationRow[] = []
    const otherRows: AdjudicationRow[] = []

    for (const r of rows) {
      const code = r.accountCode || ''
      const isOther = isOtherRevenueCode(code)

      const currentUnadj = getRowFieldValue(r.rowId, 'currentUnadjusted')
      const priorUnadj = getRowFieldValue(r.rowId, 'priorUnadjusted')
      const currentAje = getRowFieldValue(r.rowId, 'currentAje')
      const currentRje = getRowFieldValue(r.rowId, 'currentRje')
      const priorAje = getRowFieldValue(r.rowId, 'priorAje')
      const priorRje = getRowFieldValue(r.rowId, 'priorRje')

      const adjRow: AdjudicationRow = {
        rowKey: r.rowId,
        label: r.label,
        isFixed: false,
        currentUnadjusted: currentUnadj,
        currentAje,
        currentRje,
        currentAudited: calcAuditedAmount(currentUnadj, currentAje, currentRje),
        priorUnadjusted: priorUnadj,
        priorAje,
        priorRje,
        priorAudited: calcAuditedAmount(priorUnadj, priorAje, priorRje),
        isFromCrossSheet: r.source === 'tb',
        isEditable: r.source !== 'tb' || true, // 所有行可编辑 AJE/RJE
        _dynamicRow: r,
      }

      if (isOther) {
        otherRows.push(adjRow)
      } else {
        // 默认归入主营（无科目码的手工行也归主营）
        mainRows.push(adjRow)
      }
    }

    const mainSubtotal: AdjudicationRow = buildSubtotalRow('main-subtotal', '主营业务收入小计', mainRows, adjTotals.mainAje, adjTotals.mainRje)
    const otherSubtotal: AdjudicationRow = buildSubtotalRow('other-subtotal', '其他业务收入小计', otherRows, adjTotals.otherAje, adjTotals.otherRje)

    return [
      {
        sectionKey: 'main-revenue' as const,
        sectionLabel: '一、主营业务收入',
        rows: mainRows,
        subtotalRow: mainSubtotal,
      },
      {
        sectionKey: 'other-revenue' as const,
        sectionLabel: '二、其他业务收入',
        rows: otherRows,
        subtotalRow: otherSubtotal,
      },
    ]
  })

  function buildSubtotalRow(
    rowKey: string,
    label: string,
    rows: AdjudicationRow[],
    sectionAje: number,
    sectionRje: number,
  ): AdjudicationRow {
    const currentUnadj = calcSubtotal(rows.map(r => r.currentUnadjusted))
    const priorUnadj = calcSubtotal(rows.map(r => r.priorUnadjusted))
    return {
      rowKey,
      label,
      isFixed: true,
      currentUnadjusted: currentUnadj,
      currentAje: sectionAje,
      currentRje: sectionRje,
      currentAudited: calcAuditedAmount(currentUnadj, sectionAje, sectionRje),
      priorUnadjusted: priorUnadj,
      priorAje: calcSubtotal(rows.map(r => r.priorAje)),
      priorRje: calcSubtotal(rows.map(r => r.priorRje)),
      priorAudited: calcAuditedAmount(
        priorUnadj,
        calcSubtotal(rows.map(r => r.priorAje)),
        calcSubtotal(rows.map(r => r.priorRje)),
      ),
      isFromCrossSheet: false,
      isEditable: false,
    }
  }

  // ─── Grand Total Row ─────────────────────────────────────────────────

  const grandTotalRow: ComputedRef<AdjudicationRow> = computed(() => {
    const secs = sections.value
    const mainSub = secs[0]?.subtotalRow
    const otherSub = secs[1]?.subtotalRow

    if (!mainSub || !otherSub) {
      return {
        rowKey: 'grand-total', label: '营业收入合计', isFixed: true,
        currentUnadjusted: 0, currentAje: 0, currentRje: 0, currentAudited: 0,
        priorUnadjusted: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
        isFromCrossSheet: false, isEditable: false,
      }
    }

    return {
      rowKey: 'grand-total',
      label: '营业收入合计',
      isFixed: true,
      currentUnadjusted: mainSub.currentUnadjusted + otherSub.currentUnadjusted,
      currentAje: mainSub.currentAje + otherSub.currentAje,
      currentRje: mainSub.currentRje + otherSub.currentRje,
      currentAudited: mainSub.currentAudited + otherSub.currentAudited,
      priorUnadjusted: mainSub.priorUnadjusted + otherSub.priorUnadjusted,
      priorAje: mainSub.priorAje + otherSub.priorAje,
      priorRje: mainSub.priorRje + otherSub.priorRje,
      priorAudited: mainSub.priorAudited + otherSub.priorAudited,
      isFromCrossSheet: false,
      isEditable: false,
    }
  })

  // ─── Trial Balance Row ───────────────────────────────────────────────

  const trialBalanceRow: ComputedRef<{ amount6001: number; amount6051: number; total: number }> = computed(() => {
    const tb6001 = parseNum(allResponses.value.get('D4-1-adj-tb-6001')?.remark)
    const tb6051 = parseNum(allResponses.value.get('D4-1-adj-tb-6051')?.remark)
    return { amount6001: tb6001, amount6051: tb6051, total: tb6001 + tb6051 }
  })

  // ─── Difference Row ──────────────────────────────────────────────────

  const differenceRow: ComputedRef<number> = computed(() => {
    return grandTotalRow.value.currentAudited - trialBalanceRow.value.total
  })

  // ─── Cross Validation Warnings ───────────────────────────────────────

  const mainCrossValidation: ComputedRef<string | null> = computed(() => {
    const mainSubtotal = sections.value[0]?.subtotalRow
    if (!mainSubtotal) return null
    const d4_2_resp = allResponses.value.get('D4-2-rows')
    if (!d4_2_resp?.remark) return null
    const d4_2_rows = safeParseRows<any>(d4_2_resp.remark)
    if (d4_2_rows.length === 0) return null

    let d4_2_total = 0
    for (const row of d4_2_rows) {
      const months = Array.isArray(row.months) ? row.months.map(parseNum) : []
      const periodTotal = months.reduce((s: number, v: number) => s + v, 0)
      d4_2_total += periodTotal + parseNum(row.auditAdjustment)
    }

    const diff = mainSubtotal.currentAudited - d4_2_total
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `D4-1主营小计(${mainSubtotal.currentAudited.toFixed(2)}) 与 D4-2合计(${d4_2_total.toFixed(2)}) 差异${diff.toFixed(2)}`
    }
    return null
  })

  const otherCrossValidation: ComputedRef<string | null> = computed(() => {
    const otherSubtotal = sections.value[1]?.subtotalRow
    if (!otherSubtotal) return null
    const d4_3_resp = allResponses.value.get('D4-3-rows')
    if (!d4_3_resp?.remark) return null
    const d4_3_rows = safeParseRows<any>(d4_3_resp.remark)
    if (d4_3_rows.length === 0) return null

    let d4_3_total = 0
    for (const row of d4_3_rows) {
      d4_3_total += parseNum(row.currentUnadjusted) + parseNum(row.currentAdjustment)
    }

    const diff = otherSubtotal.currentAudited - d4_3_total
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `D4-1其他小计(${otherSubtotal.currentAudited.toFixed(2)}) 与 D4-3合计(${d4_3_total.toFixed(2)}) 差异${diff.toFixed(2)}`
    }
    return null
  })

  // ─── Cell update ─────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number): void {
    if (readonly.value) return
    persistFieldValue(rowKey, field, value)
  }

  // ─── EventBus: publishAdjudicated ────────────────────────────────────

  function publishAdjudicated(): void {
    const mainSub = sections.value[0]?.subtotalRow
    const otherSub = sections.value[1]?.subtotalRow

    const payload = {
      wpCode: 'D4',
      accountCode: '6001,6051',
      auditedAmount: {
        main: mainSub?.currentAudited ?? 0,
        other: otherSub?.currentAudited ?? 0,
      },
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* silent */ }

    // Writeback TB
    if (projectId.value) {
      try {
        window.dispatchEvent(new CustomEvent('d4:writeback-trial-balance', {
          detail: {
            projectId: projectId.value,
            accountCode: D4_MAIN_REVENUE_STANDARD,
            auditedAmount: mainSub?.currentAudited ?? 0,
          },
        }))
        window.dispatchEvent(new CustomEvent('d4:writeback-trial-balance', {
          detail: {
            projectId: projectId.value,
            accountCode: D4_OTHER_REVENUE_STANDARD,
            auditedAmount: otherSub?.currentAudited ?? 0,
          },
        }))
      } catch { /* silent */ }
    }
  }

  // ─── EventBus: onAdjustmentCreated ───────────────────────────────────

  function onAdjustmentCreated(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'D4') return
    // AJE/RJE changes auto-reflected via adjustmentTotals computed
  }

  // ─── Watch audit note/conclusion ─────────────────────────────────────

  watch(
    () => allResponses.value.get('D4-1-adj-note')?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get('D4-1-adj-conclusion')?.remark,
    (val) => { auditConclusion.value = val || '' },
    { immediate: true },
  )

  watch(auditNote, (val) => {
    allResponses.value.set('D4-1-adj-note', { item_id: 'D4-1-adj-note', conclusion: null, remark: val } as any)
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    allResponses.value.set('D4-1-adj-conclusion', { item_id: 'D4-1-adj-conclusion', conclusion: null, remark: val } as any)
    debounceSave()
  })

  // ─── EventBus Registration ───────────────────────────────────────────

  const adjustmentHandler = (e: Event) => onAdjustmentCreated(e)
  window.addEventListener('adjustment:created', adjustmentHandler)
  eventListeners.push({ event: 'adjustment:created', handler: adjustmentHandler })

  // ─── Debounce / Save ─────────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const items = [
        allResponses.value.get(rowsItemId(D4_ADJ_ROWS_SPEC)),
        allResponses.value.get('D4-1-adj-note'),
        allResponses.value.get('D4-1-adj-conclusion'),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Backward-compat wrappers (旧 API，供 D4TabAdjudication.vue 过渡用) ───

  /** @deprecated 使用 `addRow(label, sectionKey)` 替代 */
  function addProductRow(): void {
    addRow('', 'main-revenue')
  }

  /** @deprecated 使用 `removeRow(rowId)` 替代 */
  function removeProductRow(rowKey: string): void {
    removeRow(rowKey)
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    // Dynamic rows (new API)
    dynamicRows,
    hasPrefillData,
    seedFromPrefill,
    previewSeedFromPrefill,
    addRow,
    removeRow,
    renameRow,

    // Backward-compat (旧 API)
    addProductRow,
    removeProductRow,

    // Sections / totals
    sections,
    grandTotalRow,
    trialBalanceRow,
    differenceRow,

    // Cross validation
    mainCrossValidation,
    otherCrossValidation,

    // Audit note
    auditNote,
    auditConclusion,

    // Operations
    updateCell,
    publishAdjudicated,
  }
}

// ─── Internal helper ─────────────────────────────────────────────────────────

/** 从 `{prefix}-{rowId}-{field}` 中提取 rowId */
function extractRowIdFromItemId(itemId: string): string {
  // 格式: D4-1-{rowId}-{field}
  const prefix = `${D4_ADJ_PREFIX}-`
  if (!itemId.startsWith(prefix)) return ''
  const rest = itemId.slice(prefix.length)
  const lastDash = rest.lastIndexOf('-')
  return lastDash > 0 ? rest.slice(0, lastDash) : rest
}

export default useD4Adjudication
