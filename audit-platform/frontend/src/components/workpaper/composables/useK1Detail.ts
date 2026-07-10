/**
 * useK1Detail — K1-2 明细表逻辑
 *
 * Spec: .kiro/specs/k1-other-receivables/
 * Task: 3.4 (原始), aging-config-enhancement Task 9.1 改造
 * Requirements: 3.1-3.6, 6.1 (aging-config-enhancement)
 *
 * 职责：
 * - 36列 3区段Tab: 基础/账龄/减值
 * - 动态账龄段: 从 useAgingConfig(subject='K1') 获取配置
 * - nested keyed 结构: agingPrior/agingCurrent/agingAudited
 * - 旧格式自动迁移: 检测 flat aging1y/aging1to2/... 字段并转为 nested
 * - 配置变更时 remapRowAgingData 保留已有段
 * - 动态行 CRUD + 统计(笔数/合计/3年以上占比)
 * - 与K1-1审定表合计交叉验证
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal, calcProportion } from './useK1FormulaEngine'
import { useAgingConfig, createEmptyAgingData, type AgingSegment } from '@/composables/useAgingConfig'
import {
  isLegacyD2Format,
  migrateD2FlatToNested,
  stripLegacyFlatKeys,
  remapRowAgingData,
  type AgingData,
} from '@/composables/useAgingMigration'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K1DetailRow {
  id: string
  /** 基础区段 */
  seq: number
  counterparty: string
  nature: string
  relatedParty: string
  beginBalance: number
  endBalance: number
  /** 账龄区段 — nested keyed (动态段) */
  agingPrior: AgingData
  agingCurrent: AgingData
  agingAudited: AgingData
  agingTotal: number    // 账龄合计（公式：agingAudited 各段之和）
  /** 减值区段 */
  stage: 1 | 2 | 3
  badDebtProvision: number
  netValue: number
  voucherNo: string
  conclusion: string
  remark: string
}

export interface K1DetailStats {
  totalCount: number
  totalEndBalance: number
  over3YearRatio: number | null
}

export interface UseK1DetailOpts {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}

// ─── K1 旧 flat 字段名 → segment key 映射 ───────────────────────────────────

/**
 * K1 旧格式使用 aging1y/aging1to2/aging2to3/aging3to4/aging4to5/aging5plus
 * 对应 FIVE_YEAR preset 的 within1/y1to2/y2to3/y3to4/y4to5/over5
 */
const K1_FLAT_TO_SEGMENT: Record<string, string> = {
  aging1y: 'within1',
  aging1to2: 'y1to2',
  aging2to3: 'y2to3',
  aging3to4: 'y3to4',
  aging4to5: 'y4to5',
  aging5plus: 'over5',
}

const K1_FLAT_KEYS = new Set(Object.keys(K1_FLAT_TO_SEGMENT))

/** 检测是否为 K1 旧 flat 格式（含 aging1y 等 flat 字段且无 agingPrior nested 对象） */
function isLegacyK1Format(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false
  // 如果已经有 agingPrior 对象，说明已迁移
  if (raw.agingPrior && typeof raw.agingPrior === 'object') return false
  for (const key of K1_FLAT_KEYS) {
    if (key in raw) return true
  }
  return false
}

/** K1 旧 flat → nested 迁移 */
function migrateK1FlatToNested(raw: any): Partial<K1DetailRow> {
  const agingPrior: AgingData = {}
  const agingCurrent: AgingData = {}
  const agingAudited: AgingData = {}

  // K1 旧格式只有单组 aging 字段（对应期末审定），期初和期末未审为空
  for (const [flatKey, segKey] of Object.entries(K1_FLAT_TO_SEGMENT)) {
    const value = _toNumber(raw[flatKey])
    // K1 旧格式的 aging 字段视为期末审定（使用时 agingTotal 就是这些之和）
    agingAudited[segKey] = value
    agingPrior[segKey] = 0
    agingCurrent[segKey] = 0
  }

  return { agingPrior, agingCurrent, agingAudited }
}

