/**
 * M1 / T2 属性测试 — Property 3: handleApiError 替换错误处理不弱于裸 ElMessage.error
 *
 * 背景：frontend-consistency-m1 的 T2 把 `catch (e) { ElMessage.error('xxx失败') }`
 *   形式的裸错误提示统一替换为 `handleApiError(e, 'xxx')`。本测试形式化证明：
 *   替换后的错误反馈**不弱于（等价或更优）**替换前的裸固定文案：
 *     - 后端错误带 detail（409 / 422 通用）→ handleApiError 显示该 detail（更优）
 *     - 后端错误无 detail（非 401 各 status）→ handleApiError 至少给出带 context
 *       的中文提示或有意义的中文兜底（等价，不会"什么都不说"或"只说失败了"）
 *
 * Property 3 (Task 8.1): handleApiError 替换错误处理等价或更优
 *   ∀ 后端错误响应（含/不含 detail，各 HTTP status），替换后 handleApiError 的
 *   提示不弱于替换前裸 ElMessage.error。
 *   **Validates: Requirements 5.6**
 *
 * 子断言：
 *   P3-a：带 detail.message（409 / 通用 422）→ 反馈文本必含该 detail（更优）
 *   P3-b：无 detail（非 401）→ 反馈文本含 context 或有意义中文兜底（等价）
 *   P3-c：401 静默（不弹任何提示）——匹配原行为（401 由 http.ts 拦截器统一处理）
 *   P3-d：任意非 401 status → 至少触发一次 error/warning/notification（错误绝不被静默吞掉）
 *
 * 实施方案：vitest + fast-check（numRuns: 15）。mock element-plus 的 ElMessage /
 *   ElNotification 捕获被调用的提示文本，mock @/utils/http.getLastTraceId 固定返回。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'

// ── Mock element-plus（factory 不引用外部变量，避免 hoisting 陷阱）──
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
  ElNotification: vi.fn(),
}))

// ── Mock getLastTraceId 固定返回（5xx 分支用）──
vi.mock('@/utils/http', () => ({
  getLastTraceId: () => 'trace-fixed-abc123',
}))

import { ElMessage, ElNotification } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'

// ── 工具：把本轮所有被调用的提示文本汇聚为一个字符串 ──
// 覆盖 ElMessage.error / ElMessage.warning 的首参，以及 ElNotification 的 title+message。
function allCapturedText(): string {
  const parts: string[] = []
  for (const c of (ElMessage.error as any).mock.calls) parts.push(String(c[0] ?? ''))
  for (const c of (ElMessage.warning as any).mock.calls) parts.push(String(c[0] ?? ''))
  for (const c of (ElNotification as any).mock.calls) {
    const arg = c[0] || {}
    parts.push(String(arg.title ?? ''))
    parts.push(String(arg.message ?? ''))
  }
  return parts.join(' || ')
}

// 本轮提示调用总次数（P3-c / P3-d 用）
function feedbackCallCount(): number {
  return (
    (ElMessage.error as any).mock.calls.length +
    (ElMessage.warning as any).mock.calls.length +
    (ElNotification as any).mock.calls.length
  )
}

// ── 生成器 ──────────────────────────────────────────────
// 中文消息生成器：非空、由真实审计场景词汇构成（保证 detail.message 为 truthy 字符串）
const CHINESE_POOL = '金额不能为负版本冲突数据已存在请检查输入余额不一致科目缺失期间错误重复提交超出范围'.split('')
const chineseMsgArb = fc
  .array(fc.constantFrom(...CHINESE_POOL), { minLength: 2, maxLength: 8 })
  .map((a) => a.join(''))

// context（中文操作名）生成器：非空
const CONTEXT_POOL = '保存加载删除提交导出查看创建更新底稿项目报表分录附注'.split('')
const contextArb = fc
  .array(fc.constantFrom(...CONTEXT_POOL), { minLength: 2, maxLength: 6 })
  .map((a) => a.join(''))

// 全部测试用 HTTP status（0 = 网络错误）
const allStatusArb = fc.constantFrom(0, 401, 403, 404, 409, 422, 423, 500, 502, 503)
// 非 401（非静默）status
const nonSilentStatusArb = fc.constantFrom(0, 403, 404, 409, 422, 423, 500, 502, 503)
// 会"surface detail.message"的 status（通用路径，不含特殊 error_code）
const detailSurfacingStatusArb = fc.constantFrom(409, 422)

// 构造后端错误对象
function buildError(status: number, detail?: unknown): unknown {
  const data: Record<string, unknown> = {}
  if (detail !== undefined) data.detail = detail
  return { response: { status, data } }
}

// 有意义的中文兜底关键词（无 detail 时的等价性下限）
const FALLBACK_KEYWORDS = [
  '网络不通',
  '无权操作',
  '资源不存在',
  '数据冲突',
  '已归档',
  '系统错误',
  '请求参数',
]

describe('M1/T2 Property 3: handleApiError 替换不弱于裸 ElMessage.error', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  /**
   * P3-a：带 detail.message → 反馈文本必含该 detail（更优）
   * 针对 409 / 通用 422（不含特殊 error_code），detail.message 非空时
   * handleApiError 的提示文本必须包含该 message，证明优于裸固定文案。
   * **Validates: Requirements 5.6**
   */
  it('(P3-a) 带 detail.message 时反馈必含 detail（优于裸文案）', () => {
    fc.assert(
      fc.property(detailSurfacingStatusArb, contextArb, chineseMsgArb, (status, context, msg) => {
        vi.clearAllMocks()
        // detail 仅含 message，不含特殊 error_code → 走 surface detail 的通用路径
        handleApiError(buildError(status, { message: msg }), context)

        const text = allCapturedText()
        expect(
          text.includes(msg),
          `status=${status} detail.message="${msg}" 未出现在提示文本中："${text}"`,
        ).toBe(true)
      }),
      { numRuns: 15 },
    )
  })

  /**
   * P3-b：无 detail（非 401）→ 反馈含 context 或有意义中文兜底（等价）
   * 证明即使后端没给 detail，handleApiError 也不会比裸 'xxx失败' 更弱：
   * 至少带上 context 操作名，或给出明确的中文兜底（网络不通/无权操作/...）。
   * **Validates: Requirements 5.6**
   */
  it('(P3-b) 无 detail（非 401）时反馈含 context 或中文兜底（等价）', () => {
    fc.assert(
      fc.property(nonSilentStatusArb, contextArb, (status, context) => {
        vi.clearAllMocks()
        handleApiError(buildError(status, undefined), context)

        const text = allCapturedText()
        const ok = text.includes(context) || FALLBACK_KEYWORDS.some((k) => text.includes(k))
        expect(
          ok,
          `status=${status} context="${context}" 的提示既不含 context 也无中文兜底："${text}"`,
        ).toBe(true)
      }),
      { numRuns: 15 },
    )
  })

  /**
   * P3-c：401 静默——匹配原行为（401 由 http.ts 拦截器处理 token 刷新）
   * **Validates: Requirements 5.6**
   */
  it('(P3-c) 401 静默：不触发任何提示', () => {
    const detailArb = fc.option(
      fc.oneof(
        fc.record({ message: chineseMsgArb }),
        fc.record({ error_code: fc.constantFrom('AI_CONTENT_NOT_CONFIRMED', 'OTHER') }),
      ),
      { nil: undefined },
    )
    fc.assert(
      fc.property(contextArb, detailArb, (context, detail) => {
        vi.clearAllMocks()
        handleApiError(buildError(401, detail), context)
        expect(feedbackCallCount(), '401 不应触发任何提示').toBe(0)
      }),
      { numRuns: 15 },
    )
  })

  /**
   * P3-d：任意非 401 status → 至少触发一次提示（错误绝不被静默吞掉）
   * 这是"不弱于"的最低保证：原裸 ElMessage.error 总会弹提示，替换后也必须。
   * **Validates: Requirements 5.6**
   */
  it('(P3-d) 非 401 status 至少触发一次提示（不静默吞错）', () => {
    const detailArb = fc.option(
      fc.oneof(
        fc.record({ message: chineseMsgArb }),
        fc.record({ error: chineseMsgArb }),
        fc.record({
          error_code: fc.constantFrom(
            'AI_CONTENT_NOT_CONFIRMED',
            'CROSS_MODULE_CONFLICT_UNRESOLVED',
            'SOME_OTHER_CODE',
          ),
        }),
        fc.record({ message: chineseMsgArb, error_code: fc.constantFrom('AI_CONTENT_NOT_CONFIRMED', 'OTHER') }),
      ),
      { nil: undefined },
    )
    fc.assert(
      fc.property(nonSilentStatusArb, contextArb, detailArb, (status, context, detail) => {
        vi.clearAllMocks()
        handleApiError(buildError(status, detail), context)
        expect(
          feedbackCallCount(),
          `status=${status} 未触发任何提示（被静默吞掉）`,
        ).toBeGreaterThanOrEqual(1)
      }),
      { numRuns: 15 },
    )
  })
})
