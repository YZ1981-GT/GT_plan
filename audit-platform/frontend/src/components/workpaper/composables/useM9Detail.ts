/**
 * useM9Detail — M9-2 明细表 composable（30列区段Tab管理）
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 3.4
 * Requirements: 3.1-3.7
 *
 * 职责：
 * - OCI分项明细管理：不可重分类(G8公允变动/J2重计量) + 可重分类(其他债权/套期/外币折算)
 * - 30列按区段Tab管理（不可重分类/可重分类/税额区段，行同步）
 * - 34公式全部前端实时计算：
 *   税后净额 = 税前发生 - 所得税影响（calcAfterTaxNet）
 *   期末 = 期初 + 贷方(增加) - 借方(减少)（权益类！calcEquityEndBalance）
 *   审定数 = 未审 + AJE + RJE（calcAuditedAmount）
 * - 动态行新增（ElMessageBox.prompt输入项目名称）
 * - 导入导出数据准备
 * - 与M9-1审定表交叉验证
 *
 * 科目：4103 其他综合收益（**贷方/权益类！期末=期初+贷方-借方**）
 * OCI各项目按税后净额列示
 *
 * 46×30结构，34公式
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM9FormulaEngine'
import { calcAfterTaxNet } from './useM9OciEngine'
import type { useM9FormData } from './useM9FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** OCI分类 */
export type M9OciCategory = 'nonReclass' | 'reclass'

/** M9-2 明细表行数据（30列） */
export interface M9DetailRow {
  /** 行唯一标识 */
  key: string
  /** OCI项目名称（A列） */
  itemName: string
  /** 分类：不可重分类/可重分类 */
  ociCategory: M9OciCategory
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 本期税前发生额（C列，贷方增加为正，借方减少为负） */
  preTaxAmount: number
  /** 所得税影响额（D列，正数=税额扣减） */
  taxEffect: number
  /** 本期税后净额（E列，公式=C-D，calcAfterTaxNet） */
  afterTaxNet: number
  /** 本期贷方发生-OCI增加（F列） */
  creditAmount: number
  /** 本期借方发生-OCI减少/重分类（G列） */
  debitAmount: number
  /** 期末余额（H列，公式=B+F-G，权益类！） */
  endBalance: number
  // ─── AJE/RJE调整列（审定口径） ───
  /** 期初AJE（I列） */
  beginAje: number
  /** 期初RJE（J列） */
  beginRje: number
  /** 税前AJE（K列） */
  preTaxAje: number
  /** 税前RJE（L列） */
  preTaxRje: number
  /** 税额AJE（M列） */
  taxAje: number
  /** 税额RJE（N列） */
  taxRje: number
  // ─── 审定列（公式列） ───
  /** 审定期初（O列，公式=B+I+J） */
  auditedBegin: number
  /** 审定税前（P列，公式=C+K+L） */
  auditedPreTax: number
  /** 审定税额（Q列，公式=D+M+N） */
  auditedTax: number
  /** 审定税后净额（R列，公式=P-Q） */
  auditedAfterTaxNet: number
  /** 审定期末（S列，公式=O+auditedCredit-auditedDebit，权益类！） */
  auditedEnd: number
  // ─── 上期对比 ───
  /** 上期期初（T列） */
  priorBeginning: number
  /** 上期税后净额（U列） */
  priorAfterTaxNet: number
  /** 上期期末（V列） */
  priorEnd: number
  // ─── 变动+备注 ───
  /** 变动额（W列=S-V） */
  changeAmount: number
  /** 变动率（X列） */
  changeRate: number
  /** 来源底稿编码（Y列，如G8/J2） */
  sourceWpCode: string
  /** 备注（Z列） */
  remark: string
}

