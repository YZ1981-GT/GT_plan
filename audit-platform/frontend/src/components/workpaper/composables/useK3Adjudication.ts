/**
 * useK3Adjudication — K3-1 审定表逻辑（负债类！50公式）
 *
 * Spec: .kiro/specs/k3-other-payables/
 * Task: 3.4
 * Requirements: 2.1-2.7, 7.1-7.4
 *
 * 职责：
 * - 双区块：按性质分类(保证金/往来款/代收代付/其他) + 按账龄分类(**动态段**from useAgingConfig)
 * - 每行：审定=未审+AJE+RJE, 期末=期初+贷方-借方(负债类！), 变动率
 * - 合计行=Σ各行
 * - 三角勾稽差额校验
 * - TB回写(2241) + EventBus 'substantive:adjudicated'
 * - 底部审计说明+结论（含完整性认定说明）
 * - TB预填：无持久化数据时从tbData.unadjusted2241 seed未审数到性质合计行
 *
 * 科目：2241 其他应付款（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+贷方-借方（与资产类相反）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcTriangleReconciliation,
  calcChangeRate,
  calcSubtotal,
} from './useK3FormulaEngine'
import type { K3TbData } from './useK3FormData'
import type { AgingSegment } from '@/composables/useAgingConfig'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K3AdjRow {
  rowKey: string
  label: string
  begin: number        // 期初余额
  credit: number       // 本期贷方发生额（增加，负债增加在贷方）
  debit: number        // 本期借方发生额（减少，负债减少在借方）
  end: number          // 期末余额（公式：期初+贷-借）
  unadjusted: number   // 未审数
  aje: number          // AJE
  rje: number          // RJE
  audited: number      // 审定数（公式：未审+AJE+RJE）
  changeRate: number   // 变动率
  remark: string
}

export interface K3ReconciliationResult {
  diff: number
  isBalanced: boolean
}

export interface UseK3AdjudicationParams {
  allResponses: Ref<Map<string, any>>
  tbData: Ref<K3TbData>
  saveResponse: Function
  /** 动态账龄段（from useAgingConfig） */
  agingSegments?: Ref<AgingSegment[]>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVal(map: Map<string, any>, itemId: string): string {
  return map.get(itemId)?.remark ?? ''
}

