/**
 * useM2Detail — M2-2 明细表 composable（双版本：上市/非上市）
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 3.4
 * Requirements: 3.1-3.7
 *
 * 职责：
 * - 管理双版本状态（listedRows / unlistedRows）
 * - 上市公司版（38×36）：列 股东名称|股份性质|期初股数|本期增加|本期减少|期末股数|持股比例
 * - 非上市公司版（37×24）：列 出资人|出资方式|期初出资|本期增资|本期减资|期末出资|出资比例
 * - 动态行新增（ElMessageBox.prompt 输入出资人名称）
 * - 期末=期初+增加-减少（权益类贷方方向）
 * - 与M2-1审定表交叉验证
 *
 * 科目：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 * 增资时贷方增加（本期增加），减资时借方减少（本期减少）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcEquityEndBalance,
  calcSubtotal,
  calcShareRatio,
} from './useM2FormulaEngine'
import type { useM2FormData } from './useM2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 上市公司版明细行（38×36 股份） */
export interface M2DetailListedRow {
  /** 行唯一标识 */
  key: string
  /** 序号 */
  seq: number
  // ─── 区段1: 股东信息 ───
  /** 股东名称 */
  shareholderName: string
  /** 股份性质（流通A股/限售股/H股/B股等） */
  shareType: string
  /** 证件类型 */
  idType: string
  /** 证件号码 */
  idNumber: string
  /** 国籍/地区 */
  nationality: string
  // ─── 区段2: 股数增减变动 ───
  /** 期初股数 */
  beginShares: number
  /** 本期增加股数（贷方增资） */
  increaseShares: number
  /** 本期减少股数（借方减资） */
  decreaseShares: number
  /** 期末股数（公式=期初+增加-减少） */
  endShares: number
  /** 增加原因（增发/转增/配股/权证行权等） */
  increaseReason: string
  /** 减少原因（回购/注销/转让等） */
  decreaseReason: string
  // ─── 区段3: 比例与金额 ───
  /** 持股比例（公式=个人/合计） */
  shareRatio: number
  /** 面值 */
  parValue: number
  /** 期初金额 */
  beginAmount: number
  /** 期末金额 */
  endAmount: number
  /** 备注 */
  remark: string
}

/** 非上市公司版明细行（37×24 出资） */
export interface M2DetailUnlistedRow {
  /** 行唯一标识 */
  key: string
  /** 序号 */
  seq: number
  // ─── 区段1: 出资人信息 ───
  /** 出资人名称 */
  investorName: string
  /** 出资方式（货币/实物/知识产权/土地使用权等） */
  investType: string
  /** 证件类型 */
  idType: string
  /** 证件号码 */
  idNumber: string
  // ─── 区段2: 出资增减 ───
  /** 期初出资额 */
  beginAmount: number
  /** 本期增资额（贷方增加） */
  increaseAmount: number
  /** 本期减资额（借方减少） */
  decreaseAmount: number
  /** 期末出资额（公式=期初+增资-减资） */
  endAmount: number
  /** 增资原因 */
  increaseReason: string
  /** 减资原因 */
  decreaseReason: string
  // ─── 区段3: 比例 ───
  /** 出资比例（公式=个人/合计） */
  investRatio: number
  /** 认缴出资额 */
  subscribedAmount: number
  /** 出资日期 */
  investDate: string
  /** 备注 */
  remark: string
}

/** 明细版本分支 */
export type M2DetailBranch = 'listed' | 'unlisted'

/** 区段Tab类型 */
export type M2DetailSegment = 'info' | 'changes' | 'adjustments' | 'audited'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 上市版区段定义 */
export const M2_LISTED_SEGMENTS = [
  { key: 'info' as const, label: '股东信息' },
  { key: 'changes' as const, label: '股数增减变动' },
  { key: 'adjustments' as const, label: '调整区域' },
  { key: 'audited' as const, label: '审定数+验资' },
] as const

/** 非上市版区段定义 */
export const M2_UNLISTED_SEGMENTS = [
  { key: 'info' as const, label: '出资人信息' },
  { key: 'changes' as const, label: '出资增减' },
  { key: 'adjustments' as const, label: '调整区域' },
  { key: 'audited' as const, label: '审定数+验资' },
] as const

/** 股份性质选项 */
export const SHARE_TYPE_OPTIONS = [
  { value: 'A_tradable', label: '流通A股' },
  { value: 'A_restricted', label: '限售A股' },
  { value: 'H_share', label: 'H股' },
  { value: 'B_share', label: 'B股' },
  { value: 'preferred', label: '优先股' },
  { value: 'other', label: '其他' },
]