/** 区段Tab类型 */
export type M9DetailSegment = 'nonReclass' | 'reclass' | 'tax'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：30列拆3段 */
export const M9_DETAIL_SEGMENTS = [
  {
    key: 'nonReclass' as const,
    label: '不可重分类',
    description: '以后不能重分类进损益的OCI（G8公允变动+J2重计量）',
    fields: ['itemName', 'beginning', 'preTaxAmount', 'taxEffect', 'afterTaxNet', 'creditAmount', 'debitAmount', 'endBalance', 'beginAje', 'beginRje', 'auditedBegin', 'auditedEnd'],
  },
  {
    key: 'reclass' as const,
    label: '可重分类',
    description: '以后能重分类进损益的OCI（其他债权+套期+外币折算）',
    fields: ['itemName', 'beginning', 'preTaxAmount', 'taxEffect', 'afterTaxNet', 'creditAmount', 'debitAmount', 'endBalance', 'beginAje', 'beginRje', 'auditedBegin', 'auditedEnd'],
  },
  {
    key: 'tax' as const,
    label: '税额区段',
    description: '所得税影响明细（递延所得税资产/负债对OCI的影响）',
    fields: ['itemName', 'preTaxAmount', 'taxEffect', 'afterTaxNet', 'preTaxAje', 'preTaxRje', 'taxAje', 'taxRje', 'auditedPreTax', 'auditedTax', 'auditedAfterTaxNet', 'changeAmount', 'changeRate', 'sourceWpCode', 'remark'],
  },
] as const

