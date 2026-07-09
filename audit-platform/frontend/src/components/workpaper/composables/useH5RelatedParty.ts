/**
 * useH5RelatedParty — H5-17 关联交易 composable
 *
 * 16列, 价差率自动计算+异常高亮
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 8.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcPriceDiffRate, calcSubtotal } from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPartyRow {
  rowId: string
  seq: number
  relatedParty: string          // 关联方
  relationship: string          // 关联关系
  transType: string             // 交易类型(购买/出售/租赁/服务)
  assetName: string             // 资产名称
  oilField: string              // 油田
  transAmount: number           // 交易金额
  transPrice: number            // 交易价格(单价)
  marketPrice: number           // 市场价格
  priceDiffRate: number         // 价差率(%) - 公式
  isAbnormal: boolean           // 异常标记(价差率>10%)
  pricingBasis: string          // 定价依据
  approvalDoc: string           // 审批文件
  conclusion: string            // 检查结论
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H5-17'
/** 价差率异常阈值(%) */
const ABNORMAL_THRESHOLD = 10

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5RelatedParty(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const rows = ref<RelatedPartyRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const raw = allResponses.value.get(`${ITEM_PREFIX}-rows`)?.remark
    if (raw) {
      try { rows.value = (JSON.parse(raw) ?? []).map(_normalize) } catch { rows.value = [] }
    } else { rows.value = [] }
    auditNote.value = (allResponses.value.get(`${ITEM_PREFIX}-audit-note`)?.remark ?? '') as string
    auditConclusion.value = (allResponses.value.get(`${ITEM_PREFIX}-audit-conclusion`)?.remark ?? '') as string
  }

  function _normalize(raw: any): RelatedPartyRow {
    const transPrice = Number(raw.transPrice) || 0
    const marketPrice = Number(raw.marketPrice) || 0
    const priceDiffRate = calcPriceDiffRate(transPrice, marketPrice)
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: Number(raw.seq) || 0,
      relatedParty: raw.relatedParty ?? '',
      relationship: raw.relationship ?? '',
      transType: raw.transType ?? '',
      assetName: raw.assetName ?? '',
      oilField: raw.oilField ?? '',
      transAmount: Number(raw.transAmount) || 0,
      transPrice,
      marketPrice,
      priceDiffRate,
      isAbnormal: Math.abs(priceDiffRate) > ABNORMAL_THRESHOLD,
      pricingBasis: raw.pricingBasis ?? '',
      approvalDoc: raw.approvalDoc ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalTransAmount = computed(() => calcSubtotal(rows.value.map((r) => r.transAmount)))
  const abnormalRows = computed(() => rows.value.filter((r) => r.isAbnormal))
  const abnormalCount = computed(() => abnormalRows.value.length)

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(relatedParty: string): void {
    rows.value.push({
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1, relatedParty,
      relationship: '', transType: '', assetName: '', oilField: '',
      transAmount: 0, transPrice: 0, marketPrice: 0,
      priceDiffRate: 0, isAbnormal: false,
      pricingBasis: '', approvalDoc: '', conclusion: '', remark: '',
    })
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowId: string, field: keyof RelatedPartyRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 重算价差率
    if (field === 'transPrice' || field === 'marketPrice') {
      row.priceDiffRate = calcPriceDiffRate(row.transPrice, row.marketPrice)
      row.isAbnormal = Math.abs(row.priceDiffRate) > ABNORMAL_THRESHOLD
    }
    _persist()
  }

  function _persist(): void { onSave?.(`${ITEM_PREFIX}-rows`, rows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows, auditNote, auditConclusion,
    totalTransAmount, abnormalRows, abnormalCount,
    addRow, removeRow, updateCell, saveNote, saveConclusion,
  }
}
