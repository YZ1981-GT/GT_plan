/**
 * useG6BadDebtDetail — G6-3 坏账准备明细表（对齐 Excel 滚动态）
 *
 * Template: 坏账准备明细表G6-3
 * 结构：按单项评估计提 + 信用风险组合计提 + 合计
 * 公式（Excel）：
 *   期初审定 D = 期初未审 B + 期初账项调整 C
 *   期末未审 J = 期初未审 B + 计提E + 其他增加F − 转回G − 转销H − 其他减少I
 *   期末审定 L = 期末未审 J + 期末账项调整 K
 *
 * 说明：旧实现误用 ECL①×② 公式链（属 G6-12）；本表聚焦坏账准备滚动与 G6-1 勾稽。
 * 兼容迁移旧 ECL 双 Tab 字段。
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum } from '@/composables/useG6MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { dispatchG6SaveItems } from './g6CrossHelpers'

export type G6BadDebtCategory = 'individual' | 'portfolio'
export type G6BadDebtRowKind = 'section_header' | 'leaf' | 'subtotal' | 'total'

export interface G6BadDebtLeaf {
  id: string
  seq: number
  category: G6BadDebtCategory
  item: string
  openingUnadjusted: number
  openingAdjustment: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingAdjustment: number
  reason: string
}

export interface G6BadDebtDisplayRow extends G6BadDebtLeaf {
  kind: G6BadDebtRowKind
  editable: boolean
  openingAudited: number
  closingUnadjusted: number
  closingAudited: number
}

export interface G6BadDebtTotals {
  openingUnadjusted: number
  openingAdjustment: number
  openingAudited: number
  provisionIncrease: number
  otherIncrease: number
  reversal: number
  writeOff: number
  otherDecrease: number
  closingUnadjusted: number
  closingAdjustment: number
  closingAudited: number
}

const DATA_KEY = 'G6-3-rows'
const NOTE_KEY = 'G6-3-badDebtDetail-audit-note'
const CONCLUSION_KEY = 'G6-3-badDebtDetail-audit-conclusion'

const uid = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

function round2(n: number): number {
  return Math.round((Number(n) || 0) * 100) / 100
}

/** Excel J/D/L 公式 */
export function computeG6BadDebtMovement(leaf: Pick<
  G6BadDebtLeaf,
  | 'openingUnadjusted'
  | 'openingAdjustment'
  | 'provisionIncrease'
  | 'otherIncrease'
  | 'reversal'
  | 'writeOff'
  | 'otherDecrease'
  | 'closingAdjustment'
>): { openingAudited: number; closingUnadjusted: number; closingAudited: number } {
  const openingAudited = round2(
    parseNum(leaf.openingUnadjusted) + parseNum(leaf.openingAdjustment),
  )
  // Excel: 期末未审 = 期初未审 + 增加 − 减少（不以期初审定为起点）
  const closingUnadjusted = round2(
    parseNum(leaf.openingUnadjusted)
    + parseNum(leaf.provisionIncrease)
    + parseNum(leaf.otherIncrease)
    - parseNum(leaf.reversal)
    - parseNum(leaf.writeOff)
    - parseNum(leaf.otherDecrease),
  )
  const closingAudited = round2(closingUnadjusted + parseNum(leaf.closingAdjustment))
  return { openingAudited, closingUnadjusted, closingAudited }
}

function emptyLeaf(category: G6BadDebtCategory, item: string, seq: number): G6BadDebtLeaf {
  return {
    id: uid(category === 'portfolio' ? 'port' : 'ind'),
    seq,
    category,
    item,
    openingUnadjusted: 0,
    openingAdjustment: 0,
    provisionIncrease: 0,
    otherIncrease: 0,
    reversal: 0,
    writeOff: 0,
    otherDecrease: 0,
    closingAdjustment: 0,
    reason: '',
  }
}

function toDisplayLeaf(leaf: G6BadDebtLeaf): G6BadDebtDisplayRow {
  return {
    ...leaf,
    kind: 'leaf',
    editable: true,
    ...computeG6BadDebtMovement(leaf),
  }
}

