/**
 * useK12Adjustment — K12-3 调整分录 composable
 *
 * Spec: .kiro/specs/k12-non-operating-income/
 * Task: 6.2
 * Requirements: 6.2
 *
 * 职责：
 * - AJE/RJE 行管理（新增/删除/更新）
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created' → A13 错报汇总表
 * - 双向同步 K12-1 审定表（K12-1 订阅该事件刷新 AJE/RJE 列）
 *
 * 科目：6301 营业外收入（贷方/损益类）
 * ⚠️ 贷方科目：贷方增加=调增营业外收入，借方减少=冲减营业外收入
 *
 * 事件流：
 *   K12-3 save → emit 'adjustment:created' {entryType, accountCode:'6301', amount, wpCode:'K12'}
 *   → A13 拾取 K12-3 调整
 *   → K12-1 recalc（subscribe 'adjustment:created'）→ writebackTB → substantive:adjudicated → disclosure
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useK12FormulaEngine'
import type { useK12FormData } from './useK12FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type K12AdjustmentType = 'AJE' | 'RJE'

/** 调整分录行 */
export interface K12AdjustmentEntry {
  /** 序号 */
  index: number
  /** AJE or RJE */
  type: K12AdjustmentType
  /** 摘要/调整事项说明 */
  description: string
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 索引号 */
  refIndex: string
  /** 备注 */
  remark: string
}

