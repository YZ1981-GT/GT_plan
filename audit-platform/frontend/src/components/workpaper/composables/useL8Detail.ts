/**
 * useL8Detail — L8-2 明细表 composable（23列区段Tab管理）
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 23列按区段Tab管理（费用项目/月度金额/期末汇总+审定，行同步）
 * - 行结构：利息费用总额/减利息资本化/利息费用/减利息收入/利息净支出
 *   /未确认融资费用/减未实现融资收益/.../合计
 * - 公式：
 *   N=SUM(B:M)（本期未审合计=1月~12月之和）
 *   Q=N+O+P（本期审定=未审合计+AJE+RJE）
 *   R=Q/Q合计（占比）
 *   W=T+U+V（上期审定=上期未审+上期AJE+上期RJE）
 * - 自动计算净财务费用（calcNetFinanceExpense）
 * - 变动率计算 + 异常高亮
 * - 与审定表L8-1交叉验证
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { newRowIdentity } from './shared/rowIdentity'
import {
  L82_SKELETON_ITEMS,
  L82_DERIVED_ROW_SOURCES,
  l82TemplateRowId,
  isL82TemplateRowId,
  isL82DerivedRowKey,
  rowsForStore,
} from '../l8/core/l8DetailRowIdentity'
import {
  calcAuditedAmount,
  calcSubtotal,
  calcChangeRate,
  calcChangeAmount,
  calcNetFinanceExpense,
  isChangeRateExceeding,
} from './useL8FormulaEngine'
import type { useL8FormData } from './useL8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L8-2 明细表行数据（23列） */
export interface L8DetailRow {
  /** 行唯一标识 */
  key: string
  /** 费用项目名称（A列） */
  itemName: string
  /** 1月~12月发生额（B~M列） */
  monthly: [number, number, number, number, number, number, number, number, number, number, number, number]
  /** 本期未审合计（N列，公式=SUM(B:M)） */
  periodUnadjusted: number
  /** AJE（O列） */
  aje: number
  /** RJE（P列） */
  rje: number
  /** 本期审定（Q列，公式=N+O+P） */
  periodAudited: number
  /** 占比（R列，公式=Q/Q合计行×100） */
  ratio: number
  /** 与相关科目勾稽（S列，备注文本） */
  crossRef: string
  /** 上期未审（T列） */
  priorUnadjusted: number
  /** 上期AJE（U列） */
  priorAje: number
  /** 上期RJE（V列） */
  priorRje: number
  /** 上期审定（W列，公式=T+U+V） */
  priorAudited: number
}

/** 区段Tab类型 */
export type L8DetailSegment = 'items' | 'monthly' | 'summary'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：23列拆3段 */
export const L8_DETAIL_SEGMENTS = [
  {
    key: 'items' as const,
    label: '费用项目',
    fields: ['itemName', 'crossRef'],
  },
  {
    key: 'monthly' as const,
    label: '月度金额(1月~12月)',
    fields: ['monthly'],
  },
  {
    key: 'summary' as const,
    label: '期末汇总+审定',
    fields: [
      'periodUnadjusted', 'aje', 'rje', 'periodAudited', 'ratio',
      'priorUnadjusted', 'priorAje', 'priorRje', 'priorAudited',
    ],
  },
] as const

/**
 * 默认费用明细行（对齐 L8-1 审定表结构 + 模板 L8-2 的 13 行骨架）。
 * 🔴 方案 D：身份真源收敛到 `l8/core/l8DetailRowIdentity.ts` 的 13 行骨架（含「汇兑净损失」R20，
 * 旧 12 项缺这一项）；每个骨架行用模板身份 GTROW-L82-NNNN 认领对应槽位。
 */
export const L8_DETAIL_DEFAULT_ITEMS: readonly string[] = L82_SKELETON_ITEMS

/** 构造一行空的 L8-2 明细行（给定 key 与项目名）。 */
export function makeEmptyL8Row(key: string, itemName: string): L8DetailRow {
  return {
    key,
    itemName,
    monthly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    periodUnadjusted: 0,
    aje: 0,
    rje: 0,
    periodAudited: 0,
    ratio: 0,
    crossRef: '',
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
  }
}

/**
 * 构造 13 行默认骨架行，每行用模板身份 GTROW-L82-NNNN 认领对应槽位（按位置，顺序稳定）。
 * 用户 addRow 新增的行走 newRowIdentity('l82det')，与骨架身份命名空间分离。
 */
export function createL8DefaultRows(): L8DetailRow[] {
  return L82_SKELETON_ITEMS.map((name, i) => makeEmptyL8Row(l82TemplateRowId(i), name))
}

