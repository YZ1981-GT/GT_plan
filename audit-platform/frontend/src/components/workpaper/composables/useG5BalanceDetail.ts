/**
 * useG5BalanceDetail — G5-2 余额明细表逻辑 (22列→2区段Tab)
 *
 * Spec: .kiro/specs/g5-long-term-receivable/, aging-config-enhancement Task 9.1
 * Requirements: 6.3 (aging-config-enhancement)
 *
 * Tab1: 债务人基础信息(10列)
 * Tab2: 余额分析+账龄(动态列；表级 3年/5年/自定义 + 项目配置兜底)
 *
 * 改造内容：
 * - nested keyed 结构: agingPrior/agingCurrent/agingAudited
 * - 旧格式自动迁移: 检测 aging1Year/aging1to2/... flat 字段并转为 nested
 * - 配置变更时 remapAgingDataWithAggregation（5→3 汇入 over3）
 * - 公式：期末余额=合同总额-已收回 / 净额=余额-未实现 / 账龄合计
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { parseNum } from '@/composables/useG5FormulaEngine'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useAgingConfig,
  createEmptyAgingData,
  segmentsToBands,
  type AgingSegment,
  type AgingPreset,
  type AgingBand,
} from '@/composables/useAgingConfig'
import { type AgingData } from '@/composables/useAgingMigration'
import {
  remapRowAgingWithAggregation,
  resolveG5AgingSegments,
  validateCustomAgingLabels,
  type G5AgingPreset,
} from './g5AgingScheme'

// ─── G5 旧 flat 字段名 → segment key 映射 ───────────────────────────────────

/**
 * G5 旧格式使用 aging1Year/aging1to2/aging2to3/aging3to4/aging4to5/aging5Plus
 * 对应 FIVE_YEAR preset 的 within1/y1to2/y2to3/y3to4/y4to5/over5
 */
const G5_FLAT_TO_SEGMENT: Record<string, string> = {
  aging1Year: 'within1',
  aging1to2: 'y1to2',
  aging2to3: 'y2to3',
  aging3to4: 'y3to4',
  aging4to5: 'y4to5',
  aging5Plus: 'over5',
}

const G5_FLAT_KEYS = new Set(Object.keys(G5_FLAT_TO_SEGMENT))

/** 检测是否为 G5 旧 flat 格式 */
function isLegacyG5Format(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false
  // 如果已经有 agingAudited 对象，说明已迁移
  if (raw.agingAudited && typeof raw.agingAudited === 'object') return false
  for (const key of G5_FLAT_KEYS) {
    if (key in raw) return true
  }
  return false
}

