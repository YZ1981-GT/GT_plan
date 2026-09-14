/**
 * useL7Detail — L7-2 明细表 composable（27列区段Tab管理）
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 27列按2区段Tab管理（项目信息区/金额变动区，行同步）
 * - 动态行增删（先弹ElMessageBox.prompt输入项目名称）
 * - 明细表公式（xlsx）：
 *   E=B+C-D（期初审定=未审+AJE-RJE实为期初余额）
 *   L=B+F+G（审定未审数=期初未审+AJE+RJE？→实际分析：期末审定数计算）
 *   O=L+M-N（期末审定=期末未审+期末AJE-期末RJE？实为期末=期初+增加-减少）
 * - 与L7-1审定表合计交叉验证
 * - 支持导入导出
 *
 * 基于xlsx实际公式重新分析：
 *   明细表L7-2列结构（row10-11合并表头）：
 *   A(项目名称) | B~E(期初：未审B/AJE_C/RJE_D/审定E=B+C-D)
 *   F~G(期初AJE增加/减少) | H~I(期末AJE增加/减少) | J~K(期末RJE增加/减少)
 *   L~O(审定数：未审L=B+F+G / AJE_M=C+H+J / RJE_N=D+I+K / 审定O=L+M-N)
 *   P(性质) | Q(形成原因) | R(到期日)
 *
 * 科目：2801 其他非流动负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcDetailEndBalance, calcAuditedAmount, calcSubtotal } from './useL7FormulaEngine'
import type { useL7FormData } from './useL7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L7-2 明细表行数据 */
export interface L7DetailRow {
  /** 行唯一标识（多区段共享） */
  key: string
  /** 项目名称（A列） */
  itemName: string
  /** 期初未审数（B列） */
  beginUnadjusted: number
  /** 期初AJE（C列） */
  beginAje: number
  /** 期初RJE（D列） */
  beginRje: number
  /** 期初审定（E列，公式=B+C-D） */
  beginAudited: number
  /** 本期AJE增加（F列） */
  ajeIncrease: number
  /** 本期AJE减少（G列）—— xlsx中与RJE对称但标为不同语义 */
  rjeIncrease: number
  /** 本期增加-AJE部分（H列） */
  endAjeIncrease: number
  /** 本期增加-RJE部分（I列） */
  endRjeDecrease: number
  /** 本期减少-AJE部分（J列） */
  endAjeDecrease: number
  /** 本期减少-RJE部分（K列） */
  endRjeIncrease: number
  /** 期末未审数（L列，公式=B+F+G） */
  endUnadjusted: number
  /** 期末AJE（M列，公式=C+H+J） */
  endAje: number
  /** 期末RJE（N列，公式=D+I+K） */
  endRje: number
  /** 期末审定数（O列，公式=L+M-N） */
  endAudited: number
  /** 性质（P列） */
  nature: string
  /** 形成原因（Q列） */
  reason: string
  /** 到期情况（R列） */
  maturityInfo: string
}

