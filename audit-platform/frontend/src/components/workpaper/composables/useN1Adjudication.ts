/**
 * useN1Adjudication — 审定表N1-1 逻辑层
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.4
 * Requirements: 2.1-2.9
 *
 * 职责：
 * - 9大类暂时性差异项目行管理（资产减值准备/可弥补亏损/内部交易未实现利润/公允价值变动/预提费用/递延收益/合同负债/股份支付/其他）
 * - 列结构：期初(未审/AJE/RJE/审定) + 期末(未审/AJE/RJE/审定) + 比较(变动额×2/变动率×2) + 原因分析
 * - 公式：审定数=未审+AJE+RJE；资产类期末=期初+借-贷
 * - 交叉验证：vs N1-2明细合计（useN1CrossSheet）
 * - TB回写：审定数变化 → trial_balance 1811期末余额
 * - 审计说明+结论
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！期末余额=期初+借-贷）
 */
import { ref, computed, watch, nextTick, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
  calcChangeProportion,
  parseNum,
} from './useN1FormulaEngine'
import { deriveDisclosureDetailRows, deriveDisclosureLossRows } from './useN1DisclosureSource'
import type { useN1FormData } from './useN1FormData'
import type { useN1CrossSheet } from './useN1CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * 审定表行分类（对齐致同源模板 N1-1 审定表 A7~A13 固定7类资产侧暂时性差异）
 * 源模板顺序：资产减值准备/可抵扣亏损/内部交易未实现利润/公允价值变动/租赁负债/
 *            购入摊销年限小于税法规定的资产/其他
 */
export type N1AdjudicationCategory =
  | '资产减值准备'
  | '可抵扣亏损'
  | '内部交易未实现利润'
  | '公允价值变动'
  | '租赁负债'
  | '购入摊销年限小于税法规定的资产'
  | '其他'

/** 审定表单行数据（可编辑字段） */
export interface N1AdjudicationRow {
  /** 暂时性差异项目分类 */
  category: N1AdjudicationCategory
  /** 期初未审数 */
  beginUnadjusted: number
  /** 期初AJE */
  beginAje: number
  /** 期初RJE */
  beginRje: number
  /** 期末未审数 */
  endUnadjusted: number
  /** 期末AJE */
  endAje: number
  /** 期末RJE */
  endRje: number
  /** 原因分析（文本） */
  reason: string
}

/** 审定表行计算结果 */
export interface N1AdjudicationComputed extends N1AdjudicationRow {
  /** 期初审定数 = beginUnadjusted + beginAje + beginRje */
  beginAudited: number
  /** 期末审定数 = endUnadjusted + endAje + endRje */
  endAudited: number
  /** 变动额（未审）= 期末未审 - 期初未审 */
  changeUnadjusted: number
  /** 变动额（审定）= 期末审定 - 期初审定 */
  changeAudited: number
  /** 变动率（未审）*/
  changeRateUnadjusted: number
  /** 变动率（审定）*/
  changeRateAudited: number
}

/** 审定表合计行 */
export interface N1AdjudicationTotals {
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  changeUnadjusted: number
  changeAudited: number
}

export interface UseN1AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  formData: ReturnType<typeof useN1FormData>
  crossSheet?: ReturnType<typeof useN1CrossSheet>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 源模板 N1-1 审定表固定7类资产侧暂时性差异项目（A7~A13） */
export const N1_ADJUDICATION_CATEGORIES: N1AdjudicationCategory[] = [
  '资产减值准备',
  '可抵扣亏损',
  '内部交易未实现利润',
  '公允价值变动',
  '租赁负债',
  '购入摊销年限小于税法规定的资产',
  '其他',
]