/** 从 flat 数据中剥离旧 aging 字段 */
function stripK1FlatKeys(raw: any): any {
  const result: any = {}
  for (const key of Object.keys(raw)) {
    if (!K1_FLAT_KEYS.has(key)) {
      result[key] = raw[key]
    }
  }
  return result
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK1Detail(opts: UseK1DetailOpts) {
  const { allResponses, projectId } = opts

  // ─── Aging Config ──────────────────────────────────────────────────────────

  const { segments, bands } = useAgingConfig(projectId, 'K1')

  // ─── 行数据 ────────────────────────────────────────────────────────────────

  const rows = ref<K1DetailRow[]>([])

  /** 创建符合当前配置的空 aging 数据 */
  function _createEmptyAging(): { agingPrior: AgingData; agingCurrent: AgingData; agingAudited: AgingData } {
    const data = createEmptyAgingData(segments.value, 'K1')
    return {
      agingPrior: data.agingPrior,
      agingCurrent: data.agingCurrent!,
      agingAudited: data.agingAudited,
    }
  }

  /** 从 allResponses 加载行数据(JSON打包存储) */
  function loadRows(): void {
    const raw = allResponses.value.get('K1-2-detail-rows')?.remark
    if (!raw) { rows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) { rows.value = []; return }
      rows.value = parsed.map((item: any) => _normalizeRow(item))
    } catch { rows.value = [] }
  }

  /** 标准化行数据：检测旧格式并迁移 */
  function _normalizeRow(raw: any): K1DetailRow {
    let agingPrior: AgingData
    let agingCurrent: AgingData
    let agingAudited: AgingData

    if (isLegacyK1Format(raw)) {
      // 旧 flat 格式 → 自动迁移
      const migrated = migrateK1FlatToNested(raw)
      agingPrior = migrated.agingPrior!
      agingCurrent = migrated.agingCurrent!
      agingAudited = migrated.agingAudited!
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

    const row: K1DetailRow = {
      id: raw.id ?? `K1-2-r-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? 1,
      counterparty: raw.counterparty ?? '',
      nature: raw.nature ?? '',
      relatedParty: raw.relatedParty ?? '否',
      beginBalance: _toNumber(raw.beginBalance),
      endBalance: _toNumber(raw.endBalance),
      agingPrior,
      agingCurrent,
      agingAudited,
      agingTotal: 0,
      stage: raw.stage ?? 1,
      badDebtProvision: _toNumber(raw.badDebtProvision),
      netValue: _toNumber(raw.netValue),
      voucherNo: raw.voucherNo ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }

    // 计算账龄合计
    row.agingTotal = _calcAgingTotal(row.agingAudited)
    row.netValue = row.endBalance - row.badDebtProvision

    return row
  }

  /** 行的账龄合计（公式：agingAudited 各段之和） */
  function _calcAgingTotal(agingData: AgingData): number {
    return calcSubtotal(Object.values(agingData).map(_toNumber))
  }

  // ─── 动态行 CRUD ───────────────────────────────────────────────────────────

  function addRow(counterparty: string): K1DetailRow {
    const empty = _createEmptyAging()
    const newRow: K1DetailRow = {
      id: `K1-2-r-${Date.now()}`,
      seq: rows.value.length + 1,
      counterparty,
      nature: '',
      relatedParty: '否',
      beginBalance: 0,
      endBalance: 0,
      agingPrior: empty.agingPrior,
      agingCurrent: empty.agingCurrent,
      agingAudited: empty.agingAudited,
      agingTotal: 0,
      stage: 1,
      badDebtProvision: 0,
      netValue: 0,
      voucherNo: '',
      conclusion: '',
      remark: '',
    }
    rows.value.push(newRow)
    return newRow
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    // 重新编号
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  function updateRow(id: string, field: string, value: any): void {
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

    // 自动重算账龄合计
    row.agingTotal = _calcAgingTotal(row.agingAudited)
    // 自动重算净值
    row.netValue = row.endBalance - row.badDebtProvision
  }

  // ─── 统计 ──────────────────────────────────────────────────────────────────

  const stats: ComputedRef<K1DetailStats> = computed(() => {
    const totalCount = rows.value.length
    const totalEndBalance = calcSubtotal(rows.value.map(r => r.endBalance))

    // 3年以上: y3to4 + y4to5 + over5（如果这些 key 存在于当前配置中）
    const over3Keys = ['y3to4', 'y4to5', 'over5', 'over3']
    const over3YearAmount = calcSubtotal(
      rows.value.map(r => {
        let sum = 0
        for (const k of over3Keys) {
          if (k in r.agingAudited) sum += _toNumber(r.agingAudited[k])
        }
        return sum
      }),
    )
    const over3YearRatio = calcProportion(over3YearAmount, totalEndBalance)
    return { totalCount, totalEndBalance, over3YearRatio }
  })

  // ─── 账龄勾稽 ─────────────────────────────────────────────────────────────

  const agingMismatches: ComputedRef<string[]> = computed(() => {
    const issues: string[] = []
    for (const row of rows.value) {
      const agingSum = _calcAgingTotal(row.agingAudited)
      if (Math.abs(agingSum - row.endBalance) > 0.01) {
        issues.push(`${row.counterparty}: 账龄合计${agingSum} ≠ 期末${row.endBalance}`)
      }
    }
    return issues
  })

  // ─── 3年以上高亮行 ──────────────────────────────────────────────────────────

  function isOver3Years(row: K1DetailRow): boolean {
    const over3Keys = ['y3to4', 'y4to5', 'over5', 'over3']
    for (const k of over3Keys) {
      if (k in row.agingAudited && _toNumber(row.agingAudited[k]) > 0) return true
    }
    return false
  }

  // ─── 配置变更处理 ──────────────────────────────────────────────────────────

  function _onAgingConfigChanged(): void {
    // 配置变更时 remap 所有行的 aging 数据
    rows.value = rows.value.map(row => {
      const remapped = remapRowAgingData(row, segments.value, true)
      return {
        ...row,
        agingPrior: remapped.agingPrior,
        agingCurrent: remapped.agingCurrent,
        agingAudited: remapped.agingAudited,
        agingTotal: _calcAgingTotal(remapped.agingAudited),
      }
    })
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
    // 序列化时确保不含旧 flat 字段
    const cleaned = rows.value.map(row => {
      const { agingTotal, ...rest } = row
      return stripK1FlatKeys(rest)
    })
    return JSON.stringify(cleaned)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    stats,
    agingMismatches,
    segments,
    bands,
    loadRows,
    addRow,
    removeRow,
    updateRow,
    isOver3Years,
    serializeRows,
  }
}

// ─── 内部工具 ─────────────────────────────────────────────────────────────────

function _toNumber(val: any): number {
  if (val == null) return 0
  const num = Number(val)
  return Number.isFinite(num) ? num : 0
}