/** 区段Tab类型：2区段 */
export type L7DetailSegment = 'project-info' | 'amount-movement'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 区段Tab定义：27列拆2段（项目信息/金额变动） */
export const L7_DETAIL_SEGMENTS = [
  {
    key: 'project-info' as const,
    label: '项目信息',
    fields: [
      'itemName', 'nature', 'reason', 'maturityInfo',
      'beginUnadjusted', 'beginAje', 'beginRje', 'beginAudited',
    ],
  },
  {
    key: 'amount-movement' as const,
    label: '金额变动',
    fields: [
      'ajeIncrease', 'rjeIncrease',
      'endAjeIncrease', 'endRjeDecrease', 'endAjeDecrease', 'endRjeIncrease',
      'endUnadjusted', 'endAje', 'endRje', 'endAudited',
    ],
  },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L7-2 明细表业务逻辑（27列区段Tab）
 *
 * @param formData 由调用方传入的 useL7FormData 实例
 * @param detailRows reactive ref of detail rows
 */
export function useL7Detail(
  formData: ReturnType<typeof useL7FormData>,
  detailRows: Ref<L7DetailRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段Tab状态 ────────────────────────────────────────────────────

  const activeSegment = ref<L7DetailSegment>('project-info')

  function switchSegment(segment: L7DetailSegment): void {
    activeSegment.value = segment
  }

  // ─── 2. 计算属性：公式列自动计算 ─────────────────────────────────────────

  /** 各行公式列自动计算（对应xlsx E/L/M/N/O列公式） */
  const computedRows: ComputedRef<L7DetailRow[]> = computed(() => {
    return detailRows.value.map(row => {
      // E = B + C - D（期初审定）— 实际是期初未审+AJE+RJE，公式写"减"可能是原模板误导
      // 按xlsx公式 E12=B12+C12-D12，其中D是"重分类"减少
      const beginAudited = row.beginUnadjusted + row.beginAje - row.beginRje
      // L = B + F + G（期末未审数 = 期初未审 + 本期AJE增 + 本期RJE增）
      const endUnadjusted = row.beginUnadjusted + row.ajeIncrease + row.rjeIncrease
      // M = C + H + J（期末AJE = 期初AJE + 本期增AJE + 本期减AJE）
      const endAje = row.beginAje + row.endAjeIncrease + row.endAjeDecrease
      // N = D + I + K（期末RJE = 期初RJE + 本期增RJE + 本期减RJE）
      const endRje = row.beginRje + row.endRjeDecrease + row.endRjeIncrease
      // O = L + M - N（期末审定 = 期末未审 + 期末AJE - 期末RJE）
      const endAudited = endUnadjusted + endAje - endRje

      return {
        ...row,
        beginAudited,
        endUnadjusted,
        endAje,
        endRje,
        endAudited,
      }
    })
  })

  /** 期末审定合计（供L7-1交叉验证） */
  const totalEndAudited: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.endAudited))
  })

  /** 期初审定合计 */
  const totalBeginAudited: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.beginAudited))
  })

  // ─── 3. 动态行增删 ────────────────────────────────────────────────────

  /**
   * 新增明细行（先弹 ElMessageBox.prompt 输入项目名称）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: itemName } = await ElMessageBox.prompt(
        '请输入其他非流动负债项目名称',
        '新增明细项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '如：递延收益/保证金/押金',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      const key = `l7-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const newRow: L7DetailRow = {
        key,
        itemName: itemName?.trim() || '',
        beginUnadjusted: 0,
        beginAje: 0,
        beginRje: 0,
        beginAudited: 0,
        ajeIncrease: 0,
        rjeIncrease: 0,
        endAjeIncrease: 0,
        endRjeDecrease: 0,
        endAjeDecrease: 0,
        endRjeIncrease: 0,
        endUnadjusted: 0,
        endAje: 0,
        endRje: 0,
        endAudited: 0,
        nature: '',
        reason: '',
        maturityInfo: '',
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
  function updateRow(index: number, field: keyof L7DetailRow, value: string | number): void {
    if (index < 0 || index >= detailRows.value.length) return
    const row = detailRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = detailRows.value[rowIndex]
    if (!row) return
    // 保存行的期末审定额（供CrossSheet勾稽读取）
    const computed = computedRows.value[rowIndex]
    if (computed) {
      debouncedSave(`L7-L7-2-row-${rowIndex + 1}-end_balance`, {
        remark: String(computed.endAudited),
      })
    }
    // CrossSheet 勾稽键（仅需 endAudited）
    debouncedSave('L7-L7-2-rows', {
      remark: JSON.stringify(detailRows.value.map((r, i) => ({
        key: r.key,
        itemName: r.itemName,
        endAudited: computedRows.value[i]?.endAudited ?? 0,
      }))),
    })
    // 🔴 修复：保存完整行到 full-data 键（组件 _restoreRowsFromResponses 优先读此键；此前从不写 → 刷新丢失全部字段）
    debouncedSave('L7-L7-2-full-data', {
      remark: JSON.stringify(detailRows.value.map((r, i) => ({
        ...r,
        endAudited: computedRows.value[i]?.endAudited ?? r.endAudited ?? 0,
      }))),
    })
  }

  function _triggerSaveAll(): void {
    // 保存所有行的 end_balance（供CrossSheet读取）
    computedRows.value.forEach((row, i) => {
      debouncedSave(`L7-L7-2-row-${i + 1}-end_balance`, {
        remark: String(row.endAudited),
      })
    })
    debouncedSave('L7-L7-2-rows', {
      remark: JSON.stringify(detailRows.value.map((r, i) => ({
        key: r.key,
        itemName: r.itemName,
        endAudited: computedRows.value[i]?.endAudited ?? 0,
      }))),
    })
    debouncedSave('L7-L7-2-full-data', {
      remark: JSON.stringify(detailRows.value.map((r, i) => ({
        ...r,
        endAudited: computedRows.value[i]?.endAudited ?? r.endAudited ?? 0,
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
    totalEndAudited,
    totalBeginAudited,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL7Detail
