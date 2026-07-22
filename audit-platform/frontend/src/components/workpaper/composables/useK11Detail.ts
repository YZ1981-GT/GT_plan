/**
 * useK11Detail — K11-2 明细表逻辑（50行×18列→2区段Tab管理）
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 * Task: 3.4
 * Requirements: 2~6 全部
 *
 * 职责：
 * - 50行动态明细行管理（按资产类别逐项）
 * - 18列拆2区段Tab：基础(序号/资产类别/减值项目/本期计提/本期转回/本期发生额) | 核对(来源底稿/源底稿计提金额/差异/凭证/结论)
 * - 商誉减值不可转回（CAS8: 商誉减值不可转回，isNonReversible check）
 * - 使用 calcSourceVariance 计算差异列
 * - 动态行增删
 * - 合计行与K11-1审定表交叉验证
 * - 存储 "K11-2-total-occurrence" 供CrossSheet使用
 *
 * Item IDs: "K11-2-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcSourceVariance,
} from './useK11FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行存储结构 */
export interface K11DetailRow {
  rowKey: string
  /** 序号 */
  seq: number
  /** 资产类别 */
  assetCategory: string
  /** 减值项目名称 */
  impairmentItem: string
  /** 本期计提金额 */
  currentProvision: number
  /** 本期转回金额（商誉不可转回时为0且不可编辑） */
  currentReversal: number
  /** 本期发生额（公式：计提-转回） */
  currentOccurrence: number
  /** 来源底稿编码 */
  sourceWp: string
  /** 源底稿计提金额 */
  sourceAmount: number
  /** 差异（公式：本期发生额 - 源底稿计提金额） */
  variance: number
  /** 凭证编号/抽查结果 */
  voucherRef: string
  /** 核查结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 是否不可转回（商誉减值：CAS8不可转回） */
  isNonReversible: boolean
  /** 可编辑标记 */
  isEditable: boolean
}

/** 区段Tab标识 */
export type K11DetailTabKey = 'basic' | 'reconcile'

export interface K11DetailSubtotal {
  currentProvision: number
  currentReversal: number
  currentOccurrence: number
  sourceAmount: number
  variance: number
}

export interface UseK11DetailParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K11-2-detail-rows'
const ITEM_PREFIX = 'K11-2'

/** 商誉类别标识（CAS8：商誉减值不可转回） */
const GOODWILL_CATEGORIES = ['商誉', '商誉减值', '商誉减值损失', '商誉减值准备']

/** 2区段Tab配置 */
export const DETAIL_TABS: Array<{ key: K11DetailTabKey; label: string }> = [
  { key: 'basic', label: '基础信息' },
  { key: 'reconcile', label: '核对' },
]