export function sumG6BadDebtLeaves(leaves: G6BadDebtLeaf[]): G6BadDebtTotals {
  const openingUnadjusted = round2(leaves.reduce((s, r) => s + parseNum(r.openingUnadjusted), 0))
  const openingAdjustment = round2(leaves.reduce((s, r) => s + parseNum(r.openingAdjustment), 0))
  const provisionIncrease = round2(leaves.reduce((s, r) => s + parseNum(r.provisionIncrease), 0))
  const otherIncrease = round2(leaves.reduce((s, r) => s + parseNum(r.otherIncrease), 0))
  const reversal = round2(leaves.reduce((s, r) => s + parseNum(r.reversal), 0))
  const writeOff = round2(leaves.reduce((s, r) => s + parseNum(r.writeOff), 0))
  const otherDecrease = round2(leaves.reduce((s, r) => s + parseNum(r.otherDecrease), 0))
  const closingAdjustment = round2(leaves.reduce((s, r) => s + parseNum(r.closingAdjustment), 0))
  const mv = computeG6BadDebtMovement({
    openingUnadjusted,
    openingAdjustment,
    provisionIncrease,
    otherIncrease,
    reversal,
    writeOff,
    otherDecrease,
    closingAdjustment,
  })
  return {
    openingUnadjusted,
    openingAdjustment,
    openingAudited: mv.openingAudited,
    provisionIncrease,
    otherIncrease,
    reversal,
    writeOff,
    otherDecrease,
    closingUnadjusted: mv.closingUnadjusted,
    closingAdjustment,
    closingAudited: mv.closingAudited,
  }
}

/** G6-3→G6-1 回写载荷：始终用期末未审（不含 closingAdjustment） */
export function buildG6BadDebtWritebackDetail(leaves: G6BadDebtLeaf[]): {
  individualClosing: number
  portfolioClosing: number
  totalClosing: number
} {
  return {
    individualClosing: sumG6BadDebtLeaves(
      leaves.filter((r) => r.category === 'individual'),
    ).closingUnadjusted,
    portfolioClosing: sumG6BadDebtLeaves(
      leaves.filter((r) => r.category === 'portfolio'),
    ).closingUnadjusted,
    totalClosing: sumG6BadDebtLeaves(leaves).closingUnadjusted,
  }
}

function headerRow(id: string, item: string, category: G6BadDebtCategory): G6BadDebtDisplayRow {
  const z = emptyLeaf(category, item, 0)
  return {
    ...z,
    id,
    item,
    kind: 'section_header',
    editable: false,
    openingAudited: 0,
    closingUnadjusted: 0,
    closingAudited: 0,
  }
}

function aggregateRow(
  id: string,
  item: string,
  kind: 'subtotal' | 'total',
  category: G6BadDebtCategory,
  totals: G6BadDebtTotals,
): G6BadDebtDisplayRow {
  return {
    ...emptyLeaf(category, item, 0),
    id,
    item,
    kind,
    editable: false,
    ...totals,
  }
}

export function buildG6BadDebtDisplayRows(leaves: G6BadDebtLeaf[]): G6BadDebtDisplayRow[] {
  const ind = leaves.filter((r) => r.category === 'individual')
  const port = leaves.filter((r) => r.category === 'portfolio')
  return [
    headerRow('hdr-ind', '按单项评估计提', 'individual'),
    ...ind.map(toDisplayLeaf),
    aggregateRow('sub-ind', '单项小计', 'subtotal', 'individual', sumG6BadDebtLeaves(ind)),
    headerRow('hdr-port', '信用风险组合计提', 'portfolio'),
    ...port.map(toDisplayLeaf),
    aggregateRow('sub-port', '组合小计', 'subtotal', 'portfolio', sumG6BadDebtLeaves(port)),
    aggregateRow('total', '合计', 'total', 'portfolio', sumG6BadDebtLeaves(leaves)),
  ]
}