/**
 * 从 store 载荷（方案 D1：只含 10 输入骨架行 + 用户新增行，无派生行）复原**完整 13 行 + 用户行**
 * 的显示用数组：
 *   - 以 `createL8DefaultRows()` 的 13 行骨架为底板（含 3 派生行占位，其值由 computedRows 跨行算）；
 *   - 把 store 里的输入骨架行按 GTROW key 覆盖到对应槽位（保留用户填的 monthly/aje/… 数据）；
 *   - 兼容历史：store 行缺 key 或是旧自铸身份时，按**位置**认领输入槽位（跳过派生槽位）；
 *   - store 里的用户新增行（l82det-*，或既非骨架也非派生的）追加到末尾。
 * 返回新数组，不改入参。
 */
export function restoreL8RowsForDisplay(stored: L8DetailRow[]): L8DetailRow[] {
  const skeleton = createL8DefaultRows() // 13 行，GTROW 身份（含 3 派生占位）
  const byKey = new Map(skeleton.map(r => [r.key, r]))
  const inputSlotKeys = skeleton.filter(r => !isL82DerivedRowKey(r.key)).map(r => r.key)
  const userRows: L8DetailRow[] = []

  // 🔴 新格式（store 已含 GTROW 输入行）与历史格式（纯自铸身份）分流：
  //   有任一 GTROW 身份 ⇒ 新格式，非模板行一律当用户新增行；
  //   无 GTROW 身份 ⇒ 历史迁移，非模板行按位置认领输入槽位。
  const hasTemplateIds = stored.some(r => typeof r?.key === 'string' && isL82TemplateRowId(r.key))
  let nextInputSlot = 0
  for (const raw of stored) {
    const row = { ...raw } as L8DetailRow
    if (typeof row.key === 'string' && isL82TemplateRowId(row.key) && byKey.has(row.key)) {
      // 输入骨架槽位覆盖（派生行本不该在 store；若混入也不覆盖派生占位）
      if (!isL82DerivedRowKey(row.key)) byKey.set(row.key, { ...row })
      continue
    }
    if (!hasTemplateIds && nextInputSlot < inputSlotKeys.length) {
      // 历史迁移：按剩余输入槽位顺序认领
      const slotKey = inputSlotKeys[nextInputSlot++]
      byKey.set(slotKey, { ...row, key: slotKey })
    } else {
      // 用户新增行（新格式）或历史槽位认领满后的溢出行
      userRows.push({ ...row, key: (typeof row.key === 'string' && row.key) ? row.key : newRowIdentity('l82det') })
    }
  }
  // 按骨架顺序 + 末尾用户行
  return [...skeleton.map(r => byKey.get(r.key)!), ...userRows]
}

