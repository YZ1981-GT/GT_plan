/**
 * useConsolRefreshTracking — 一键刷新进度追踪与附注重读编排。
 *
 * 从 ConsolidationIndex.vue 抽取的 composable，职责：
 * - SSE 订阅 + 轮询兜底（EH6）
 * - 幂等异步 finish（树/报表刷新 + 附注持久化重读）
 * - tree / note 独立状态管理
 * - 严格身份过滤（job_id + project_id + year）
 * - steps_skipped 精确区分跳过与成功
 *
 * 设计：consol-note-node-refresh-and-formula-orchestration §六
 */
import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { consolidation as P_consol } from '@/services/apiPaths'
import { subscribeProjectEvent, type ProjectEventSubscription } from '@/services/sse/projectEventStream'
import { eventBus } from '@/utils/eventBus'

export type RefreshPartStatus = 'pending' | 'done' | 'failed' | 'skipped'

export interface RefreshContext {
  projectId: string
  year: number
  nodeKey: string
  sectionId: string
}

export interface RefreshTrackingState {
  tree: RefreshPartStatus
  note: RefreshPartStatus
  noteReason: string
  treeReason: string
}

export interface RefreshProgress {
  visible: boolean
  step: string
  current: number
  total: number
  node: string
}

/** 创建刷新追踪 composable 需要的外部回调。 */
export interface RefreshTrackingDeps {
  /** 刷新报表视图。 */
  reloadReportView: () => void
  /** 加载企业树，返回是否成功。 */
  loadGroupTree: () => Promise<boolean>
  /** 重新读取附注章节（向子组件代理）。 */
  reloadNoteForRefresh: (context: RefreshContext) => Promise<any>
  /** 捕获当前刷新上下文快照。 */
  captureRefreshContext: () => RefreshContext
  /** 当前活跃 tab 名。 */
  getActiveTab: () => string
}

