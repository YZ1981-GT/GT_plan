/**
 * useM8Detail — M8-2 明细表 composable
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 3.4
 * Requirements: 3.1-3.2, 3.8
 *
 * 职责：
 * - 动态行管理（新增/删除行）+ 合计行（row 17）
 * - 列结构（24×18，56公式）：
 *   A:项目 | B:期初 | C:本期增加 | D:本期减少 | E:期末(=B+C-D)
 *   F:期初AJE | G:期初RJE | H:增加AJE | I:减少AJE | J:增加RJE | K:减少RJE
 *   L:审定期初(=B+F+G) | M:审定增加(=C+H+J) | N:审定减少(=D+I+K) | O:审定期末(=L+M-N)
 *   P:文件依据 | Q:索引号 | R:备注
 * - 公式：
 *   E=B+C-D（期末=期初+增加-减少，权益类贷方！）
 *   L=B+F+G（审定期初=未审期初+期初AJE+期初RJE）
 *   M=C+H+J（审定增加=未审增加+增加AJE+增加RJE）
 *   N=D+I+K（审定减少=未审减少+减少AJE+减少RJE）
 *   O=L+M-N（审定期末=审定期初+审定增加-审定减少，权益类！）
 * - Row 17: SUM(B10:B16) 等合计行
 * - 导入导出数据准备
 * - 与M8-1审定表交叉验证
 *
 * 科目：4104 一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 * 金融企业从净利润中计提（增加=贷方），转回/使用（减少=借方）
 *
 * 24×18结构，56公式
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from './useM8FormulaEngine'
import type { useM8FormData } from './useM8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** M8-2 明细表行数据（18列） */
export interface M8DetailRow {
  /** 行唯一标识 */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 期初余额（B列，贷方余额） */
  beginning: number
  /** 本期增加（C列，贷方计提增加） */
  increase: number
  /** 本期减少（D列，借方转回/使用减少） */
  decrease: number
  /** 期末余额（E列，公式=B+C-D，权益类！） */
  endBalance: number
  // ─── AJE/RJE调整列 ───
  /** 期初AJE（F列） */
  beginAje: number
  /** 期初RJE（G列） */
  beginRje: number
  /** 增加AJE（H列） */
  increaseAje: number
  /** 减少AJE（I列） */
  decreaseAje: number
  /** 增加RJE（J列） */
  increaseRje: number
  /** 减少RJE（K列） */
  decreaseRje: number
  // ─── 审定列（公式列） ───
  /** 审定期初（L列，公式=B+F+G） */
  auditedBegin: number
  /** 审定增加（M列，公式=C+H+J） */
  auditedIncrease: number
  /** 审定减少（N列，公式=D+I+K） */
  auditedDecrease: number
  /** 审定期末（O列，公式=L+M-N，权益类！） */
  auditedEnd: number
  // ─── 文件+备注 ───
  /** 文件依据（P列） */
  docReference: string
  /** 索引号（Q列） */
  refIndex: string
  /** 备注（R列） */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认明细项目（xlsx rows 10-15 对应的一般风险准备类别） */
export const M8_DETAIL_DEFAULT_ITEMS = [
  '一般风险准备',
  '信用风险准备',
  '市场风险准备',
  '操作风险准备',
  '其他风险准备',
  '合计调整',
]

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M8-2 明细表业务逻辑（18列 + 56公式 + 动态行）
 *
 * @param formData 由调用方传入的 useM8FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useM8Detail(
  formData: ReturnType<typeof useM8FormData>,
  detailRows: Ref<M8DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 计算属性：公式列全部前端实时计算 ──────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M8DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // E=B+C-D 期末余额（权益类：期初+增加-减少）
      const endBalance = calcEquityEndBalance(row.beginning, row.increase, row.decrease)
      // L=B+F+G 审定期初
      const auditedBegin = calcAuditedAmount(row.beginning, row.beginAje, row.beginRje)
      // M=C+H+J 审定增加
      const auditedIncrease = calcAuditedAmount(row.increase, row.increaseAje, row.increaseRje)
      // N=D+I+K 审定减少
      const auditedDecrease = calcAuditedAmount(row.decrease, row.decreaseAje, row.decreaseRje)
      // O=L+M-N 审定期末（权益类！）
      const auditedEnd = calcEquityEndBalance(auditedBegin, auditedIncrease, auditedDecrease)

      return {
        ...row,
        endBalance,
        auditedBegin,
        auditedIncrease,
        auditedDecrease,
        auditedEnd,
      }
    })
  })

  // ─── 2. 合计行（对应xlsx row 17: SUM(B10:B16)） ──────────────────────

  /** 各列合计（供审定表交叉验证） */
  const totals = computed(() => {
    const r = computedRows.value
    const beginning = calcSubtotal(r.map(x => x.beginning))
    const increase = calcSubtotal(r.map(x => x.increase))
    const decrease = calcSubtotal(r.map(x => x.decrease))
    const endBalance = calcEquityEndBalance(beginning, increase, decrease)
    const beginAje = calcSubtotal(r.map(x => x.beginAje))
    const beginRje = calcSubtotal(r.map(x => x.beginRje))
    const increaseAje = calcSubtotal(r.map(x => x.increaseAje))
    const decreaseAje = calcSubtotal(r.map(x => x.decreaseAje))
    const increaseRje = calcSubtotal(r.map(x => x.increaseRje))
    const decreaseRje = calcSubtotal(r.map(x => x.decreaseRje))
    const auditedBegin = calcAuditedAmount(beginning, beginAje, beginRje)
    const auditedIncrease = calcAuditedAmount(increase, increaseAje, increaseRje)
    const auditedDecrease = calcAuditedAmount(decrease, decreaseAje, decreaseRje)
    const auditedEnd = calcEquityEndBalance(auditedBegin, auditedIncrease, auditedDecrease)
    return {
      beginning,
      increase,
      decrease,
      endBalance,
      beginAje,
      beginRje,
      increaseAje,
      decreaseAje,
      increaseRje,
      decreaseRje,
      auditedBegin,
      auditedIncrease,
      auditedDecrease,
      auditedEnd,
    }
  })

  /** 审定期末合计（供M8-1交叉验证） */
  const totalAuditedEnd: ComputedRef<number> = computed(() => totals.value.auditedEnd)

  /** 审定期初合计（供M8-1交叉验证） */
  const totalAuditedBegin: ComputedRef<number> = computed(() => totals.value.auditedBegin)

  /** 审定增加合计（供附注引用） */
  const totalAuditedIncrease: ComputedRef<number> = computed(() => totals.value.auditedIncrease)

  /** 审定减少合计（供附注引用） */
  const totalAuditedDecrease: ComputedRef<number> = computed(() => totals.value.auditedDecrease)

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入项目名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: itemName } = await ElMessageBox.prompt(
        '请输入一般风险准备明细项目名称',
        '新增明细项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：信用风险准备/市场风险准备/操作风险准备',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      const key = `m8-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: M8DetailRow = {
        key,
        itemName: itemName?.trim() || '',
        beginning: 0,
        increase: 0,
        decrease: 0,
        endBalance: 0,
        beginAje: 0,
        beginRje: 0,
        increaseAje: 0,
        decreaseAje: 0,
        increaseRje: 0,
        decreaseRje: 0,
        auditedBegin: 0,
        auditedIncrease: 0,
        auditedDecrease: 0,
        auditedEnd: 0,
        docReference: '',
        refIndex: '',
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
  function updateRow(index: number, field: keyof M8DetailRow, value: any): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  // ─── 4. 导入导出数据准备 ──────────────────────────────────────────────

  /** 导出数据准备（所有计算行+合计行） */
  function prepareExportData(): { rows: M8DetailRow[]; totals: typeof totals.value } {
    return {
      rows: computedRows.value,
      totals: totals.value,
    }
  }

  /** 导入数据（替换所有行） */
  function importData(imported: Array<Partial<M8DetailRow>>): void {
    detailRows.value = imported.map((item, i) => ({
      key: item.key || `m8-detail-import-${i}-${Date.now()}`,
      itemName: item.itemName || '',
      beginning: item.beginning || 0,
      increase: item.increase || 0,
      decrease: item.decrease || 0,
      endBalance: 0,
      beginAje: item.beginAje || 0,
      beginRje: item.beginRje || 0,
      increaseAje: item.increaseAje || 0,
      decreaseAje: item.decreaseAje || 0,
      increaseRje: item.increaseRje || 0,
      decreaseRje: item.decreaseRje || 0,
      auditedBegin: 0,
      auditedIncrease: 0,
      auditedDecrease: 0,
      auditedEnd: 0,
      docReference: item.docReference || '',
      refIndex: item.refIndex || '',
      remark: item.remark || '',
    }))
    _triggerSaveAll()
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    const computed = computedRows.value[rowIndex]
    // 保存审定期末（供CrossSheet勾稽）
    if (computed) {
      debouncedSave(`M8-2-row-${rowIndex}-auditedEnd`, {
        remark: String(computed.auditedEnd),
      })
    }
    // 保存行完整数据
    debouncedSave(`M8-2-row-${rowIndex}-data`, {
      remark: JSON.stringify({
        key: row.key,
        itemName: row.itemName,
        beginning: row.beginning,
        increase: row.increase,
        decrease: row.decrease,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        increaseAje: row.increaseAje,
        decreaseAje: row.decreaseAje,
        increaseRje: row.increaseRje,
        decreaseRje: row.decreaseRje,
        docReference: row.docReference,
        refIndex: row.refIndex,
        remark: row.remark,
      }),
    })
    // 保存明细表审定期末合计（供M8-1交叉验证）
    debouncedSave('M8-2-auditedEndTotal', {
      remark: String(totalAuditedEnd.value),
    })
  }

  function _triggerSaveAll(): void {
    computedRows.value.forEach((_, i) => {
      _triggerSave(i)
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算属性
    computedRows,
    totals,
    totalAuditedEnd,
    totalAuditedBegin,
    totalAuditedIncrease,
    totalAuditedDecrease,

    // 行操作
    addRow,
    removeRow,
    updateRow,

    // 导入导出
    prepareExportData,
    importData,
  }
}

export default useM8Detail