/** 旧 ECL 行 → 滚动态 leaf */
export function migrateLegacyEclToMovement(arr: any[]): G6BadDebtLeaf[] {
  return arr.map((raw, i) => {
    const stage = String(raw.stageGroup || raw.stage || '')
    const category: G6BadDebtCategory =
      stage === '单项' || raw.category === 'individual' || raw.provisionMethod === 'individual'
        ? 'individual'
        : 'portfolio'
    const openingUnadjusted = parseNum(
      raw.openingUnadjusted ?? raw.priorProvision ?? raw.priorYearProvision ?? raw.prior_provision,
    )
    const provisionIncrease = parseNum(
      raw.provisionIncrease ?? raw.currentProvision ?? raw.currentYearProvision,
    )
    const reversal = parseNum(raw.reversal ?? raw.currentReversal ?? raw.currentYearReversal)
    const writeOff = parseNum(raw.writeOff ?? raw.currentWriteOff)
    const closingAdjFromEcl = parseNum(
      raw.closingAdjustment ?? raw.impairmentAdjustment ?? raw.balanceAdjustment,
    )
    // 若旧数据有审定坏账⑧，用其与滚动未审的差作为期末调整
    const legacyClosingAudited = parseNum(raw.adjustedProvision ?? raw.closingAudited)
    const provisional = computeG6BadDebtMovement({
      openingUnadjusted,
      openingAdjustment: parseNum(raw.openingAdjustment),
      provisionIncrease,
      otherIncrease: parseNum(raw.otherIncrease),
      reversal,
      writeOff,
      otherDecrease: parseNum(raw.otherDecrease),
      closingAdjustment: 0,
    })
    const closingAdjustment =
      legacyClosingAudited && Math.abs(legacyClosingAudited - provisional.closingUnadjusted) > 0.005
        ? round2(legacyClosingAudited - provisional.closingUnadjusted)
        : closingAdjFromEcl

    return {
      id: String(raw.id || uid(category === 'individual' ? 'ind' : 'port')),
      seq: i + 1,
      category,
      item: String(raw.item || raw.investProject || raw.invest_project || `项目${i + 1}`),
      openingUnadjusted,
      openingAdjustment: parseNum(raw.openingAdjustment),
      provisionIncrease,
      otherIncrease: parseNum(raw.otherIncrease),
      reversal,
      writeOff,
      otherDecrease: parseNum(raw.otherDecrease),
      closingAdjustment,
      reason: String(raw.reason || raw.remark || raw.conclusion || ''),
    }
  })
}

export function parseG6BadDebtStore(raw: string | null | undefined): G6BadDebtLeaf[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      if (parsed.length && (parsed[0].bookBalance != null || parsed[0].creditLossRate != null)) {
        return migrateLegacyEclToMovement(parsed)
      }
      return parsed.map((r: any, i: number) => ({
        ...emptyLeaf(
          r.category === 'individual' ? 'individual' : 'portfolio',
          r.item || `项目${i + 1}`,
          i + 1,
        ),
        ...r,
        id: String(r.id || uid('row')),
        seq: i + 1,
        openingUnadjusted: parseNum(r.openingUnadjusted),
        openingAdjustment: parseNum(r.openingAdjustment),
        provisionIncrease: parseNum(r.provisionIncrease),
        otherIncrease: parseNum(r.otherIncrease),
        reversal: parseNum(r.reversal),
        writeOff: parseNum(r.writeOff),
        otherDecrease: parseNum(r.otherDecrease),
        closingAdjustment: parseNum(r.closingAdjustment),
        reason: String(r.reason || ''),
      }))
    }
  } catch { /* ignore */ }
  return []
}

const EDITABLE_FIELDS: Array<keyof G6BadDebtLeaf> = [
  'item',
  'openingUnadjusted',
  'openingAdjustment',
  'provisionIncrease',
  'otherIncrease',
  'reversal',
  'writeOff',
  'otherDecrease',
  'closingAdjustment',
  'reason',
]

export interface UseG6BadDebtDetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  htmlData?: Ref<Record<string, any> | null>
}

