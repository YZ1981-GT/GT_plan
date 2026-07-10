/**
 * useG5BalanceDetail — G5-2 余额明细表逻辑 (22列→2区段Tab)
 *
 * Spec: .kiro/specs/g5-long-term-receivable/, aging-config-enhancement Task 9.1
 * Requirements: 6.3 (aging-config-enhancement)
 *
 * Tab1: 债务人基础信息(10列)
 * Tab2: 余额分析+账龄(动态列 from useAgingConfig)
 *
 * 改造内容：
 * - nested keyed 结构: agingPrior/agingCurrent/agingAudited
 * - 旧格式自动迁移: 检测 aging1Year/aging1to2/... flat 字段并转为 nested
 * - 配置变更时 remapRowAgingData 保留已有段
 * - 公式：期末余额=合同总额-已收回 / 净额=余额-未实现 / 账龄合计
 */
import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'
import { parseNum, calcAgingTotal as calcAgingTotalLegacy } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'
import { useAgingConfig, createEmptyAgingData, type AgingSegment } from '@/composables/useAgingConfig'
import {
  remapRowAgingData,
  type AgingData,
} from '@/composables/useAgingMigration'

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
  contractAmount: number
  recoveredAmount: number
  closingBalance: number
  isRelatedParty: boolean
  unrealizedIncome: number
  netAmount: number
  /** 账龄 — nested keyed (动态段) */
  agingPrior: AgingData
  agingCurrent: AgingData
  agingAudited: AgingData
  agingTotal: number
  remark: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG5BalanceDetail(projectId?: Ref<string>) {
  // ─── Aging Config ──────────────────────────────────────────────────────────

  const _projectId = projectId ?? ref('')
  const { segments, bands } = useAgingConfig(_projectId, 'G5')

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<BalanceDetailRow[]>([])
  const activeTab = ref<'basic' | 'aging'>('basic')
  const activeRowIndex = ref(0)

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
      contractAmount: parseNum(raw.contractAmount),
      recoveredAmount: parseNum(raw.recoveredAmount),
      closingBalance: parseNum(raw.closingBalance),
      isRelatedParty: Boolean(raw.isRelatedParty),
      unrealizedIncome: parseNum(raw.unrealizedIncome),
      netAmount: parseNum(raw.netAmount),
      agingPrior,
      agingCurrent,
      agingAudited,
      agingTotal: 0,
      remark: raw.remark ?? '',
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
      contractAmount: 0,
      recoveredAmount: 0,
      closingBalance: 0,
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

  // ─── 配置变更处理 ──────────────────────────────────────────────────────────

  function _onAgingConfigChanged(): void {
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
    recalcRow, agingMismatchRows, totals,
    addRow, removeRow, updateCell,
    loadRows, serializeRows,
  }
}

// ─── 内部工具 ─────────────────────────────────────────────────────────────────

function _toNumber(val: any): number {
  if (val == null) return 0
  const num = Number(val)
  return Number.isFinite(num) ? num : 0
}
