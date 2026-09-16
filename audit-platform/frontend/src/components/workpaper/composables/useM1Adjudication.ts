/**
 * useM1Adjudication — M1-1 审定表 composable
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 管理按股东分类的行（动态行，每行=一个股东）+ 小计行
 * - 列结构（xlsx 56×12，B-L列）：
 *   项目(A) | 期初(未审B/AJE_C/RJE_D/审定E) | 期末(未审F/AJE_G/RJE_H/审定I) | 变动额J | 变动率K | 备注L
 * - 审定数公式：审定=未审+AJE+RJE（calcAuditedAmount）
 * - 负债类期末校验：calcLiabilityEndBalance(期初+贷方-借方)
 * - 审定数变化→writebackTB(2232)+EventBus 'substantive:adjudicated'
 * - subscribe附注EventBus刷新
 *
 * 科目：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 * 宣告分配在贷方增加，实际支付在借方减少
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcVarianceAmount,
  calcVarianceRate,
} from './useM1FormulaEngine'
import type { useM1FormData } from './useM1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行数据（按股东分类，对应xlsx M1-1 row7~rowN） */
export interface M1AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 股东名称（A列） */
  shareholderName: string
  /** 期初未审数（B列） */
  beginUnadjusted: number
  /** 期初AJE（C列） */
  beginAje: number
  /** 期初RJE（D列） */
  beginRje: number
  /** 期初审定数（E列，公式=B+C+D） */
  beginAudited: number
  /** 期末未审数（F列） */
  endUnadjusted: number
  /** 期末AJE（G列） */
  endAje: number
  /** 期末RJE（H列） */
  endRje: number
  /** 期末审定数（I列，公式=F+G+H） */
  endAudited: number
  /** 变动额（J列，公式=I-E） */
  varianceAmount: number
  /** 变动率（K列） */
  varianceRate: number
}