/** 减值来源底稿映射 */
export const IMPAIRMENT_SOURCE_MAP: Record<string, string> = {
  '存货跌价': 'F2',
  '存货跌价准备': 'F2',
  '固定资产减值': 'H1',
  '固定资产减值准备': 'H1',
  '无形资产减值': 'I1',
  '无形资产减值准备': 'I1',
  '开发支出减值': 'I2',
  '开发支出减值准备': 'I2',
  '商誉减值': 'I3',
  '商誉减值损失': 'I3',
  '商誉减值准备': 'I3',
  '在建工程减值': 'H2',
  '在建工程减值准备': 'H2',
  '长期股权投资减值': 'G7',
  '长期股权投资减值准备': 'G7',
  '工程物资减值': 'H4',
  '工程物资减值准备': 'H4',
  '使用权资产减值': 'H8',
  '使用权资产减值准备': 'H8',
  '投资性房地产减值': 'H3',
  '投资性房地产减值准备': 'H3',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 判断是否为商誉类别（不可转回） */
function isGoodwillCategory(category: string): boolean {
  if (!category) return false
  const normalized = category.trim()
  return GOODWILL_CATEGORIES.some(kw => normalized.includes(kw))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK11Detail(params: UseK11DetailParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K11DetailRow[]>([])
  const activeTab = ref<K11DetailTabKey>('basic')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map((r, idx) => _normalizeRow(r, idx))
    } else {
      rows.value = []
    }
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): K11DetailRow {
    const assetCategory = raw.assetCategory ?? ''
    const isNonReversible = raw.isNonReversible ?? isGoodwillCategory(assetCategory)
    const currentProvision = parseNum(raw.currentProvision)
    const currentReversal = isNonReversible ? 0 : parseNum(raw.currentReversal)
    const currentOccurrence = currentProvision - currentReversal
    const sourceAmount = parseNum(raw.sourceAmount)
    const variance = calcSourceVariance(currentOccurrence, sourceAmount)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: idx + 1,
      assetCategory,
      impairmentItem: raw.impairmentItem ?? '',
      currentProvision,
      currentReversal,
      currentOccurrence,
      sourceWp: raw.sourceWp ?? (IMPAIRMENT_SOURCE_MAP[assetCategory] ?? ''),
      sourceAmount,
      variance,
      voucherRef: raw.voucherRef ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      isNonReversible,
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<K11DetailRow[]> = computed(() => {
    return rows.value.map((row, idx) => {
      const currentReversal = row.isNonReversible ? 0 : row.currentReversal
      const currentOccurrence = row.currentProvision - currentReversal
      const variance = calcSourceVariance(currentOccurrence, row.sourceAmount)
      return { ...row, seq: idx + 1, currentReversal, currentOccurrence, variance }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotal: ComputedRef<K11DetailSubtotal> = computed(() => {
    const detail = computedRows.value
    const currentProvision = calcSubtotal(detail.map(r => r.currentProvision))
    const currentReversal = calcSubtotal(detail.map(r => r.currentReversal))
    const currentOccurrence = calcSubtotal(detail.map(r => r.currentOccurrence))
    const sourceAmount = calcSubtotal(detail.map(r => r.sourceAmount))
    const variance = calcSourceVariance(currentOccurrence, sourceAmount)
    return { currentProvision, currentReversal, currentOccurrence, sourceAmount, variance }
  })

  // ─── 差异非零行判断（红色标记） ───────────────────────────────────────────

  const varianceRows: ComputedRef<Array<{ rowKey: string; variance: number }>> = computed(() => {
    return computedRows.value
      .filter(r => Math.abs(r.variance) >= 0.01)
      .map(r => ({ rowKey: r.rowKey, variance: r.variance }))
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return

    // 商誉不可转回保护
    if (field === 'currentReversal' && row.isNonReversible) return

    ;(row as any)[field] = value

    // 资产类别变更时自动更新不可转回标识和来源底稿
    if (field === 'assetCategory') {
      row.isNonReversible = isGoodwillCategory(value as string)
      if (row.isNonReversible) row.currentReversal = 0
      row.sourceWp = IMPAIRMENT_SOURCE_MAP[value as string] ?? row.sourceWp
    }

    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K11DetailRow): void {
    const currentReversal = row.isNonReversible ? 0 : row.currentReversal
    row.currentOccurrence = row.currentProvision - currentReversal
    row.variance = calcSourceVariance(row.currentOccurrence, row.sourceAmount)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(assetCategory: string, impairmentItem: string = ''): void {
    if (isReadonly?.value) return
    const isNonReversible = isGoodwillCategory(assetCategory)
    const sourceWp = IMPAIRMENT_SOURCE_MAP[assetCategory] ?? ''
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seq: rows.value.length + 1,
      assetCategory,
      impairmentItem,
      currentProvision: 0,
      currentReversal: 0,
      currentOccurrence: 0,
      sourceWp,
      sourceAmount: 0,
      variance: 0,
      voucherRef: '',
      conclusion: '',
      remark: '',
      isNonReversible,
      isEditable: true,
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

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 同步发生额合计供CrossSheet使用（K11-1↔K11-2交叉验证）
    onSave('K11-2-total-occurrence', subtotal.value.currentOccurrence)
  }

  // ─── Tab切换 ──────────────────────────────────────────────────────────────

  function setActiveTab(tab: K11DetailTabKey): void {
    activeTab.value = tab
  }

  function computeAll(): void {
    for (const row of rows.value) _recalcRow(row)
    _persist()
  }

  /**
   * 自 H1-14 拉取本期补提⑧写入固定资产行 sourceAmount，并刷新 CrossSheet 键。
   */
  async function pullH1SupplementAsSource(): Promise<{ ok: boolean; amount: number; message: string }> {
    if (isReadonly?.value) return { ok: false, amount: 0, message: '只读模式' }
    const pid = projectId.value
    if (!pid) return { ok: false, amount: 0, message: '缺少 projectId' }
    try {
      const { api } = await import('@/services/apiProxy')
      const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
        params: { project_id: pid, wp_code: 'H1' },
        _silent: true,
      } as any)
      const h1WpId = (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id
      if (!h1WpId) return { ok: false, amount: 0, message: '项目中未找到 H1 底稿' }

      const res = await api.get(`/api/workpapers/${h1WpId}/checklist-responses`, { _silent: true } as any)
      const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const readNum = (id: string): number | null => {
        const item = list.find((r) => r.item_id === id)
        if (!item) return null
        const n = Number(item.remark ?? item.conclusion)
        return Number.isFinite(n) ? n : null
      }
      let amount = readNum('H1-14-supplement-total')
        ?? readNum('H1-14-本期减值合计')
      if (amount == null) {
        const calcItem = list.find((r) => r.item_id === 'H1-14-calc-rows')
        const raw = calcItem?.remark
        if (raw) {
          try {
            const rowsJson = typeof raw === 'string' ? JSON.parse(raw) : raw
            if (Array.isArray(rowsJson)) {
              amount = rowsJson.reduce(
                (s: number, r: any) => s + Math.max((Number(r.impairmentAmount) || 0) - (Number(r.alreadyProvided) || 0), 0),
                0,
              )
            }
          } catch { /* ignore */ }
        }
      }
      if (amount == null) return { ok: false, amount: 0, message: 'H1-14 尚无本期补提数据' }

      // 写入 CrossSheet 键 + 明细行 sourceAmount
      onSave?.('K11-2-fixed-asset-source-amount', amount)
      onSave?.('K11-source-H1-amount', amount)
      let touched = 0
      for (const row of rows.value) {
        const isFa = row.sourceWp === 'H1'
          || String(row.assetCategory || '').includes('固定资产')
        if (isFa) {
          row.sourceAmount = amount
          _recalcRow(row)
          touched++
        }
      }
      if (touched === 0) {
        // 自动补一行固定资产核对行
        addRow('固定资产减值准备', '自 H1-14 本期补提')
        const last = rows.value[rows.value.length - 1]
        if (last) {
          last.sourceAmount = amount
          last.sourceWp = 'H1'
          _recalcRow(last)
        }
      }
      isChanged.value = true
      _persist()
      return { ok: true, amount, message: `已自 H1-14 引入本期补提 ${amount.toFixed(2)}` }
    } catch (e) {
      return { ok: false, amount: 0, message: e instanceof Error ? e.message : String(e) }
    }
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    subtotal,
    activeTab,
    isChanged,
    varianceRows,
    updateCell,
    addRow,
    removeRow,
    setActiveTab,
    computeAll,
    pullH1SupplementAsSource,
    initFromResponses,
  }
}

export default useK11Detail
