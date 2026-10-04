/**
 * 合并页节点级异步加载的「请求上下文 + 递增序号」过期响应保护
 * （spec consol-node-key-isolation-and-shared-context 任务 5.4，需求 4.5 / 5.2，设计 §七、P9、ADR-CNSC-005）。
 *
 * 问题：快速切换 project / year / nodeKey 时，先发的慢请求后到，旧节点响应会覆盖当前节点
 * 的 consolReportRows / noteTree，造成跨节点数据串用。
 *
 * 设计（ADR-CNSC-005）：缓存分区与过期响应保护是两个独立条件，二者都必须满足。
 * 本模块只负责「过期响应保护」：
 *   - 每次发起加载前 begin()：捕获当时的 (projectId, year, nodeKey) 快照 + 该通道单调递增序号；
 *   - 响应回来提交前 isCurrent()：当且仅当「序号仍是该通道最新」且「上下文四元仍与当前一致」才允许提交；
 *     任一不满足即判定为过期，调用方必须丢弃该响应，不写入响应式状态、不写缓存。
 *
 * 关键点（禁止只依赖缓存或取消请求）：
 *   - 序号校验独立于缓存命中：即使缓存没命中、即使请求没被 AbortController 取消，旧响应也必须被拦下。
 *   - 取消请求只是资源优化，不能替代提交前校验（后到的旧响应即便未取消也会被序号/上下文判为过期）。
 *   - 同一通道内「序号最新」与「上下文一致」是两重独立闸门：
 *       · 同节点连发两次（context 相同），只有后一次序号最新 ⇒ 先到的旧序号响应被丢弃；
 *       · 切到新节点（context 不同）⇒ 旧节点响应即便序号在它自己通道里最新，上下文也已不符 ⇒ 丢弃。
 */

/** 节点级请求的上下文身份：与缓存 scope 同维度（project / year / nodeKey）。 */
export interface RequestContext {
  projectId: string | number
  year: number
  nodeKey: string
}

/** begin() 返回的一次性票据：记录发起时的上下文与该通道序号。 */
export interface RequestTicket {
  readonly channel: string
  readonly seq: number
  readonly context: RequestContext
}

/** 两个上下文四元是否逐项相等（projectId 用字符串比较，兼容 number/string）。 */
export function sameContext(a: RequestContext, b: RequestContext): boolean {
  return (
    String(a.projectId) === String(b.projectId) &&
    a.year === b.year &&
    a.nodeKey === b.nodeKey
  )
}

/**
 * 过期响应守卫：按通道维护单调递增序号。
 * 一个合并页用一个实例，不同加载通道（如 'report' / 'note'）互不干扰。
 */
export class ConsolRequestGuard {
  /** 每个通道的最新已发起序号。 */
  private latest = new Map<string, number>()

  /**
   * 发起一次加载，捕获当前上下文快照并递增该通道序号。
   * @param channel 加载通道标识（如 'report'、'note'）。
   * @param context 发起时的 (projectId, year, nodeKey) 快照。
   */
  begin(channel: string, context: RequestContext): RequestTicket {
    const seq = (this.latest.get(channel) ?? 0) + 1
    this.latest.set(channel, seq)
    return {
      channel,
      seq,
      // 复制一份，避免调用方后续 mutate 影响票据快照。
      context: { projectId: context.projectId, year: context.year, nodeKey: context.nodeKey },
    }
  }

  /**
   * 响应提交前校验：当且仅当「序号仍最新」且「上下文仍与 current 一致」才可提交。
   * @param ticket   begin() 返回的票据。
   * @param current  响应到达时读取的当前上下文（通常来自页面响应式状态）。
   * @returns true=最新且上下文一致，允许提交；false=过期，必须丢弃。
   */
  isCurrent(ticket: RequestTicket, current: RequestContext): boolean {
    // 闸门一：序号必须仍是该通道最新（同通道后发请求会推高序号，先到的旧响应即被判过期）。
    if (this.latest.get(ticket.channel) !== ticket.seq) return false
    // 闸门二：发起时上下文必须仍等于当前上下文（切 project/year/nodeKey 后旧响应被判过期）。
    if (!sameContext(ticket.context, current)) return false
    return true
  }
}
