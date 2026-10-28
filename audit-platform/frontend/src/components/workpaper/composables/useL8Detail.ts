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
 * - 公式（与权威模板 明细表L8-2 逐格同式）：
 *   N=SUM(B:M)（本期未审合计=1月~12月之和）
 *   Q=N+O+P（本期审定=未审合计+AJE+RJE）
 *   R=IF(Q=0,0,Q/Q22)（占比，比值；Q22 = 合计行）
 *   W=T+U+V（上期审定=上期未审+上期AJE+上期RJE）
 *   派生行 R11 / R13 / R20 的月度与调整列跨行算（L82_DERIVED_ROW_SOURCES / L82_DERIVED_AMOUNT_FIELDS）
 * - 合计 = 净财务费用（模板 R22：利息净支出 + 未确认融资费用 − 未实现融资收益 + 承兑汇票贴息
 *   + 汇兑净损失 + 手续费及其他，L82_TOTAL_TERMS）；新增行不在模板合计里
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
  L82_DERIVED_AMOUNT_FIELDS,
  L82_TOTAL_TERMS,
  l82TemplateRowId,
  isL82TemplateRowId,
  isL82DerivedRowKey,
  isL82DerivedAmountField,
  rowsForStore,
} from '../l8/core/l8DetailRowIdentity'
import {
  calcAuditedAmount,
  calcSubtotal,
  calcChangeRate,
  calcChangeAmount,
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
  /** 占比（R列，公式=IF(Q=0,0,Q/Q22)，比值；显示时 ×100%） */
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

/** 合计行 R22：本期审定 Q22、上期审定 W22 */
export interface L82Totals {
  periodAudited: number
  priorAudited: number
}

/**
 * 按模板合计行 R22 求合计（`Q22 = Q13 + Q14 − Q15 + Q16 + Q20 + Q21`，W 同）。
 * rows 是已算好公式列的行；只取 `L82_TOTAL_TERMS` 六个骨架行，新增行不计入（模板合计公式里没有它们）。
 * 原先把全部行相加：利息费用总额 / 利息费用 / 利息净支出三层重复计入、各「减：」行反当加项。
 */
export function calcL82Totals(rows: readonly L8DetailRow[]): L82Totals {
  const byKey = new Map(rows.map(r => [r.key, r]))
  let periodAudited = 0
  let priorAudited = 0
  for (const [idx, sign] of L82_TOTAL_TERMS) {
    const row = byKey.get(l82TemplateRowId(idx))
    if (!row) continue
    periodAudited += sign * (Number(row.periodAudited) || 0)
    priorAudited += sign * (Number(row.priorAudited) || 0)
  }
  return { periodAudited, priorAudited }
}

/**
 * 各行公式列（纯函数，不碰 store）：派生行跨行算、N=SUM(B:M)、Q=N+O+P、W=T+U+V、
 * 占比 R = IF(Q=0, 0, Q / Q22)（比值，模板格式 0.00%）。
 */
export function computeL8DetailRows(base: readonly L8DetailRow[]): L8DetailRow[] {
  // 🔴 方案 D1：派生行（利息费用 R11 / 利息净支出 R13 / 汇兑净损失 R20）按模板跨行减法由上方科目算出
  //   （只读显示，不持久化）：1~12 月，加上 L82_DERIVED_AMOUNT_FIELDS 列出的调整 / 上期列。
  //   按下标从小到大算 ⇒ R13 取的是已算好的 R11（原先读 base 里未计算的 R11，R13 恒为「−利息收入」）。
  const resolved: L8DetailRow[] = base.map(row => ({ ...row }))
  const derivedIndices = Object.keys(L82_DERIVED_ROW_SOURCES).map(Number).sort((a, b) => a - b)
  for (const idx of derivedIndices) {
    const row = resolved[idx]
    if (!row || !isL82DerivedRowKey(row.key)) continue
    const sources = L82_DERIVED_ROW_SOURCES[idx]
    const combine = (read: (src: L8DetailRow) => unknown): number =>
      sources.reduce((sum, [srcIdx, sign]) => {
        const src = resolved[srcIdx]
        return src ? sum + sign * (Number(read(src)) || 0) : sum
      }, 0)
    const next: L8DetailRow = {
      ...row,
      monthly: Array.from({ length: 12 }, (_, m) => combine(src => src.monthly?.[m])) as L8DetailRow['monthly'],
    }
    for (const field of L82_DERIVED_AMOUNT_FIELDS[idx] ?? []) next[field] = combine(src => src[field])
    resolved[idx] = next
  }

  const rowsWithFormulas = resolved.map(row => {
    // N=SUM(B:M) 本期未审合计
    const periodUnadjusted = calcSubtotal(row.monthly as unknown as number[])
    // Q=N+O+P 本期审定
    const periodAudited = calcAuditedAmount(periodUnadjusted, row.aje, row.rje)
    // W=T+U+V 上期审定
    const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
    return { ...row, periodUnadjusted, periodAudited, priorAudited }
  })

  // R = IF(Q=0,0,Q/$Q$22)：合计为 0 时模板是 #DIV/0!，表单记 0
  const total = calcL82Totals(rowsWithFormulas).periodAudited
  return rowsWithFormulas.map(row => ({
    ...row,
    ratio: row.periodAudited === 0 || total === 0 ? 0 : row.periodAudited / total,
  }))
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

  /** 各行公式列自动计算（纯函数 computeL8DetailRows） */
  const computedRows: ComputedRef<L8DetailRow[]> = computed(() => computeL8DetailRows(detailRows.value))

  // ─── 3. 合计行 ────────────────────────────────────────────────────────

  const totals: ComputedRef<L82Totals> = computed(() => calcL82Totals(computedRows.value))

  /** 本期审定合计 = 模板合计行 Q22（净财务费用，供L8-1交叉验证） */
  const totalPeriodAudited: ComputedRef<number> = computed(() => totals.value.periodAudited)

  /** 上期审定合计 = 模板合计行 W22 */
  const totalPriorAudited: ComputedRef<number> = computed(() => totals.value.priorAudited)

  /** 是否有新增行（不在模板合计行里，界面提示用户并入相应项目） */
  const hasRowsOutsideTotal: ComputedRef<boolean> = computed(() =>
    computedRows.value.some(r => !isL82TemplateRowId(r.key)),
  )

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
    // 派生行的调整 / 上期列是模板跨行公式（只读，UI 已禁用，这里兜底）
    if (isL82DerivedAmountField(detailRows.value[index].key, field)) return
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
    // 🔴 存**算好公式列**的行：R 列占比是 auto_source（模板裸 IF 中性化后是字面量，由表单写入），
    //   原先存 detailRows（占比恒 0）⇒ OnlyOffice 侧各项目占比全是 0.00%。
    debouncedSave('L8-2-full-data', {
      remark: JSON.stringify(rowsForStore(computedRows.value)),
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
    hasRowsOutsideTotal,

    // 行操作
    addRow,
    removeRow,
    updateRow,
    updateMonthly,
  }
}

export default useL8Detail
