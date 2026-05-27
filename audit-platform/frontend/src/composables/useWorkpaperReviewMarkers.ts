/**
 * useWorkpaperReviewMarkers — 底稿复核红点 composable
 *
 * R1 需求 2 验收 3：编制人打开被退回的底稿，编辑器在对应单元格显示红点
 * （读取 ReviewRecord.cell_reference 列表），点击红点弹出意见全文与关联工单。
 *
 * 实现策略：
 *  1. 依赖 Univer @univerjs/sheets-ui facade 的 `FRange.attachPopup`，由 Univer
 *     的 canvas-pop-manager 内部处理滚动/缩放/视口跟踪，不用手动监听；
 *  2. 弹出 Vue 3 组件（通过 `univerAPI.registerComponent` 注册 + `isVue3: true`）
 *     展示红点；点击红点由 ElPopover 展开意见全文与关联工单；
 *  3. 失败降级：红点加载失败不影响底稿本体（catch 所有异常）；
 *  4. 红点附着不触发 Univer dirty，因为没有调用 sheet.setCellValue 等写入命令。
 *
 * 使用：
 *   const markers = useWorkpaperReviewMarkers({ projectId, wpId, onJumpToIssue })
 *   await markers.loadData()       // 拉 reviews + issues
 *   markers.attachMarkers(univerAPI) // Univer 就绪后挂载红点
 *   markers.scrollToCell(univerAPI, 'B5') // 可选：路由 query.cell 跳转
 *
 * @module composables/useWorkpaperReviewMarkers
 * @see .kiro/specs/refinement-round1-review-closure/tasks.md Task 5
 */
import { defineComponent, h, markRaw, onUnmounted, ref } from 'vue'
import { ElButton, ElPopover, ElTag } from 'element-plus'
import { listReviews, type ReviewComment } from '@/services/workpaperApi'
import { listIssues, type IssueTicket } from '@/services/governanceApi'

export interface ReviewMarkerTicket extends IssueTicket {
  /** R1 扩展：后端返回的关联源 ID（对应 ReviewRecord.id） */
  source_ref_id?: string | null
  /** R1 扩展：后端返回的底稿 ID */
  wp_id?: string | null
}

interface Disposable { dispose: () => void }

interface MarkerState {
  reviews: ReviewComment[]
  ticketsByReviewId: Map<string, ReviewMarkerTicket>
  disposables: Disposable[]
}

export interface UseWorkpaperReviewMarkersOptions {
  projectId: () => string
  wpId: () => string
  /** 点击"查看工单"按钮回调（通常 router.push 到 IssueTicketList） */
  onJumpToIssue?: (ticket: ReviewMarkerTicket) => void
}

