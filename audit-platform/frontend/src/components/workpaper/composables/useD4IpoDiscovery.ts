/**
 * useD4IpoDiscovery — D4-29/30/31/32 IPO 风险发现 → 人工认定 → A13
 *
 * spec: d4-ipo-fraud-writeback-formula-io（Task 4 / Task 5）
 *
 * 铁律（Requirements 3.1/3.2）：
 *  · 高风险客户、访谈红旗、异常流水先保留发现/风险记录，不自动造错报。
 *  · 描述型 amount=0 不能自动进 A13。
 *  · reason 或"否"非空不能单独判异常。
 *  · 人工确认方向、金额和证据后才发布 A13。
 *  · D4-31 findings/q5_otherMatters 留痕。
 *
 * 复用 useD4InspectionWriteback 做最终 A13 推送。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { useD4InspectionWriteback, type D4Discovery } from './useD4InspectionWriteback'

// ─── 发现来源类型 ─────────────────────────────────────────────────────

export type DiscoverySource =
  | 'D4-29-risk'       // 客户信息异常（关联方/供应商/失信/拖欠等）
  | 'D4-30-interview'  // 访谈异常发现
  | 'D4-31-redFlag'    // 访谈记录红旗
  | 'D4-32-anomaly'    // 资金流水异常

export interface IpoDiscoveryCandidate {
  /** 稳定 id（=来源表 item_id + 行/客户 id） */
  sourceId: string
  /** 来源类型 */
  source: DiscoverySource
  /** 描述（含溯源信息） */
  description: string
  /** 关联客户/单位名称 */
  entityName: string
  /** 候选金额（发现时可为 0，人工确认时必须 >0） */
  amount: number
  /** 人工确认状态 */
  confirmed: boolean
  /** 确认后的方向 */
  direction?: 'debit' | 'credit' | null
  /** 确认后的证据索引 */
  evidence?: string
}

export interface UseD4IpoDiscoveryOptions {
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly: Ref<boolean>
}

// ─── Composable ──────────────────────────────────────────────────────