/** 出资方式选项 */
export const INVEST_TYPE_OPTIONS = [
  { value: 'cash', label: '货币' },
  { value: 'asset', label: '实物' },
  { value: 'ip', label: '知识产权' },
  { value: 'land', label: '土地使用权' },
  { value: 'equity', label: '股权' },
  { value: 'debt_to_equity', label: '债转股' },
  { value: 'other', label: '其他' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M2-2 明细表业务逻辑（双版本分支 + 动态行 + 交叉验证）
 *
 * @param formData 由调用方传入的 useM2FormData 实例
 * @param listedRows reactive ref of listed version rows
 * @param unlistedRows reactive ref of unlisted version rows
 */
export function useM2Detail(
  formData: ReturnType<typeof useM2FormData>,
  listedRows: Ref<M2DetailListedRow[]>,
  unlistedRows: Ref<M2DetailUnlistedRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 分支状态 ──────────────────────────────────────────────────────

  const activeBranch = ref<M2DetailBranch>('unlisted')
  const activeSegment = ref<M2DetailSegment>('info')

  function switchBranch(branch: M2DetailBranch): void {
    activeBranch.value = branch
    activeSegment.value = 'info' // 切换分支时重置区段
  }

  function switchSegment(segment: M2DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 上市版计算属性 ────────────────────────────────────────────────

  /** 上市版各行公式列自动计算 */
  const computedListedRows: ComputedRef<M2DetailListedRow[]> = computed(() => {
    const totalShares = calcSubtotal(listedRows.value.map(r => {
      return calcEquityEndBalance(r.beginShares, r.increaseShares, r.decreaseShares)
    }))
    return listedRows.value.map(row => {
      const endShares = calcEquityEndBalance(row.beginShares, row.increaseShares, row.decreaseShares)
      const shareRatio = calcShareRatio(endShares, totalShares)
      const endAmount = endShares * (row.parValue || 1)
      return {
        ...row,
        endShares,
        shareRatio,
        endAmount,
      }
    })
  })

  /** 上市版合计 */
  const listedTotalEndShares: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedListedRows.value.map(r => r.endShares))
  })

  const listedTotalBeginShares: ComputedRef<number> = computed(() => {
    return calcSubtotal(listedRows.value.map(r => r.beginShares))
  })

  // ─── 3. 非上市版计算属性 ──────────────────────────────────────────────

  /** 非上市版各行公式列自动计算 */
  const computedUnlistedRows: ComputedRef<M2DetailUnlistedRow[]> = computed(() => {
    const totalAmount = calcSubtotal(unlistedRows.value.map(r => {
      return calcEquityEndBalance(r.beginAmount, r.increaseAmount, r.decreaseAmount)
    }))
    return unlistedRows.value.map(row => {
      const endAmount = calcEquityEndBalance(row.beginAmount, row.increaseAmount, row.decreaseAmount)
      const investRatio = calcShareRatio(endAmount, totalAmount)
      return {
        ...row,
        endAmount,
        investRatio,
      }
    })
  })

  /** 非上市版合计 */
  const unlistedTotalEndAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedUnlistedRows.value.map(r => r.endAmount))
  })

  const unlistedTotalBeginAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(unlistedRows.value.map(r => r.beginAmount))
  })

  // ─── 4. 统一合计（供CrossSheet验证） ──────────────────────────────────

  /** 当前分支的期末合计金额（上市用endAmount合计，非上市直接endAmount合计） */
  const currentBranchTotalEnd: ComputedRef<number> = computed(() => {
    if (activeBranch.value === 'listed') {
      return calcSubtotal(computedListedRows.value.map(r => r.endAmount))
    }
    return unlistedTotalEndAmount.value
  })

  // ─── 5. 与M2-1审定表交叉验证 ─────────────────────────────────────────

  /**
   * 交叉验证差额（明细合计 vs M2-1审定表期末合计）
   * adjudicationTotal 需由外部注入
   */
  function crossValidate(adjudicationEndAudited: number): { diff: number; isMatch: boolean } {
    const detailTotal = currentBranchTotalEnd.value
    const diff = detailTotal - adjudicationEndAudited
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  }

  // ─── 6. 动态行新增 ────────────────────────────────────────────────────

  /**
   * 新增上市版明细行（先弹 ElMessageBox.prompt 输入股东名称）
   */
  async function addListedRow(): Promise<void> {
    try {
      const { value: shareholderName } = await ElMessageBox.prompt(
        '请输入股东名称',
        '新增股东明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX控股集团有限公司',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '股东名称不能为空'
            return true
          },
        },
      )

      const key = `m2-listed-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const seq = listedRows.value.length + 1
      const newRow: M2DetailListedRow = {
        key,
        seq,
        shareholderName: shareholderName?.trim() || '',
        shareType: '',
        idType: '',
        idNumber: '',
        nationality: '',
        beginShares: 0,
        increaseShares: 0,
        decreaseShares: 0,
        endShares: 0,
        increaseReason: '',
        decreaseReason: '',
        shareRatio: 0,
        parValue: 1,
        beginAmount: 0,
        endAmount: 0,
        remark: '',
      }
      listedRows.value.push(newRow)
      _triggerSaveListed(listedRows.value.length - 1)
    } catch {
      // 用户取消
    }
  }

  /**
   * 新增非上市版明细行（先弹 ElMessageBox.prompt 输入出资人名称）
   */
  async function addUnlistedRow(): Promise<void> {
    try {
      const { value: investorName } = await ElMessageBox.prompt(
        '请输入出资人名称',
        '新增出资人明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX有限公司/张三',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '出资人名称不能为空'
            return true
          },
        },
      )

      const key = `m2-unlisted-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const seq = unlistedRows.value.length + 1
      const newRow: M2DetailUnlistedRow = {
        key,
        seq,
        investorName: investorName?.trim() || '',
        investType: '',
        idType: '',
        idNumber: '',
        beginAmount: 0,
        increaseAmount: 0,
        decreaseAmount: 0,
        endAmount: 0,
        increaseReason: '',
        decreaseReason: '',
        investRatio: 0,
        subscribedAmount: 0,
        investDate: '',
        remark: '',
      }
      unlistedRows.value.push(newRow)
      _triggerSaveUnlisted(unlistedRows.value.length - 1)
    } catch {
      // 用户取消
    }
  }

  /** 删除上市版行 */
  function removeListedRow(index: number): void {
    if (index < 0 || index >= listedRows.value.length) return
    listedRows.value.splice(index, 1)
    listedRows.value.forEach((r, i) => { r.seq = i + 1 })
    _triggerSaveAllListed()
  }

  /** 删除非上市版行 */
  function removeUnlistedRow(index: number): void {
    if (index < 0 || index >= unlistedRows.value.length) return
    unlistedRows.value.splice(index, 1)
    unlistedRows.value.forEach((r, i) => { r.seq = i + 1 })
    _triggerSaveAllUnlisted()
  }

  /** 更新上市版行某字段 */
  function updateListedRow(index: number, field: keyof M2DetailListedRow, value: any): void {
    if (index < 0 || index >= listedRows.value.length) return
    const row = listedRows.value[index] as any
    row[field] = value
    _triggerSaveListed(index)
  }

  /** 更新非上市版行某字段 */
  function updateUnlistedRow(index: number, field: keyof M2DetailUnlistedRow, value: any): void {
    if (index < 0 || index >= unlistedRows.value.length) return
    const row = unlistedRows.value[index] as any
    row[field] = value
    _triggerSaveUnlisted(index)
  }

  // ─── 7. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSaveListed(rowIndex: number): void {
    const row = listedRows.value[rowIndex]
    if (!row) return
    debouncedSave(`M2-M2-2-listed-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        seq: row.seq,
        shareholderName: row.shareholderName,
        shareType: row.shareType,
        idType: row.idType,
        idNumber: row.idNumber,
        nationality: row.nationality,
        beginShares: row.beginShares,
        increaseShares: row.increaseShares,
        decreaseShares: row.decreaseShares,
        increaseReason: row.increaseReason,
        decreaseReason: row.decreaseReason,
        parValue: row.parValue,
        beginAmount: row.beginAmount,
        remark: row.remark,
      }),
    })
    // 保存明细合计（供CrossSheet交叉验证）
    debouncedSave('M2-M2-2-listed-totalEnd', {
      remark: String(listedTotalEndShares.value),
    })
    // 🔴 修复：同步写整包 full-data（M2TabDetail._restoreRows 读此键；此前从不写 → 刷新明细全丢）
    debouncedSave('M2-M2-2-listed-full-data', { remark: JSON.stringify(listedRows.value) })
  }

  function _triggerSaveUnlisted(rowIndex: number): void {
    const row = unlistedRows.value[rowIndex]
    if (!row) return
    debouncedSave(`M2-M2-2-unlisted-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        seq: row.seq,
        investorName: row.investorName,
        investType: row.investType,
        idType: row.idType,
        idNumber: row.idNumber,
        beginAmount: row.beginAmount,
        increaseAmount: row.increaseAmount,
        decreaseAmount: row.decreaseAmount,
        increaseReason: row.increaseReason,
        decreaseReason: row.decreaseReason,
        subscribedAmount: row.subscribedAmount,
        investDate: row.investDate,
        remark: row.remark,
      }),
    })
    // 保存明细合计（供CrossSheet交叉验证）
    debouncedSave('M2-M2-2-unlisted-totalEnd', {
      remark: String(unlistedTotalEndAmount.value),
    })
    // 🔴 修复：同步写整包 full-data（M2TabDetail._restoreRows 读此键；此前从不写 → 刷新明细全丢）
    debouncedSave('M2-M2-2-unlisted-full-data', { remark: JSON.stringify(unlistedRows.value) })
  }

  function _triggerSaveAllListed(): void {
    listedRows.value.forEach((_, i) => _triggerSaveListed(i))
  }

  function _triggerSaveAllUnlisted(): void {
    unlistedRows.value.forEach((_, i) => _triggerSaveUnlisted(i))
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 分支状态
    activeBranch,
    activeSegment,
    switchBranch,
    switchSegment,

    // 上市版
    computedListedRows,
    listedTotalEndShares,
    listedTotalBeginShares,

    // 非上市版
    computedUnlistedRows,
    unlistedTotalEndAmount,
    unlistedTotalBeginAmount,

    // 统一合计
    currentBranchTotalEnd,

    // 交叉验证
    crossValidate,

    // 行操作
    addListedRow,
    addUnlistedRow,
    removeListedRow,
    removeUnlistedRow,
    updateListedRow,
    updateUnlistedRow,
  }
}

export default useM2Detail