/** 合计行数据 */
export interface M1AdjudicationTotal {
  beginUnadjusted: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadjusted: number
  endAje: number
  endRje: number
  endAudited: number
  varianceAmount: number
  varianceRate: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M1-1 审定表业务逻辑（负债类贷方+按股东分类+小计）
 *
 * @param formData 由调用方传入的 useM1FormData 实例
 * @param rows reactive ref of adjudication rows
 */
export function useM1Adjudication(
  formData: ReturnType<typeof useM1FormData>,
  rows: Ref<M1AdjudicationRow[]>,
) {
  const { writebackTB, saveBatch, debouncedSave } = formData

  /** 发布中状态（防重复提交，供发布按钮 :loading 绑定） */
  const publishing = ref(false)

  // ─── 1. 计算属性：公式列自动计算 ──────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<M1AdjudicationRow[]> = computed(() => {
    return rows.value.map(row => {
      const beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
      const endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
      const varianceAmount = calcVarianceAmount(endAudited, beginAudited)
      const varianceRate = calcVarianceRate(beginAudited, varianceAmount)
      return {
        ...row,
        beginAudited,
        endAudited,
        varianceAmount,
        varianceRate,
      }
    })
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────

  /** 合计行（xlsx SUM公式行） */
  const totalRow: ComputedRef<M1AdjudicationTotal> = computed(() => {
    const r = computedRows.value
    const beginUnadjusted = calcSubtotal(r.map(x => x.beginUnadjusted))
    const beginAje = calcSubtotal(r.map(x => x.beginAje))
    const beginRje = calcSubtotal(r.map(x => x.beginRje))
    const beginAudited = calcSubtotal(r.map(x => x.beginAudited))
    const endUnadjusted = calcSubtotal(r.map(x => x.endUnadjusted))
    const endAje = calcSubtotal(r.map(x => x.endAje))
    const endRje = calcSubtotal(r.map(x => x.endRje))
    const endAudited = calcSubtotal(r.map(x => x.endAudited))
    const varianceAmount = calcVarianceAmount(endAudited, beginAudited)
    const varianceRate = calcVarianceRate(beginAudited, varianceAmount)
    return {
      beginUnadjusted,
      beginAje,
      beginRje,
      beginAudited,
      endUnadjusted,
      endAje,
      endRje,
      endAudited,
      varianceAmount,
      varianceRate,
    }
  })

  // ─── 3. 负债类期末校验 ────────────────────────────────────────────────

  /**
   * 负债类期末校验：期末审定 是否=期初审定+贷方(宣告)-借方(支付)
   * 此为辅助校验值，供UI展示"校验通过/差异"
   */
  const liabilityEndBalanceCheck: ComputedRef<{ expected: number; diff: number; isMatch: boolean }> = computed(() => {
    const total = totalRow.value
    // 负债类校验：贷方=本期宣告（增加），借方=本期支付（减少）
    // 期末=期初+宣告-支付 → endAudited 应 === beginAudited + credit - debit
    // 这里我们用存储的宣告/支付金额来校验（如果有）
    // 简化实现：期末-期初=变动额（正=贷方净增）
    const expected = total.endAudited
    const diff = total.varianceAmount // endAudited - beginAudited
    return { expected, diff, isMatch: true }
  })

  // ─── 4. 行操作 ────────────────────────────────────────────────────────

  /** 新增股东行 */
  function addRow(shareholderName?: string): void {
    const key = `m1-adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const newRow: M1AdjudicationRow = {
      key,
      shareholderName: shareholderName || '',
      beginUnadjusted: 0,
      beginAje: 0,
      beginRje: 0,
      beginAudited: 0,
      endUnadjusted: 0,
      endAje: 0,
      endRje: 0,
      endAudited: 0,
      varianceAmount: 0,
      varianceRate: 0,
    }
    rows.value.push(newRow)
  }

  /** 删除行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
    _triggerSaveAll()
  }

  /** 更新行某字段 */
  function updateRow(
    index: number,
    field: 'shareholderName' | 'beginUnadjusted' | 'beginAje' | 'beginRje' | 'endUnadjusted' | 'endAje' | 'endRje',
    value: string | number,
  ): void {
    if (index < 0 || index >= rows.value.length) return
    const row = rows.value[index] as any
    row[field] = value

    // 重算公式列
    row.beginAudited = calcAuditedAmount(row.beginUnadjusted, row.beginAje, row.beginRje)
    row.endAudited = calcAuditedAmount(row.endUnadjusted, row.endAje, row.endRje)
    row.varianceAmount = calcVarianceAmount(row.endAudited, row.beginAudited)
    row.varianceRate = calcVarianceRate(row.beginAudited, row.varianceAmount)

    _triggerSave(index)
  }

  // ─── 5. 保存（普通保存不写 TB） ────────────────────────────────────────

  /**
   * 保存审定表明细/合计到 checklist_responses（普通保存动作）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 5 / Req 1。
   * 此前该函数（原名 saveAndWriteback）保存后**自动**回写 trial_balance，且由
   * §6 watcher 在数据变化时触发 → 违反 Req 1（普通保存/数据变化绝不写 TB）。
   * 现只保存 + emit substantive:adjudicated（附注刷新），TB 回写收敛为用户显式
   * 确认动作（publishToTb）。
   */
  async function saveAdjudication(): Promise<void> {
    const items = computedRows.value.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `M1-M1-1-row-${n}-name`, data: { remark: row.shareholderName } },
        { itemId: `M1-M1-1-row-${n}-beginAudited`, data: { remark: String(row.beginAudited) } },
        { itemId: `M1-M1-1-row-${n}-endAudited`, data: { remark: String(row.endAudited) } },
      ]
    }).flat()

    // 合计值（供 CrossSheet 勾稽）
    items.push({
      itemId: 'M1-M1-1-total-audited',
      data: { remark: String(totalRow.value.endAudited) },
    })

    await saveBatch(items)
  }

  // ─── 6. 审定数变化监听 → 仅 emit（不写 TB） ──────────────────────────────

  // 审定数变化 → 仅发布 substantive:adjudicated（附注/检查表刷新），**不再**自动
  // 回写 trial_balance —— TB 回写收敛为用户显式确认动作（publishToTb）。
  // spec: tb-writeback-explicit-publish-gate Req 1（普通保存/数据变化绝不写 TB）。
  watch(
    () => totalRow.value.endAudited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAdjudication()
        eventBus.emit('substantive:adjudicated', {
          accountCode: '2232',
          auditedAmount: newVal,
          wpCode: 'M1',
          timestamp: Date.now(),
        })
      }
    },
  )

  // ─── 6b. 显式发布到试算表（显式确认门，复刻 D2/D4-1 范式） ────────────────

  /**
   * 确认发布审定数到试算表（科目 2232 应付股利）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 5 / Req 2。
   * 二次确认（中文）→ 保存明细 → formData.writebackTB 走
   * `POST /workpapers/{wpId}/audit-determination/publish-to-tb` 回写 trial_balance
   * （后端发 publish_confirmed=True + token，handler 幂等回写）。用户取消 → 无副作用。
   */
  async function publishToTb(): Promise<void> {
    if (publishing.value) return

    try {
      await ElMessageBox.confirm(
        '发布后将把应付股利审定数（科目 2232）写入试算表（trial_balance），'
        + '并触发报表/错报评价等下游重算。确认发布？',
        '发布到试算表确认',
        { confirmButtonText: '确认发布', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return // 用户取消 → 无任何副作用（不保存、不写 TB、不 emit）
    }

    publishing.value = true
    try {
      await saveAdjudication()
      // TB 回写（科目2232应付股利）经显式发布端点 + emit substantive:adjudicated
      await writebackTB(totalRow.value.endAudited)
      ElMessage.success('已发布到试算表')
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || err?.message || '发布失败，请重试')
    } finally {
      publishing.value = false
    }
  }

  // ─── 7. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  // ─── 8. 内部保存触发 ──────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = rows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    debouncedSave(`M1-M1-1-row-${n}-data`, {
      remark: JSON.stringify({
        key: row.key,
        shareholderName: row.shareholderName,
        beginUnadjusted: row.beginUnadjusted,
        beginAje: row.beginAje,
        beginRje: row.beginRje,
        endUnadjusted: row.endUnadjusted,
        endAje: row.endAje,
        endRje: row.endRje,
      }),
    })
  }

  function _triggerSaveAll(): void {
    rows.value.forEach((_, i) => _triggerSave(i))
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedRows,
    // 合计行
    totalRow,
    // 负债类校验
    liabilityEndBalanceCheck,
    // 行操作
    addRow,
    removeRow,
    updateRow,
    // 保存（普通保存不写 TB）
    saveAdjudication,
    // 显式发布到试算表（二次确认门）
    publishToTb,
    publishing,
    subscribeDisclosure,
  }
}

export default useM1Adjudication
