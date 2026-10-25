/**
 * useL5Detail — L5-2 明细表 composable（30列按区段Tab管理）
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.4
 * Requirements: 3.1-3.2, 3.5-3.6
 *
 * 职责：
 * - 30列按区段Tab管理（未审数区/调整区/审定数区）
 * - 动态行增删（先弹ElMessageBox.prompt输入款项名称）
 * - 期末余额计算：负债类 期末=期初+贷方(增加)-借方(偿还)
 * - 与L5-1交叉验证（明细合计=审定表合计）
 * - 与L5-5摊销测算按款项一一对应
 *
 * 科目：2701 长期应付款（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { newRowIdentity } from './shared/rowIdentity'
import { calcLiabilityEndBalance, calcSubtotal } from './useL5FormulaEngine'
import type { useL5FormData, ChecklistResponse } from './useL5FormData'

/** 🔴 P0 修复：JSON 存储键（此前组件无 hydration + 保存仅序列化字段子集 → 刷新数据丢失/大部分字段丢失） */
const ITEM_ROWS = 'L5-L5-2-rows'

/**
 * L5-2 三区段归属值（spec l5-true-bidirectional-2026-10-01 · T2）。
 * 与后端 `phase5_l5_long_term_payables` 的 `row_section_value` 逐值对齐（售后租回 / 分期付款 / 其他）；
 * 引擎 `iter_store_rows` 按 `section` 过滤三个受管区（R11:15 / R18:22 / R24:24），
 * merge 给新增行补段归属 —— 缺它 OO 侧在区②/③插的行回前端会落错区。
 */
export type L5DetailSection = 'saleLeaseback' | 'installment' | 'other'
export const L5_SECTION_SALE_LEASEBACK: L5DetailSection = 'saleLeaseback'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * L5-2 明细表行数据。
 *
 * 🔴 字段分两类（spec l5-true-bidirectional-2026-10-01 · T2 方案 b）：
 *   - **受管列**（进契约、OO 侧双向回流）：Excel `明细表L5-2` 的 roll-forward / 多栏调整 / 披露 / 账龄列。
 *     见下方「受管区」注释块；行身份字段仍叫 `key`（非 rowId，照 T1/报告 §七）。
 *   - **html_only 列**（前端照常编辑、喂 L5-5/L5-6/L5-7，但不进契约、OO 侧不渲染）：融资属性 + HTML 旧标量调整。
 *     见 `L5_HTML_ONLY_KEYS`。退 html_only 不损失它们（HTML 侧照常编辑）。
 */
export interface L5DetailRow {
  /** 行唯一标识（多区段共享）。T2 起由 `newRowIdentity('l52det')` 铸造，保留字段名 `key`。 */
  key: string
  /** 🔴 区段归属（受管：引擎按它过滤三区）。saleLeaseback/installment/other。 */
  section: L5DetailSection

  // ── 受管区：Excel 列 A..S + 账龄 T~X（真双向回流） ───────────────────────
  /** A 债权人名称（款项来源/名称）。 */
  payableName: string
  /** B 期初余额（未审）。 */
  beginning: number
  /** C 借方发生（未审，HTML 语义「本期偿还」）。 */
  periodRepayment: number
  /** D 贷方发生（未审，HTML 语义「本期增加」）。 */
  periodIncrease: number
  /** E 期末余额＝B-C+D（公式列，只读派生）。 */
  endBalance: number
  /** F 期初调整-账项调整。 */
  priorAdjustment: number
  /** G 期初调整-重分类调整。 */
  priorReclass: number
  /** H 账项调整-借方发生。 */
  ajeDebit: number
  /** I 账项调整-贷方发生。 */
  ajeCredit: number
  /** J 重分类调整-借方发生。 */
  rjeDebit: number
  /** K 重分类调整-贷方发生。 */
  rjeCredit: number
  /** L 审定期初＝B+F+G（公式列，只读派生）。 */
  auditedBeginning: number
  /** M 审定借方＝C+H+J（公式列，只读派生）。 */
  auditedDebit: number
  /** N 审定贷方＝D+I+K（公式列，只读派生）。 */
  auditedCredit: number
  /** O 审定期末＝L-M+N（公式列，只读派生）。 */
  auditedEnding: number
  /** P 减：期初一年内到期长期应付款。 */
  minusPriorDue: number
  /** Q 减：期末一年内到期长期应付款。 */
  minusEndDue: number
  /** R 披露期初审定＝L-P（公式列，只读派生）。 */
  disclosureBeginning: number
  /** S 披露期末审定＝O-Q（公式列，只读派生）。 */
  disclosureEnding: number
  /** T 账龄：6个月以内。 */
  agingWithin6m: number
  /** U 账龄：6-12月。 */
  aging6to12m: number
  /** V 账龄：1～2年。 */
  aging1to2y: number
  /** W 账龄：２～3年。 */
  aging2to3y: number
  /** X 账龄：3年以上。 */
  agingOver3y: number

