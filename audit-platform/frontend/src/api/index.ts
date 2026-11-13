/**
 * AI 功能 API 占位桩
 *
 * 这些 API 客户端对应尚未接入后端的 AI 面板组件
 * （AIInsightsDashboard / ConfirmationAIAssistant / NLCommandInput / WorkpaperAIFill）。
 * 当前返回空数据以保证编译和运行时不崩溃。
 * 待后端端点就绪后替换为真实实现。
 */

const emptyResponse = <T>(data: T) => Promise.resolve({ data })

/** AI 洞察中心 */
export const aiContentApi = {
  listInsights: (_projectId: string) => emptyResponse([]),
}

/** 函证 AI 审核 */
export const confirmationAIApi = {
  runChecks: (_listId: string | null, _types: string[]) => emptyResponse([]),
  confirm: (_checkId: string, _payload: { confirmed: boolean }) => emptyResponse({}),
}

/** 自然语言指令 */
export const nlCommandApi = {
  execute: (_projectId: string, _query: string) =>
    emptyResponse({ status: 'error', message: '自然语言指令功能开发中' }),
}

/** AI 底稿填充 */
export const workpaperFillApi = {
  startFill: (_projectId: string, _opts: Record<string, unknown>) => emptyResponse({ jobId: null }),
  getStatus: (_jobId: string) => emptyResponse({ progress: 0, status: 'pending', steps: [], results: [] }),
}