const ITEM_PREFIX = 'N1-1-adj'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN1Adjudication(options: UseN1AdjudicationOptions) {
  const { allResponses, formData } = options

  // ─── 1. 数据行（从 allResponses 恢复或初始化） ───────────────────────────

  const rows = ref<N1AdjudicationRow[]>(_initRows())

  function _initRows(): N1AdjudicationRow[] {
    return N1_ADJUDICATION_CATEGORIES.map((cat, i) => {
      const stored = allResponses.value.get(`${ITEM_PREFIX}-${i}`)
      if (stored?.conclusion) {
        try {
          return { category: cat, ...JSON.parse(stored.conclusion) }
        } catch { /* fallback */ }
      }
      return _emptyRow(cat)
    })
  }

  function _emptyRow(category: N1AdjudicationCategory): N1AdjudicationRow {
    return {
      category,
      beginUnadjusted: 0,
      beginAje: 0,
      beginRje: 0,
      endUnadjusted: 0,
      endAje: 0,
      endRje: 0,
      reason: '',
    }
  }

  // ─── 1b. 异步 hydrate（formData.loadData 是异步，setup 阶段 allResponses 为空） ───
  // 铁律：rows 在 setup 同步初始化时 allResponses 尚未加载完成，
  //       必须在 allResponses 首次填充后重新 hydrate，否则刷新后数据全空、
  //       且用户一编辑就以空值覆盖持久化（数据丢失）。
  let _hydrated = false
  /** hydrate 期间抑制 TB 自动回写（避免用刚加载的值触发回写+事件） */
  let _suppressWriteback = true

  function _hasStoredRows(): boolean {
    for (let i = 0; i < N1_ADJUDICATION_CATEGORIES.length; i++) {
      if (allResponses.value.get(`${ITEM_PREFIX}-${i}`)?.conclusion) return true
    }
    return false
  }

  watch(
    allResponses,
    () => {
      if (_hydrated) return
      if (!_hasStoredRows()) return
      rows.value = _initRows()
      _hydrated = true
      // hydrate 后同步一次合计（供 crossSheet / 下游 N5 读取）
      _syncTotals()
      nextTick(() => {
        _suppressWriteback = false
      })
    },
    { immediate: true },
  )

  // 无历史数据（新底稿）时也应放开自动回写
  nextTick(() => {
    if (!_hydrated) _suppressWriteback = false
  })

  // ─── 2. 计算属性：公式列自动计算 ──────────────────────────────────────────

  const computedRows: ComputedRef<N1AdjudicationComputed[]> = computed(() => {
    return rows.value.map((row) => {
      const beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
      const endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
      const changeUnadjusted = parseNum(row.endUnadjusted) - parseNum(row.beginUnadjusted)
      const changeAudited = endAudited - beginAudited
      return {
        ...row,
        beginAudited,
        endAudited,
        changeUnadjusted,
        changeAudited,
        changeRateUnadjusted: calcChangeProportion(changeUnadjusted, row.beginUnadjusted),
        changeRateAudited: calcChangeProportion(changeAudited, beginAudited),
      }
    })
  })

  // ─── 3. 合计行 ─────────────────────────────────────────────────────────

  const totals: ComputedRef<N1AdjudicationTotals> = computed(() => {
    const r = computedRows.value
    const beginAudited = calcSubtotal(r.map(x => x.beginAudited))
    const endAudited = calcSubtotal(r.map(x => x.endAudited))
    return {
      beginUnadjusted: calcSubtotal(r.map(x => x.beginUnadjusted)),
      beginAje: calcSubtotal(r.map(x => x.beginAje)),
      beginRje: calcSubtotal(r.map(x => x.beginRje)),
      beginAudited,
      endUnadjusted: calcSubtotal(r.map(x => x.endUnadjusted)),
      endAje: calcSubtotal(r.map(x => x.endAje)),
      endRje: calcSubtotal(r.map(x => x.endRje)),
      endAudited,
      changeUnadjusted: calcSubtotal(r.map(x => x.changeUnadjusted)),
      changeAudited: endAudited - beginAudited,
    }
  })

  // ─── 3b. 与试算平衡表核对（科目1811 期末余额） ──────────────────────────

  /**
   * 审定合计 vs 试算平衡表（tb_balance 科目1811 期末余额）。
   *
   * 铁律：审定表必须有「试算平衡表数 / 差异数」核对，否则回写 TB 没有反向校验。
   * TB 种子来源：后端 render-config 的 html_data.trial_balance（active dataset + 叶子口径）。
   */
  const tbReconcile: ComputedRef<{
    tbEndBalance: number
    auditedEndTotal: number
    diff: number
    isMatch: boolean
    hasTb: boolean
  }> = computed(() => {
    const tbEndBalance = parseNum(formData.tbSeed.value?.endBalance)
    const auditedEndTotal = totals.value.endAudited
    const diff = parseFloat((auditedEndTotal - tbEndBalance).toFixed(2))
    return {
      tbEndBalance,
      auditedEndTotal,
      diff,
      isMatch: Math.abs(diff) < 0.01,
      // TB 未取到数（全 0）时不产生误导性告警
      hasTb: tbEndBalance !== 0,
    }
  })

  // ─── 4. 行操作 ─────────────────────────────────────────────────────────

  /**
   * 从 N1-2 明细表带入未审数（按暂时性差异分类聚合），保留手工 AJE/RJE。
   *
   * 口径：期初未审 = Σ(期初暂时性差异×期初税率)，期末未审 = Σ(期末可抵扣差异×期末税率)，
   * 与 N1-2 明细同一 engine（useN1DisclosureSource.deriveDisclosureDetailRows）。
   * 明细分类不属于审定表 7 类时归入「其他」。
   *
   * @returns 带入的明细行数（0 表示 N1-2 无数据）
   */
  function pullFromDetail(): number {
    const detailRows = deriveDisclosureDetailRows(allResponses.value)
    if (detailRows.length === 0) return 0

    const beginByCat = new Map<string, number>()
    const endByCat = new Map<string, number>()
    for (const r of detailRows) {
      const cat = (N1_ADJUDICATION_CATEGORIES as string[]).includes(r.category)
        ? r.category
        : '其他'
      beginByCat.set(cat, (beginByCat.get(cat) ?? 0) + r.beginDeferredTax)
      endByCat.set(cat, (endByCat.get(cat) ?? 0) + r.endDeferredTax)
    }

    // 🔴 只覆盖「明细表里确实出现过的分类」。
    // 此前无条件写 0：明细未涉及的分类（如租赁负债/购入摊销年限小于税法规定的资产）
    // 上手工录入的未审数会被静默清零（确认框只说覆盖未审数，未提示清零）。
    rows.value.forEach((row, i) => {
      const touched = beginByCat.has(row.category) || endByCat.has(row.category)
      if (!touched) return
      row.beginUnadjusted = parseFloat((beginByCat.get(row.category) ?? 0).toFixed(2))
      row.endUnadjusted = parseFloat((endByCat.get(row.category) ?? 0).toFixed(2))
      _persistRow(i)
    })
    _syncTotals()
    return detailRows.length
  }

  /**
   * 从四表库带入未审数（tb_balance 科目 1811 子科目按暂时性差异类别归集，
   * 后端 `_build_adjudication_prefill` 预填，经 render-config → `formData.adjudicationPrefill`）。
   *
   * 口径：子科目期初余额 → 期初未审数，期末余额 → 期末未审数（1811 借方/资产类直取）。
   * 只覆盖预填里出现的类别（其余类别的手工录入不清零），保留手工 AJE/RJE。
   *
   * @returns 带入的类别数（0 表示四表库无 1811 子科目数据 / 只有父级 1811 无法分类）
   */
  function pullFromTB(): number {
    const prefill = formData.adjudicationPrefill?.value || {}
    const cats = Object.keys(prefill)
    if (cats.length === 0) return 0
    let touched = 0
    rows.value.forEach((row, i) => {
      const src = prefill[row.category]
      if (!src) return
      row.beginUnadjusted = parseFloat((Number(src.opening) || 0).toFixed(2))
      row.endUnadjusted = parseFloat((Number(src.closing) || 0).toFixed(2))
      _persistRow(i)
      touched++
    })
    _syncTotals()
    return touched
  }

  /**
   * 从 N1-5 亏损检查表带入「可抵扣亏损」分类行的期末未审数（= 可确认递延所得税资产合计）。
   *
   * 🔴 只写该一行，不动其他分类（不清零）；届满行由 N1-5 侧判定后不产生可确认额。
   * 审定表口径是「递延所得税资产金额」，故带入的是可确认递延税资产而非亏损本金。
   *
   * @param auditYear 审计年度（届满判定用，禁用当前自然年）
   * @returns 带入金额；N1-5 无数据时返回 null（调用方据此提示）
   */
  function pullLossFromN15(auditYear: number): number | null {
    // 优先读新键 N1-5-rows（新模型 useN1LossCheck，spec n1-loss-check-source-alignment Task 6.2）
    const newKeyEntry = allResponses.value.get('N1-5-rows')
    let v2Rows: any[] = []
    if (newKeyEntry) {
      const raw = typeof newKeyEntry === 'string' ? newKeyEntry : newKeyEntry?.conclusion
      if (typeof raw === 'string' && raw) {
        try { v2Rows = JSON.parse(raw) } catch { /* fall through */ }
      }
      if (!Array.isArray(v2Rows)) v2Rows = []
    }

    let recognizable: number
    if (v2Rows.length > 0) {
      // 新模型：Σ effectiveRecognized × taxRate（非届满行）
      let total = 0
      for (const row of v2Rows) {
        const expiryYear = Number(row.expiryYear) || 0
        if (expiryYear < auditYear) continue // expired → effectiveRecognized = 0
        const recognized = Number(row.recognizedAmount) || 0
        const taxRate = Number(row.taxRate) || 0.25
        total += recognized * taxRate
      }
      recognizable = parseFloat(total.toFixed(2))
    } else {
      // 回退旧键（legacy 兼容）
      const lossRows = deriveDisclosureLossRows(allResponses.value, auditYear)
      if (lossRows.length === 0) return null
      recognizable = parseFloat(
        lossRows.reduce((s, r) => s + parseNum(r.recognizableAsset), 0).toFixed(2),
      )
    }

    if (recognizable <= 0 && v2Rows.length === 0) return null
    const idx = rows.value.findIndex((r) => r.category === '可抵扣亏损')
    if (idx < 0) return null
    rows.value[idx].endUnadjusted = recognizable
    _persistRow(idx)
    _syncTotals()
    return recognizable
  }

  /** 更新行可编辑字段 */
  function updateRow(
    index: number,
    field: keyof Omit<N1AdjudicationRow, 'category'>,
    value: number | string,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    ;(rows.value[index] as any)[field] = value
    _persistRow(index)
  }

  /** 添加调整（aje/rje 累加到对应期） */
  function addAdjustment(index: number, period: 'begin' | 'end', type: 'aje' | 'rje', amount: number): void {
    if (index < 0 || index >= rows.value.length) return
    const field = period === 'begin'
      ? (type === 'aje' ? 'beginAje' : 'beginRje')
      : (type === 'aje' ? 'endAje' : 'endRje')
    rows.value[index][field] += parseNum(amount)
    _persistRow(index)
  }

  /** 移除调整（对应字段归零） */
  function removeAdjustment(index: number, period: 'begin' | 'end', type: 'aje' | 'rje'): void {
    if (index < 0 || index >= rows.value.length) return
    const field = period === 'begin'
      ? (type === 'aje' ? 'beginAje' : 'beginRje')
      : (type === 'aje' ? 'endAje' : 'endRje')
    rows.value[index][field] = 0
    _persistRow(index)
  }

  // ─── 5. 审计结论 + 说明 ────────────────────────────────────────────────

  /**
   * 审计说明 / 结论。
   *
   * 🔴 键必须与组件保存路径一致：组件用 `formData.setField('1','audit-notes'|'audit-conclusion')`
   * → item_id `N1-1-audit-notes` / `N1-1-audit-conclusion`（conclusion 列）。
   * 此前这里读 `N1-1-notes`(remark) / `N1-1-conclusion`(conclusion) —— 与写入键不同，
   * 导致刷新后审计说明/结论恒空，且一编辑就以空值覆盖。旧键作向后兼容回退。
   */
  function _readNote(field: 'audit-notes' | 'audit-conclusion', legacyKey: string, legacyCol: 'conclusion' | 'remark'): string {
    const v = formData.getField('1', field)
    if (v != null && String(v) !== '') return String(v)
    const legacy = allResponses.value.get(legacyKey)
    return (legacyCol === 'remark' ? legacy?.remark : legacy?.conclusion) || ''
  }

  const auditConclusion = ref<string>(_readNote('audit-conclusion', 'N1-1-conclusion', 'conclusion'))
  const auditNotes = ref<string>(_readNote('audit-notes', 'N1-1-notes', 'remark'))

  // ─── 6. 持久化 ─────────────────────────────────────────────────────────

  function _persistRow(index: number): void {
    const row = rows.value[index]
    const { category: _cat, ...data } = row
    formData.debouncedSave(`${ITEM_PREFIX}-${index}`, {
      conclusion: JSON.stringify(data),
    })
  }

  /**
   * 同步合计到 allResponses（供 crossSheet / 附注 / N5 读取）。
   *
   * 铁律：不能只在「期末审定合计变化」时写——只改期初列、或首次加载后
   * 从未编辑时，下游读到的 total 会陈旧/缺失，导致交叉验证出现假差异。
   * 故改为 rows 任意变化即同步（debounce 合并写）。
   */
  function _syncTotals(): void {
    formData.debouncedSave('N1-1-total-audited', { remark: String(totals.value.endAudited) })
    formData.debouncedSave('N1-1-total-begin', { remark: String(totals.value.beginAudited) })
  }

  watch(rows, () => _syncTotals(), { deep: true })

  // ─── 7. TB回写触发（审定数变化） ───────────────────────────────────────

  /**
   * 审定合计变化 → 回写 trial_balance。
   *
   * 🔴 去抖 2s：逐格录入时 endAudited 每敲一下就变，原实现每次变化立即 PUT
   *    → 一次录入产生数十次 TB 回写请求（且中间态是不完整数字）。
   *    去抖后只回写"停手后的稳定值"；显式「回写试算表」按钮仍走 formData.writebackTB。
   */
  const _WRITEBACK_DEBOUNCE_MS = 2000
  let _writebackTimer: ReturnType<typeof setTimeout> | null = null

  watch(
    () => totals.value.endAudited,
    (newVal, oldVal) => {
      if (_suppressWriteback) return
      if (oldVal === undefined || newVal === oldVal) return
      if (_writebackTimer) clearTimeout(_writebackTimer)
      _writebackTimer = setTimeout(() => {
        _writebackTimer = null
        void formData.writebackTB(newVal)
      }, _WRITEBACK_DEBOUNCE_MS)
    },
  )

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    totals,
    tbReconcile,
    pullFromDetail,
    pullFromTB,
    pullLossFromN15,
    addAdjustment,
    removeAdjustment,
    updateRow,
    auditConclusion,
    auditNotes,
  }
}

export default useN1Adjudication
