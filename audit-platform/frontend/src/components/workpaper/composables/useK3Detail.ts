/**
 * useK3Detail — K3-2 明细表 composable（27列3区段Tab+账龄）
 *
 * Spec: .kiro/specs/k3-other-payables/
 * Task: 3.4 (原始), aging-config-enhancement Task 9.1 改造
 * Requirements: 3.1-3.6, 6.2 (aging-config-enhancement)
 *
 * 职责：
 * - 27列拆为3区段Tab：
 *   基础(序号/往来对象/性质/关联关系/期初/期末)
 *   账龄(动态段 from useAgingConfig)
 *   检查(形成原因/预计偿付时间/凭证号/结论/备注)
 * - nested keyed 结构: agingPrior/agingCurrent/agingAudited
 * - 旧格式自动迁移: 检测 agingWithin1Y/aging1To2Y/... 字段并转为 nested
 * - 配置变更时 remapRowAgingData 保留已有段
 * - 期末=期初+增加(贷)-减少(借)（负债类！增加在贷方）
 * - 账龄合计与期末勾稽
 * - 动态行新增（ElMessageBox.prompt输入往来对象）+导入导出
 * - 3年以上账龄行标记橙色背景（长期挂账风险）
 * - 底部统计：往来笔数/期末合计/3年以上占比
 * - JSON打包存储到 checklist_responses "K3-2-rows"
 *
 * 科目：2241 其他应付款（**贷方/负债类**）
 * ⚠️ 负债类！增加=贷方发生；减少=借方发生
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from './useK3FormulaEngine'
import { useAgingConfig, createEmptyAgingData, type AgingSegment } from '@/composables/useAgingConfig'
import {
  remapRowAgingData,
  stripLegacyFlatKeys,
  type AgingData,
} from '@/composables/useAgingMigration'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K3DetailRow {
  rowId: string
  // 区段0 基础
  seqNo: number
  counterparty: string         // 往来对象
  nature: string               // 性质（保证金/往来款/代收代付/其他）
  relatedParty: string         // 关联关系（非关联/控股子公司/联营合营/...）
  beginBalance: number         // 期初余额
  increase: number             // 本期增加（贷方发生）
  decrease: number             // 本期减少（借方发生）
  endBalance: number           // 期末余额（公式：期初+贷-借，负债类）
  // 区段1 账龄 — nested keyed (动态段)
  agingPrior: AgingData
  agingCurrent: AgingData
  agingAudited: AgingData
  agingTotal: number           // 账龄合计（应=期末余额）
  // 区段2 检查
  formationReason: string      // 形成原因
  repaymentDate: string        // 预计偿付时间
  voucherRef: string           // 凭证号
  checkConclusion: string      // 结论
  suspectedUnrecorded: boolean // 疑似未入账 (Req 7.4)
  remark: string
}

export type K3DetailSection = 0 | 1 | 2

export const K3_DETAIL_SECTION_LABELS = ['基础', '账龄', '检查'] as const

export interface K3DetailSubtotals {
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  agingTotals: Record<string, number>  // 按 segment key 汇总
  count: number
}

export interface K3DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'select' | 'checkbox'
  options?: string[]
  tooltip?: string
}

// ─── K3 旧 flat 字段名 → segment key 映射 ───────────────────────────────────

/**
 * K3 旧格式使用 agingWithin1Y/aging1To2Y/aging2To3Y/agingOver3Y
 * 对应 THREE_YEAR/FIVE_YEAR preset 的 within1/y1to2/y2to3/over3
 * （K3 默认 FIVE_YEAR 但旧数据可能只有 4 段）
 */
const K3_FLAT_TO_SEGMENT: Record<string, string> = {
  agingWithin1Y: 'within1',
  aging1To2Y: 'y1to2',
  aging2To3Y: 'y2to3',
  agingOver3Y: 'over3',
  // 如果有 5 年段旧格式
  aging3To4Y: 'y3to4',
  aging4To5Y: 'y4to5',
  agingOver5Y: 'over5',
}

const K3_FLAT_KEYS = new Set(Object.keys(K3_FLAT_TO_SEGMENT))

/** 检测是否为 K3 旧 flat 格式 */
function isLegacyK3Format(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false
  // 如果已经有 agingPrior/agingAudited 对象，说明已迁移
  if (raw.agingPrior && typeof raw.agingPrior === 'object') return false
  if (raw.agingAudited && typeof raw.agingAudited === 'object') return false
  for (const key of K3_FLAT_KEYS) {
    if (key in raw) return true
  }
  return false
}

