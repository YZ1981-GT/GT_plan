/**
 * useL5RelatedParty — L5-6 关联方及交易检查 composable
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.4
 * Requirements: 5.1
 *
 * 职责：
 * - 关联方名称/关系/交易金额/定价依据/公允性评价
 * - 净额计算：长期应付款-未确认融资费用=账面余额
 * - 动态行管理
 *
 * 科目：2701 长期应付款 + 未确认融资费用 → 净额
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcNetPayable, calcSubtotal } from './useL5FormulaEngine'
import type { useL5FormData, ChecklistResponse } from './useL5FormData'

/** 🔴 P0 修复：JSON 存储键（此前无 hydration + 保存仅序列化字段子集 → 刷新数据丢失） */
const ITEM_ROWS = 'L5-L5-6-related-party-rows'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 关联方关系类型 */
export type L5RelationshipType =
  | '母公司'
  | '子公司'
  | '联营企业'
  | '合营企业'
  | '关键管理人员'
  | '其他关联方'

/** 公允性评价等级 */
export type L5FairnessLevel = '公允' | '基本公允' | '不公允' | '待评估'

/** 关联方检查行数据 */
export interface L5RelatedPartyRow {
  /** 行唯一标识 */
  key: string
  /** 关联方名称 */
  partyName: string
  /** 关联关系 */
  relationship: L5RelationshipType | string
  /** 长期应付款余额（面值） */
  payableBalance: number
  /** 未确认融资费用余额 */
  unrecognizedBalance: number
  /** 账面余额（净额=应付款-未确认） */
  netBalance: number
  /** 交易金额（本期发生额） */
  transactionAmount: number
  /** 定价依据 */
  pricingBasis: string
  /** 公允性评价 */
  fairnessLevel: L5FairnessLevel
  /** 公允性说明 */
  fairnessNote: string
  /** 备注 */
  remark: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L5-6 关联方及交易检查业务逻辑
 *
 * @param formData 由调用方传入的 useL5FormData 实例
 * @param relatedPartyRows reactive ref of rows
 */
export function useL5RelatedParty(
  formData: ReturnType<typeof useL5FormData>,
  relatedPartyRows: Ref<L5RelatedPartyRow[]>,
) {
  const { allResponses, debouncedSave } = formData

  // ─── 0. Hydration ────────────────────────────────────────────────────
  function hydrate(): void {
    const raw = allResponses.value.get(ITEM_ROWS)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) relatedPartyRows.value = parsed
    } catch { /* ignore */ }
  }
  hydrate()
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (v) => { if (v && relatedPartyRows.value.length === 0) hydrate() },
  )

  // ─── 1. 计算属性 ──────────────────────────────────────────────────────

  /** 各行净额自动计算：长期应付款-未确认融资费用=账面余额 */
  const computedRows: ComputedRef<L5RelatedPartyRow[]> = computed(() => {
    return relatedPartyRows.value.map(row => ({
      ...row,
      netBalance: calcNetPayable(row.payableBalance, row.unrecognizedBalance),
    }))
  })

  /** 关联方交易金额合计 */
  const totalTransactionAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(relatedPartyRows.value.map(r => r.transactionAmount))
  })

  /** 关联方净额合计 */
  const totalNetBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.netBalance))
  })

  /** 不公允项数量（需关注） */
  const unfairCount: ComputedRef<number> = computed(() => {
    return relatedPartyRows.value.filter(r => r.fairnessLevel === '不公允').length
  })

  /** 待评估项数量 */
  const pendingCount: ComputedRef<number> = computed(() => {
    return relatedPartyRows.value.filter(r => r.fairnessLevel === '待评估').length
  })

  // ─── 2. 按关联关系分组统计 ────────────────────────────────────────────

  /** 按关联关系分组的交易金额合计 */
  const groupByRelationship: ComputedRef<Record<string, number>> = computed(() => {
    const result: Record<string, number> = {}
    for (const row of relatedPartyRows.value) {
      const rel = row.relationship || '未分类'
      result[rel] = (result[rel] || 0) + row.transactionAmount
    }
    return result
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增关联方检查行
   */
  async function addRow(): Promise<void> {
    try {
      const { value: partyName } = await ElMessageBox.prompt(
        '请输入关联方名称',
        '新增关联方检查',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX投资有限公司',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '关联方名称不能为空'
            return true
          },
        },
      )

      const key = `l5-rp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: L5RelatedPartyRow = {
        key,
        partyName: partyName?.trim() || '',
        relationship: '其他关联方',
        payableBalance: 0,
        unrecognizedBalance: 0,
        netBalance: 0,
        transactionAmount: 0,
        pricingBasis: '',
        fairnessLevel: '待评估',
        fairnessNote: '',
        remark: '',
      }

      relatedPartyRows.value.push(newRow)
      _triggerSave()
    } catch {
      // 用户取消
    }
  }

  /** 删除指定行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= relatedPartyRows.value.length) return
    relatedPartyRows.value.splice(index, 1)
    _triggerSave()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof L5RelatedPartyRow, value: string | number): void {
    if (index < 0 || index >= relatedPartyRows.value.length) return
    const row = relatedPartyRows.value[index] as any
    row[field] = value

    // 如果是金额字段，重算净额
    if (['payableBalance', 'unrecognizedBalance'].includes(field)) {
      row.netBalance = calcNetPayable(row.payableBalance, row.unrecognizedBalance)
    }

    _triggerSave()
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(): void {
    // 序列化完整行数据（含所有字段）+ 保证 netBalance 新鲜，供持久化+CrossSheet勾稽
    const payload = relatedPartyRows.value.map(r => ({
      ...r,
      netBalance: calcNetPayable(r.payableBalance, r.unrecognizedBalance),
    }))
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(payload) } as Partial<ChecklistResponse>)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算属性
    computedRows,
    totalTransactionAmount,
    totalNetBalance,
    unfairCount,
    pendingCount,

    // 分组统计
    groupByRelationship,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL5RelatedParty