export function useWorkpaperReviewMarkers(opts: UseWorkpaperReviewMarkersOptions) {
  const state: MarkerState = {
    reviews: [],
    ticketsByReviewId: new Map(),
    disposables: [],
  }
  const markersReady = ref(false)
  const loadError = ref<string | null>(null)

  /** "B5" → { row: 4, col: 1 }；解析失败返回 null */
  function parseCellRef(ref: string): { row: number; col: number } | null {
    const m = /^([A-Za-z]+)(\d+)$/.exec(ref.trim())
    if (!m) return null
    const letters = m[1].toUpperCase()
    let col = 0
    for (const c of letters) col = col * 26 + (c.charCodeAt(0) - 64)
    const row = parseInt(m[2], 10) - 1
    if (row < 0 || col < 1) return null
    return { row, col: col - 1 }
  }

  /** 拉取 ReviewRecord (status=open, cell_reference != null) + 关联 IssueTicket */
  async function loadData(): Promise<void> {
    loadError.value = null
    // 1) reviews
    try {
      const reviews = await listReviews(opts.wpId(), 'open')
      state.reviews = (reviews || []).filter(
        (r) => !!r.cell_reference && r.cell_reference.trim().length > 0,
      )
    } catch (e: any) {
      state.reviews = []
      loadError.value = e?.message || 'listReviews failed'
      return
    }

    // 2) 无 review 就不用查工单
    if (state.reviews.length === 0) {
      state.ticketsByReviewId.clear()
      return
    }

    // 3) 关联工单：listIssues 不支持按 source_ref_id 筛选，拉全量 source=review_comment
    //    前端按 source_ref_id 建映射。page_size=500 够覆盖中大型项目。
    try {
      const result: any = await listIssues({
        project_id: opts.projectId(),
        source: 'review_comment',
        page_size: 500,
      })
      const items: ReviewMarkerTicket[] = Array.isArray(result?.items) ? result.items : []
      state.ticketsByReviewId.clear()
      for (const ticket of items) {
        const rid = ticket.source_ref_id
        if (rid) state.ticketsByReviewId.set(rid, ticket)
      }
    } catch {
      // 工单服务故障不阻断红点显示（红点仍展示意见全文，仅"关联工单"区域显示"无关联"）
      state.ticketsByReviewId.clear()
    }
  }

  /**
   * Univer 就绪后调用。给每条有 cell_reference 的 review 附一个 Univer canvas
   * popup（Univer 内部跟踪视口，不需要手动重算位置）。
   */
  function attachMarkers(univerAPI: any): void {
    disposeAll()
    if (!univerAPI || state.reviews.length === 0) {
      markersReady.value = false
      return
    }

    const workbook = safeCall(() => univerAPI.getActiveWorkbook?.())
    const sheet = safeCall(() => workbook?.getActiveSheet?.())
    if (!workbook || !sheet) {
      markersReady.value = false
      return
    }

    const componentKey = 'GtReviewMarkerDot'

    // 注册 Vue3 渲染组件（单次，幂等：重复注册会返回新 disposable，由本函数的
    // disposeAll 统一回收。某些版本 Univer registerComponent 不接受 options 时
    // 回退到两参调用）。
    try {
      const MarkerComp = createMarkerComponent(state, opts.onJumpToIssue)
      let regDisposable: Disposable | undefined
      try {
        regDisposable = univerAPI.registerComponent(
          componentKey,
          markRaw(MarkerComp) as any,
          { framework: 'vue3' } as any,
        )
      } catch {
        regDisposable = univerAPI.registerComponent(componentKey, markRaw(MarkerComp) as any)
      }
      if (regDisposable && typeof regDisposable.dispose === 'function') {
        state.disposables.push(regDisposable)
      }
    } catch (e) {
      // 组件注册失败（Univer 版本 API 差异）→ 降级：不挂红点，打印 warn
      // 不阻断底稿加载
      // eslint-disable-next-line no-console
      console.warn('[review-markers] registerComponent failed, markers disabled:', e)
      markersReady.value = false
      return
    }

    for (const review of state.reviews) {
      if (!review.cell_reference) continue
      const pos = parseCellRef(review.cell_reference)
      if (!pos) continue
      try {
        const fRange = sheet.getRange(pos.row, pos.col, 1, 1)
        if (!fRange || typeof fRange.attachPopup !== 'function') continue
        const popupDisposable = fRange.attachPopup({
          componentKey,
          isVue3: true,
          direction: 'top',
          offset: [0, 0],
          extraProps: { reviewId: review.id },
        } as any)
        if (popupDisposable && typeof popupDisposable.dispose === 'function') {
          state.disposables.push(popupDisposable)
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn(
          '[review-markers] attachPopup failed for cell',
          review.cell_reference,
          e,
        )
      }
    }
    markersReady.value = true
  }

  /** 通过路由 query.cell 跳转到指定单元格（Univer scrollToCell 已处理视口） */
  function scrollToCell(univerAPI: any, cellRef: string): void {
    const pos = parseCellRef(cellRef)
    if (!pos) return
    try {
      const sheet = univerAPI?.getActiveWorkbook?.()?.getActiveSheet?.()
      sheet?.scrollToCell?.(pos.row, pos.col)
    } catch {
      /* ignore */
    }
  }

  /** 根据 review_id 查找 review.cell_reference（IssueTicketList 跳转用） */
  function findCellRefByReviewId(reviewId: string): string | null {
    const rv = state.reviews.find((r) => r.id === reviewId)
    return rv?.cell_reference || null
  }

  function disposeAll(): void {
    for (const d of state.disposables) {
      try {
        d.dispose()
      } catch {
        /* ignore */
      }
    }
    state.disposables = []
    markersReady.value = false
  }

  onUnmounted(disposeAll)

  return {
    markersReady,
    loadError,
    loadData,
    attachMarkers,
    scrollToCell,
    disposeAll,
    findCellRefByReviewId,
  }
}

function safeCall<T>(fn: () => T): T | null {
  try { return fn() } catch { return null }
}

/**
 * 动态构建红点 Vue 组件：共享外层 state 闭包，避免 Univer props 传递不稳定问题。
 */
function createMarkerComponent(
  state: MarkerState,
  onJumpToIssue?: (t: ReviewMarkerTicket) => void,
) {
  return defineComponent({
    name: 'GtReviewMarkerDot',
    props: {
      reviewId: { type: String, required: true },
    },
    setup(props) {
      return () => {
        const review = state.reviews.find((r) => r.id === props.reviewId)
        if (!review) return null
        const ticket = state.ticketsByReviewId.get(review.id) || null

        return h(
          ElPopover,
          {
            width: 320,
            trigger: 'click',
            placement: 'top',
            popperClass: 'gt-review-marker-popover',
          },
          {
            reference: () =>
              h('div', {
                class: 'gt-review-marker-dot',
                title: '复核意见（点击查看）',
              }),
            default: () =>
              h('div', { style: 'font-size:13px;line-height:1.5' }, [
                h('div', { style: 'font-weight:600;margin-bottom:6px;color:#e6443e' }, [
                  h('span', '● '),
                  h('span', '复核意见'),
                ]),
                h(
                  'div',
                  {
                    style:
                      'font-size:12px;color:#303133;margin-bottom:6px;' +
                      'white-space:pre-wrap;max-height:180px;overflow-y:auto;',
                  },
                  review.comment_text,
                ),
                h(
                  'div',
                  { style: 'font-size:11px;color:#909399;margin-bottom:6px' },
                  [
                    review.cell_reference
                      ? h('span', `单元格 ${review.cell_reference}`)
                      : null,
                    review.created_at
                      ? h(
                          'span',
                          { style: 'margin-left:8px' },
                          review.created_at.slice(0, 16).replace('T', ' '),
                        )
                      : null,
                  ].filter(Boolean) as any[],
                ),
                h(
                  'div',
                  {
                    style:
                      'margin-top:8px;padding-top:8px;border-top:1px solid #ebeef5;' +
                      'display:flex;align-items:center;gap:6px;flex-wrap:wrap',
                  },
                  ticket
                    ? [
                        h('span', { style: 'font-size:11px;color:#909399' }, '关联工单:'),
                        h(
                          ElTag,
                          { size: 'small', type: ticketStatusTagType(ticket.status) },
                          () => issueStatusLabel(ticket.status),
                        ),
                        h(
                          ElButton,
                          {
                            size: 'small',
                            type: 'primary',
                            link: true,
                            onClick: () => onJumpToIssue?.(ticket),
                          },
                          () => '查看工单 →',
                        ),
                      ]
                    : [
                        h(
                          'span',
                          { style: 'font-size:11px;color:#c0c4cc' },
                          '（无关联工单）',
                        ),
                      ],
                ),
              ]),
          },
        )
      }
    },
  })
}

function ticketStatusTagType(s: string): 'success' | 'danger' | 'warning' | 'info' {
  if (s === 'closed') return 'success'
  if (s === 'rejected') return 'danger'
  if (s === 'open') return 'warning'
  return 'info'
}

function issueStatusLabel(s: string): string {
  const m: Record<string, string> = {
    open: '待处理',
    in_fix: '修复中',
    pending_recheck: '待复验',
    closed: '已关闭',
    rejected: '已驳回',
  }
  return m[s] || s
}