/** K3 旧 flat → nested 迁移 */
function migrateK3FlatToNested(raw: any): { agingPrior: AgingData; agingCurrent: AgingData; agingAudited: AgingData } {
  const agingPrior: AgingData = {}
  const agingCurrent: AgingData = {}
  const agingAudited: AgingData = {}

  // K3 旧格式的 aging 字段视为期末审定
  for (const [flatKey, segKey] of Object.entries(K3_FLAT_TO_SEGMENT)) {
    if (flatKey in raw) {
      const value = _toNumber(raw[flatKey])
      agingAudited[segKey] = value
      agingPrior[segKey] = 0
      agingCurrent[segKey] = 0
    }
  }

  return { agingPrior, agingCurrent, agingAudited }
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K3-2-rows'

const NATURE_OPTIONS = ['保证金及押金', '往来款', '代收代付', '其他']
const RELATED_PARTY_OPTIONS = ['非关联', '控股子公司', '联营/合营企业', '关键管理人员', '关联自然人', '其他关联方']
const CONCLUSION_OPTIONS = ['正常', '异常', '长期挂账', '待确认']

/** 区段0 基础列 */
const BASIC_COLUMNS: K3DetailColumn[] = [
  { key: 'seqNo', label: '序号', width: 60, editable: false, type: 'number' },
  { key: 'counterparty', label: '往来对象', width: 180, editable: true, type: 'text' },
  { key: 'nature', label: '性质', width: 120, editable: true, type: 'select', options: NATURE_OPTIONS },
  { key: 'relatedParty', label: '关联关系', width: 130, editable: true, type: 'select', options: RELATED_PARTY_OPTIONS },
  { key: 'beginBalance', label: '期初余额', width: 130, editable: true, type: 'number' },
  { key: 'increase', label: '本期增加(贷方)', width: 130, editable: true, type: 'number' },
  { key: 'decrease', label: '本期减少(借方)', width: 130, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末余额', width: 130, editable: false, type: 'formula', tooltip: '期末=期初+贷方-借方（负债类）' },
]

/** 区段2 检查列 */
const CHECK_COLUMNS: K3DetailColumn[] = [
  { key: 'counterparty', label: '往来对象', width: 180, editable: false, type: 'text' },
  { key: 'formationReason', label: '形成原因', width: 200, editable: true, type: 'text' },
  { key: 'repaymentDate', label: '预计偿付时间', width: 130, editable: true, type: 'text' },
  { key: 'voucherRef', label: '凭证号', width: 120, editable: true, type: 'text' },
  { key: 'checkConclusion', label: '结论', width: 110, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'suspectedUnrecorded', label: '疑似未入账', width: 100, editable: true, type: 'checkbox' },
  { key: 'remark', label: '备注', width: 200, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK3Detail(params: {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
  projectId: Ref<string>
}) {
  const { allResponses, saveResponse, projectId } = params

  // ─── Aging Config ──────────────────────────────────────────────────────────

  const { segments, bands } = useAgingConfig(projectId, 'K3')

  // ─── State ─────────────────────────────────────────────────────────────────

  const detailRows = ref<K3DetailRow[]>([])
  const activeSection = ref<K3DetailSection>(0)

  // ─── 动态账龄列（基于 bands） ──────────────────────────────────────────────

  const agingColumns = computed<K3DetailColumn[]>(() => {
    const cols: K3DetailColumn[] = [
      { key: 'counterparty', label: '往来对象', width: 180, editable: false, type: 'text' },
    ]
    // 动态生成各账龄段列（期末审定）
    for (const band of bands.value) {
      cols.push({
        key: `agingAudited.${band.key}`,
        label: band.label,
        width: 120,
        editable: true,
        type: 'number',
      })
    }
    cols.push(
      { key: 'agingTotal', label: '账龄合计', width: 120, editable: false, type: 'formula', tooltip: '=各账龄段之和' },
      { key: 'endBalance', label: '期末余额', width: 120, editable: false, type: 'formula', tooltip: '勾稽：账龄合计应=期末余额' },
    )
    return cols
  })

  // ─── 创建空 aging 数据 ─────────────────────────────────────────────────────

  function _createEmptyAging(): { agingPrior: AgingData; agingCurrent: AgingData; agingAudited: AgingData } {
    const data = createEmptyAgingData(segments.value, 'K3')
    return {
      agingPrior: data.agingPrior,
      agingCurrent: data.agingCurrent!,
      agingAudited: data.agingAudited,
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { detailRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed.map(_normalizeRow)
      } else {
        detailRows.value = []
      }
    } catch {
      detailRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K3DetailRow {
    let agingPrior: AgingData
    let agingCurrent: AgingData
    let agingAudited: AgingData

    if (isLegacyK3Format(raw)) {
      // 旧 flat 格式 → 自动迁移
      const migrated = migrateK3FlatToNested(raw)
      agingPrior = migrated.agingPrior
      agingCurrent = migrated.agingCurrent
      agingAudited = migrated.agingAudited
    } else if (raw.agingPrior && typeof raw.agingPrior === 'object') {
      // 新 nested 格式 — 直接使用
      agingPrior = { ...raw.agingPrior }
      agingCurrent = (raw.agingCurrent && typeof raw.agingCurrent === 'object') ? { ...raw.agingCurrent } : {}
      agingAudited = (raw.agingAudited && typeof raw.agingAudited === 'object') ? { ...raw.agingAudited } : {}
    } else {
      // 全新空数据
      const empty = _createEmptyAging()
      agingPrior = empty.agingPrior
      agingCurrent = empty.agingCurrent
      agingAudited = empty.agingAudited
    }

    // 确保所有当前配置的 segment key 都存在
    for (const seg of segments.value) {
      if (!(seg.key in agingPrior)) agingPrior[seg.key] = 0
      if (!(seg.key in agingCurrent)) agingCurrent[seg.key] = 0
      if (!(seg.key in agingAudited)) agingAudited[seg.key] = 0
    }

    const row: K3DetailRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      counterparty: raw.counterparty ?? '',
      nature: raw.nature ?? '',
      relatedParty: raw.relatedParty ?? '',
      beginBalance: _toNumber(raw.beginBalance),
      increase: _toNumber(raw.increase),
      decrease: _toNumber(raw.decrease),
      endBalance: _toNumber(raw.endBalance),
      agingPrior,
      agingCurrent,
      agingAudited,
      agingTotal: 0,
      formationReason: raw.formationReason ?? '',
      repaymentDate: raw.repaymentDate ?? '',
      voucherRef: raw.voucherRef ?? '',
      checkConclusion: raw.checkConclusion ?? '',
      suspectedUnrecorded: Boolean(raw.suspectedUnrecorded),
      remark: raw.remark ?? '',
    }

    // Recalc
    _recalcRow(row)

    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K3DetailRow): void {
    // 负债类期末=期初+贷方(增加)-借方(减少)
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.increase, row.decrease)
    // 账龄合计
    row.agingTotal = calcSubtotal(Object.values(row.agingAudited).map(_toNumber))
  }

  function recalcAll(): void {
    for (const row of detailRows.value) _recalcRow(row)
  }

  // ─── Subtotals (Req 3.6 底部统计) ─────────────────────────────────────────

  const subtotals: ComputedRef<K3DetailSubtotals> = computed(() => {
    const r = detailRows.value
    // 按 segment key 汇总
    const agingTotals: Record<string, number> = {}
    for (const seg of segments.value) {
      agingTotals[seg.key] = calcSubtotal(r.map(x => _toNumber(x.agingAudited[seg.key])))
    }
    return {
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      increase: calcSubtotal(r.map(x => x.increase)),
      decrease: calcSubtotal(r.map(x => x.decrease)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      agingTotals,
      count: r.length,
    }
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K3DetailSection): void {
    activeSection.value = section
  }

  const activeColumns = computed(() => {
    switch (activeSection.value) {
      case 0: return BASIC_COLUMNS
      case 1: return agingColumns.value
      case 2: return CHECK_COLUMNS
      default: return BASIC_COLUMNS
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = detailRows.value.find(r => r.rowId === rowId)
    if (!row) return

    // 处理 nested aging 字段更新 (如 "agingAudited.within1")
    if (field.startsWith('agingPrior.') || field.startsWith('agingCurrent.') || field.startsWith('agingAudited.')) {
      const [period, segKey] = field.split('.')
      if (period && segKey && (row as any)[period]) {
        ;(row as any)[period][segKey] = _toNumber(value)
      }
    } else {
      ;(row as any)[field] = value
    }

    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add (Req 3.4: ElMessageBox.prompt输入往来对象) ──────────────

  async function addRow(counterparty?: string): Promise<void> {
    let name = counterparty
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入往来对象名称',
          '新增明细行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX公司',
            inputValidator: (val) => (!val?.trim() ? '往来对象不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return // 用户取消
      }
    }
    if (!name) return

    const empty = _createEmptyAging()
    const newRow: K3DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: detailRows.value.length + 1,
      counterparty: name,
      nature: '',
      relatedParty: '非关联',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      agingPrior: empty.agingPrior,
      agingCurrent: empty.agingCurrent,
      agingAudited: empty.agingAudited,
      agingTotal: 0,
      formationReason: '',
      repaymentDate: '',
      voucherRef: '',
      checkConclusion: '',
      suspectedUnrecorded: false,
      remark: '',
    }

    detailRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= detailRows.value.length) return
    detailRows.value.splice(idx, 1)
    detailRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    detailRows.value = data.map((raw, i) => {
      const row = _normalizeRow(raw, i)
      _recalcRow(row)
      return row
    })
    _persist()
  }

  // ─── 统计方法 ──────────────────────────────────────────────────────────────

  /** 明细表期末合计 */
  function getDetailTotal(): number {
    return subtotals.value.endBalance
  }

  /** 3年以上账龄行数 */
  function getAgingOver3YCount(): number {
    const over3Keys = ['y3to4', 'y4to5', 'over5', 'over3']
    return detailRows.value.filter(r => {
      for (const k of over3Keys) {
        if (k in r.agingAudited && _toNumber(r.agingAudited[k]) > 0) return true
      }
      return false
    }).length
  }

  /** 3年以上账龄金额合计 */
  function getAgingOver3YTotal(): number {
    const over3Keys = ['y3to4', 'y4to5', 'over5', 'over3']
    return calcSubtotal(detailRows.value.map(r => {
      let sum = 0
      for (const k of over3Keys) {
        if (k in r.agingAudited) sum += _toNumber(r.agingAudited[k])
      }
      return sum
    }))
  }

  /** 获取超过阈值的大额项目 (Req 4.4 联动K3-4) */
  function getLargeAmountItems(threshold: number): K3DetailRow[] {
    return detailRows.value
      .filter(r => Math.abs(r.endBalance) >= threshold)
      .sort((a, b) => Math.abs(b.endBalance) - Math.abs(a.endBalance))
  }

  // ─── 配置变更处理 ──────────────────────────────────────────────────────────

  function _onAgingConfigChanged(): void {
    detailRows.value = detailRows.value.map(row => {
      const remapped = remapRowAgingData(row, segments.value, true)
      return {
        ...row,
        agingPrior: remapped.agingPrior,
        agingCurrent: remapped.agingCurrent,
        agingAudited: remapped.agingAudited,
        agingTotal: calcSubtotal(Object.values(remapped.agingAudited).map(_toNumber)),
      }
    })
    _persist()
  }

  // ─── EventBus 监听 ─────────────────────────────────────────────────────────

  function _handleConfigEvent(): void {
    _onAgingConfigChanged()
  }

  onMounted(() => {
    window.addEventListener('aging-config:changed', _handleConfigEvent)
  })

  onUnmounted(() => {
    window.removeEventListener('aging-config:changed', _handleConfigEvent)
  })

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    // 序列化时不含 agingTotal（公式字段）且不含旧 flat keys
    const cleaned = detailRows.value.map(row => {
      const { agingTotal, ...rest } = row
      // 移除旧的 flat aging 字段（如果存在）
      const result: any = {}
      for (const key of Object.keys(rest)) {
        if (!K3_FLAT_KEYS.has(key)) {
          result[key] = (rest as any)[key]
        }
      }
      return result
    })
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(cleaned) })
    // 同步跨sheet数据到allResponses供computed链使用
    saveResponse('K3-2-detail-total', { remark: String(getDetailTotal()) })
    saveResponse('K3-2-aging-over3y-count', { remark: String(getAgingOver3YCount()) })
    saveResponse('K3-2-aging-over3y-total', { remark: String(getAgingOver3YTotal()) })
    // 大额款项count/total（供useK3CrossSheet.largeAmountVsDetail→主入口全局告警③消费）
    // 阈值取K3-4-threshold（若已设），否则默认10万
    const thItem = allResponses.value.get('K3-4-threshold')
    const threshold = Number(thItem?.remark) || 100000
    const largeItems = getLargeAmountItems(threshold)
    saveResponse('K3-2-large-amount-count', { remark: String(largeItems.length) })
    saveResponse('K3-2-large-amount-total', { remark: String(calcSubtotal(largeItems.map(r => r.endBalance))) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    detailRows,
    activeSection,
    subtotals,
    activeColumns,
    agingColumns,
    segments,
    bands,
    sections: [
      { key: 0 as K3DetailSection, label: '基础', columns: BASIC_COLUMNS },
      { key: 1 as K3DetailSection, label: '账龄', columns: null as any }, // 动态，使用 agingColumns
      { key: 2 as K3DetailSection, label: '检查', columns: CHECK_COLUMNS },
    ],
    switchSection,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    getDetailTotal,
    getAgingOver3YCount,
    getAgingOver3YTotal,
    getLargeAmountItems,
  }
}

// ─── 内部工具 ─────────────────────────────────────────────────────────────────

function _toNumber(val: any): number {
  if (val == null) return 0
  const num = Number(val)
  return Number.isFinite(num) ? num : 0
}