export function useConsolRefreshTracking(deps: RefreshTrackingDeps) {
  const state = reactive<RefreshTrackingState>({
    tree: 'pending',
    note: 'pending',
    noteReason: '',
    treeReason: '',
  })

  const progress = reactive<RefreshProgress>({
    visible: false, step: '', current: 0, total: 0, node: '',
  })

  let subs: ProjectEventSubscription[] = []
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let settled = false

  function stop() {
    for (const s of subs) s.close()
    subs = []
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
  }

  /**
   * 幂等终态处理器（SSE 和轮询共用）：先刷新树/报表，再重读当前附注章节。
   * 附注持久化 GET 是完成证据；只有 done 才标 note.done（ADR-CNFO-002）。
   */
  async function finish(
    ok: boolean, msg: string | undefined,
    stepsCompleted: string[] | undefined, stepsSkipped: string[] | undefined,
    context: RefreshContext,
  ) {
    if (settled) return
    settled = true
    stop()
    progress.visible = false

    if (!ok) {
      state.tree = 'failed'
      state.treeReason = msg || '未知错误'
      state.note = 'failed'
      state.noteReason = msg || '未知错误'
      if (msg) ElMessage.error(msg)
      return
    }

    // 树完成判定
    const steps = Array.isArray(stepsCompleted) ? stepsCompleted : []
    state.tree = steps.includes('tree') ? 'done' : 'failed'
    state.treeReason = steps.includes('tree') ? '' : '建树步骤未完成'

    // 刷新当前 tab 报表/树视图
    let treeOk = true
    try {
      if (deps.getActiveTab() === 'consol_report') deps.reloadReportView()
      treeOk = await deps.loadGroupTree()
    } catch { treeOk = false }
    if (!treeOk && state.tree === 'done') {
      state.tree = 'failed'
      state.treeReason = '企业树加载失败'
    }

    // 附注持久化重读
    const skipped = Array.isArray(stepsSkipped) ? stepsSkipped : []
    if (skipped.includes('notes')) {
      state.note = 'skipped'
      state.noteReason = '附注步骤被后端跳过（V2 未启用）'
    } else if (!steps.includes('notes')) {
      state.note = 'failed'
      state.noteReason = '附注步骤未完成'
    } else {
      try {
        let noteResult = await deps.reloadNoteForRefresh(context)
        // 冻结上下文过期时 best-effort 用当前章节补重读一次
        if (noteResult?.status === 'stale' || noteResult?.status === 'skipped') {
          const currentCtx = deps.captureRefreshContext()
          if (currentCtx.sectionId && currentCtx.sectionId !== context.sectionId
              && currentCtx.projectId === context.projectId
              && currentCtx.year === context.year
              && currentCtx.nodeKey === context.nodeKey) {
            noteResult = await deps.reloadNoteForRefresh(currentCtx)
          }
        }
        if (noteResult?.status === 'done') {
          state.note = 'done'
          state.noteReason = ''
        } else if (noteResult?.status === 'stale') {
          state.note = 'skipped'
          state.noteReason = noteResult?.reason || '刷新期间合并节点已切换'
        } else if (noteResult?.status === 'skipped') {
          state.note = 'skipped'
          state.noteReason = noteResult?.reason || '刷新开始时未选择附注章节'
        } else {
          state.note = 'failed'
          state.noteReason = noteResult?.reason || '附注章节重读失败'
        }
      } catch {
        state.note = 'failed'
        state.noteReason = '附注章节重读异常'
      }
    }

    // 综合提示
    const noteOk = state.note === 'done' || state.note === 'skipped'
    if (noteOk) {
      ElMessage.success(msg || '一键刷新完成')
    } else {
      ElMessage.warning(`一键刷新完成，但附注重读${state.note === 'failed' ? '失败' : '跳过'}：${state.noteReason}`)
    }
    eventBus.emit('consol-refresh-done', { projectId: context.projectId, year: context.year })
  }

  /** 启动追踪：订阅 SSE 进度 + 轮询兜底。 */
  function start(jobId: string, context: RefreshContext) {
    stop()
    settled = false
    state.tree = 'pending'
    state.treeReason = ''
    state.note = 'pending'
    state.noteReason = ''

    // SSE
    try {
      const onEvent = (data: any, eventName?: string) => {
        if (!data) return
        if (!data.job_id || data.job_id !== jobId) return
        if (data.project_id && String(data.project_id) !== context.projectId) return
        if (data.year && Number(data.year) !== context.year) return
        if (eventName === 'consol.refresh.progress') {
          progress.step = data.step || ''
          progress.current = data.current || 0
          progress.total = data.total || 0
          progress.node = data.current_node || ''
        } else if (eventName === 'consol.refresh.completed') {
          const errCount = Array.isArray(data.errors) ? data.errors.length : 0
          const steps = Array.isArray(data.steps_completed) ? data.steps_completed : []
          const sk = Array.isArray(data.steps_skipped) ? data.steps_skipped : []
          finish(true, errCount > 0 ? `一键刷新完成（${errCount} 步部分失败，请检查）` : '一键刷新完成', steps, sk, context).catch(() => {})
        } else if (eventName === 'consol.refresh.error') {
          finish(false, `一键刷新失败：${data.error || '未知错误'}`, undefined, undefined, context).catch(() => {})
        }
      }
      for (const ev of ['consol.refresh.progress', 'consol.refresh.completed', 'consol.refresh.error']) {
        subs.push(subscribeProjectEvent(context.projectId, ev, onEvent))
      }
    } catch { /* 订阅失败不致命，靠轮询兜底 */ }

    // 轮询兜底
    if (!jobId) return
    let polls = 0
    const poll = async () => {
      if (settled) return
      polls += 1
      try {
        const st: any = await api.get(P_consol.refreshStatus(context.projectId, context.year, jobId))
        if (st?.status === 'completed') {
          const errCount = Array.isArray(st.errors) ? st.errors.length : 0
          const steps = Array.isArray(st.steps_completed) ? st.steps_completed : []
          const sk = Array.isArray(st.steps_skipped) ? st.steps_skipped : []
          await finish(true, errCount > 0 ? `一键刷新完成（${errCount} 步部分失败，请检查）` : '一键刷新完成', steps, sk, context)
          return
        }
        if (st?.status === 'failed') {
          const errMsg = Array.isArray(st.errors) && st.errors.length ? st.errors[st.errors.length - 1]?.error : ''
          await finish(false, `一键刷新失败：${errMsg || '未知错误'}`, undefined, undefined, context)
          return
        }
      } catch { /* 单次轮询失败忽略 */ }
      if (polls < 120 && !settled) {
        pollTimer = setTimeout(poll, 3000)
      } else if (!settled) {
        progress.visible = false
      }
    }
    pollTimer = setTimeout(poll, 3000)
  }

  return { state, progress, start, stop }
}
