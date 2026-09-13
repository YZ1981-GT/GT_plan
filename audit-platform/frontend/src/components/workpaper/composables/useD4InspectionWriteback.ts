/**
 * useD4InspectionWriteback — D4-17/18/19/20 发现→人工确认门→A13 请求
 *
 * spec: d4-cutoff-return-writeback-formula-io（Task 4 / Task 5）
 * 挂靠总纲: d4-dual-mode-formula-governance
 *
 * 铁律（Requirements 3.1/3.2/3.3，与 memory「联动边界」一致）：
 *  · 风险发现 ≠ 错报：跨期/折扣/退货/计提差异先进入**候选风险记录**，不自动造错报。
 *  · A13 请求必须**人工逐项确认方向、金额、证据**后才形成；
 *    - amount<=0 的候选不可确认（错报汇总必须有金额）；
 *    - reason 或"否"非空不能单独判异常（证据缺失不可确认）。
 *  · 不自动推整笔凭证/客户收入；不推 amount=0 事项。
 *  · 发送 A13 用统一 `a13:push-misstatement` EventBus（唯一消费者
 *    `useA13MisstatementBridge` 负责 durable POST + 5s 去重幂等 + source_wp_code 溯源）；
 *    事件不代表成功，durable ack 由桥侧完成。本地维持 `pushedIds` 幂等标记防重复确认。
 *
 * 本 composable 只做「候选收集 + 人工确认过滤 + 规范化 emit」，不落库、不碰 TB。
 */
import { ref, computed, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'

/** 一条候选发现（尚未确认，不是错报）。 */
export interface D4Discovery {
  /** 稳定来源行 id（幂等 source identity 的一部分） */
  sourceId: string
  /** 描述（含凭证号/日期等溯源信息） */
  description: string
  /** 错报方向：借（多计资产/费用）/ 贷（多计收入/负债）—— 人工确认项 */
  direction?: 'debit' | 'credit' | null
  /** 金额（>0 才可确认；派生自公式，人工可核） */
  amount: number
  /** 证据索引（人工确认项，空则视为证据缺失不可确认） */
  evidence?: string
  /** 受影响科目编码 */
  accountCode?: string | null
  accountName?: string | null
}

export interface UseD4InspectionWritebackOptions {
  /** 来源底稿编码（如 D4-17，写入 source_wp_code 溯源） */
  wpCode: string
  projectId: Ref<string>
  /** 默认受影响科目（收入循环主营 6001） */
  defaultAccountCode?: string
  defaultAccountName?: string
}

export function useD4InspectionWriteback(options: UseD4InspectionWritebackOptions) {
  const { wpCode, projectId } = options

  /** 已确认并推送过的 sourceId（本地幂等标记，防重复确认重复推送）。 */
  const pushedIds = ref<Set<string>>(new Set())

  /**
   * 候选是否可确认为错报：
   *  - 金额 > 0（错报必须有金额，排除 amount=0）
   *  - 证据非空（reason/"否"非空不算证据，必须有索引证据）
   *  - 方向已定（借/贷，人工确认过）
   */
  function canConfirm(d: D4Discovery): boolean {
    return d.amount > 0 && !!(d.evidence && d.evidence.trim()) && (d.direction === 'debit' || d.direction === 'credit')
  }

  /** 是否已推送（幂等标记）。 */
  function isPushed(sourceId: string): boolean {
    return pushedIds.value.has(sourceId)
  }

  /**
   * 人工确认后推送已确认的候选到 A13。
   *
   * @param confirmed 已由审计师逐项确认方向/金额/证据的候选（调用方保证）
   * @returns 实际发出的错报笔数（已过滤不可确认与已推送）
   */
  function pushConfirmed(confirmed: D4Discovery[]): number {
    const items = confirmed.filter((d) => canConfirm(d) && !pushedIds.value.has(d.sourceId))
    if (!items.length) return 0

    eventBus.emit('a13:push-misstatement' as any, {
      wpCode,
      accountCode: options.defaultAccountCode ?? null,
      accountName: options.defaultAccountName ?? null,
      projectId: projectId.value,
      source: wpCode,
      // 事实错报：截止跨期/退货计提差异是已确认的具体错报
      misstatementType: 'factual',
      items: items.map((d) => ({
        // sourceId 内联进描述，形成幂等 source identity（桥侧 dedup hash 含 description）
        description: `${d.description}｜确认方向:${d.direction === 'debit' ? '借' : '贷'}｜证据:${d.evidence}`.trim(),
        amount: d.amount,
        accountCode: d.accountCode ?? options.defaultAccountCode ?? null,
        accountName: d.accountName ?? options.defaultAccountName ?? null,
        indexRef: d.sourceId,
      })),
      timestamp: Date.now(),
    })

    for (const d of items) pushedIds.value.add(d.sourceId)
    return items.length
  }

  return {
    pushedIds: computed(() => pushedIds.value),
    canConfirm,
    isPushed,
    pushConfirmed,
  }
}

export default useD4InspectionWriteback