/** 默认OCI分项明细行 */
export const M9_DETAIL_DEFAULT_ITEMS: Array<{ name: string; category: M9OciCategory; source: string }> = [
  // 不可重分类
  { name: '其他权益工具投资公允价值变动', category: 'nonReclass', source: 'G8' },
  { name: '设定受益计划重计量', category: 'nonReclass', source: 'J2' },
  // 可重分类
  { name: '其他债权投资公允价值变动', category: 'reclass', source: '' },
  { name: '现金流量套期损益', category: 'reclass', source: '' },
  { name: '外币财务报表折算差额', category: 'reclass', source: '' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M9-2 明细表业务逻辑（30列区段Tab + 34公式 + 税后净额）
 *
 * @param formData 由调用方传入的 useM9FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM9Detail(
  formData: ReturnType<typeof useM9FormData>,
  detailRows: Ref<M9DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<M9DetailSegment>('nonReclass')

  function switchSegment(segment: M9DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：34公式全部前端实时计算 ────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M9DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // E=C-D 本期税后净额
      const afterTaxNet = calcAfterTaxNet(row.preTaxAmount, row.taxEffect)
      // H=B+F-G 期末余额（权益类！）
      const endBalance = calcEquityEndBalance(row.beginning, row.creditAmount, row.debitAmount)
      // O=B+I+J 审定期初
      const auditedBegin = calcAuditedAmount(row.beginning, row.beginAje, row.beginRje)
      // P=C+K+L 审定税前
      const auditedPreTax = calcAuditedAmount(row.preTaxAmount, row.preTaxAje, row.preTaxRje)
      // Q=D+M+N 审定税额
      const auditedTax = calcAuditedAmount(row.taxEffect, row.taxAje, row.taxRje)
      // R=P-Q 审定税后净额
      const auditedAfterTaxNet = calcAfterTaxNet(auditedPreTax, auditedTax)
      // S=O+审定贷方-审定借方 简化为 O+auditedAfterTaxNet（期末=期初+本期净增减）
      const auditedEnd = auditedBegin + auditedAfterTaxNet
      // W=S-V 变动额
      const changeAmount = auditedEnd - row.priorEnd
      // X 变动率
      const changeRate = row.priorEnd === 0
        ? (auditedEnd === 0 ? 0 : 1)
        : (auditedEnd - row.priorEnd) / row.priorEnd

      return {
        ...row,
        afterTaxNet,
        endBalance,
        auditedBegin,
        auditedPreTax,
        auditedTax,
        auditedAfterTaxNet,
        auditedEnd,
        changeAmount,
        changeRate,
      }
    })
  })

  // ─── 3. 按分类过滤+合计 ───────────────────────────────────────────────

  /** 不可重分类行 */
  const nonReclassRows: ComputedRef<M9DetailRow[]> = computed(() => {
    return computedRows.value.filter(r => r.ociCategory === 'nonReclass')
  })

  /** 可重分类行 */
  const reclassRows: ComputedRef<M9DetailRow[]> = computed(() => {
    return computedRows.value.filter(r => r.ociCategory === 'reclass')
  })

  /** 各列合计（供审定表交叉验证） */
  const totals = computed(() => {
    const r = computedRows.value
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const preTaxAmount = calcSubtotal(r.map(x => x.preTaxAmount))
    const taxEffect = calcSubtotal(r.map(x => x.taxEffect))
    const afterTaxNet = calcAfterTaxNet(preTaxAmount, taxEffect)
    const creditAmount = calcSubtotal(r.map(x => x.creditAmount))
    const debitAmount = calcSubtotal(r.map(x => x.debitAmount))
    const endBalance = calcEquityEndBalance(beginning, creditAmount, debitAmount)
    const auditedBegin = calcSubtotal(r.map(x => x.auditedBegin))
    const auditedPreTax = calcSubtotal(r.map(x => x.auditedPreTax))
    const auditedTax = calcSubtotal(r.map(x => x.auditedTax))
    const auditedAfterTaxNet = calcAfterTaxNet(auditedPreTax, auditedTax)
    const auditedEnd = auditedBegin + auditedAfterTaxNet
    return {
      beginning,
      preTaxAmount,
      taxEffect,
      afterTaxNet,
      creditAmount,
      debitAmount,
      endBalance,
      auditedBegin,
      auditedPreTax,
      auditedTax,
      auditedAfterTaxNet,
      auditedEnd,
    }
  })

  /** 不可重分类合计（供M9-1 CrossSheet交叉验证） */
  const nonReclassTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(nonReclassRows.value.map(x => x.auditedEnd))
  })

  /** 可重分类合计（供M9-1 CrossSheet交叉验证） */
  const reclassTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(reclassRows.value.map(x => x.auditedEnd))
  })

  /** 审定期末合计（供M9-1交叉验证） */
  const totalAuditedEnd: ComputedRef<number> = computed(() => totals.value.auditedEnd)

  // ─── 4. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入OCI项目名称）
   */
  async function addRow(defaultCategory?: M9OciCategory): Promise<void> {
    try {
      const { value: itemName } = await ElMessageBox.prompt(
        '请输入OCI项目名称',
        '新增OCI明细项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：其他权益工具投资公允变动/外币折算差额',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      const key = `m9-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M9DetailRow = {
        key,
        itemName: itemName?.trim() || '',
        ociCategory: defaultCategory || 'nonReclass',
        beginning: 0,
        preTaxAmount: 0,
        taxEffect: 0,
        afterTaxNet: 0,
        creditAmount: 0,
        debitAmount: 0,
        endBalance: 0,
        beginAje: 0,
        beginRje: 0,
        preTaxAje: 0,
        preTaxRje: 0,
        taxAje: 0,
        taxRje: 0,
        auditedBegin: 0,
        auditedPreTax: 0,
        auditedTax: 0,
        auditedAfterTaxNet: 0,
        auditedEnd: 0,
        priorBeginning: 0,
        priorAfterTaxNet: 0,
        priorEnd: 0,
        changeAmount: 0,
        changeRate: 0,
        sourceWpCode: '',
        remark: '',
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
  function updateRow(index: number, field: keyof M9DetailRow, value: any): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  // ─── 5. 导入导出数据准备 ──────────────────────────────────────────────

  /** 导出数据准备（所有计算行+合计行，30列完整数据） */
  function prepareExportData(): { rows: M9DetailRow[]; totals: typeof totals.value } {
    return {
      rows: computedRows.value,
      totals: totals.value,
    }
  }

  /** 导入数据（替换所有行） */
  function importData(imported: Array<Partial<M9DetailRow>>): void {
    detailRows.value = imported.map((item, i) => ({
      key: item.key || `m9-detail-import-${i}-${Date.now()}`,
      itemName: item.itemName || '',
      ociCategory: item.ociCategory || 'nonReclass',
      beginning: item.beginning || 0,
      preTaxAmount: item.preTaxAmount || 0,
      taxEffect: item.taxEffect || 0,
      afterTaxNet: 0,
      creditAmount: item.creditAmount || 0,
      debitAmount: item.debitAmount || 0,
      endBalance: 0,
      beginAje: item.beginAje || 0,
      beginRje: item.beginRje || 0,
      preTaxAje: item.preTaxAje || 0,
      preTaxRje: item.preTaxRje || 0,
      taxAje: item.taxAje || 0,
      taxRje: item.taxRje || 0,
      auditedBegin: 0,
      auditedPreTax: 0,
      auditedTax: 0,
      auditedAfterTaxNet: 0,
      auditedEnd: 0,
      priorBeginning: item.priorBeginning || 0,
      priorAfterTaxNet: item.priorAfterTaxNet || 0,
      priorEnd: item.priorEnd || 0,
      changeAmount: 0,
      changeRate: 0,
      sourceWpCode: item.sourceWpCode || '',
      remark: item.remark || '',
    }))
    _triggerSaveAll()
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const computed = computedRows.value[rowIndex]
    // 保存审定期末（供CrossSheet勾稽）
    if (computed) {
      debouncedSave(`M9-2-row-${rowIndex}-auditedEnd`, {
        remark: String(computed.auditedEnd),
      })
    }
    // 保存行完整数据
    debouncedSave(`M9-2-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        ociCategory: row.ociCategory,
        beginning: row.beginning,
        preTaxAmount: row.preTaxAmount,
        taxEffect: row.taxEffect,
        creditAmount: row.creditAmount,
        debitAmount: row.debitAmount,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        preTaxAje: row.preTaxAje,
        preTaxRje: row.preTaxRje,
        taxAje: row.taxAje,
        taxRje: row.taxRje,
        priorBeginning: row.priorBeginning,
        priorAfterTaxNet: row.priorAfterTaxNet,
        priorEnd: row.priorEnd,
        sourceWpCode: row.sourceWpCode,
        remark: row.remark,
      }),
    })
    // 保存明细表审定期末合计（供M9-1交叉验证）
    debouncedSave('M9-2-auditedEndTotal', {
      remark: String(totalAuditedEnd.value),
    })
    // 同步写整包JSON（与M9TabDetail._initDefaultRows读取路径 getField('2','detail-rows') 一致）
    _syncFullData()
  }

  function _triggerSaveAll(): void {
    computedRows.value.forEach((_, i) => {
      _triggerSave(i)
    })
    _syncFullData()
  }

  /**
   * 同步写整包 full-data（保证 _initDefaultRows 读取路径 M9-2-detail-rows / conclusion 一致）
   * 只存基础字段（公式列 afterTaxNet/endBalance/auditedX/changeX 由 computedRows 重算）
   */
  function _syncFullData(): void {
    debouncedSave('M9-2-detail-rows', {
      conclusion: JSON.stringify(detailRows.value.map(row => ({
        key: row.key,
        itemName: row.itemName,
        ociCategory: row.ociCategory,
        beginning: row.beginning,
        preTaxAmount: row.preTaxAmount,
        taxEffect: row.taxEffect,
        creditAmount: row.creditAmount,
        debitAmount: row.debitAmount,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        preTaxAje: row.preTaxAje,
        preTaxRje: row.preTaxRje,
        taxAje: row.taxAje,
        taxRje: row.taxRje,
        priorBeginning: row.priorBeginning,
        priorAfterTaxNet: row.priorAfterTaxNet,
        priorEnd: row.priorEnd,
        sourceWpCode: row.sourceWpCode,
        remark: row.remark,
      }))),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段Tab
    activeSegment,
    switchSegment,

    // 计算属性
    computedRows,
    nonReclassRows,
    reclassRows,
    totals,
    nonReclassTotal,
    reclassTotal,
    totalAuditedEnd,

    // 行操作
    addRow,
    removeRow,
    updateRow,

    // 导入导出
    prepareExportData,
    importData,
  }
}

export default useM9Detail
