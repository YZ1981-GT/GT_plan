/**
 * B2-12 对前任注册会计师评价底稿 — 组件测试
 *
 * 验证：
 * - 注册契约：b2-12-evaluation 在 HTML_RENDERER_REGISTRY
 * - hydrate：从 htmlData.responses_snapshot 载入 9 步 + 7 点判断 + 说明
 * - P5：存在不利事项（exists='是'）→ 顶部 badge 计数 + 行高亮 class
 *
 * Spec: b2-predecessor-communication-hardening Task 6/7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const mockGet = vi.fn()
const mockPut = vi.fn()
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...a: any[]) => mockGet(...a),
    put: (...a: any[]) => mockPut(...a),
    post: (...a: any[]) => mockPost(...a),
  },
}))

const mockEmit = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: (...a: any[]) => mockEmit(...a), on: vi.fn(), off: vi.fn() },
}))

import { HTML_RENDERER_REGISTRY } from '../htmlRendererRegistry'
import GtB212Evaluation from '../GtB212Evaluation.vue'

const SNAPSHOT = {
  'B2-12-steps': { conclusion: null, remark: JSON.stringify([{ record: '李某，执业10年', subChecks: [] }]) },
  'B2-12-conclusions': {
    conclusion: null,
    remark: JSON.stringify([
      { exists: '是', measure: '扩大实质性程序', impact: '增加期初余额审计范围' },
      { exists: '否', measure: '', impact: '' },
    ]),
  },
  'B2-12-note': { conclusion: null, remark: '综合评价：前任独立性存在威胁，已采取应对。' },
}

function mountB212(readonly = false) {
  return mount(GtB212Evaluation, {
    props: {
      wpId: 'wp-b2-12',
      projectId: 'proj-1',
      readonly,
      htmlData: {
        project_context: { client_name: '北京测试科技有限公司', audit_year: '2025' },
        responses_snapshot: SNAPSHOT,
      },
    },
    global: { plugins: [ElementPlus] },
  })
}

describe('B2-12 注册契约', () => {
  it('b2-12-evaluation 已注册到 HTML_RENDERER_REGISTRY', () => {
    const entry = HTML_RENDERER_REGISTRY.get('b2-12-evaluation' as any)
    expect(entry).toBeTruthy()
    expect(entry?.component).toBeTruthy()
  })
})

describe('B2-12 评价底稿组件', () => {
  beforeEach(() => {
    mockGet.mockReset(); mockPut.mockReset(); mockPost.mockReset()
    mockGet.mockResolvedValue([])
    mockPut.mockResolvedValue({})
  })

  it('从 htmlData.responses_snapshot 载入数据 + 显示抬头', async () => {
    const w = mountB212()
    await flushPromises()
    const text = w.text()
    expect(text).toContain('北京测试科技有限公司')
    expect(text).toContain('2025')
    // 综合说明载入
    expect(w.find('textarea').exists()).toBe(true)
    // htmlData 路径下不应触发 api.get
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('P5：存在不利事项 → badge 计数 + 行高亮', async () => {
    const w = mountB212()
    await flushPromises()
    // 第 1 条结论 exists='是' → 顶部 badge 显示"存在 1 项"
    expect(w.text()).toContain('存在 1 项不利事项')
    // 行高亮 class 存在
    expect(w.find('.exists-row').exists()).toBe(true)
  })

  it('推送发现至 B50 → emit b50:push-risk-factor（Task 9）', async () => {
    const w = mountB212()
    await flushPromises()
    const pushBtn = w.findAll('button').find((b) => b.text().includes('推送发现至 B50'))
    expect(pushBtn).toBeTruthy()
    await pushBtn!.trigger('click')
    expect(mockEmit).toHaveBeenCalledWith('b50:push-risk-factor', expect.objectContaining({
      factors: expect.arrayContaining([expect.stringContaining('前任沟通发现')]),
      source: 'B2-12',
    }))
  })

  it('readonly 模式下 textarea 全禁用', async () => {
    const w = mountB212(true)
    await flushPromises()
    const textareas = w.findAll('textarea')
    expect(textareas.length).toBeGreaterThan(0)
    expect(textareas.every((t) => (t.element as HTMLTextAreaElement).disabled)).toBe(true)
  })
})