export function useD4IpoDiscovery(options: UseD4IpoDiscoveryOptions) {
  const { projectId, isReadonly } = options

  const candidates = ref<IpoDiscoveryCandidate[]>([])

  // 四个来源的 writeback 实例（共用 A13 推送逻辑）
  const writeback = useD4InspectionWriteback({
    wpCode: 'D4-IPO',
    projectId,
    defaultAccountCode: '6001',
    defaultAccountName: '主营业务收入',
  })

  // ─── 发现收集（各 Tab 调用） ─────────────────────────────────────

  /**
   * 从 D4-29 客户信息提取风险发现。
   * 只收集风险标记（关联方/供应商/失信/拖欠），不自动判为错报。
   */
  function collectD429Risks(customers: Array<{ id: string; name: string; fields: Record<string, string> }>) {
    const risks: IpoDiscoveryCandidate[] = []
    for (const cust of customers) {
      const flags: string[] = []
      if (cust.fields.isRelated === '是') flags.push('关联方')
      if (cust.fields.isAlsoSupplier === '是') flags.push('同时为供应商')
      if (cust.fields.isBlacklisted === '是') flags.push('列入失信人')
      if (cust.fields.hasOverdue === '是') flags.push('长期拖欠')
      if (flags.length > 0) {
        risks.push({
          sourceId: `D4-29:${cust.id}`,
          source: 'D4-29-risk',
          description: `客户「${cust.name}」存在风险标记：${flags.join('、')}`,
          entityName: cust.name,
          amount: 0,
          confirmed: false,
        })
      }
    }
    // 替换（不累加）D4-29 来源的候选
    candidates.value = [
      ...candidates.value.filter(c => c.source !== 'D4-29-risk'),
      ...risks,
    ]
  }

  /**
   * 从 D4-30 访谈汇总提取异常发现。
   * 结论含「异常」/「不一致」/「存疑」等关键词时标记。
   */
  function collectD430Findings(customers: Array<{ id: string; name: string; fields: Record<string, string> }>) {
    const RISK_KEYWORDS = ['异常', '不一致', '存疑', '不匹配', '拒绝', '不配合', '矛盾']
    const findings: IpoDiscoveryCandidate[] = []
    for (const cust of customers) {
      const conclusion = cust.fields.conclusion || ''
      const matched = RISK_KEYWORDS.filter(kw => conclusion.includes(kw))
      if (matched.length > 0) {
        findings.push({
          sourceId: `D4-30:${cust.id}`,
          source: 'D4-30-interview',
          description: `客户「${cust.name}」访谈结论含风险关键词：${matched.join('、')}`,
          entityName: cust.name,
          amount: 0,
          confirmed: false,
        })
      }
    }
    candidates.value = [
      ...candidates.value.filter(c => c.source !== 'D4-30-interview'),
      ...findings,
    ]
  }

  /**
   * 从 D4-31 访谈记录提取红旗发现。
   * q5_otherMatters 非空 → 留痕；四章节中的异常选项也标记。
   */
  function collectD431RedFlags(data: Record<string, any>) {
    const flags: string[] = []
    if (data.q5_otherMatters && String(data.q5_otherMatters).trim()) {
      flags.push(`其他重要事项: ${String(data.q5_otherMatters).trim().slice(0, 80)}`)
    }
    if (data.q4_otherFunds === '是') {
      flags.push('存在其他资金往来')
    }
    const target = data.target || '未知客户'
    const findings: IpoDiscoveryCandidate[] = []
    if (flags.length > 0) {
      findings.push({
        sourceId: `D4-31:${target}`,
        source: 'D4-31-redFlag',
        description: `访谈对象「${target}」红旗: ${flags.join('; ')}`,
        entityName: target,
        amount: 0,
        confirmed: false,
      })
    }
    candidates.value = [
      ...candidates.value.filter(c => c.source !== 'D4-31-redFlag'),
      ...findings,
    ]
  }

  /**
   * 从 D4-32 资金流水提取异常发现。
   * hasAnomaly === '是' 的行。
   */
  function collectD432Anomalies(groups: Array<{ key: string; rows: Array<{ id: string; name: string; amount: number | string; hasAnomaly: string }> }>) {
    const anomalies: IpoDiscoveryCandidate[] = []
    for (const g of groups) {
      for (const row of g.rows) {
        if (row.hasAnomaly === '是') {
          const amt = typeof row.amount === 'number' ? row.amount : parseFloat(String(row.amount)) || 0
          anomalies.push({
            sourceId: `D4-32:${g.key}:${row.id}`,
            source: 'D4-32-anomaly',
            description: `${g.key}组「${row.name}」发现异常交易（金额: ${amt}）`,
            entityName: row.name,
            amount: amt,
            confirmed: false,
          })
        }
      }
    }
    candidates.value = [
      ...candidates.value.filter(c => c.source !== 'D4-32-anomaly'),
      ...anomalies,
    ]
  }

  // ─── 人工确认 ───────────────────────────────────────────────────

  /**
   * 审计师确认一条候选为错报。
   * 必须提供 direction、evidence，且 amount > 0。
   */
  function confirmCandidate(
    sourceId: string,
    direction: 'debit' | 'credit',
    amount: number,
    evidence: string,
  ): boolean {
    if (isReadonly.value) return false
    if (amount <= 0 || !evidence.trim()) return false
    const c = candidates.value.find(x => x.sourceId === sourceId)
    if (!c) return false
    c.confirmed = true
    c.direction = direction
    c.amount = amount
    c.evidence = evidence
    return true
  }

  /**
   * 将已确认的候选推送到 A13。
   * 复用 useD4InspectionWriteback 的 pushConfirmed。
   */
  function pushToA13(): number {
    if (isReadonly.value) return 0
    const confirmed = candidates.value
      .filter(c => c.confirmed && !writeback.isPushed(c.sourceId))
      .map((c): D4Discovery => ({
        sourceId: c.sourceId,
        description: c.description,
        direction: c.direction,
        amount: c.amount,
        evidence: c.evidence,
      }))
    return writeback.pushConfirmed(confirmed)
  }

  // ─── 统计 ──────────────────────────────────────────────────────

  const totalCandidates = computed(() => candidates.value.length)
  const confirmedCount = computed(() => candidates.value.filter(c => c.confirmed).length)
  const pushedCount = computed(() => {
    let n = 0
    for (const c of candidates.value) {
      if (writeback.isPushed(c.sourceId)) n++
    }
    return n
  })

  return {
    candidates,
    totalCandidates,
    confirmedCount,
    pushedCount,
    collectD429Risks,
    collectD430Findings,
    collectD431RedFlags,
    collectD432Anomalies,
    confirmCandidate,
    pushToA13,
    canConfirm: writeback.canConfirm,
    isPushed: writeback.isPushed,
  }
}

export default useD4IpoDiscovery