/** 变动率异常阈值（20%） */
const CHANGE_RATE_THRESHOLD = 20

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L8-2 明细表业务逻辑（23列区段Tab）
 *
 * @param formData 由调用方传入的 useL8FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useL8Detail(
  formData: ReturnType<typeof useL8FormData>,
  detailRows: Ref<L8DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L8DetailSegment>('items')

  function switchSegment(segment: L8DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：公式列自动计算 ─────────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L8DetailRow[]> = computed(() => {
    // 🔴 方案 D1：派生行（利息费用/利息净支出/汇兑净损失）的月度金额按模板跨行减法由上方科目算出
    //   （只读显示，不持久化）。先按下标把派生行的 monthly 覆盖为跨行结果，再走统一公式列计算。
    const base = detailRows.value
    const derivedMonthly = (sources: ReadonlyArray<readonly [number, 1 | -1]>): number[] => {
      const out = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
      for (const [srcIdx, sign] of sources) {
        const src = base[srcIdx]
        if (!src) continue
        for (let m = 0; m < 12; m++) out[m] += sign * (Number(src.monthly?.[m]) || 0)
      }
      return out
    }
    const resolved = base.map((row, idx) => {
      const sources = L82_DERIVED_ROW_SOURCES[idx]
      if (sources && isL82DerivedRowKey(row.key)) {
        return { ...row, monthly: derivedMonthly(sources) as L8DetailRow['monthly'] }
      }
      return row
    })

    // 先计算各行审定数以确定合计行审定值（用于占比计算）
    const rowsWithFormulas = resolved.map(row => {
      // N=SUM(B:M) 本期未审合计
      const periodUnadjusted = calcSubtotal(row.monthly as unknown as number[])
      // Q=N+O+P 本期审定
      const periodAudited = calcAuditedAmount(periodUnadjusted, row.aje, row.rje)
      // W=T+U+V 上期审定
      const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
      return { ...row, periodUnadjusted, periodAudited, priorAudited }
    })

    // 计算合计行的审定数（用于占比）
    const totalAudited = calcSubtotal(rowsWithFormulas.map(r => r.periodAudited))

    // 添加占比列
    return rowsWithFormulas.map(row => ({
      ...row,
      ratio: totalAudited !== 0 ? (row.periodAudited / totalAudited) * 100 : 0,
    }))
  })

  // ─── 3. 合计行 ────────────────────────────────────────────────────────

  /** 本期审定合计（供L8-1交叉验证） */
  const totalPeriodAudited: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.periodAudited))
  })

  /** 上期审定合计 */
  const totalPriorAudited: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.priorAudited))
  })

  /** 变动率（合计行） */
  const totalChangeRate: ComputedRef<number | 'N/A'> = computed(() => {
    return calcChangeRate(totalPeriodAudited.value, totalPriorAudited.value)
  })

  /** 变动额（合计行） */
  const totalChangeAmount: ComputedRef<number> = computed(() => {
    return calcChangeAmount(totalPeriodAudited.value, totalPriorAudited.value)
  })

  // ─── 4. 异常变动率行 ──────────────────────────────────────────────────

  /** 变动率超阈值的行索引 */
  const abnormalRows: ComputedRef<number[]> = computed(() => {
    const indices: number[] = []
    computedRows.value.forEach((row, idx) => {
      const rate = calcChangeRate(row.periodAudited, row.priorAudited)
      if (isChangeRateExceeding(rate, CHANGE_RATE_THRESHOLD)) {
        indices.push(idx)
      }
    })
    return indices
  })

  // ─── 5. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入项目名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: itemName } = await ElMessageBox.prompt(
        '请输入费用项目名称',
        '新增明细项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：银行手续费/保函费/信用证费用',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      const key = newRowIdentity('l82det')
      const newRow: L8DetailRow = {
        key,
        itemName: itemName?.trim() || '',
        monthly: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        periodUnadjusted: 0,
        aje: 0,
        rje: 0,
        periodAudited: 0,
        ratio: 0,
        crossRef: '',
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        priorAudited: 0,
      }
      detailRows.value.push(newRow)
      _triggerSaveAll()
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
  function updateRow(index: number, field: keyof L8DetailRow, value: any): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  /** 更新某行某月金额（B~M列） */
  function updateMonthly(rowIndex: number, monthIndex: number, value: number): void {
    if (rowIndex < 0 || rowIndex >= detailRows.value.length) return
    if (monthIndex < 0 || monthIndex > 11) return
    // 🔴 方案 D1：派生行月度金额是模板跨行计算的只读值，不接受直接编辑（UI 已禁用，这里兜底）。
    if (isL82DerivedRowKey(detailRows.value[rowIndex].key)) return
    detailRows.value[rowIndex].monthly[monthIndex] = value
    _triggerSave(rowIndex)
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const computed = computedRows.value[rowIndex]
    // 保存净发生额（供CrossSheet勾稽）
    if (computed) {
      debouncedSave(`L8-2-row-${rowIndex}-audited`, {
        remark: String(computed.periodAudited),
      })
    }
    // 保存行完整数据
    debouncedSave(`L8-2-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        monthly: row.monthly,
        aje: row.aje,
        rje: row.rje,
        priorUnadjusted: row.priorUnadjusted,
        priorAje: row.priorAje,
        priorRje: row.priorRje,
        crossRef: row.crossRef,
      }),
    })
    // 保存明细表净财务费用合计（供 CrossSheet 交叉验证）
    debouncedSave('L8-2-netFinExpense', {
      remark: String(totalPeriodAudited.value),
    })
    // 🔴 修复：保存完整行到 L8-2-full-data（组件 _restoreRows 读此键；此前从不写 → 刷新数据全丢）
    // 🔴 方案 D1：只存 10 输入骨架行 + 用户新增行；3 个派生行（模板计算只读）不进 store，
    //   真 OO 往返时不在 projection ⇒ 模板跨行公式幸存。
    debouncedSave('L8-2-full-data', {
      remark: JSON.stringify(rowsForStore(detailRows.value)),
    })
  }

  function _triggerSaveAll(): void {
    computedRows.value.forEach((_, i) => {
      _triggerSave(i)
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalPeriodAudited,
    totalPriorAudited,
    totalChangeRate,
    totalChangeAmount,
    abnormalRows,

    // 行操作
    addRow,
    removeRow,
    updateRow,
    updateMonthly,
  }
}

export default useL8Detail
