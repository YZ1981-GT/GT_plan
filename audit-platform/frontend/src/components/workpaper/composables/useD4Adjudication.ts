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
import { ElMessage, ElMessageBox } from 'element-plus'
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
  readRowFieldWithFallback,
  resolveCellState,
  displayValueForCellState,
  normalizeLabel,
  labelKey,
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
  /**
   * 选项 b 逐格覆盖态（Task 14）：仅派生行（isFromCrossSheet）有值。key = 6 金额字段名，
   * value = 该格四态 + 三值（供 UI 标「已人工覆盖」/S4 冲突呈现/恢复取数）。
   * 无覆盖（全 S1）时为 undefined，普通行不产生。
   */
  cellOverrides?: Record<
    string,
    { state: 'S1' | 'S2' | 'S3' | 'S4'; stored: number; snap: number; derived: number }
  >
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

  /** 派生快照的 per-field item 键（选项 b 覆盖状态机的 `snap`，Task 12 写入 / 本处读出）。 */
  function snapItemId(rowId: string, field: string): string {
    return `${rowFieldItemId(D4_ADJ_ROWS_SPEC, rowId, field)}-snap`
  }

  /**
   * 序列化 D4-1-rows 用的读取器（Task 8/10 双写）：
   * - `readField`：读**该字段的 per-field item 当前值**（不走 getRowFieldValue，避免与
   *   「行对象值优先」的读侧循环依赖 —— 行对象金额本就是 per-field 的同步快照）；
   * - `readDerivedSnapshot`：读派生行的 `snap`（Task 12 落在 `{rowId}-{field}-snap`），
   *   缺则不落 derivedSnapshot 键。
   */
  const rowListReader = {
    readField: (rowId: string, field: string): number | null => {
      const raw = readRaw(allResponses.value as Map<string, unknown>, rowFieldItemId(D4_ADJ_ROWS_SPEC, rowId, field))
      if (raw === '') return null
      const n = Number(raw)
      return Number.isFinite(n) ? n : null
    },
    readDerivedSnapshot: (rowId: string): Record<string, number | null> | null => {
      const snap: Record<string, number | null> = {}
      let has = false
      for (const field of D4_ADJ_ROWS_SPEC.valueFields) {
        const raw = readRaw(allResponses.value as Map<string, unknown>, snapItemId(rowId, field))
        if (raw === '') continue
        const n = Number(raw)
        snap[field] = Number.isFinite(n) ? n : null
        has = true
      }
      return has ? snap : null
    },
  }

  function persistRowList(rows: DynamicAdjRow[]): void {
    const itemId = rowsItemId(D4_ADJ_ROWS_SPEC)
    // 🔴 双写（Task 10 / 裁决 D3）：行清单同时携带金额（行对象顶层）+ 派生行的 derivedSnapshot。
    //    行对象金额是 per-field item 的同步快照——读侧（getRowFieldValue）行对象优先、缺则
    //    回落 per-field，故双写期任一路径都读得到正确值；回滚只需改读侧优先级、无需回填数据。
    const json = serializeRows(rows, { spec: D4_ADJ_ROWS_SPEC, reader: rowListReader })
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: json } as any)
    debounceSave()
  }

  function persistFieldValue(rowId: string, field: string, value: string | number): void {
    const itemId = rowFieldItemId(D4_ADJ_ROWS_SPEC, rowId, field)
    const strVal = String(value ?? 0)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: strVal } as any)
    // 🔴 per-field 落库后**同步重写行清单**，把新值刷进行对象顶层（双写）。否则行对象金额
    //    停在旧快照、而读侧行对象优先 ⇒ 用户改的数被自己的旧行对象值盖住。
    persistRowList(dynamicRows.value)
    debounceSave()
  }

  // ─── Read field value from responses ─────────────────────────────────

  function getRowFieldValue(rowId: string, field: string): number {
    // 🔴 单源读（Task 9）：行对象顶层值优先、缺则回落 per-field item。
    //    D4-1-rows 的行对象自 Task 8 起可携带金额（也是 OO 回写的落点），必须优先于旧
    //    per-field 值，否则 OO 侧改的数会被旧 per-field 盖住（缺陷 A2 反向翻版）。
    //    旧项目金额仍只在 per-field，由 readRowFieldWithFallback 回落，不归零（需求 4.2）。
    const row = dynamicRows.value.find((r) => r.rowId === rowId) ?? null
    return readRowFieldWithFallback(
      row,
      allResponses.value as Map<string, unknown>,
      D4_ADJ_ROWS_SPEC,
      field,
    )
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

    // appendManualRow 需要 label（既有调用漏传，wave 3 收紧 DynamicAdjRow 类型后暴露）。
    // 直接传 normalized（一步到位）；下面的 map 保留作幂等兜底，行为不变。
    const { rows, row } = appendManualRow(dynamicRows.value, normalized)
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

  // ─── CrossSheet 派生行（D4-2/D4-3 明细行 → D4-1 审定行，computed 派生） ───
  //
  // 🔴 修复 d4:sync-row 死代码（spec d4-price-analysis-writeback-linkage / Req 1）：
  // 原实现靠 useD4CrossSheet 发 `d4:sync-row` CustomEvent 同步行结构，但**无接收端**。
  // 参照 D2 范式（useD2CrossSheet 的 computed 派生链，非行同步事件）：D4-1 审定表的
  // 主营/其他产品行改为 **computed 派生自 mainRevenueByProduct/otherRevenueByItem**
  // （二者读 D4-2-rows/D4-3-rows），D4-2 增删产品行 → 下一次 computed 重算即联动。
  //
  // 派生行 rowKey 用稳定归一键 `xsheet-{section}-{labelKey}`（不用 label 防撞键）；
  // isFromCrossSheet=true（金额列只读、浅蓝背景）；AJE/RJE 仍从 per-field 键读，
  // 键以稳定 rowKey 为组成部分 → 审计师对派生行填的调整不丢。

  /**
   * 派生行：从上游明细聚合生成 isFromCrossSheet 行（供 sections 合并）。
   *
   * 派生行未审数 = 上游明细逐产品/项目聚合值（只读，UI 按 isFromCrossSheet 门控为只读）。
   * 派生行的 AJE/RJE 恒 0：D4-1 编制约定「浅蓝跨表行不可手工编辑」，审计调整统一走
   * D4-4 调整分录 → adjustmentTotals → 小计 AJE/RJE 列（非逐行手填）。
   * rowKey 用稳定归一键（不用 label 防撞键；同名产品折叠为一行）。
   */
  /**
   * 派生格逐格覆盖解析（Task 14 / 选项 b）：给定派生行 rowId + 字段 + 派生值，读 store 的
   * stored/snap，按四态返回**显示值** + 覆盖元信息。S1/S3 显示派生值（跟随上游），
   * S2/S4 显示 stored（人工覆盖值）。无覆盖（S1/S3）不产生 cellOverrides 条目。
   */
  function _resolveDerivedCell(
    rowId: string,
    field: string,
    derivedValue: number,
  ): { display: number; override?: { state: 'S1' | 'S2' | 'S3' | 'S4'; stored: number; snap: number; derived: number } } {
    const storedRaw = readRaw(allResponses.value as Map<string, unknown>, rowFieldItemId(D4_ADJ_ROWS_SPEC, rowId, field))
    const snapRaw = readRaw(allResponses.value as Map<string, unknown>, snapItemId(rowId, field))
    const stored = storedRaw === '' ? null : Number(storedRaw)
    const snap = snapRaw === '' ? null : Number(snapRaw)
    const state = resolveCellState(stored, snap, derivedValue)
    const display = displayValueForCellState(state, stored, derivedValue)
    if (state === 'S2' || state === 'S4') {
      return {
        display,
        override: { state, stored: stored ?? 0, snap: snap ?? 0, derived: derivedValue },
      }
    }
    return { display }
  }

  function buildCrossSheetRow(
    section: 'main' | 'other',
    label: string,
    agg: { current: number; prior: number },
  ): AdjudicationRow {
    const rowKey = `xsheet-${section}-${labelKey(label)}`
    // 🔴 逐格覆盖（Task 14）：currentUnadjusted / priorUnadjusted 两个派生字段按四态定显示值——
    //    S1/S3 用上游派生值，S2/S4 用 OO 侧人工覆盖值（选项 b）。AJE/RJE 派生恒 0（Task 16 处理）。
    const curCell = _resolveDerivedCell(rowKey, 'currentUnadjusted', agg.current)
    const priorCell = _resolveDerivedCell(rowKey, 'priorUnadjusted', agg.prior)
    const cellOverrides: Record<
      string,
      { state: 'S1' | 'S2' | 'S3' | 'S4'; stored: number; snap: number; derived: number }
    > = {}
    if (curCell.override) cellOverrides.currentUnadjusted = curCell.override
    if (priorCell.override) cellOverrides.priorUnadjusted = priorCell.override
    const hasOverride = Object.keys(cellOverrides).length > 0
    // 🔴 Task 16 清死代码：派生行 AJE/RJE 此前硬编码 0，而上方注释声称「仍从 per-field 键读
    //    ⇒ 审计师对派生行填的调整不丢」——注释描述的行为并不存在。改为走单源读
    //    （getRowFieldValue：行对象优先、缺回落 per-field），使注释成真：派生行的未审数来自
    //    上游聚合（curCell/priorCell），而 AJE/RJE 若审计师在 OO/D4-1 填过则读回、不被抹 0。
    const currentAje = getRowFieldValue(rowKey, 'currentAje')
    const currentRje = getRowFieldValue(rowKey, 'currentRje')
    const priorAje = getRowFieldValue(rowKey, 'priorAje')
    const priorRje = getRowFieldValue(rowKey, 'priorRje')
    return {
      rowKey,
      label,
      isFixed: false,
      currentUnadjusted: curCell.display,
      currentAje,
      currentRje,
      currentAudited: calcAuditedAmount(curCell.display, currentAje, currentRje),
      priorUnadjusted: priorCell.display,
      priorAje,
      priorRje,
      priorAudited: calcAuditedAmount(priorCell.display, priorAje, priorRje),
      isFromCrossSheet: true,
      isEditable: false, // 未审数只读（来自上游聚合）；AJE/RJE 由 OO/D4-4 调整，读回不抹 0
      ...(hasOverride ? { cellOverrides } : {}),
    }
  }

  const crossSheetMainRows = computed<AdjudicationRow[]>(() =>
    Object.entries(mainRevenueByProduct.value).map(([product, agg]) =>
      buildCrossSheetRow('main', product, agg),
    ),
  )

  const crossSheetOtherRows = computed<AdjudicationRow[]>(() =>
    Object.entries(otherRevenueByItem.value).map(([item, agg]) =>
      buildCrossSheetRow('other', item, agg),
    ),
  )

  // ─── 派生行落库（Task 12：缺陷 B —— 派生行不进 store ⇒ 切 OO 恒空）─────────────
  //
  // 缺陷 B：主营/其他两区显示的行主体是 crossSheet 派生行（computed，从不进 dynamicRows、
  // 从不落 D4-1-rows）⇒ store-projection 两区贡献 0 行、overlay 退回模板占位空行 ⇒ OO 空表。
  // 本函数把派生行 upsert 进 store（source='tb'），并写 derivedSnapshot（选项 b 状态机的 snap）。
  //
  // 🔴 不放在 flushHtml 里：flushHtml 是「切 OO」路径，在那里第一次落库会让"切一次 OO 就改
  //    一次内容版本"、把只读浏览变成写操作、并让复用命中类判据失稳（design 裁决 D4）。
  //    改为 watch 派生源变化时同步：幂等（值未变不写）、source 恒 'tb'、带 sectionKey。
  //
  // snap 写在 per-field item `{rowId}-{field}-snap`（rowListReader.readDerivedSnapshot 读它，
  // 序列化时落进行对象 derivedSnapshot）。stored（per-field 主值）也同步写成派生值——
  // 纯派生态 S1 下 stored==snap==derived，Task 13 据此判 S1。

  const SECTION_ACCOUNT_CODE = {
    main: D4_MAIN_REVENUE_STANDARD,
    other: D4_OTHER_REVENUE_STANDARD,
  } as const

  function _writeIfChanged(itemId: string, value: number): boolean {
    const cur = readRaw(allResponses.value as Map<string, unknown>, itemId)
    const next = String(value)
    if (cur === next) return false // 幂等：值未变不写
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: next } as any)
    return true
  }

  /**
   * 派生行某格的**纯派生值**（上游现算聚合值），**不是**显示值。
   *
   * 🔴 `row[field]` 是 `_resolveDerivedCell` 算出的**显示值**，覆盖态（S2/S4）下它等于
   *    `stored`。两处调用方各有各的理由必须区分二者：
   *
   *    * `restoreDerivedValue`（可达分支）：恢复取数要把该格写回**派生值**。若取显示值，
   *      写回去的就是覆盖值本身 —— 恢复变成空操作，store 里当场留着错值（此刻若发生
   *      flushSave / 切 OO，错值直接落库）。判据 P15「当场写对，不靠下一 tick 自愈」。
   *    * `syncDerivedRowsIntoStore`（当前恒走 else 分支）：那里只在 `!overridden` 时写，
   *      而 `overridden ⟺ stored≠snap ⟺ S2/S4 ⟺ cellOverrides 有条目`，故该处 `cell`
   *      恒为 undefined。保留这层区分是为了不把「写回 store 的值必须是派生值」这条约束
   *      交给调用点的时序去保证 —— 那条约束一旦被时序兜住，改动顺序就会静默破坏它。
   */
  function _pureDerived(
    row: AdjudicationRow,
    field: 'currentUnadjusted' | 'priorUnadjusted',
  ): number {
    const cell = row.cellOverrides?.[field]
    return cell ? cell.derived : row[field]
  }

  /** 该 store 行是否被人工覆盖过（任一派生字段 stored ≠ snap）——覆盖过的派生行不作孤儿清理。 */
  function _derivedRowHasOverride(rid: string): boolean {
    for (const field of D4_ADJ_ROWS_SPEC.valueFields) {
      const storedRaw = readRaw(allResponses.value as Map<string, unknown>, rowFieldItemId(D4_ADJ_ROWS_SPEC, rid, field))
      const snapRaw = readRaw(allResponses.value as Map<string, unknown>, snapItemId(rid, field))
      if (storedRaw === '' || snapRaw === '') continue
      if (Math.abs(Number(storedRaw) - Number(snapRaw)) > BALANCE_TOLERANCE) return true
    }
    return false
  }

  function syncDerivedRowsIntoStore(): void {
    if (readonly.value) return
    const derived: Array<{ section: 'main' | 'other'; row: AdjudicationRow }> = [
      ...crossSheetMainRows.value.map((row) => ({ section: 'main' as const, row })),
      ...crossSheetOtherRows.value.map((row) => ({ section: 'other' as const, row })),
    ]
    let rowListDirty = false
    let anyWrite = false

    // 🔴 孤儿派生行清理（Task 12 回归修复）：上游 D4-2/D4-3 删产品后，之前 upsert 进 store 的
    //    派生行成了孤儿——它以 source='tb'/isFromCrossSheet 混进 sections（重复行）。
    //    规则：当前派生集里不存在、且 source==='tb' 的 store 行，若**无人工覆盖**（stored==snap）
    //    则删除（跟随上游消失）；若被人工覆盖过则**保留**（用户改过的数不静默丢，选项 b 语义）。
    const liveDerivedIds = new Set(derived.map((d) => d.row.rowKey))
    const orphans = dynamicRows.value.filter(
      (d) => d.source === 'tb' && !liveDerivedIds.has(d.rowId) && !_derivedRowHasOverride(d.rowId),
    )
    if (orphans.length > 0) {
      const orphanIds = new Set(orphans.map((o) => o.rowId))
      dynamicRows.value = dynamicRows.value.filter((d) => !orphanIds.has(d.rowId))
      // 清掉孤儿的 per-field(stored) + snap item（避免残留脏值）。
      for (const o of orphans) {
        for (const field of D4_ADJ_ROWS_SPEC.valueFields) {
          allResponses.value.delete(rowFieldItemId(D4_ADJ_ROWS_SPEC, o.rowId, field))
          allResponses.value.delete(snapItemId(o.rowId, field))
        }
      }
      rowListDirty = true
    }

    for (const { section, row } of derived) {
      const rid = row.rowKey // 派生 rowKey = xsheet-{section}-{labelKey}，直接作 store rowId
      // 1) upsert 行清单：不存在则加一条 source='tb' 派生行（带 sectionKey + accountCode）。
      let def = dynamicRows.value.find((d) => d.rowId === rid)
      if (!def) {
        def = {
          rowId: rid,
          label: row.label,
          source: 'tb',
          accountCode: SECTION_ACCOUNT_CODE[section],
        }
        ;(def as any).sectionKey = section === 'main' ? 'main-revenue' : 'other-revenue'
        dynamicRows.value = [...dynamicRows.value, def]
        rowListDirty = true
      } else if (def.label !== row.label || def.source !== 'tb') {
        // 派生 label 变了（上游改名）或 source 漂移 → 校正（仍是派生行）。
        def.label = row.label
        def.source = 'tb'
        rowListDirty = true
      }
      // 2) 幂等写派生的两个金额（currentUnadjusted / priorUnadjusted）到 per-field(stored) + snap。
      //    AJE/RJE 派生恒 0，不主动写（避免把用户在 OO 侧填的 AJE/RJE 覆盖成 0；Task 16 收口）。
      const derivedPairs: Array<['currentUnadjusted' | 'priorUnadjusted', number]> = [
        ['currentUnadjusted', _pureDerived(row, 'currentUnadjusted')],
        ['priorUnadjusted', _pureDerived(row, 'priorUnadjusted')],
      ]
      for (const [field, value] of derivedPairs) {
        // 判定是否已被人工覆盖：stored ≠ snap（选项 b 状态机，见 Task 13）。
        const storedRaw = readRaw(allResponses.value as Map<string, unknown>, rowFieldItemId(D4_ADJ_ROWS_SPEC, rid, field))
        const snapRaw = readRaw(allResponses.value as Map<string, unknown>, snapItemId(rid, field))
        const stored = storedRaw === '' ? null : Number(storedRaw)
        const snap = snapRaw === '' ? null : Number(snapRaw)
        const overridden =
          stored != null && snap != null && Math.abs(stored - snap) > BALANCE_TOLERANCE
        // 🔴 snap 与 stored 都**只在未被人工覆盖时**跟随派生值（S1 纯派生 / S3 自动跟随）。
        //    snap 若无条件跟随，被覆盖的格在上游一变时 snap 立刻追上 derived ⇒ `snap ≠ derived`
        //    永不成立 ⇒ **S4 不可达**，需求 6.4 要求的「同时呈现覆盖值 / 原派生值 / 现派生值」
        //    就丢了中间那一个（被覆盖时的原派生值）。覆盖态下 snap 必须冻结在覆盖发生时的
        //    派生值上，它正是 S4 要展示的「原派生值」。判据 P14（snap 冻结那条）。
        if (!overridden) {
          if (_writeIfChanged(snapItemId(rid, field), value)) anyWrite = true
          if (_writeIfChanged(rowFieldItemId(D4_ADJ_ROWS_SPEC, rid, field), value)) anyWrite = true
        }
      }
    }

    if (rowListDirty || anyWrite) {
      // 行清单重写（会把 stored + derivedSnapshot 一并刷进行对象，见 persistRowList/rowListReader）。
      persistRowList(dynamicRows.value)
    }
  }

  /**
   * 恢复取数（Task 15 / 需求 6.5）：把某派生格从覆盖态退回 S1（纯派生）。
   * 只影响被点的那一格：stored ← derived、snap ← derived（用当前派生值）。下次物化
   * （syncDerivedRowsIntoStore 幂等）会保持它跟随上游，等价"写回派生值"。
   */
  function restoreDerivedValue(rowId: string, field: string): void {
    if (readonly.value) return
    // 当前派生值 = crossSheet computed 里该行该字段的聚合值。
    const derivedRow =
      crossSheetMainRows.value.find((r) => r.rowKey === rowId) ??
      crossSheetOtherRows.value.find((r) => r.rowKey === rowId)
    if (!derivedRow) return
    // 🔴 必须取**纯派生值**：`derivedRow[field]` 是显示值，覆盖态下等于 stored ——
    //    用它"恢复"等于把覆盖值又写回去一遍（恢复取数变成空操作）。见 `_pureDerived` 注释。
    const derivedVal =
      field === 'currentUnadjusted' || field === 'priorUnadjusted'
        ? _pureDerived(derivedRow, field)
        : 0
    _writeIfChanged(rowFieldItemId(D4_ADJ_ROWS_SPEC, rowId, field), derivedVal)
    _writeIfChanged(snapItemId(rowId, field), derivedVal)
    persistRowList(dynamicRows.value)
  }

  // watch 派生源：D4-2/D4-3 变化 → 派生行重算 → 同步进 store。immediate 让首次挂载即落库。
  watch(
    [crossSheetMainRows, crossSheetOtherRows],
    () => { syncDerivedRowsIntoStore() },
    { immediate: true, deep: true },
  )

  // ─── Sections computed (combining crossSheet 派生行 + dynamic 手工行) ─────────

  const sections: ComputedRef<AdjudicationSection[]> = computed(() => {
    const rows = dynamicRows.value

    // 1) 先放上游派生行（isFromCrossSheet），并登记已占用的 labelKey（派生优先，Req 1.6）
    const mainRows: AdjudicationRow[] = [...crossSheetMainRows.value]
    const otherRows: AdjudicationRow[] = [...crossSheetOtherRows.value]
    const mainSeen = new Set(mainRows.map(r => labelKey(r.label)))
    const otherSeen = new Set(otherRows.map(r => labelKey(r.label)))

    // 2) 再放手工/历史动态行。
    // 🔴 跳过 source==='tb' 行：派生行的**显示**权威是 crossSheet computed（实时随上游增减），
    //    dynamicRows 里的 tb 副本仅为**落库**（Task 12 syncDerivedRowsIntoStore 写入，供出方向
    //    projection）。若把 tb 副本也渲染，上游删产品后 watch 异步清理孤儿前会短暂重复
    //    （d4AdjudicationRowLinkage 实测）。覆盖态的显示由 Task 14 在 crossSheet 行上逐格合并。
    for (const r of rows) {
      if (r.source === 'tb') continue
      const code = r.accountCode || ''
      const isOther = isOtherRevenueCode(code)
      const lk = labelKey(r.label)
      if (isOther ? otherSeen.has(lk) : mainSeen.has(lk)) continue

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
        // 此处只剩 manual/legacy 手工行（source==='tb' 已在上面 continue 跳过，显示走 crossSheet）。
        isFromCrossSheet: false,
        isEditable: true,
        _dynamicRow: r,
      }

      if (isOther) {
        otherRows.push(adjRow)
        otherSeen.add(lk)
      } else {
        // 默认归入主营（无科目码的手工行也归主营）
        mainRows.push(adjRow)
        mainSeen.add(lk)
      }
    }

    const mainSubtotal: AdjudicationRow = buildSubtotalRow('main-subtotal', '主营业务收入小计', mainRows)
    const otherSubtotal: AdjudicationRow = buildSubtotalRow('other-subtotal', '其他业务收入小计', otherRows)

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
  ): AdjudicationRow {
    // 🔴 Task 16：本期 AJE/RJE 小计改**逐行汇总**（与模板 C12=SUM(C8:C11) / D12=SUM 同口径，
    //    也与上期 AJE/RJE 小计的逐行汇总口径一致）。此前本期取 D4-4 汇总额（adjTotals），与
    //    Excel 公式口径不同 ⇒ 两侧小计可能不等且无告警。逐行 vs D4-4 的差异改由 crossValidation
    //    显式告警（不静默盖掉任一侧，D4-4 仍是调整分录权威源）。
    const currentUnadj = calcSubtotal(rows.map(r => r.currentUnadjusted))
    const priorUnadj = calcSubtotal(rows.map(r => r.priorUnadjusted))
    const currentAje = calcSubtotal(rows.map(r => r.currentAje))
    const currentRje = calcSubtotal(rows.map(r => r.currentRje))
    const priorAje = calcSubtotal(rows.map(r => r.priorAje))
    const priorRje = calcSubtotal(rows.map(r => r.priorRje))
    return {
      rowKey,
      label,
      isFixed: true,
      currentUnadjusted: currentUnadj,
      currentAje,
      currentRje,
      currentAudited: calcAuditedAmount(currentUnadj, currentAje, currentRje),
      priorUnadjusted: priorUnadj,
      priorAje,
      priorRje,
      priorAudited: calcAuditedAmount(priorUnadj, priorAje, priorRje),
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

  // ─── D4-4 校验告警（Task 16 / 需求 7.2）───────────────────────────────
  //
  // 🔴 与 mainCrossValidation/otherCrossValidation **同构范式**（computed 返回提示串、超容差
  //    才亮、指明差异、不改任一侧、不阻塞），不另造校验机制。小计本期 AJE/RJE 现改为**逐行汇总**
  //    （与模板 C12=SUM 同口径），而 D4-4 是调整分录权威源；两者不等本身是审计师需要知道的事实
  //    （由他调平），不由系统盖掉。「D4-1 小计恒等于 D4-4」若为审计要求，由审计师依本告警调平。
  const adjustmentTotalsValidation: ComputedRef<string | null> = computed(() => {
    const secs = sections.value
    const mainSub = secs[0]?.subtotalRow
    const otherSub = secs[1]?.subtotalRow
    if (!mainSub || !otherSub) return null
    const t = adjustmentTotals.value
    const msgs: string[] = []
    const rowSumMainAdj = mainSub.currentAje + mainSub.currentRje
    const d44MainAdj = t.mainAje + t.mainRje
    if (Math.abs(rowSumMainAdj - d44MainAdj) > BALANCE_TOLERANCE) {
      msgs.push(
        `主营逐行调整合计(${rowSumMainAdj.toFixed(2)}) 与 D4-4调整分录(${d44MainAdj.toFixed(2)}) ` +
        `差异${(rowSumMainAdj - d44MainAdj).toFixed(2)}`,
      )
    }
    const rowSumOtherAdj = otherSub.currentAje + otherSub.currentRje
    const d44OtherAdj = t.otherAje + t.otherRje
    if (Math.abs(rowSumOtherAdj - d44OtherAdj) > BALANCE_TOLERANCE) {
      msgs.push(
        `其他逐行调整合计(${rowSumOtherAdj.toFixed(2)}) 与 D4-4调整分录(${d44OtherAdj.toFixed(2)}) ` +
        `差异${(rowSumOtherAdj - d44OtherAdj).toFixed(2)}`,
      )
    }
    return msgs.length > 0 ? msgs.join('；') : null
  })

  // ─── Cell update ─────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number): void {
    if (readonly.value) return
    persistFieldValue(rowKey, field, value)
  }

  // ─── EventBus: publishAdjudicated ────────────────────────────────────

  const publishing = ref(false)

  /**
   * 确认审定 → 发布审定数到试算表（P0-项3：显式确认门）。
   *
   * 🔴 修复情形B（AC-3.4）：D4-1 用 d4-operating-revenue 组件渲染（非 GtAuditSheet），
   * 此前 publishAdjudicated 只 dispatch `d4:writeback-trial-balance` → 经
   * `PUT /projects/{pid}/trial-balance/writeback` 直写 audited_amount，**绕过** P0-项3 的
   * `publish_confirmed` 显式确认门（门只接在 GtAuditSheet）。现改为与 GtAuditSheet 同范式：
   * 二次确认（中文）→ `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （携带审定表 sheet 名 + audit_rows），后端计算审定数、校验发布权限、发 `publish_confirmed=True`
   * + token → 回写 handler 幂等回写 trial_balance。普通保存对 TB 仍是 no-op。
   *
   * audit_rows 口径：主营小计→6001、其他小计→6051；每行 current_unadjusted/adj_amount(AJE)/
   * reclass_amount(RJE) 取自 sections 小计行，后端 audited = 三者之和（与前端 calcAuditedAmount 一致）。
   */
  async function publishAdjudicated(): Promise<void> {
    if (readonly.value || publishing.value) return

    const mainSub = sections.value[0]?.subtotalRow
    const otherSub = sections.value[1]?.subtotalRow

    // 二次确认（中文，危险操作提示）
    try {
      await ElMessageBox.confirm(
        '发布后将把营业收入审定数（主营 6001 / 其他 6051）写入试算表（trial_balance），'
        + '并触发报表/错报评价等下游重算。确认发布？',
        '发布到试算表确认',
        {
          confirmButtonText: '确认发布',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch {
      return // 用户取消
    }

    if (!wpId.value) {
      ElMessage.error('缺少底稿标识，无法发布')
      return
    }

    // 构造 audit_rows（主营小计→6001，其他小计→6051）
    const auditRows = [
      {
        id: 'D4-1-6001',
        account_code: D4_MAIN_REVENUE_STANDARD,
        current_unadjusted: mainSub?.currentUnadjusted ?? 0,
        adj_amount: mainSub?.currentAje ?? 0,
        reclass_amount: mainSub?.currentRje ?? 0,
      },
      {
        id: 'D4-1-6051',
        account_code: D4_OTHER_REVENUE_STANDARD,
        current_unadjusted: otherSub?.currentUnadjusted ?? 0,
        adj_amount: otherSub?.currentAje ?? 0,
        reclass_amount: otherSub?.currentRje ?? 0,
      },
    ]

    publishing.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const resp: any = await api.post(
        `/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`,
        {
          // sheet 名固定含审定表子码 D4-1，后端 extract_determination_wp_code 据此解出 D4-1
          sheet_name: '审定表D4-1',
          html_data: { audit_rows: auditRows },
        },
      )
      ElMessage.success(resp?.message || '已发布到试算表')

      // 发布成功 → 通知下游附注/检查表刷新（TB 回写已由后端确认门完成）
      try {
        window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
          detail: {
            wpCode: 'D4',
            accountCode: '6001,6051',
            auditedAmount: {
              main: mainSub?.currentAudited ?? 0,
              other: otherSub?.currentAudited ?? 0,
            },
          },
        }))
      } catch { /* silent */ }
    } catch (err: any) {
      const status = err?.response?.status
      if (status === 403) {
        ElMessage.error('无发布权限（需底稿编辑权）')
      } else if (status === 423) {
        ElMessage.error('项目已被合并锁定，无法发布')
      } else if (status === 400) {
        ElMessage.error(err?.response?.data?.detail || err?.response?.data?.message || '当前审定表无可发布的审定数')
      } else {
        ElMessage.error('发布失败，请稍后重试')
      }
    } finally {
      publishing.value = false
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
    adjustmentTotalsValidation,

    // Audit note
    auditNote,
    auditConclusion,

    // Operations
    updateCell,
    restoreDerivedValue,
    publishAdjudicated,
    publishing,

    // Sync bridge 接桥用：flush 待存改动（先于 readStoreProjection 读投影，防投影旧值）。
    // 别名内部 flushSave（走 `d4:save-items` 事件由宿主 formData 落库）。
    flushPendingSave: flushSave,
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