export function useG6BadDebtDetail(opts: UseG6BadDebtDetailOptions) {
  const leaves = ref<G6BadDebtLeaf[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function debounceFlush(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      flushPending()
    }, 500)
  }

  function flushPending(): void {
    try {
      const items: ChecklistResponse[] = []
      for (const key of [DATA_KEY, NOTE_KEY, CONCLUSION_KEY]) {
        const it = opts.allResponses.value.get(key)
        if (it) items.push(it)
      }
      if (items.length) {
        dispatchG6SaveItems(opts.wpId.value, items)
      }
    } catch { /* silent */ }
  }

  function persist(): void {
    if (opts.isReadonly.value) return
    const json = JSON.stringify(leaves.value)
    opts.allResponses.value.set(DATA_KEY, { item_id: DATA_KEY, conclusion: json, remark: json })
    debounceFlush()
  }

  function load(): void {
    const raw =
      opts.allResponses.value.get(DATA_KEY)?.conclusion
      || opts.allResponses.value.get(DATA_KEY)?.remark
    let loaded = parseG6BadDebtStore(raw)
    if (!loaded.length) {
      const hd = opts.htmlData?.value
      const items = hd?.bad_debt_rows || hd?.badDebtDetail?.rows || hd?.rows
      if (Array.isArray(items) && items.length) {
        loaded = migrateLegacyEclToMovement(items)
      }
    }
    if (!loaded.length) {
      loaded = [
        emptyLeaf('individual', '债务人A', 1),
        emptyLeaf('portfolio', '组合1', 2),
      ]
    }
    leaves.value = loaded
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.remark || ''
  }

  const displayRows = computed(() => buildG6BadDebtDisplayRows(leaves.value))

  const individualClosingAudited = computed(
    () => sumG6BadDebtLeaves(leaves.value.filter((r) => r.category === 'individual')).closingAudited,
  )
  const portfolioClosingAudited = computed(
    () => sumG6BadDebtLeaves(leaves.value.filter((r) => r.category === 'portfolio')).closingAudited,
  )
  const totalClosingAudited = computed(() => sumG6BadDebtLeaves(leaves.value).closingAudited)

  /** 回写 G6-1 必须用期末未审，避免与 G6-1「未审+调整=审定」双重叠加 */
  const writebackDetail = computed(() => buildG6BadDebtWritebackDetail(leaves.value))
  const individualClosingUnadjusted = computed(() => writebackDetail.value.individualClosing)
  const portfolioClosingUnadjusted = computed(() => writebackDetail.value.portfolioClosing)
  const totalClosingUnadjusted = computed(() => writebackDetail.value.totalClosing)

  function updateCell(id: string, field: keyof G6BadDebtLeaf, value: string | number): void {
    if (opts.isReadonly.value) return
    if (!EDITABLE_FIELDS.includes(field)) return
    const idx = leaves.value.findIndex((r) => r.id === id)
    if (idx < 0) return
    const next = { ...leaves.value[idx], [field]: value }
    leaves.value[idx] = next
    leaves.value = [...leaves.value]
    persist()
  }

  async function addRow(category: G6BadDebtCategory = 'portfolio'): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt(
        category === 'individual' ? '请输入债务人/项目名称' : '请输入组合名称',
        category === 'individual' ? '新增单项' : '新增组合',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '名称不能为空',
        },
      )
      if (!value?.trim()) return
      const leaf = emptyLeaf(category, value.trim(), leaves.value.length + 1)
      leaves.value = [...leaves.value, leaf]
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    leaves.value = leaves.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  watch(auditNote, (val) => {
    if (opts.isReadonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceFlush()
  })
  watch(auditConclusion, (val) => {
    if (opts.isReadonly.value) return
    opts.allResponses.value.set(CONCLUSION_KEY, {
      item_id: CONCLUSION_KEY,
      conclusion: null,
      remark: val,
    })
    debounceFlush()
  })

  /** 回写 G6-1 减值准备单项/组合期末未审（不含 closingAdjustment） */
  function writebackToAdjudication(): void {
    if (opts.isReadonly.value) return
    try {
      window.dispatchEvent(
        new CustomEvent('g6:bad-debt-writeback', {
          detail: {
            individualClosing: individualClosingUnadjusted.value,
            portfolioClosing: portfolioClosingUnadjusted.value,
            totalClosing: totalClosingUnadjusted.value,
          },
        }),
      )
    } catch { /* silent */ }
  }

  function reload(): void {
    load()
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    flushPending()
  })

  return {
    leaves,
    displayRows,
    auditNote,
    auditConclusion,
    individualClosingAudited,
    portfolioClosingAudited,
    totalClosingAudited,
    individualClosingUnadjusted,
    portfolioClosingUnadjusted,
    totalClosingUnadjusted,
    updateCell,
    addRow,
    removeRow,
    writebackToAdjudication,
    reload,
  }
}

export default useG6BadDebtDetail
