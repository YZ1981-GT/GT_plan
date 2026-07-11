/**
 * useD2Detail — 明细表D2-2核心逻辑 composable (动态账龄版)
 *
 * Spec: .kiro/specs/aging-config-enhancement/
 * Task: 7.1
 *
 * 职责：
 * - DetailRow 类型定义（核心字段 + nested keyed 账龄: agingPrior/agingCurrent/agingAudited）
 * - rows reactive（从 D2-detail-rows remark JSON加载）
 * - 加载时自动检测旧 flat 格式，调用 migrateD2FlatToNested 迁移
 * - 保存时调用 stripLegacyFlatKeys 确保仅 nested 格式
 * - totalRow computed（SUM全部行各金额列 + 动态账龄段）
 * - searchQuery + filteredRows computed（模糊搜索客户名称）
 * - addRow / removeRow 动态行管理
 * - matchRelatedParty（关联方自动匹配）
 * - 行公式链自动计算（priorAudited/endBalance/currentUnadjusted/currentAudited）
 * - updateCell（编辑→公式重算→关联方匹配→debounce保存）
 * - useVirtualScroll computed（rows.length > 30 启用）
 * - 监听 aging-config:changed 事件，保留已有段数据/零初始化新增段
 * - 序列化/反序列化（JSON.stringify rows → D2-detail-rows remark字段）
 *
 * Requirements: 4.1, 4.2, 4.3, 4.5, 10.2, 10.3, 10.4
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  getAuditedAmount,
} from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'
import { useAgingConfig, createEmptyAgingData, type AgingSegment } from '@/composables/useAgingConfig'
import {
  isLegacyD2Format,
  migrateD2FlatToNested,
  stripLegacyFlatKeys,
  remapRowAgingData,
  type AgingData,
} from '@/composables/useAgingMigration'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  seq: number                    // 序号
  customerName: string           // 客户名称
  companyCode: string            // 公司代码
  relationType: string           // 关联方类型(非关联方/控股股东/实际控制人/其他关联方)
  // 期初(4列)
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number           // 自动计算 = priorUnadjusted + priorAje + priorRje
  // 期初审定账龄 (nested keyed)
  agingPrior: AgingData
  // 本期发生
  debitOccurrence: number        // 借方发生
  creditOccurrence: number       // 贷方发生
  endBalance: number             // 期末余额 = 期初审定 + 借方 - 贷方
  reclassification: number       // 被审计单位重分类
  currentUnadjusted: number      // 期末未审 = 期末余额 + 重分类
  // 期末未审账龄 (nested keyed)
  agingCurrent: AgingData
  // 调整
  currentAje: number             // 账项调整(Z列)
  currentRje: number             // 重分类调整(AA列)
  currentAudited: number         // 期末审定 = 期末未审 + AJE + RJE
  // 期末审定账龄 (nested keyed)
  agingAudited: AgingData
  // 分类与标记
  creditRiskClassification: string  // 信用风险组合方式(AI列): 单项计提/账龄组合/客户类型组合
  groupName: string              // 组合名称(AJ列)
  isConfirmation: boolean        // 是否函证
  postPayment: number            // 期后回款
  remark: string                 // 备注
}

/** 需要SUM求和的固定金额字段列表（不含动态账龄段） */
const FIXED_NUMERIC_FIELDS: (keyof DetailRow)[] = [
  'priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited',
  'debitOccurrence', 'creditOccurrence', 'endBalance',
  'reclassification', 'currentUnadjusted',
  'currentAje', 'currentRje', 'currentAudited',
  'postPayment',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成简易唯一ID（nanoid替代） */
function generateRowId(): string {
  return `dr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/** 创建空行（使用动态 segments 初始化账龄数据） */
function createEmptyRow(seq: number, segments: AgingSegment[]): DetailRow {
  const agingData = createEmptyAgingData(segments, 'D2')
  return {
    rowId: generateRowId(),
    seq,
    customerName: '',
    companyCode: '',
    relationType: '非关联方',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    agingPrior: agingData.agingPrior,
    debitOccurrence: 0,
    creditOccurrence: 0,
    endBalance: 0,
    reclassification: 0,
    currentUnadjusted: 0,
    agingCurrent: agingData.agingCurrent!,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
    agingAudited: agingData.agingAudited,
    creditRiskClassification: '',
    groupName: '',
    isConfirmation: false,
    postPayment: 0,
    remark: '',
  }
}

/**
 * 行公式链自动计算
 * - priorAudited = priorUnadjusted + priorAje + priorRje
 * - endBalance = priorAudited + debitOccurrence - creditOccurrence
 * - currentUnadjusted = endBalance + reclassification
 * - currentAudited = currentUnadjusted + currentAje + currentRje
 */
function recalcRow(row: DetailRow): DetailRow {
  row.priorAudited = getAuditedAmount(
    parseNum(row.priorUnadjusted),
    parseNum(row.priorAje),
    parseNum(row.priorRje)
  )
  row.endBalance = row.priorAudited + parseNum(row.debitOccurrence) - parseNum(row.creditOccurrence)
  row.currentUnadjusted = row.endBalance + parseNum(row.reclassification)
  row.currentAudited = getAuditedAmount(
    row.currentUnadjusted,
    parseNum(row.currentAje),
    parseNum(row.currentRje)
  )
  return row
}

/**
 * 对 nested aging 对象的所有 key 求和
 */
function sumAgingData(dataList: AgingData[]): AgingData {
  const result: AgingData = {}
  for (const data of dataList) {
    for (const [key, val] of Object.entries(data)) {
      result[key] = (result[key] || 0) + (Number(val) || 0)
    }
  }
  return result
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Detail(options: UseD2BaseOptions & { relatedParties: Ref<string[]> }) {
  const { allResponses, isReadonly, relatedParties, projectId } = options

  // ─── 引入 useAgingConfig（subject='D2'） ───────────────────────────────

  const { segments, bands } = useAgingConfig(projectId, 'D2')

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<DetailRow[]>([])
  const searchQuery = ref<string>('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadRows(): void {
    const response = allResponses.value.get('D2-detail-rows')
    const jsonStr = response?.remark
    if (!jsonStr) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(jsonStr)
      if (Array.isArray(parsed)) {
        rows.value = parsed.map((raw: any, idx: number) => {
          // 旧 flat 格式检测与迁移 (Req 4.3, 10.2, 10.3)
          let migrated: any = raw
          if (isLegacyD2Format(raw)) {
            migrated = migrateD2FlatToNested(raw)
          }

          // 确保 nested aging 字段存在（防御性）
          const agingPrior: AgingData = (migrated.agingPrior && typeof migrated.agingPrior === 'object')
            ? { ...migrated.agingPrior }
            : {}
          const agingCurrent: AgingData = (migrated.agingCurrent && typeof migrated.agingCurrent === 'object')
            ? { ...migrated.agingCurrent }
            : {}
          const agingAudited: AgingData = (migrated.agingAudited && typeof migrated.agingAudited === 'object')
            ? { ...migrated.agingAudited }
            : {}

          const row: DetailRow = {
            rowId: migrated.rowId || generateRowId(),
            seq: migrated.seq ?? idx + 1,
            customerName: migrated.customerName || '',
            companyCode: migrated.companyCode || '',
            relationType: migrated.relationType || '非关联方',
            priorUnadjusted: parseNum(migrated.priorUnadjusted),
            priorAje: parseNum(migrated.priorAje),
            priorRje: parseNum(migrated.priorRje),
            priorAudited: parseNum(migrated.priorAudited),
            agingPrior,
            debitOccurrence: parseNum(migrated.debitOccurrence),
            creditOccurrence: parseNum(migrated.creditOccurrence),
            endBalance: parseNum(migrated.endBalance),
            reclassification: parseNum(migrated.reclassification),
            currentUnadjusted: parseNum(migrated.currentUnadjusted),
            agingCurrent,
            currentAje: parseNum(migrated.currentAje),
            currentRje: parseNum(migrated.currentRje),
            currentAudited: parseNum(migrated.currentAudited),
            agingAudited,
            creditRiskClassification: migrated.creditRiskClassification || '',
            groupName: migrated.groupName || '',
            isConfirmation: migrated.isConfirmation === true || migrated.isConfirmation === 'true',
            postPayment: parseNum(migrated.postPayment),
            remark: migrated.remark || '',
          }
          // Recalc formula fields to ensure consistency
          return recalcRow(row)
        })
      }
    } catch {
      rows.value = []
    }
  }

  // Watch allResponses for D2-detail-rows changes (initial load)
  watch(
    () => allResponses.value.get('D2-detail-rows')?.remark,
    () => {
      // Only reload if rows is empty (initial load) to avoid overwriting user edits
      if (rows.value.length === 0) {
        loadRows()
      }
    },
    { immediate: true }
  )

  // ─── Total Row ─────────────────────────────────────────────────────────

  /**
   * 合计行：SUM所有行各金额列 + 动态账龄段，不可编辑
   */
  const totalRow: ComputedRef<Partial<DetailRow>> = computed(() => {
    const result: Partial<DetailRow> = {
      rowId: '__total__',
      seq: 0,
      customerName: '合计',
      companyCode: '',
      relationType: '',
      creditRiskClassification: '',
      groupName: '',
      isConfirmation: false,
      remark: '',
    }
    // 固定金额字段求和
    for (const field of FIXED_NUMERIC_FIELDS) {
      (result as any)[field] = rows.value.reduce(
        (sum, row) => sum + parseNum((row as any)[field]),
        0
      )
    }
    // 动态账龄段求和
    result.agingPrior = sumAgingData(rows.value.map(r => r.agingPrior))
    result.agingCurrent = sumAgingData(rows.value.map(r => r.agingCurrent))
    result.agingAudited = sumAgingData(rows.value.map(r => r.agingAudited))

    return result
  })

  // ─── Search & Filter ───────────────────────────────────────────────────

  /**
   * 按客户名称模糊搜索，大小写不敏感
   */
  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter(row =>
      row.customerName.toLowerCase().includes(q)
    )
  })

  // ─── Row Management ────────────────────────────────────────────────────

  /**
   * 在合计行上方新增空行，使用当前 segments 初始化账龄数据
   */
  function addRow(): void {
    if (isReadonly.value) return
    const newSeq = rows.value.length + 1
    const newRow = createEmptyRow(newSeq, segments.value)
    rows.value.push(newRow)
    debounceSave()
  }

  /**
   * 删除指定行
   */
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    // Resequence
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    debounceSave()
  }

  // ─── Related Party Matching ────────────────────────────────────────────

  /**
   * 从 relatedParties 列表模糊匹配关联方
   * 使用 includes/contains 逻辑（不要求精确匹配）
   *
   * 返回关联方类型：匹配到 → '其他关联方'；未匹配 → '非关联方'
   */
  function matchRelatedParty(name: string): string {
    if (!name || !relatedParties.value || relatedParties.value.length === 0) {
      return '非关联方'
    }
    const lowerName = name.toLowerCase()
    const matched = relatedParties.value.some(party =>
      party.toLowerCase().includes(lowerName) || lowerName.includes(party.toLowerCase())
    )
    return matched ? '其他关联方' : '非关联方'
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  /**
   * 编辑单元格 → 公式重算 → 触发关联方匹配(如编辑customerName) → debounce保存
   *
   * 支持 nested aging 字段更新：field 格式 "agingPrior.within1" / "agingCurrent.y1to2" 等
   *
   * @param rowId - 行唯一标识
   * @param field - 字段名（支持 dot notation for aging fields）
   * @param value - 新值
   */
  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // Handle nested aging field (e.g. "agingPrior.within1")
    if (field.startsWith('agingPrior.') || field.startsWith('agingCurrent.') || field.startsWith('agingAudited.')) {
      const [period, segKey] = field.split('.')
      const agingObj = (row as any)[period] as AgingData
      if (agingObj && segKey) {
        agingObj[segKey] = parseNum(value)
      }
    } else {
      // Update flat value
      const key = field as keyof DetailRow
      if (key === 'isConfirmation') {
        row.isConfirmation = value === true || value === 'true'
      } else if (FIXED_NUMERIC_FIELDS.includes(key)) {
        ;(row as any)[key] = parseNum(value)
      } else {
        ;(row as any)[key] = value
      }
    }

    // Recalculate formula chain
    recalcRow(row)

    // If customerName changed, auto-match related party
    if (field === 'customerName' && typeof value === 'string') {
      row.relationType = matchRelatedParty(value)
    }

    // Selection fields (creditRiskClassification, relationType, isConfirmation) → immediate save
    const immediateFields = ['creditRiskClassification', 'relationType', 'isConfirmation']
    if (immediateFields.includes(field)) {
      immediateSave()
    } else {
      debounceSave()
    }
  }

  // ─── Virtual Scroll ────────────────────────────────────────────────────

  /**
   * 当行数超过30行时启用虚拟滚动
   */
  const useVirtualScroll: ComputedRef<boolean> = computed(() => {
    return rows.value.length > 30
  })

  // ─── Serialization & Save ──────────────────────────────────────────────

  /**
   * 序列化行数据为 JSON，存储到 D2-detail-rows remark 字段
   * 保存时调用 stripLegacyFlatKeys 确保不含 flat 字段 (Req 4.2, 10.4)
   */
  function serializeRows(): string {
    const cleanedRows = rows.value.map(row => stripLegacyFlatKeys(row))
    return JSON.stringify(cleanedRows)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function immediateSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    flushSave()
  }

  function flushSave(): void {
    const json = serializeRows()
    // Update allResponses Map
    allResponses.value.set('D2-detail-rows', {
      item_id: 'D2-detail-rows',
      conclusion: null,
      remark: json,
    })
    // Dispatch save event
    dispatchSaveEvent()
  }

  /**
   * 触发保存事件（CustomEvent 'd2:save-items'，由 useD2FormData 监听处理）
   */
  function dispatchSaveEvent(): void {
    try {
      const item = {
        item_id: 'D2-detail-rows',
        conclusion: null,
        remark: serializeRows(),
      }
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
    } catch {
      // silent
    }
  }

  // ─── Aging Config Change Handling (Req 4.5) ────────────────────────────

  /**
   * 监听 aging-config:changed 事件，保留已有段数据/零初始化新增段
   */
  function onAgingConfigChanged(): void {
    if (rows.value.length === 0) return

    const newSegments = segments.value
    if (!newSegments || newSegments.length === 0) return

    // 重新映射每一行的 aging 数据
    rows.value = rows.value.map(row => {
      const remapped = remapRowAgingData(row, newSegments, true /* isThreePeriod */)
      return {
        ...row,
        agingPrior: remapped.agingPrior,
        agingCurrent: remapped.agingCurrent,
        agingAudited: remapped.agingAudited,
      }
    })

    // 配置变更后触发保存
    debounceSave()
  }

  window.addEventListener('aging-config:changed', onAgingConfigChanged)

  // ─── Import from Aux Balance (Task 45.1) ────────────────────────────

  /**
   * 从辅助余额表导入客户明细数据
   * GET /api/projects/{pid}/ledger/aux-balance-detail?account_code=1122&aux_type=customer
   *
   * merge模式：按客户名去重，仅更新 priorUnadjusted/endBalance，不覆盖 AJE/RJE/账龄
   * @returns { imported, updated, added } 摘要
   */
  async function importFromAuxBalance(projectId: string): Promise<{ imported: number; updated: number; added: number }> {
    try {
      const response = await fetch(
        `/api/projects/${projectId}/ledger/aux-balance-detail?account_code=1122&aux_type=customer`
      )
      if (!response.ok) {
        ElMessage.info('辅助余额表无数据或请求失败')
        return { imported: 0, updated: 0, added: 0 }
      }

      const result = await response.json()
      const data: Array<{ aux_name: string; prior_balance?: number; end_balance?: number }> =
        result.data || result || []

      if (!data.length) {
        ElMessage.info('辅助余额表中无1122科目客户维度数据')
        return { imported: 0, updated: 0, added: 0 }
      }

      let updated = 0
      let added = 0

      for (const item of data) {
        const customerName = item.aux_name?.trim()
        if (!customerName) continue

        // 按客户名去重查找已有行
        const existing = rows.value.find(
          r => r.customerName.trim().toLowerCase() === customerName.toLowerCase()
        )

        if (existing) {
          // merge: 仅更新 priorUnadjusted/endBalance，不覆盖手工字段
          if (item.prior_balance !== undefined) {
            existing.priorUnadjusted = item.prior_balance
          }
          if (item.end_balance !== undefined) {
            existing.endBalance = item.end_balance
          }
          recalcRow(existing)
          updated++
        } else {
          // 新增行
          const newRow = createEmptyRow(rows.value.length + 1, segments.value)
          newRow.customerName = customerName
          if (item.prior_balance !== undefined) {
            newRow.priorUnadjusted = item.prior_balance
          }
          if (item.end_balance !== undefined) {
            newRow.endBalance = item.end_balance
          }
          recalcRow(newRow)
          rows.value.push(newRow)
          added++
        }
      }

      const imported = updated + added
      if (imported > 0) {
        debounceSave()
      }

      ElMessage.success(`从余额表导入完成：更新${updated}行，新增${added}行`)
      return { imported, updated, added }
    } catch {
      ElMessage.error('从余额表导入失败')
      return { imported: 0, updated: 0, added: 0 }
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  /** EventBus listener for confirmation:completed (Task 44.1) */
  function onConfirmationCompleted(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || !detail.customerName) return

    const targetName = (detail.customerName as string).toLowerCase()
    let matched = false

    for (const row of rows.value) {
      if (row.customerName && row.customerName.toLowerCase().includes(targetName)) {
        row.isConfirmation = true
        ;(row as any)._confirmationAutoMarked = true
        matched = true
      }
    }

    if (matched) {
      debounceSave()
    }
  }

  // Register EventBus listener
  window.addEventListener('confirmation:completed', onConfirmationCompleted)

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    window.removeEventListener('confirmation:completed', onConfirmationCompleted)
    window.removeEventListener('aging-config:changed', onAgingConfigChanged)
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 行数据
    rows,
    filteredRows,
    totalRow,

    // 搜索
    searchQuery,

    // 行操作
    addRow,
    removeRow,
    updateCell,

    // 关联方匹配
    matchRelatedParty,

    // 虚拟滚动
    useVirtualScroll,

    // 导入
    importFromAuxBalance,

    // 账龄配置（供模板/视图渲染使用）
    segments,
    bands,

    // 工具方法（供外部/测试使用）
    loadRows,
    serializeRows,
  }
}

export default useD2Detail