  // ── html_only：融资属性 + HTML 旧标量调整（不进契约，喂 L5-5/L5-6/L5-7） ──
  /** 债权人（html_only）。 */
  creditor: string
  /** 起始日期（html_only）。 */
  startDate: string
  /** 到期日期（html_only）。 */
  maturityDate: string
  /** 款项类型：融资租赁/分期付款/其他（html_only）。 */
  category: string
  /** 名义金额（合同总价，html_only，L5-5 摊销输入源）。 */
  nominalAmount: number
  /** 折现率（实际利率，html_only，L5-5 摊销输入源）。 */
  discountRate: number
  /** 现值（html_only，L5-5 摊销输入源）。 */
  presentValue: number
  /** 未审数（html_only，HTML 旧标量调整模型）。 */
  unadjusted: number
  /** AJE调整（html_only，HTML 旧标量调整模型）。 */
  aje: number
  /** RJE调整（html_only，HTML 旧标量调整模型）。 */
  rje: number
  /** 审定数（html_only，HTML 旧标量调整模型）。 */
  audited: number
  /** 币种（html_only）。 */
  currency: string
  /** 担保方式（html_only）。 */
  guaranteeType: string
  /** 备注（html_only）。 */
  remark: string
}

/**
 * 🔴 html_only 字段键（spec l5-true-bidirectional-2026-10-01 · T2，照 D4-5 范式）。
 * 这些列继续存在 `L5-L5-2-rows` 的 JSON 里、继续喂 L5-5/L5-6/L5-7，但**不进契约、OO 侧不渲染**。
 * 后端 provider 的 `html_only_keys` 必须与此逐值一致（adapter 测试守护）。
 */
export const L5_HTML_ONLY_KEYS = [
  'nominalAmount', 'discountRate', 'presentValue', 'startDate', 'maturityDate',
  'category', 'currency', 'guaranteeType', 'unadjusted', 'aje', 'rje', 'audited', 'creditor',
] as const

/** 构造一个全字段默认的 L5-2 行（新增/hydrate 补铸共用）。 */
export function createL5DetailRow(
  payableName: string,
  section: L5DetailSection = L5_SECTION_SALE_LEASEBACK,
): L5DetailRow {
  return {
    key: newRowIdentity('l52det'),
    section,
    payableName,
    beginning: 0, periodRepayment: 0, periodIncrease: 0, endBalance: 0,
    priorAdjustment: 0, priorReclass: 0,
    ajeDebit: 0, ajeCredit: 0, rjeDebit: 0, rjeCredit: 0,
    auditedBeginning: 0, auditedDebit: 0, auditedCredit: 0, auditedEnding: 0,
    minusPriorDue: 0, minusEndDue: 0, disclosureBeginning: 0, disclosureEnding: 0,
    agingWithin6m: 0, aging6to12m: 0, aging1to2y: 0, aging2to3y: 0, agingOver3y: 0,
    creditor: '', startDate: '', maturityDate: '', category: '',
    nominalAmount: 0, discountRate: 0, presentValue: 0,
    unadjusted: 0, aje: 0, rje: 0, audited: 0,
    currency: 'CNY', guaranteeType: '', remark: '',
  }
}

