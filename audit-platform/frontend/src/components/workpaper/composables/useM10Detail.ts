/**
 * useM10Detail — M10-2 明细表 composable
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 动态行管理：按工具类型（永续债/优先股/转股特征）分组，每组可动态增行
 * - 30列宽表拆分为3个区段Tab：工具信息/发行赎回/分派
 * - 权益类贷方期末：期末=期初+本期发行(净额)-本期赎回/转换
 * - 使用 calcDetailEndBalance, calcNetIssuance from useM10FormulaEngine
 * - 与M10-1审定表合计交叉验证
 *
 * 科目：4003 其他权益工具（**贷方/权益类！期末=期初+贷方-借方**）
 * 45×30结构，13公式
 */
import { computed, ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcDetailEndBalance,
  calcNetIssuance,
  calcSubtotal,
} from './useM10FormulaEngine'
import type { useM10FormData } from './useM10FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表区段Tab */
export type M10DetailTab = 'instrumentInfo' | 'issuanceRedemption' | 'distribution'

/** 工具类型分组 */
export type M10InstrumentType = 'perpetualBond' | 'preferredStock' | 'convertible'

/** M10-2 明细表行数据（30列结构） */
export interface M10DetailRow {
  /** 行唯一标识 */
  key: string
  /** 工具类型分组 */
  instrumentType: M10InstrumentType

  // ─── 区段1: 工具信息（10列） ───
  /** 工具名称 */
  instrumentName: string
  /** 发行日期 */
  issueDate: string
  /** 票面金额/面值 */
  faceValue: number
  /** 票面利率/股息率(%) */
  couponRate: number
  /** 存续期限/到期日 */
  maturityDate: string
  /** 是否可赎回 */
  isRedeemable: boolean
  /** 是否可转股 */
  isConvertible: boolean
  /** 转股价格 */
  conversionPrice: number
  /** 付息/分派方式 */
  distributionMethod: string
  /** 备注 */
  remark: string

  // ─── 区段2: 发行赎回（10列） ───
  /** 期初余额（贷方余额） */
  beginning: number
  /** 本期发行总额 */
  grossIssuance: number
  /** 发行费用 */
  issuanceCost: number
  /** 本期发行净额（公式=总额-费用） */
  netIssuance: number
  /** 本期赎回金额 */
  redemption: number
  /** 本期转换金额 */
  conversion: number
  /** 本期减少合计（赎回+转换） */
  totalReduction: number
  /** 期末余额（公式=期初+净发行-减少合计，权益类贷方！） */
  endBalance: number
  /** 未审期末 */
  unadjustedEnd: number
  /** 审定期末（=未审+AJE+RJE） */
  auditedEnd: number

  // ─── 区段3: 分派（10列） ───
  /** AJE净影响 */
  ajeAmount: number
  /** RJE净影响 */
  rjeAmount: number
  /** 本期应付利息/股息 */
  interestDue: number
  /** 本期已付利息/股息 */
  interestPaid: number
  /** 累计未付利息/股息 */
  accruedUnpaid: number
  /** 递延利息标记 */
  isDeferrable: boolean
  /** 是否已递延 */
  isDeferred: boolean
  /** 递延期数 */
  deferralPeriods: number
  /** 权益/负债分类（CAS37判定结果） */
  classification: 'equity' | 'liability' | ''
  /** 分派备注 */
  distributionRemark: string
}

