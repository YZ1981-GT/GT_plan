/**
 * useK13Adjustment — K13-3 调整分录 composable
 *
 * Spec: .kiro/specs/k13-non-operating-expense/
 * Task: 4.5
 * Requirements: 6.2
 *
 * 职责：
 * - AJE/RJE 行管理（新增/删除/更新）
 * - 类别下拉：报表调整/账项调整/其他
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created' → A13 错报汇总表
 * - 双向同步 K13-1 审定表（K13-1 订阅该事件刷新 AJE/RJE 列）
 *
 * 科目：6711 营业外支出（借方/损益类）
 * ⚠️ 借方科目：借方增加=支出增加，贷方减少=冲减/红冲营业外支出
 * ⚠️ 与K12(6301贷方)方向相反！K13净影响=借方-贷方
 *
 * 事件流：
 *   K13-3 save → emit 'adjustment:created' {entryType, accountCode:'6711', amount, wpCode:'K13'}
 *   → A13 拾取 K13-3 调整
 *   → K13-1 recalc（subscribe 'adjustment:created'）→ writebackTB → substantive:adjudicated → disclosure
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useK13FormulaEngine'
import type { useK13FormData } from './useK13FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type K13AdjustmentType = 'AJE' | 'RJE'

/** 调整分录类别 */
export type K13AdjustmentCategory = '报表调整' | '账项调整' | '其他'