/** 区段Tab类型：3区段 */
export type L5DetailSegment = 'unadjusted' | 'adjustment' | 'audited'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：30列拆3段 */
export const L5_DETAIL_SEGMENTS = [
  {
    key: 'unadjusted' as const,
    label: '未审数区',
    fields: [
      'payableName', 'creditor', 'startDate', 'maturityDate', 'category',
      'nominalAmount', 'discountRate', 'presentValue', 'beginning',
      'periodIncrease', 'periodRepayment', 'endBalance',
    ],
  },
  {
    key: 'adjustment' as const,
    label: '调整区',
    fields: ['unadjusted', 'aje', 'rje', 'audited'],
  },
  {
    key: 'audited' as const,
    label: '审定数区',
    fields: ['currency', 'guaranteeType', 'remark'],
  },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L5-2 明细表业务逻辑（30列区段Tab）
 *
 * @param formData 由调用方传入的 useL5FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useL5Detail(
  formData: ReturnType<typeof useL5FormData>,
  detailRows: Ref<L5DetailRow[]>,
) {
  const { allResponses, debouncedSave } = formData

  // ─── 0. Hydration（从 allResponses 解析完整行 JSON） ─────────────────────
  function hydrate(): void {
    const raw = allResponses.value.get(ITEM_ROWS)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        // 🔴 历史行补铸：缺 key 的补铸稳定身份、已有优先保留；缺 section 的落默认区（售后租回）。
        detailRows.value = parsed.map((row: Partial<L5DetailRow>) => ({
          ...row,
          key: (typeof row.key === 'string' && row.key.trim()) ? row.key : newRowIdentity('l52det'),
          section: (row.section as L5DetailSection) || L5_SECTION_SALE_LEASEBACK,
        })) as L5DetailRow[]
      }
    } catch { /* ignore */ }
  }
  hydrate()
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (v) => { if (v && detailRows.value.length === 0) hydrate() },
  )

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L5DetailSegment>('unadjusted')

  function switchSegment(segment: L5DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：负债类期末余额 ─────────────────────────────────────────

  /** 各行期末余额自动计算（负债类：期初+贷方-借方） */
  const computedRows: ComputedRef<L5DetailRow[]> = computed(() => {
    return detailRows.value.map(row => ({
      ...row,
      // 负债类：期末 = 期初 + 本期增加(贷方) - 本期偿还(借方)
      endBalance: calcLiabilityEndBalance(row.beginning, row.periodIncrease, row.periodRepayment),
    }))
  })

  /** 期末余额合计（供L5-1交叉验证） */
  const totalEndBalance: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endBalance))
  })

  /** 期初余额合计 */
  const totalBeginning: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.beginning))
  })

  /** 名义金额合计 */
  const totalNominalAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(detailRows.value.map(r => r.nominalAmount))
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入款项名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: payableName } = await ElMessageBox.prompt(
        '请输入款项来源/名称',
        '新增长期应付款明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：XX融资租赁/XX设备分期付款',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '款项名称不能为空'
            return true
          },
        },
      )

      // 新增行默认落售后租回区（区①）；区归属后续可由列设置切换（受管字段 section）。
      const newRow = createL5DetailRow(payableName?.trim() || '', L5_SECTION_SALE_LEASEBACK)
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
  function updateRow(index: number, field: keyof L5DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value

    // 如果是金额字段，重算期末余额
    if (['beginning', 'periodIncrease', 'periodRepayment'].includes(field)) {
      row.endBalance = calcLiabilityEndBalance(row.beginning, row.periodIncrease, row.periodRepayment)
    }

    _triggerSave(index)
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(_rowIndex?: number): void {
    // 序列化完整行数据（含所有字段）+ 保证 endBalance 新鲜，供持久化+CrossSheet勾稽
    const payload = detailRows.value.map(r => ({
      ...r,
      endBalance: calcLiabilityEndBalance(r.beginning, r.periodIncrease, r.periodRepayment),
    }))
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(payload) } as Partial<ChecklistResponse>)
  }

  function _triggerSaveAll(): void {
    _triggerSave()
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    totalEndBalance,
    totalBeginning,
    totalNominalAmount,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL5Detail