/** 分组小计 */
export interface M10DetailSubtotal {
  beginning: number
  grossIssuance: number
  issuanceCost: number
  netIssuance: number
  redemption: number
  conversion: number
  totalReduction: number
  endBalance: number
  auditedEnd: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义 */
export const M10_DETAIL_TABS = [
  { key: 'instrumentInfo' as const, label: '工具信息' },
  { key: 'issuanceRedemption' as const, label: '发行赎回' },
  { key: 'distribution' as const, label: '分派' },
] as const

/** 工具类型分组定义 */
export const M10_INSTRUMENT_TYPES = [
  { key: 'perpetualBond' as const, label: '永续债' },
  { key: 'preferredStock' as const, label: '优先股' },
  { key: 'convertible' as const, label: '转股特征工具' },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M10-2 明细表业务逻辑（30列3区段Tab+动态行+13公式）
 *
 * @param formData 由调用方传入的 useM10FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM10Detail(
  formData: ReturnType<typeof useM10FormData>,
  detailRows: { value: M10DetailRow[] },
) {
  const { debouncedSave } = formData

  // ─── 1. Tab区段状态（行同步：切换Tab不影响行数据，仅影响列显示） ────

  const activeTab = ref<M10DetailTab>('instrumentInfo')

  function switchTab(tab: M10DetailTab): void {
    activeTab.value = tab
  }

  // ─── 2. 计算属性：公式列自动计算（13公式） ────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M10DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // 净发行额=发行总额-发行费用
      const netIssuance = calcNetIssuance(row.grossIssuance, row.issuanceCost)
      // 减少合计=赎回+转换
      const totalReduction = row.redemption + row.conversion
      // 权益类贷方：期末=期初+净发行-减少合计
      const endBalance = calcDetailEndBalance(row.beginning, netIssuance, totalReduction)
      // 审定期末=未审+AJE+RJE
      const auditedEnd = row.unadjustedEnd + row.ajeAmount + row.rjeAmount
      return { ...row, netIssuance, totalReduction, endBalance, auditedEnd }
    })
  })

  // ─── 3. 按工具类型分组视图 ────────────────────────────────────────────

  /** 永续债行 */
  const perpetualBondRows: ComputedRef<M10DetailRow[]> = computed(() => {
    return computedRows.value.filter(r => r.instrumentType === 'perpetualBond')
  })

  /** 优先股行 */
  const preferredStockRows: ComputedRef<M10DetailRow[]> = computed(() => {
    return computedRows.value.filter(r => r.instrumentType === 'preferredStock')
  })

  /** 转股特征工具行 */
  const convertibleRows: ComputedRef<M10DetailRow[]> = computed(() => {
    return computedRows.value.filter(r => r.instrumentType === 'convertible')
  })

  // ─── 4. 分组小计（供M10-1交叉验证） ──────────────────────────────────

  /** 永续债小计 */
  const perpetualBondSubtotal: ComputedRef<M10DetailSubtotal> = computed(() => {
    return _calcTypeSubtotal('perpetualBond')
  })

  /** 优先股小计 */
  const preferredStockSubtotal: ComputedRef<M10DetailSubtotal> = computed(() => {
    return _calcTypeSubtotal('preferredStock')
  })

  /** 转股特征工具小计 */
  const convertibleSubtotal: ComputedRef<M10DetailSubtotal> = computed(() => {
    return _calcTypeSubtotal('convertible')
  })

  /** 全部合计 */
  const grandTotal: ComputedRef<M10DetailSubtotal> = computed(() => {
    const r = computedRows.value
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const grossIssuance = calcSubtotal(r.map(x => x.grossIssuance))
    const issuanceCost = calcSubtotal(r.map(x => x.issuanceCost))
    const netIssuance = calcNetIssuance(grossIssuance, issuanceCost)
    const redemption = calcSubtotal(r.map(x => x.redemption))
    const conversion = calcSubtotal(r.map(x => x.conversion))
    const totalReduction = redemption + conversion
    const endBalance = calcDetailEndBalance(beginning, netIssuance, totalReduction)
    const auditedEnd = calcSubtotal(r.map(x => x.auditedEnd))
    return { beginning, grossIssuance, issuanceCost, netIssuance, redemption, conversion, totalReduction, endBalance, auditedEnd }
  })

  function _calcTypeSubtotal(type: M10InstrumentType): M10DetailSubtotal {
    const r = computedRows.value.filter(x => x.instrumentType === type)
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const grossIssuance = calcSubtotal(r.map(x => x.grossIssuance))
    const issuanceCost = calcSubtotal(r.map(x => x.issuanceCost))
    const netIssuance = calcNetIssuance(grossIssuance, issuanceCost)
    const redemption = calcSubtotal(r.map(x => x.redemption))
    const conversion = calcSubtotal(r.map(x => x.conversion))
    const totalReduction = redemption + conversion
    const endBalance = calcDetailEndBalance(beginning, netIssuance, totalReduction)
    const auditedEnd = calcSubtotal(r.map(x => x.auditedEnd))
    return { beginning, grossIssuance, issuanceCost, netIssuance, redemption, conversion, totalReduction, endBalance, auditedEnd }
  }

  // ─── 5. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入工具名称）
   */
  async function addRow(instrumentType?: M10InstrumentType): Promise<void> {
    const targetType = instrumentType || 'perpetualBond'
    const typeLabel = M10_INSTRUMENT_TYPES.find(t => t.key === targetType)?.label || '工具'

    try {
      const { value: instrumentName } = await ElMessageBox.prompt(
        `请输入${typeLabel}名称`,
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: targetType === 'perpetualBond'
            ? '如：2024年第一期永续债'
            : targetType === 'preferredStock'
              ? '如：A系列优先股'
              : '如：可转换优先股',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '工具名称不能为空'
            return true
          },
        },
      )

      const key = `m10-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M10DetailRow = {
        key,
        instrumentType: targetType,
        instrumentName: instrumentName?.trim() || '',
        issueDate: '',
        faceValue: 0,
        couponRate: 0,
        maturityDate: '',
        isRedeemable: false,
        isConvertible: targetType === 'convertible',
        conversionPrice: 0,
        distributionMethod: '',
        remark: '',
        beginning: 0,
        grossIssuance: 0,
        issuanceCost: 0,
        netIssuance: 0,
        redemption: 0,
        conversion: 0,
        totalReduction: 0,
        endBalance: 0,
        unadjustedEnd: 0,
        auditedEnd: 0,
        ajeAmount: 0,
        rjeAmount: 0,
        interestDue: 0,
        interestPaid: 0,
        accruedUnpaid: 0,
        isDeferrable: false,
        isDeferred: false,
        deferralPeriods: 0,
        classification: '',
        distributionRemark: '',
      }

      detailRows.value.push(newRow)
      _triggerSave(detailRows.value.length - 1)
    } catch {
      // 用户取消
    }
  }

  /** 删除指定行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= detailRows.value.length) return
    detailRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新某行某字段 */
  function updateRow(index: number, field: keyof M10DetailRow, value: string | number | boolean): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 金额字段变动→重算公式列
    if (['grossIssuance', 'issuanceCost'].includes(field as string)) {
      row.netIssuance = calcNetIssuance(row.grossIssuance, row.issuanceCost)
    }
    if (['redemption', 'conversion'].includes(field as string)) {
      row.totalReduction = row.redemption + row.conversion
    }
    if (['beginning', 'grossIssuance', 'issuanceCost', 'redemption', 'conversion'].includes(field as string)) {
      row.netIssuance = calcNetIssuance(row.grossIssuance, row.issuanceCost)
      row.totalReduction = row.redemption + row.conversion
      row.endBalance = calcDetailEndBalance(row.beginning, row.netIssuance, row.totalReduction)
    }
    if (['unadjustedEnd', 'ajeAmount', 'rjeAmount'].includes(field as string)) {
      row.auditedEnd = row.unadjustedEnd + row.ajeAmount + row.rjeAmount
    }

    _triggerSave(index)
  }

  // ─── 6. 与M10-1审定表交叉验证 ────────────────────────────────────────

  /**
   * 与M10-1审定表合计交叉验证
   */
  function crossValidateWithAdjudication(
    adjTotal: number,
  ): { diff: number; isMatch: boolean } {
    const diff = grandTotal.value.auditedEnd - adjTotal
    const isMatch = Math.abs(diff) < 0.01
    return { diff, isMatch }
  }

  // ─── 7. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M10-2-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        instrumentType: row.instrumentType,
        instrumentName: row.instrumentName,
        issueDate: row.issueDate,
        faceValue: row.faceValue,
        couponRate: row.couponRate,
        maturityDate: row.maturityDate,
        isRedeemable: row.isRedeemable,
        isConvertible: row.isConvertible,
        conversionPrice: row.conversionPrice,
        distributionMethod: row.distributionMethod,
        beginning: row.beginning,
        grossIssuance: row.grossIssuance,
        issuanceCost: row.issuanceCost,
        redemption: row.redemption,
        conversion: row.conversion,
        unadjustedEnd: row.unadjustedEnd,
        ajeAmount: row.ajeAmount,
        rjeAmount: row.rjeAmount,
        interestDue: row.interestDue,
        interestPaid: row.interestPaid,
        accruedUnpaid: row.accruedUnpaid,
        isDeferrable: row.isDeferrable,
        isDeferred: row.isDeferred,
        deferralPeriods: row.deferralPeriods,
        classification: row.classification,
        remark: row.remark,
        distributionRemark: row.distributionRemark,
      }),
    })
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < detailRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // Tab区段
    activeTab,
    switchTab,

    // 计算属性
    computedRows,
    perpetualBondRows,
    preferredStockRows,
    convertibleRows,

    // 分组小计
    perpetualBondSubtotal,
    preferredStockSubtotal,
    convertibleSubtotal,
    grandTotal,

    // 行操作
    addRow,
    removeRow,
    updateRow,

    // 交叉验证
    crossValidateWithAdjudication,
  }
}

export default useM10Detail