/** 借贷平衡状态 */
export interface K12BalanceStatus {
  /** 借方合计 */
  totalDebit: number
  /** 贷方合计 */
  totalCredit: number
  /** 差额 */
  diff: number
  /** 是否平衡（差额绝对值≤0.01） */
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 平衡阈值 */
const BALANCE_THRESHOLD = 0.01
/** 科目编码 */
const ACCOUNT_CODE = '6301'
/** 底稿编码 */
const WP_CODE = 'K12'
/** item_id 前缀（legacy per-field 键仍用它做回退读） */
const ITEM_PREFIX = 'K12-3'
/**
 * 单一存储键（JSON 数组，存 remark 列）
 *
 * spec: adjustment-import-export-contract / Task 3.1
 * 迁移前为 per-field 键 `K12-3-entry-{n}-{field}`，与后端导入导出（写 `K12-3-rows` JSON 数组）
 * 结构级不匹配 → 底稿通道导入的数据前端永远读不到。现收敛为单键 JSON 数组：
 *   - 写：只写 ROWS_KEY（不再写 per-field 键）
 *   - 读：优先解析 ROWS_KEY；为空/解析失败 → 回退 per-field 重建（历史数据不丢），
 *         重建后首次保存自然收敛为 JSON；旧 per-field 键不主动删除
 */
export const K12_ADJ_ROWS_KEY = 'K12-3-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * K12-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useK12FormData 实例
 */
export function useK12Adjustment(formData: ReturnType<typeof useK12FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<K12AdjustmentEntry[]>([])
  const activeType = ref<K12AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<K12AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<K12AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<K12AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<K12BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<K12BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<K12BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目6301的净影响
   * ⚠️ 6301是贷方科目：贷方增加=调增营业外收入，借方减少=冲减
   * 净影响 = 贷方 - 借方（正数=调增收入）
   */
  const ajeNet6301: ComputedRef<number> = computed(() => {
    const aje6301 = ajeEntries.value.filter(e => e.accountCode === ACCOUNT_CODE)
    const credit = calcSubtotal(aje6301.map(e => e.creditAmount))
    const debit = calcSubtotal(aje6301.map(e => e.debitAmount))
    return credit - debit // 贷方科目：贷-借
  })

  /**
   * RJE 对科目6301的净影响
   * 净影响 = 贷方 - 借方（正数=调增收入）
   */
  const rjeNet6301: ComputedRef<number> = computed(() => {
    const rje6301 = rjeEntries.value.filter(e => e.accountCode === ACCOUNT_CODE)
    const credit = calcSubtotal(rje6301.map(e => e.creditAmount))
    const debit = calcSubtotal(rje6301.map(e => e.debitAmount))
    return credit - debit // 贷方科目：贷-借
  })

  function _calcBalance(items: K12AdjustmentEntry[]): K12BalanceStatus {
    const totalDebit = parseFloat(calcSubtotal(items.map(e => e.debitAmount)).toFixed(2))
    const totalCredit = parseFloat(calcSubtotal(items.map(e => e.creditAmount)).toFixed(2))
    const diff = parseFloat((totalDebit - totalCredit).toFixed(2))
    return {
      totalDebit,
      totalCredit,
      diff,
      isBalanced: Math.abs(diff) <= BALANCE_THRESHOLD,
    }
  }

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /** 新增调整分录行 */
  function addEntry(type?: K12AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: K12AdjustmentEntry = {
      index: entries.value.length + 1,
      type: t,
      description: '',
      accountCode: '',
      accountName: '',
      debitAmount: 0,
      creditAmount: 0,
      refIndex: '',
      remark: '',
    }
    entries.value.push(newEntry)
    _triggerSave(entries.value.length - 1)
  }

  /** 删除分录行 */
  function removeEntry(index: number): void {
    if (index < 0 || index >= entries.value.length) return
    entries.value.splice(index, 1)
    // 重新编号
    entries.value.forEach((e, i) => { e.index = i + 1 })
    _triggerSaveAll()
  }

  /** 更新分录行字段 */
  function updateEntry(
    index: number,
    field: keyof K12AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: K12AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步K12-1 ────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   *
   * 校验：借贷平衡（Σ借方===Σ贷方）通过后才允许保存+发布。
   *
   * 事件效果：
   * - 通知 A13 审计调整汇总拾取 K12-3 的 AJE/RJE
   * - 双向同步 K12-1 审定表（K12-1 订阅该事件刷新 AJE/RJE 列）
   *
   * EventPayload 契约：
   *   {
   *     entryType: 'AJE' | 'RJE',
   *     accountCode: '6301',
   *     amount: number (AJE/RJE净影响金额),
   *     wpCode: 'K12',
   *     ajeNet: number,
   *     rjeNet: number,
   *     timestamp: number
   *   }
   */
  async function saveAndPublish(): Promise<void> {
    // 校验借贷平衡
    const balance = currentBalance.value
    if (!balance.isBalanced) {
      return // 不平衡时不允许发布
    }

    // 保存到 checklist_responses（单键 JSON 数组，与后端导入导出同结构）
    await saveBatch([{ itemId: K12_ADJ_ROWS_KEY, value: _serializeEntries() }])

    // EventBus publish 'adjustment:created'
    // ⚠️ 此事件触发两个下游：
    //   1. A13 错报汇总表拾取 K12-3 调整（通过 accountCode + wpCode 匹配）
    //   2. K12-1 订阅后刷新 AJE/RJE 列 → recalc → writebackTB → substantive:adjudicated → disclosure
    eventBus.emit('adjustment:created', {
      entryType: activeType.value,
      accountCode: ACCOUNT_CODE,
      amount: activeType.value === 'AJE' ? ajeNet6301.value : rjeNet6301.value,
      wpCode: WP_CODE,
      ajeNet: ajeNet6301.value,
      rjeNet: rjeNet6301.value,
      timestamp: Date.now(),
    })
  }

  // ─── 5. 恢复已保存分录 ────────────────────────────────────────────────

  /**
   * 从 checklist_responses 恢复已保存的分录行
   *
   * 优先读单键 JSON 数组（K12-3-rows，与后端导入导出同结构）；
   * 为空或解析失败 → 回退 legacy per-field 键 `K12-3-entry-{n}-{field}` 重建（历史数据不丢）。
   */
  function restoreEntries(): void {
    const raw = formData.allResponses.value.get(K12_ADJ_ROWS_KEY)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const rows = Array.isArray(parsed)
          ? parsed
          : (Array.isArray(parsed?.rows) ? parsed.rows : null)
        if (rows && rows.length) {
          entries.value.push(...rows.map((r: any, i: number) => _normalizeEntry(r, i)))
          return
        }
        if (rows) return // 显式空数组：用户已清空，不再回退旧 per-field 数据
      } catch {
        // JSON 解析失败 → 回退 per-field 重建，绝不清空用户数据
        console.warn('[useK12Adjustment] K12-3-rows JSON 解析失败，回退 per-field 重建')
      }
    }
    _restoreLegacyEntries()
  }

