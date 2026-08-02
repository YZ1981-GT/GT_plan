/**
 * useK5Adjudication — K5-1 审定表逻辑（25行×12列，负债类，8类型行）
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.4
 * Requirements: 2.1-2.8
 *
 * 职责：
 * - 管理审定表状态：项目/期初/计提/转销/期末/未审/AJE/RJE/审定数/备注
 * - 8类型行：产品质保/未决诉讼/亏损合同/重组义务/弃置义务/其他/合计/差异
 * - 负债类公式：期末=期初+计提-转销
 * - 审定数=未审+AJE+RJE
 * - 三角勾稽校验（期末 vs 审定数）+ 红色高亮
 * - TB回写2701
 * - Save with prefix "K5-1-"
 *
 * 科目：2701 预计负债（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+计提-转销（与资产类相反）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from './useK5FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { K5TbData } from './useK5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K5AdjRow {
  rowKey: string
  label: string
  begin: number         // 期初余额
  provision: number     // 本期计提（增加）
  release: number       // 本期转销/冲回（减少）
  end: number           // 期末余额（公式：期初+计提-转销）
  unadjusted: number    // 未审数
  aje: number           // AJE
  rje: number           // RJE
  audited: number       // 审定数（公式：未审+AJE+RJE）
  remark: string
}

export interface K5ReconciliationResult {
  diff: number
  isBalanced: boolean
}

export interface UseK5AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  tbData: Ref<K5TbData>
  prefill?: Ref<Array<{ name: string; code?: string; opening_balance: number; closing_balance: number }> | undefined>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(map: Map<string, any>, itemId: string): string {
  const item = map.get(itemId)
  if (!item) return ''
  return item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : '')
}

function num(map: Map<string, any>, itemId: string): number {
  const v = getVal(map, itemId)
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 预设行标签（K5-1 审定表 8 类型行） ──────────────────────────────────────

const ROW_LABELS = [
  '产品质量保证',
  '未决诉讼',
  '亏损合同',
  '重组义务',
  '弃置义务',
  '其他',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Adjudication(params: UseK5AdjudicationParams) {
  const { allResponses, tbData, prefill, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const auditConclusion = ref('')

  // ─── 构建行数据（负债类！期末=期初+计提-转销） ─────────────────────────────

  function buildRow(rowKey: string, label: string): K5AdjRow {
    const id = `K5-1-${rowKey}`
    const begin = num(allResponses.value, `${id}-begin`)
    const provision = num(allResponses.value, `${id}-provision`)
    const release = num(allResponses.value, `${id}-release`)
    // 负债类：期末=期初+计提-转销
    const end = calcLiabilityEndBalance(begin, provision, release)
    const unadjusted = num(allResponses.value, `${id}-unadj`)
    const aje = num(allResponses.value, `${id}-aje`)
    const rje = num(allResponses.value, `${id}-rje`)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const remark = getVal(allResponses.value, `${id}-remark`)
    return { rowKey, label, begin, provision, release, end, unadjusted, aje, rje, audited, remark }
  }

  // ─── 行数据 ────────────────────────────────────────────────────────────────

  const rows: ComputedRef<K5AdjRow[]> = computed(() => {
    const result: K5AdjRow[] = []
    for (let i = 0; i < ROW_LABELS.length; i++) {
      result.push(buildRow(`r${i}`, ROW_LABELS[i]))
    }
    return result
  })

  // ─── 合计行 ────────────────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<K5AdjRow> = computed(() => {
    const r = rows.value
    const s = (fn: (row: K5AdjRow) => number) => calcSubtotal(r.map(fn))
    return {
      rowKey: 'subtotal',
      label: '合计',
      begin: s(row => row.begin),
      provision: s(row => row.provision),
      release: s(row => row.release),
      end: s(row => row.end),
      unadjusted: s(row => row.unadjusted),
      aje: s(row => row.aje),
      rje: s(row => row.rje),
      audited: s(row => row.audited),
      remark: '',
    }
  })

  // ─── 差异行（审定数 vs 期末） ──────────────────────────────────────────────

  const diffRow: ComputedRef<K5AdjRow> = computed(() => {
    const sub = subtotalRow.value
    return {
      rowKey: 'diff',
      label: '差异',
      begin: 0,
      provision: 0,
      release: 0,
      end: sub.audited - sub.end,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: sub.audited - sub.end,
      remark: '',
    }
  })

  // ─── 三角勾稽校验 (Req 2.5) ─────────────────────────────────────────────────

  const reconciliation: ComputedRef<K5ReconciliationResult> = computed(() => {
    const sub = subtotalRow.value
    // 勾稽：期末 是否等于 期初+计提-转销
    const expectedEnd = calcLiabilityEndBalance(sub.begin, sub.provision, sub.release)
    const diff = sub.end - expectedEnd
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── TB 勾稽（审定数 vs TB 审定） ─────────────────────────────────────────

  const tbReconciliation = computed(() => {
    const auditedTotal = subtotalRow.value.audited
    const tbAudited = tbData.value.audited
    const diff = auditedTotal - tbAudited
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── 从 tb_balance 明细子科目逐行预填（按 name 模糊匹配固定行） ──────────

  function seedFromPrefill(): void {
    if (!prefill?.value || prefill.value.length === 0) return
    // 仅在全部行未审数为 0 时 seed（手工优先）
    const hasAnyUnadj = rows.value.some(r => r.unadjusted !== 0)
    if (hasAnyUnadj) return

    for (const p of prefill.value) {
      const pName = (p.name || '').replace(/准备|损失|计提|义务/g, '').trim()
      // 按核心词模糊匹配 ROW_LABELS
      let matchIdx = ROW_LABELS.findIndex(label => {
        const core = label.replace(/准备|损失|计提|义务/g, '').trim()
        return core.includes(pName) || pName.includes(core)
      })
      // 未匹配 → 落入"其他"行（最后一行）
      if (matchIdx < 0) matchIdx = ROW_LABELS.length - 1

      const id = `K5-1-r${matchIdx}`
      // 写期初余额和期末未审数到 Map 触发 computed 重算
      const existing = num(allResponses.value, `${id}-unadj`)
      if (existing === 0) {
        allResponses.value.set(`${id}-begin`, { item_id: `${id}-begin`, conclusion: null, remark: String(p.opening_balance) })
        allResponses.value.set(`${id}-unadj`, { item_id: `${id}-unadj`, conclusion: null, remark: String(p.closing_balance) })
        // 持久化到 DB（一次性落库）
        saveResponse(`1-r${matchIdx}-begin`, { remark: String(p.opening_balance) })
        saveResponse(`1-r${matchIdx}-unadj`, { remark: String(p.closing_balance) })
      }
    }
  }

  // ─── 从 allResponses 初始化审计说明 ────────────────────────────────────────

  function initFromResponses(): void {
    auditConclusion.value = getVal(allResponses.value, 'K5-1-audit-conclusion')
  }

  // ─── 保存全部 ──────────────────────────────────────────────────────────────

  async function saveAll(): Promise<void> {
    await saveResponse('1-audit-conclusion', { remark: auditConclusion.value })
    await saveResponse('1-audited-total', { remark: String(subtotalRow.value.audited) })
  }

  // ─── 发布审定数事件（对齐 F4/D2 范式，通知附注/A13/下游） ───────────────────

  function publishAdjudicated(): void {
    const auditedAmount = subtotalRow.value.audited
    try {
      eventBus.emit('substantive:adjudicated', {
        wpCode: 'K5',
        accountCode: '2701',
        auditedAmount,
        adjudicatedAmount: auditedAmount,
        timestamp: Date.now(),
      } as any)
    } catch {
      console.warn('[useK5Adjudication] EventBus publish substantive:adjudicated failed')
    }
  }

  // ─── 获取审定数合计（供TB回写 + CrossSheet） ───────────────────────────────

  function getAuditedTotal(): number {
    return subtotalRow.value.audited
  }

  /** 获取指定类型行审定数（供专项检查交叉验证） */
  function getRowAudited(rowIndex: number): number {
    return rows.value[rowIndex]?.audited ?? 0
  }

  /** 获取产品质保行审定数（idx=0） */
  function getWarrantyAudited(): number {
    return getRowAudited(0)
  }

  /** 获取未决诉讼行审定数（idx=1） */
  function getLitigationAudited(): number {
    return getRowAudited(1)
  }

  /** 获取弃置义务行审定数（idx=4） */
  function getDecommissionAudited(): number {
    return getRowAudited(4)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })
  watch([() => prefill?.value], () => seedFromPrefill(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    subtotalRow,
    diffRow,
    auditConclusion,
    reconciliation,
    tbReconciliation,
    initFromResponses,
    saveAll,
    publishAdjudicated,
    getAuditedTotal,
    getRowAudited,
    getWarrantyAudited,
    getLitigationAudited,
    getDecommissionAudited,
  }
}