/** 调整分录行 */
export interface K13AdjustmentEntry {
  /** 序号 */
  index: number
  /** AJE or RJE */
  type: K13AdjustmentType
  /** 类别：报表调整/账项调整/其他 */
  category: K13AdjustmentCategory | ''
  /** 摘要/调整事项说明 */
  description: string
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
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
export interface K13BalanceStatus {
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
const ACCOUNT_CODE = '6711'
/** 底稿编码 */
const WP_CODE = 'K13'
/** item_id 前缀（legacy verbose 迁移用） */
const ITEM_PREFIX = 'K13-3'
/** 单一 JSON 持久化键（与后端 _k13_import_export._K13_SPECS["K13-3"].item_id 一致） */
const ITEM_KEY = 'K13-3-adj-entries'
/** K13-1 审定表 AJE/RJE 汇总回写键（K13-1 reconcile 消费） */
const K13_1_AJE_TOTAL = 'K13-1-aje-total'
const K13_1_RJE_TOTAL = 'K13-1-rje-total'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * K13-3 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useK13FormData 实例
 */
export function useK13Adjustment(formData: ReturnType<typeof useK13FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<K13AdjustmentEntry[]>([])
  const activeType = ref<K13AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<K13AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<K13AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<K13AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<K13BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<K13BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<K13BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /**
   * AJE 对科目6711的净影响
   * ⚠️ 6711是借方科目：借方增加=支出增加，贷方减少=冲减支出
   * 净影响 = 借方 - 贷方（正数=支出增加）
   * ⚠️ 与K12(6301贷方)方向相反！
   */
  const ajeNet6711: ComputedRef<number> = computed(() => {
    const aje = ajeEntries.value
    const debit = calcSubtotal(aje.map(e => e.debitAmount))
    const credit = calcSubtotal(aje.map(e => e.creditAmount))
    return debit - credit // 借方科目：借-贷
  })

  /**
   * RJE 对科目6711的净影响
   * 净影响 = 借方 - 贷方（正数=支出增加）
   */
  const rjeNet6711: ComputedRef<number> = computed(() => {
    const rje = rjeEntries.value
    const debit = calcSubtotal(rje.map(e => e.debitAmount))
    const credit = calcSubtotal(rje.map(e => e.creditAmount))
    return debit - credit // 借方科目：借-贷
  })

  function _calcBalance(items: K13AdjustmentEntry[]): K13BalanceStatus {
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
  function addEntry(type?: K13AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: K13AdjustmentEntry = {
      index: entries.value.length + 1,
      type: t,
      category: '',
      description: '',
      reportItem: '',
      accountName: '',
      noteItem: '',
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
    field: keyof K13AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: K13AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步K13-1 ────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   *
   * 校验：借贷平衡（Σ借方===Σ贷方）通过后才允许保存+发布。
   *
   * 事件效果：
   * - 通知 A13 审计调整汇总拾取 K13-3 的 AJE/RJE
   * - 双向同步 K13-1 审定表（K13-1 订阅该事件刷新 AJE/RJE 列）
   *
   * EventPayload 契约：
   *   {
   *     entryType: 'AJE' | 'RJE',
   *     accountCode: '6711',
   *     amount: number (AJE/RJE净影响金额),
   *     wpCode: 'K13',
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

    // 单一 JSON 数组持久化（与后端 IE item_id=K13-3-adj-entries 一致）
    // 同时回写 K13-1 审定表 AJE/RJE 汇总列（K13-1 reconcile 消费，修复回写死链）
    await saveBatch([
      { itemId: ITEM_KEY, value: _serializeEntries() },
      { itemId: K13_1_AJE_TOTAL, value: String(ajeNet6711.value) },
      { itemId: K13_1_RJE_TOTAL, value: String(rjeNet6711.value) },
    ])

    // EventBus publish 'adjustment:created'
    // ⚠️ 此事件触发两个下游：
    //   1. A13 错报汇总表拾取 K13-3 调整（通过 accountCode + wpCode 匹配）
    //   2. K13-1 订阅后刷新 AJE/RJE 列 → recalc → writebackTB → substantive:adjudicated → disclosure
    eventBus.emit('adjustment:created', {
      entryType: activeType.value,
      accountCode: ACCOUNT_CODE,
      amount: activeType.value === 'AJE' ? ajeNet6711.value : rjeNet6711.value,
      wpCode: WP_CODE,
      ajeNet: ajeNet6711.value,
      rjeNet: rjeNet6711.value,
      timestamp: Date.now(),
    })

    // 补发 a13:push-misstatement（K10-3/K9-3 范式）→ A13 错报汇总表拾取当前分录明细
    eventBus.emit('a13:push-misstatement', {
      wpCode: WP_CODE,
      accountCode: ACCOUNT_CODE,
      entryType: activeType.value,
      entries: _serializeEntries().filter(e => e.debitAmount || e.creditAmount),
      totalDebit: balance.totalDebit,
      totalCredit: balance.totalCredit,
      ajeNet: ajeNet6711.value,
      rjeNet: rjeNet6711.value,
      timestamp: Date.now(),
    })
  }

  /** 序列化分录为纯对象数组（剥离响应式代理，供持久化/事件载荷） */
  function _serializeEntries(): K13AdjustmentEntry[] {
    return entries.value.map((e, i) => ({
      index: i + 1,
      type: e.type,
      category: e.category,
      description: e.description,
      reportItem: e.reportItem,
      accountName: e.accountName,
      noteItem: e.noteItem,
      debitAmount: Number(e.debitAmount) || 0,
      creditAmount: Number(e.creditAmount) || 0,
      refIndex: e.refIndex,
      remark: e.remark,
    }))
  }

  // ─── 5. 恢复已保存分录 ────────────────────────────────────────────────

  /**
   * 从 checklist_responses 恢复已保存的分录行。
   *
   * 优先读单一 JSON 数组键 `K13-3-adj-entries`（当前格式，与后端 IE 一致）；
   * 若不存在则回退旧 verbose per-field 键 `K13-3-entry-{n}-{field}`（legacy 迁移，不丢数据）。
   */
  function restoreEntries(): void {
    entries.value = []

    // 1. 优先：单一 JSON 数组键
    const jsonItem = formData.allResponses.value.get(ITEM_KEY)
    const rawJson = jsonItem?.remark ?? jsonItem?.conclusion
    if (rawJson) {
      try {
        const parsed = JSON.parse(rawJson)
        const arr: any[] = Array.isArray(parsed)
          ? parsed
          : Array.isArray(parsed?.rows)
            ? parsed.rows
            : []
        if (arr.length > 0) {
          entries.value = arr.map((e, i) => _normalizeEntry(e, i))
          return
        }
      } catch {
        // JSON 解析失败 → 回退 legacy
      }
    }

    // 2. 回退：legacy verbose per-field 键
    _restoreLegacyEntries()
  }

  /** 归一化导入/加载的原始对象为 K13AdjustmentEntry */
  function _normalizeEntry(e: any, i: number): K13AdjustmentEntry {
    return {
      index: i + 1,
      type: (e?.type === 'RJE' ? 'RJE' : 'AJE') as K13AdjustmentType,
      category: (e?.category || '') as K13AdjustmentCategory | '',
      description: String(e?.description ?? ''),
      reportItem: String(e?.reportItem ?? ''),
      accountName: String(e?.accountName ?? ''),
      noteItem: String(e?.noteItem ?? ''),
      debitAmount: Number(e?.debitAmount) || 0,
      creditAmount: Number(e?.creditAmount) || 0,
      refIndex: String(e?.refIndex ?? ''),
      remark: String(e?.remark ?? ''),
    }
  }

  /** legacy 迁移：读旧 K13-3-entry-{n}-{field} verbose 键 */
  function _restoreLegacyEntries(): void {
    const prefix = `${ITEM_PREFIX}-entry-`
    let maxIdx = 0

    for (const [key] of formData.allResponses.value.entries()) {
      if (key.startsWith(prefix) && key.endsWith('-type')) {
        const match = key.match(/K13-3-entry-(\d+)-type/)
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
        type: (typeVal === 'RJE' ? 'RJE' : 'AJE') as K13AdjustmentType,
        category: (getVal(`${prefix}${i}-category`) || '') as K13AdjustmentCategory | '',
        description: getVal(`${prefix}${i}-desc`),
        reportItem: getVal(`${prefix}${i}-reportItem`),
        accountName: getVal(`${prefix}${i}-accountName`),
        noteItem: getVal(`${prefix}${i}-noteItem`),
        debitAmount: Number(getVal(`${prefix}${i}-debit`)) || 0,
        creditAmount: Number(getVal(`${prefix}${i}-credit`)) || 0,
        refIndex: getVal(`${prefix}${i}-ref`),
        remark: getVal(`${prefix}${i}-remark`),
      })
    }
  }

  // ─── 6. 导入导出支持 ──────────────────────────────────────────────────

  /** 导出调整分录为结构化数据（供 useK13ImportExport 使用） */
  function exportEntries(): K13AdjustmentEntry[] {
    return [...entries.value]
  }

  /** 从导入数据恢复分录（覆盖现有） */
  function importEntries(importedEntries: K13AdjustmentEntry[]): void {
    entries.value = importedEntries.map((e, i) => _normalizeEntry(e, i))
    _triggerSaveAll()
  }

  // ─── 7. 保存触发（单一 JSON 数组键，debounce 2s） ─────────────────────────

  /** 逐行编辑后触发保存：整表 JSON 序列化写入 ITEM_KEY（不再 per-field 展开） */
  function _triggerSave(_rowIndex?: number): void {
    const remark = JSON.stringify(_serializeEntries())
    debouncedSave(ITEM_KEY, { item_id: ITEM_KEY, conclusion: null, remark })
  }

  function _triggerSaveAll(): void {
    _triggerSave()
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
    ajeNet6711,
    rjeNet6711,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,

    // 恢复
    restoreEntries,

    // 导入导出
    exportEntries,
    importEntries,
  }
}

export default useK13Adjustment