  /** 单行归一（导入/历史数据可能缺字段或类型为字符串） */
  function _normalizeEntry(r: any, i: number): K12AdjustmentEntry {
    const rawType = String(r?.type ?? '').toUpperCase()
    return {
      index: Number(r?.index) || i + 1,
      type: (rawType === 'RJE' ? 'RJE' : 'AJE') as K12AdjustmentType,
      description: String(r?.description ?? ''),
      accountCode: String(r?.accountCode ?? ''),
      accountName: String(r?.accountName ?? ''),
      debitAmount: Number(r?.debitAmount) || 0,
      creditAmount: Number(r?.creditAmount) || 0,
      refIndex: String(r?.refIndex ?? ''),
      remark: String(r?.remark ?? ''),
    }
  }

  /** legacy 回退：per-field 键 `K12-3-entry-{n}-{field}` 重建 */
  function _restoreLegacyEntries(): void {
    const prefix = `${ITEM_PREFIX}-entry-`
    let maxIdx = 0

    for (const [key] of formData.allResponses.value.entries()) {
      if (key.startsWith(prefix) && key.endsWith('-type')) {
        const match = key.match(/K12-3-entry-(\d+)-type/)
        if (match) {
          const n = parseInt(match[1])
          if (n > maxIdx) maxIdx = n
        }
      }
    }

    if (maxIdx === 0) return

    const getVal = (itemId: string): string => {
      const item = formData.allResponses.value.get(itemId)
      return item?.remark ?? ''
    }

    for (let i = 1; i <= maxIdx; i++) {
      const typeVal = getVal(`${prefix}${i}-type`)
      if (!typeVal) continue // 跳过无效条目

      entries.value.push({
        index: i,
        type: (typeVal === 'RJE' ? 'RJE' : 'AJE') as K12AdjustmentType,
        description: getVal(`${prefix}${i}-desc`),
        accountCode: getVal(`${prefix}${i}-code`),
        accountName: getVal(`${prefix}${i}-name`),
        debitAmount: Number(getVal(`${prefix}${i}-debit`)) || 0,
        creditAmount: Number(getVal(`${prefix}${i}-credit`)) || 0,
        refIndex: getVal(`${prefix}${i}-ref`),
        remark: getVal(`${prefix}${i}-remark`),
      })
    }
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  /** 序列化全部分录为 JSON 字符串（与后端 K12-3 Sheet_Spec field_keys 同字段名） */
  function _serializeEntries(): string {
    return JSON.stringify(entries.value.map((e) => ({ ...e })))
  }

  /** 持久化：只写单键 JSON 数组（不再写 legacy per-field 键） */
  function _persistEntries(): void {
    debouncedSave(K12_ADJ_ROWS_KEY, {
      item_id: K12_ADJ_ROWS_KEY,
      conclusion: null,
      remark: _serializeEntries(),
    })
  }

  function _triggerSave(_rowIndex: number): void {
    _persistEntries()
  }

  function _triggerSaveAll(): void {
    _persistEntries()
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    entries,
    activeType,

    // 计算
    filteredEntries,
    ajeEntries,
    rjeEntries,
    ajeBalance,
    rjeBalance,
    currentBalance,
    ajeNet6301,
    rjeNet6301,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,

    // 恢复
    restoreEntries,
  }
}

export default useK12Adjustment