/** G5 旧 flat → nested 迁移 */
function migrateG5FlatToNested(raw: any): { agingPrior: AgingData; agingCurrent: AgingData; agingAudited: AgingData } {
  const agingPrior: AgingData = {}
  const agingCurrent: AgingData = {}
  const agingAudited: AgingData = {}

  // G5 旧格式的 aging 字段视为期末审定
  for (const [flatKey, segKey] of Object.entries(G5_FLAT_TO_SEGMENT)) {
    if (flatKey in raw) {
      const value = _toNumber(raw[flatKey])
      agingAudited[segKey] = value
      agingPrior[segKey] = 0
      agingCurrent[segKey] = 0
    }
  }

  return { agingPrior, agingCurrent, agingAudited }
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface BalanceDetailRow {
  id: string
  seq: number
  debtorName: string
  businessType: 'lease' | 'installment' | 'factoring' | 'other'
  contractNo: string
  startDate: string
  maturityDate: string
  /** 是否属于「1年内到期」重分类部分（优先于到期日启发） */
  isWithinOneYear: boolean
  contractAmount: number
  recoveredAmount: number
  closingBalance: number
  /** 本期借方发生（对齐源模板 H 列，供 G5-12 检查比例勾稽） */
  debitOccurrence: number
  /** 本期贷方发生（对齐源模板 I 列） */
  creditOccurrence: number
  isRelatedParty: boolean
  unrealizedIncome: number
  netAmount: number
  /** 账龄 — nested keyed (动态段) */
  agingPrior: AgingData
  agingCurrent: AgingData
  agingAudited: AgingData
  agingTotal: number
  remark: string
  /** 跨期稳定键（上年结转优先匹配；勿用临时 row.id 冒充） */
  crossSheetReceivableId?: string
}

/** Excel/导入布尔：兼容 是/否、TRUE/FALSE、0/1（「否」不得为 true） */
export function parseG5Bool(value: unknown): boolean {
  if (value === true || value === 1) return true
  if (value === false || value === 0 || value == null) return false
  const s = String(value).trim().toLowerCase()
  if (!s) return false
  if (['否', 'false', 'n', 'no', '0', 'f'].includes(s)) return false
  if (['是', 'true', 'y', 'yes', '1', 't'].includes(s)) return true
  return false
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG5BalanceDetail(projectId?: Ref<string>) {
  // ─── Aging Config（项目级兜底 + 表级覆盖）──────────────────────────────────

  const _projectId = projectId ?? ref('')
  const projectAging = useAgingConfig(_projectId, 'G5')

  const sheetAgingPreset = ref<G5AgingPreset | null>(null)
  const customAgingLabels = ref<string[]>([])

  const agingPreset: ComputedRef<AgingPreset> = computed(() => {
    if (sheetAgingPreset.value) return sheetAgingPreset.value
    return projectAging.preset.value || 'FIVE_YEAR'
  })

  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    if (sheetAgingPreset.value === 'CUSTOM' && customAgingLabels.value.length >= 2) {
      return resolveG5AgingSegments('CUSTOM', customAgingLabels.value)
    }
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') {
      return resolveG5AgingSegments(sheetAgingPreset.value)
    }
    // 跟随项目：CUSTOM 时项目已给 effective segments
    if (projectAging.segments.value.length) return projectAging.segments.value
    return resolveG5AgingSegments(agingPreset.value, customAgingLabels.value)
  })

  const bands: ComputedRef<AgingBand[]> = computed(() => segmentsToBands(segments.value, 'G5'))

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<BalanceDetailRow[]>([])
  const activeTab = ref<'basic' | 'aging'>('basic')
  const activeRowIndex = ref(0)

  function _applySegmentsToRows(nextSegs: AgingSegment[]): void {
    rows.value = rows.value.map((row) => {
      const remapped = remapRowAgingWithAggregation(row, nextSegs, true)
      return {
        ...row,
        agingPrior: remapped.agingPrior,
        agingCurrent: remapped.agingCurrent,
        agingAudited: remapped.agingAudited,
        agingTotal: _calcAgingTotal(remapped.agingAudited),
      }
    })
  }

  // 段定义变化时再 remap（避免与 async project refresh 抢跑）
  watch(
    segments,
    (next, prev) => {
      if (!rows.value.length) return
      const nextKeys = next.map((s) => s.key).join('|')
      const prevKeys = (prev || []).map((s) => s.key).join('|')
      if (nextKeys === prevKeys) return
      _applySegmentsToRows(next)
    },
    { deep: true },
  )

  // ─── 创建空 aging 数据 ─────────────────────────────────────────────────────

  function _createEmptyAging(): { agingPrior: AgingData; agingCurrent: AgingData; agingAudited: AgingData } {
    const data = createEmptyAgingData(segments.value, 'G5')
    return {
      agingPrior: data.agingPrior,
      agingCurrent: data.agingCurrent!,
      agingAudited: data.agingAudited,
    }
  }

  // ─── 行标准化（含旧格式迁移） ─────────────────────────────────────────────

  function _normalizeRow(raw: any): BalanceDetailRow {
    let agingPrior: AgingData
    let agingCurrent: AgingData
    let agingAudited: AgingData

    if (isLegacyG5Format(raw)) {
      // 旧 flat 格式 → 自动迁移
      const migrated = migrateG5FlatToNested(raw)
      agingPrior = migrated.agingPrior
      agingCurrent = migrated.agingCurrent
      agingAudited = migrated.agingAudited
    } else if (raw.agingAudited && typeof raw.agingAudited === 'object') {
      // 新 nested 格式 — 直接使用
      agingPrior = (raw.agingPrior && typeof raw.agingPrior === 'object') ? { ...raw.agingPrior } : {}
      agingCurrent = (raw.agingCurrent && typeof raw.agingCurrent === 'object') ? { ...raw.agingCurrent } : {}
      agingAudited = { ...raw.agingAudited }
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

    const row: BalanceDetailRow = {
      id: raw.id ?? crypto.randomUUID(),
      seq: parseNum(raw.seq) || 1,
      debtorName: raw.debtorName ?? '',
      businessType: raw.businessType ?? 'other',
      contractNo: raw.contractNo ?? '',
      startDate: raw.startDate ?? '',
      maturityDate: raw.maturityDate ?? '',
      isWithinOneYear: parseG5Bool(raw.isWithinOneYear),
      contractAmount: parseNum(raw.contractAmount),
      recoveredAmount: parseNum(raw.recoveredAmount),
      closingBalance: parseNum(raw.closingBalance),
      debitOccurrence: parseNum(raw.debitOccurrence ?? raw.debit),
      creditOccurrence: parseNum(raw.creditOccurrence ?? raw.credit),
      isRelatedParty: parseG5Bool(raw.isRelatedParty),
      unrealizedIncome: parseNum(raw.unrealizedIncome),
      netAmount: parseNum(raw.netAmount),
      agingPrior,
      agingCurrent,
      agingAudited,
      agingTotal: 0,
      remark: raw.remark ?? '',
      crossSheetReceivableId: raw.crossSheetReceivableId
        ? String(raw.crossSheetReceivableId)
        : undefined,
    }

    recalcRow(row)
    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function recalcRow(row: BalanceDetailRow) {
    row.closingBalance = parseNum(row.contractAmount) - parseNum(row.recoveredAmount)
    row.netAmount = row.closingBalance - parseNum(row.unrealizedIncome)
    row.agingTotal = _calcAgingTotal(row.agingAudited)
  }

  function _calcAgingTotal(agingData: AgingData): number {
    return Object.values(agingData).reduce((sum, val) => sum + _toNumber(val), 0)
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const agingMismatchRows = computed(() =>
    rows.value.filter(r => Math.abs(r.agingTotal - r.netAmount) > 0.01),
  )

  const totals = computed(() => {
    const base = {
      contractAmount: rows.value.reduce((s, r) => s + parseNum(r.contractAmount), 0),
      recoveredAmount: rows.value.reduce((s, r) => s + parseNum(r.recoveredAmount), 0),
      closingBalance: rows.value.reduce((s, r) => s + parseNum(r.closingBalance), 0),
      netAmount: rows.value.reduce((s, r) => s + parseNum(r.netAmount), 0),
      debitOccurrence: rows.value.reduce((s, r) => s + parseNum(r.debitOccurrence), 0),
      creditOccurrence: rows.value.reduce((s, r) => s + parseNum(r.creditOccurrence), 0),
    }

    // 按 segment key 汇总账龄
    const agingTotals: Record<string, number> = {}
    for (const seg of segments.value) {
      agingTotals[seg.key] = rows.value.reduce((s, r) => s + _toNumber(r.agingAudited[seg.key]), 0)
    }

    return { ...base, agingTotals }
  })

  // ─── Row Management ────────────────────────────────────────────────────────

  async function addRow() {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return

    const empty = _createEmptyAging()
    const newRow: BalanceDetailRow = {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      debtorName: value.trim(),
      businessType: 'other',
      contractNo: '',
      startDate: '',
      maturityDate: '',
      isWithinOneYear: false,
      contractAmount: 0,
      recoveredAmount: 0,
      closingBalance: 0,
      debitOccurrence: 0,
      creditOccurrence: 0,
      isRelatedParty: false,
      unrealizedIncome: 0,
      netAmount: 0,
      agingPrior: empty.agingPrior,
      agingCurrent: empty.agingCurrent,
      agingAudited: empty.agingAudited,
      agingTotal: 0,
      remark: '',
    }
    rows.value.push(newRow)
  }

  function removeRow(id: string) {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(id: string, field: string, value: any): void {
    const row = rows.value.find(r => r.id === id)
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

    recalcRow(row)
  }

  // ─── 加载行数据 ────────────────────────────────────────────────────────────

  function loadRows(data: any[]): void {
    if (Array.isArray(data)) {
      rows.value = data.map((raw, i) => {
        const row = _normalizeRow(raw)
        row.seq = i + 1
        return row
      })
    }
  }

  // ─── 账龄口径切换 ──────────────────────────────────────────────────────────

  function setAgingPreset(preset: G5AgingPreset, customLabels?: string[]): boolean {
    if (preset === 'CUSTOM') {
      const labels = (customLabels || customAgingLabels.value).map((l) => l.trim()).filter(Boolean)
      const err = validateCustomAgingLabels(labels)
      if (err) {
        ElMessage.warning(err)
        return false
      }
      customAgingLabels.value = labels
    } else {
      customAgingLabels.value = []
    }
    sheetAgingPreset.value = preset
    const nextSegs = resolveG5AgingSegments(preset, customAgingLabels.value)
    _applySegmentsToRows(nextSegs)
    return true
  }

  function loadAgingPreset(presetRaw: string | null | undefined, customRaw?: string | null): void {
    const p = String(presetRaw || '').trim() as G5AgingPreset
    if (p === 'THREE_YEAR' || p === 'FIVE_YEAR' || p === 'CUSTOM') {
      sheetAgingPreset.value = p
    } else {
      sheetAgingPreset.value = null
    }
    if (customRaw) {
      try {
        const parsed = JSON.parse(customRaw)
        if (Array.isArray(parsed)) {
          customAgingLabels.value = parsed.map((x) => String(x).trim()).filter(Boolean)
        }
      } catch { /* ignore */ }
    }
  }

  // ─── 配置变更处理（项目级刷新完成后由 watch(segments) 驱动）──────────────

  function _onAgingConfigChanged(): void {
    // 表级已覆盖时不跟随项目 remap 触发源；segments watch 会处理项目兜底变化
    if (sheetAgingPreset.value) return
    void projectAging.refresh()
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

  // ─── 序列化 ────────────────────────────────────────────────────────────────

  function serializeRows(): string {
    // 序列化时不含 agingTotal（公式字段）且不含旧 flat keys
    const cleaned = rows.value.map(row => {
      const { agingTotal, ...rest } = row
      const result: any = {}
      for (const key of Object.keys(rest)) {
        if (!G5_FLAT_KEYS.has(key)) {
          result[key] = (rest as any)[key]
        }
      }
      return result
    })
    return JSON.stringify(cleaned)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, activeTab, activeRowIndex,
    segments, bands,
    agingPreset,
    customAgingLabels,
    recalcRow, agingMismatchRows, totals,
    addRow, removeRow, updateCell,
    loadRows, serializeRows,
    setAgingPreset,
    loadAgingPreset,
  }
}

// ─── 内部工具 ─────────────────────────────────────────────────────────────────

function _toNumber(val: any): number {
  if (val == null) return 0
  const num = Number(val)
  return Number.isFinite(num) ? num : 0
}