function num(map: Map<string, any>, itemId: string): number {
  const v = getVal(map, itemId)
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 性质分类预设标签 ─────────────────────────────────────────────────────────

const NATURE_ROW_LABELS = ['保证金及押金', '往来款', '代收代付', '其他']
/** 旧硬编码兜底（仅当 agingSegments 未传入时使用） */
const DEFAULT_AGING_ROW_LABELS = ['1年以内', '1-2年', '2-3年', '3年以上']

/**
 * 旧 item_id rowKey 映射表（保留对旧持久化数据的兼容）
 * 旧数据 item_id: K3-1-aging-r0-begin ... K3-1-aging-r3-begin
 * 新动态段 item_id: K3-1-aging-{seg.key}-begin
 * 读取时两套 key 都尝试
 */
const LEGACY_AGING_ROWKEY: Record<string, string> = {
  within1: 'r0',
  y1to2: 'r1',
  y2to3: 'r2',
  over3: 'r3',
  y3to4: 'r3',  // FIVE_YEAR 的 3-4年 复用旧 r3 slot（兜底）
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK3Adjudication(params: UseK3AdjudicationParams) {
  const { allResponses, tbData, saveResponse, agingSegments } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const auditConclusion = ref('')
  const completenessNote = ref('')  // 完整性认定说明

  // ─── 构建行数据（负债类！期末=期初+贷-借） ────────────────────────────────────

  function buildRow(prefix: string, rowKey: string, label: string): K3AdjRow {
    const id = `K3-1-${prefix}-${rowKey}`
    const begin = num(allResponses.value, `${id}-begin`)
    const credit = num(allResponses.value, `${id}-credit`)
    const debit = num(allResponses.value, `${id}-debit`)
    // 负债类！期末=期初+贷方-借方
    const end = calcLiabilityEndBalance(begin, credit, debit)
    const unadjusted = num(allResponses.value, `${id}-unadj`)
    const aje = num(allResponses.value, `${id}-aje`)
    const rje = num(allResponses.value, `${id}-rje`)
    const audited = calcAuditedAmount(unadjusted, aje, rje)
    const prior = num(allResponses.value, `${id}-prior-audited`)
    const changeRate = calcChangeRate(audited, prior)
    const remark = getVal(allResponses.value, `${id}-remark`)
    return { rowKey, label, begin, credit, debit, end, unadjusted, aje, rje, audited, changeRate, remark }
  }

  function buildSubtotalRow(label: string, rows: K3AdjRow[]): K3AdjRow {
    const s = (fn: (r: K3AdjRow) => number) => calcSubtotal(rows.map(fn))
    const audited = s(r => r.audited)
    const priorTotal = s(r => {
      // 各行prior之和
      return num(allResponses.value, `K3-1-nature-${r.rowKey}-prior-audited`)
    })
    return {
      rowKey: 'subtotal', label,
      begin: s(r => r.begin), credit: s(r => r.credit), debit: s(r => r.debit),
      end: s(r => r.end), unadjusted: s(r => r.unadjusted),
      aje: s(r => r.aje), rje: s(r => r.rje), audited,
      changeRate: calcChangeRate(audited, priorTotal), remark: '',
    }
  }

  // ─── 按性质分类区块 (Req 2.1: 保证金/往来款/代收代付/其他) ──────────────────

  const byNatureRows: ComputedRef<K3AdjRow[]> = computed(() => {
    const rows: K3AdjRow[] = []
    const count = num(allResponses.value, 'K3-1-nature-count') || NATURE_ROW_LABELS.length
    for (let i = 0; i < count; i++) {
      const label = getVal(allResponses.value, `K3-1-nature-r${i}-label`) || NATURE_ROW_LABELS[i] || `项目${i + 1}`
      rows.push(buildRow('nature', `r${i}`, label))
    }
    return rows
  })

  // ─── 按账龄分类区块（**动态段**，from useAgingConfig → agingSegments） ────

  const byAgingRows: ComputedRef<K3AdjRow[]> = computed(() => {
    const rows: K3AdjRow[] = []
    const segs = agingSegments?.value

    if (segs && segs.length > 0) {
      // 动态段模式：按项目账龄配置生成行
      for (const seg of segs) {
        // 优先用 seg.key 作为 item_id rowKey；兼容旧持久化数据用 LEGACY_AGING_ROWKEY 回退
        const legacyKey = LEGACY_AGING_ROWKEY[seg.key]
        // 尝试新 key：K3-1-aging-{seg.key}-begin
        const newId = `K3-1-aging-${seg.key}`
        const hasNewData = allResponses.value.has(`${newId}-begin`) || allResponses.value.has(`${newId}-unadj`)
        // 尝试旧 key：K3-1-aging-r{N}-begin
        const legacyId = legacyKey ? `K3-1-aging-${legacyKey}` : null
        const hasLegacyData = legacyId ? (allResponses.value.has(`${legacyId}-begin`) || allResponses.value.has(`${legacyId}-unadj`)) : false

        // 优先新key，回退旧key
        const effectiveRowKey = hasNewData ? seg.key : (hasLegacyData && legacyKey ? legacyKey : seg.key)
        rows.push(buildRow('aging', effectiveRowKey, seg.label))
      }
    } else {
      // 兜底：无动态段时使用旧硬编码（向后兼容）
      const count = num(allResponses.value, 'K3-1-aging-count') || DEFAULT_AGING_ROW_LABELS.length
      for (let i = 0; i < count; i++) {
        const label = getVal(allResponses.value, `K3-1-aging-r${i}-label`) || DEFAULT_AGING_ROW_LABELS[i] || `账龄${i + 1}`
        rows.push(buildRow('aging', `r${i}`, label))
      }
    }
    return rows
  })

  // ─── 合计行 ────────────────────────────────────────────────────────────────

  const natureSubtotal: ComputedRef<K3AdjRow> = computed(() => {
    return buildSubtotalRow('合计', byNatureRows.value)
  })

  const agingSubtotal: ComputedRef<K3AdjRow> = computed(() => {
    const rows = byAgingRows.value
    const s = (fn: (r: K3AdjRow) => number) => calcSubtotal(rows.map(fn))
    const audited = s(r => r.audited)
    const priorTotal = s(r => num(allResponses.value, `K3-1-aging-${r.rowKey}-prior-audited`))
    return {
      rowKey: 'subtotal', label: '合计',
      begin: s(r => r.begin), credit: s(r => r.credit), debit: s(r => r.debit),
      end: s(r => r.end), unadjusted: s(r => r.unadjusted),
      aje: s(r => r.aje), rje: s(r => r.rje), audited,
      changeRate: calcChangeRate(audited, priorTotal), remark: '',
    }
  })

  // ─── 三角勾稽校验 (Req 2.4) ─────────────────────────────────────────────────

  const reconciliation: ComputedRef<K3ReconciliationResult> = computed(() => {
    const row = natureSubtotal.value
    // 负债类：增加=贷方 减少=借方
    const diff = calcTriangleReconciliation(row.begin, row.credit, row.debit, row.end)
    return { diff, isBalanced: Math.abs(diff) < 0.01 }
  })

  // ─── 从 allResponses 初始化审计说明 + TB预填seed ─────────────────────────

  function initFromResponses(): void {
    auditConclusion.value = getVal(allResponses.value, 'K3-1-audit-conclusion')
    completenessNote.value = getVal(allResponses.value, 'K3-1-completeness-note')
  }

  /**
   * TB预填：仅在性质行全部未审数为0且无持久化数据时，
   * 将tbData.unadjusted2241 seed到性质合计的"其他"行未审数（兜底预填）。
   * 持久化优先——已编辑过的不覆盖。
   */
  function seedFromTbIfEmpty(): void {
    const tbUnadj = tbData.value?.unadjusted2241 ?? 0
    if (tbUnadj === 0) return
    // 检查是否所有性质行未审数都为0（无人录入）
    const hasAnyUnadj = byNatureRows.value.some(r => r.unadjusted !== 0)
    if (hasAnyUnadj) return
    // 检查是否有持久化的审定数合计（说明已编辑过）
    const savedTotal = num(allResponses.value, 'K3-1-audited-total')
    if (savedTotal !== 0) return
    // seed: 将TB未审数写入最后一行("其他")的未审数字段
    // 注：真正审定表应从tb_balance子科目分行预填，此处为兜底总额seed
    const lastIdx = byNatureRows.value.length - 1
    if (lastIdx >= 0) {
      const rowKey = `r${lastIdx}`
      const itemId = `K3-1-nature-${rowKey}-unadj`
      if (!allResponses.value.has(itemId)) {
        // 写入本地Map供computed链即时消费（不持久化，避免覆盖）
        allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: String(tbUnadj) })
      }
    }
  }

  // ─── 保存全部 ──────────────────────────────────────────────────────────────

  async function saveAll(): Promise<void> {
    // 保存审计结论
    await saveResponse('K3-1-audit-conclusion', { remark: auditConclusion.value })
    // 保存完整性认定说明
    await saveResponse('K3-1-completeness-note', { remark: completenessNote.value })
    // 保存审定数合计供跨sheet使用
    await saveResponse('K3-1-audited-total', { remark: String(natureSubtotal.value.audited) })
  }

  // ─── 获取审定数合计（供TB回写） ────────────────────────────────────────────

  function getAuditedTotal(): number {
    return natureSubtotal.value.audited
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })
  // TB数据到达后尝试seed
  watch(tbData, () => seedFromTbIfEmpty(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    byNatureRows,
    byAgingRows,
    natureSubtotal,
    agingSubtotal,
    auditConclusion,
    completenessNote,
    reconciliation,
    initFromResponses,
    seedFromTbIfEmpty,
    saveAll,
    getAuditedTotal,
  }
}
