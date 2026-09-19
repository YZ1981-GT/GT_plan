/**
 * useH3RelatedParty — H3-13 关联交易 composable
 *
 * RelatedPartyRow 11列 + 差异率 + 高亮规则
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.17
 * Requirements: 13.1-13.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 关联方关系标准选项（对齐 Excel 数据验证列表） */
export const RELATED_PARTY_RELATIONSHIPS = [
  '实际控制人',
  '控股股东',
  '控股股东、实际控制人的附属企业',
  '持有5%以上股份的法人或其他组织',
  '联营企业',
  '合营企业',
  '董监高等关键管理人员',
  '其他关联方',
] as const

export type RelatedPartyRelationship = (typeof RELATED_PARTY_RELATIONSHIPS)[number]

export const TRANS_TYPES = ['出租', '购入', '处置', '转换'] as const
export type TransType = (typeof TRANS_TYPES)[number]

export interface RelatedPartyRow {
  rowId: string
  seq: number
  relatedParty: string        // 关联方
  relationship: string        // 关联关系
  transType: string           // 交易类型(出租/购入/处置/转换)
  amount: number              // 金额
  pricingMethod: string       // 定价方式/定价政策
  marketRef: number           // 市场价参考
  diffRate: number            // 差异率（公式）
  approvalDoc: boolean        // 已获取审批文件
  conclusion: string          // 审计结论
  remark: string              // 备注/支持性文档索引号
}

const ITEM_ID = 'H3-13-rp-rows'
const DIFF_WARN_THRESHOLD = 10

export function calcDiffRate(amount: number, marketRef: number): number {
  if (!marketRef || marketRef === 0) return 0
  return ((amount - marketRef) / marketRef) * 100
}

export function suggestConclusion(row: Pick<RelatedPartyRow, 'diffRate' | 'approvalDoc' | 'marketRef'>): string {
  if (!row.marketRef) return ''
  if (Math.abs(row.diffRate) > DIFF_WARN_THRESHOLD) return '不合理'
  if (Math.abs(row.diffRate) > 5) return '需关注'
  if (!row.approvalDoc) return '需关注'
  return '无异常'
}

export function useH3RelatedParty(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params
  const rows = ref<RelatedPartyRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any, idx?: number): RelatedPartyRow {
    const amount = Number(raw.amount) || 0
    const market = Number(raw.marketRef) || 0
    const diffRate = calcDiffRate(amount, market)
    const approvalDoc = raw.approvalDoc === true || raw.approvalDoc === '是' || raw.approvalDoc === 'Y'
    return {
      rowId: raw.rowId ?? `rp-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      relatedParty: raw.relatedParty ?? '',
      relationship: raw.relationship ?? '',
      transType: raw.transType ?? '',
      amount,
      pricingMethod: raw.pricingMethod ?? '',
      marketRef: market,
      diffRate,
      approvalDoc,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  /** 差异率>10%高亮行 */
  const highDiffRows = computed(() => rows.value.filter((r) => Math.abs(r.diffRate) > DIFF_WARN_THRESHOLD))

  /** 审计结论异常行（需关注/不合理） */
  const issueRows = computed(() => rows.value.filter((r) => r.conclusion === '需关注' || r.conclusion === '不合理'))

  /** 出租类交易行（应与 H3-14 勾稽） */
  const rentalRows = computed(() => rows.value.filter((r) => r.transType === '出租'))

  function addRow(): void {
    rows.value.push(_normalize({ seq: rows.value.length + 1 }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(index: number, field: keyof RelatedPartyRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  /**
   * 行变更：组件已 v-model 就地修改 row（同引用），此处重算差异率并持久化。
   */
  function updateRow(index: number, _row?: any): void {
    const row = rows.value[index]
    if (!row) return
    _recalcRow(row)
    if (!row.conclusion) {
      const suggested = suggestConclusion(row)
      if (suggested) row.conclusion = suggested
    }
    _persist()
  }

  function _recalcRow(row: RelatedPartyRow): void {
    row.amount = Number(row.amount) || 0
    row.marketRef = Number(row.marketRef) || 0
    row.diffRate = calcDiffRate(row.amount, row.marketRef)
  }

  /** 金额合计 */
  const totalAmount = computed(() => rows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0))

  /** 生成审计说明草稿 */
  function draftAuditNote(): string {
    const lines: string[] = []
    lines.push('一、关联方识别与范围')
    lines.push(`本期共识别投资性房地产相关关联交易 ${rows.value.length} 笔，金额合计 ${totalAmount.value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元。`)
    if (rentalRows.value.length) {
      lines.push(`其中出租类 ${rentalRows.value.length} 笔，应与 H3-14 租金收入测算表勾稽。`)
    }
    lines.push('')
    lines.push('二、定价公允性核查')
    if (highDiffRows.value.length) {
      lines.push(`差异率超过10%的交易 ${highDiffRows.value.length} 笔：`)
      highDiffRows.value.forEach((r) => {
        lines.push(`  - ${r.relatedParty}（${r.transType}）：金额 ${r.amount}，市场价参考 ${r.marketRef}，差异率 ${r.diffRate.toFixed(1)}%`)
      })
    } else {
      lines.push('经与市场价参考比对，未发现差异率超过10%的交易。')
    }
    lines.push('')
    lines.push('三、程序执行')
    lines.push('对于合并范围外关联交易，已核对合同、发票等有关文件，了解交易目的、价格和条件，确认关联交易真实、公允。')
    if (issueRows.value.length) {
      lines.push('')
      lines.push(`四、关注事项（${issueRows.value.length} 笔需进一步说明）`)
      issueRows.value.forEach((r) => {
        lines.push(`  - ${r.relatedParty}：${r.conclusion}${r.remark ? `（${r.remark}）` : ''}`)
      })
    }
    return lines.join('\n')
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows,
    highDiffRows,
    issueRows,
    rentalRows,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    totalAmount,
    draftAuditNote,
    loadRows,
    ITEM_ID,
  }
}

export default useH3RelatedParty
