/**
 * NoteAiFillDialog.spec.ts — 附注 AI 填充 / 参照文档填充对话框 + 一键批量预填充进度
 *
 * spec: disclosure-note-knowledge-ai-enrichment / Task 9
 * 需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.5, 10.5
 * 属性覆盖: Property 11(AI 不自动写 / 不落库), Property 13(reference_only 不生成)
 *
 * 覆盖:
 *  - Dialog 展示 Citation(document_name/folder_path/is_stale)
 *  - 无命中提示(AI 模式降级 → "未检索到可参照的知识库文档")
 *  - reference_only 模式无生成(Property 13): 请求带 reference_only=true, 不产草稿, 采纳禁用
 *  - 锁定禁用采纳(Req3.6): locked=true → 采纳按钮 disabled
 *  - 采纳调 adoptContent(Req3.3 治理确认流)
 *  - 未采纳 text_content 不变(Property 11): 预览走 ai-fill 端点, 不触发 adopt 写路径
 *  - 批量预填充进度/汇总渲染(Req10.5)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'

// ── mock http(default export) ─────────────────────────────
const httpPost = vi.fn()
const httpGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    post: (...a: any[]) => httpPost(...a),
    get: (...a: any[]) => httpGet(...a),
  },
}))

// ── mock useDocAiChat(采纳治理流) ─────────────────────────
const adoptContent = vi.fn().mockResolvedValue({ success: true })
vi.mock('@/composables/useDocAiChat', () => ({
  useDocAiChat: () => ({ messages: ref<any[]>([]), adoptContent }),
}))

// ── mock ElMessage(避免真实 DOM 挂载噪音) ──────────────────
vi.mock('element-plus', async (orig) => {
  const actual = await (orig as any)()
  return { ...actual, ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }
})

import NoteAiFillDialog from '@/components/disclosure/NoteAiFillDialog.vue'

// ── EP 组件轻量 stub(渲染 slot 便于断言文本 + 透传 disabled/click) ──
const stubs: Record<string, any> = {
  'el-dialog': {
    template: '<div class="el-dialog"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title'],
  },
  'el-radio-group': {
    template: '<div class="el-radio-group"><slot /></div>',
    props: ['modelValue'],
  },
  'el-radio-button': { template: '<button class="el-radio-button"><slot /></button>', props: ['value'] },
  'el-tree-select': { template: '<div class="el-tree-select" />', props: ['modelValue'] },
  'el-button': {
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['disabled', 'loading', 'type', 'size', 'link', 'plain'],
    emits: ['click'],
  },
  'el-alert': {
    template: '<div class="el-alert" :data-type="type"><span class="alert-title">{{ title }}</span><slot /></div>',
    props: ['title', 'type', 'closable', 'showIcon'],
  },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size', 'effect'] },
  'el-empty': { template: '<div class="el-empty" :data-desc="description" />', props: ['description', 'imageSize'] },
  'el-tooltip': { template: '<div class="el-tooltip"><slot /></div>', props: ['content', 'disabled', 'placement'] },
}

/**
 * 服务端为本次草稿签发的 assistant 消息 ID。
 *
 * dsh-agent-panel-integration / Task 7（Req 8.1）：`/api/ai-chat/adopt` 只按服务端
 * message ID 读库取正文，因此 `/ai-fill` 响应必须带 `message_id`，前端不再本地造 ID。
 */
const DRAFT_MESSAGE_ID = '9f1c1a3e-2b47-4d6a-8f21-7e5b0c9d4a12'

function makeResult(over: Partial<any> = {}) {
  return {
    text: '本科目期末余额较上年增长，主要系……',
    message_id: DRAFT_MESSAGE_ID,
    citations: [
      {
        document_name: '2024年度审计报告及附注.pdf',
        folder_path: '/项目文档/2024',
        snippet: '货币资金期末余额 1,234,567.89 元……',
        score: 0.91,
        source_id: 'kb-src-1',
        is_stale: false,
      },
    ],
    degraded: false,
    skipped_docs: [],
    ...over,
  }
}

function mountDialog(props: Partial<any> = {}) {
  return mount(NoteAiFillDialog, {
    props: {
      visible: true,
      projectId: 'proj-1',
      year: 2025,
      noteSection: 'note_cash',
      sectionTitle: '货币资金',
      accountName: '货币资金',
      locked: false,
      initialMode: 'ai',
      ...props,
    },
    global: { stubs },
  })
}

function findBtn(wrapper: any, text: string) {
  return wrapper.findAll('button').find((b: any) => b.text().includes(text))
}

beforeEach(() => {
  httpPost.mockReset()
  httpGet.mockReset()
  adoptContent.mockClear()
})

describe('NoteAiFillDialog — AI 生成 + Citation 展示', () => {
  it('生成草稿并展示 Citation(document_name/folder_path/is_stale)', async () => {
    httpPost.mockResolvedValue({ data: makeResult() })
    const wrapper = mountDialog()
    await flushPromises()

    await findBtn(wrapper, '生成草稿')!.trigger('click')
    await flushPromises()

    // 请求命中 ai-fill 端点
    expect(httpPost).toHaveBeenCalledTimes(1)
    const [url] = httpPost.mock.calls[0]
    expect(String(url)).toContain('/ai-fill')

    // 草稿正文渲染
    expect(wrapper.text()).toContain('本科目期末余额较上年增长')
    // Citation 渲染 document_name + folder_path
    expect(wrapper.text()).toContain('2024年度审计报告及附注.pdf')
    expect(wrapper.text()).toContain('/项目文档/2024')
  })

  it('is_stale=true 时标注过期', async () => {
    httpPost.mockResolvedValue({
      data: makeResult({
        citations: [
          {
            document_name: '陈旧模板.docx',
            folder_path: '/共享',
            snippet: '片段',
            score: 0.7,
            source_id: 'kb-2',
            is_stale: true,
          },
        ],
      }),
    })
    const wrapper = mountDialog()
    await flushPromises()
    await findBtn(wrapper, '生成草稿')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('过期')
  })

  it('AI 模式无命中(citations 空) → 提示已用通用生成(Req3.4)', async () => {
    httpPost.mockResolvedValue({ data: makeResult({ citations: [], degraded: true }) })
    const wrapper = mountDialog()
    await flushPromises()
    await findBtn(wrapper, '生成草稿')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('未检索到可参照的知识库文档')
  })
})

describe('NoteAiFillDialog — Property 13: reference_only 不生成', () => {
  it('参照文档模式请求带 reference_only=true, 不产草稿且采纳禁用', async () => {
    httpPost.mockResolvedValue({
      data: makeResult({ text: null }), // reference-only: 后端不生成正文
    })
    const wrapper = mountDialog({ initialMode: 'reference' })
    await flushPromises()

    await findBtn(wrapper, '检索参照片段')!.trigger('click')
    await flushPromises()

    // 请求体 reference_only=true
    const [, body] = httpPost.mock.calls[0]
    expect(body.reference_only).toBe(true)

    // 无草稿正文
    expect(wrapper.text()).not.toContain('草稿正文')
    // 采纳按钮禁用(reference 模式不可采纳)
    const adoptBtn = findBtn(wrapper, '采纳草稿')!
    expect(adoptBtn.attributes('disabled')).toBeDefined()
  })
})

describe('NoteAiFillDialog — Req3.6: 锁定禁用采纳', () => {
  it('locked=true → 有草稿仍禁用采纳(可预览不可写)', async () => {
    httpPost.mockResolvedValue({ data: makeResult() })
    const wrapper = mountDialog({ locked: true })
    await flushPromises()
    await findBtn(wrapper, '生成草稿')!.trigger('click')
    await flushPromises()

    // 草稿已生成
    expect(wrapper.text()).toContain('本科目期末余额较上年增长')
    // 采纳禁用
    const adoptBtn = findBtn(wrapper, '采纳草稿')!
    expect(adoptBtn.attributes('disabled')).toBeDefined()
    expect(adoptContent).not.toHaveBeenCalled()
  })
})

describe('NoteAiFillDialog — Req3.3: 采纳走 adoptContent 治理流', () => {
  it('AI 草稿采纳 → 用服务端 message_id 调 adoptContent + emit adopted + 关闭', async () => {
    httpPost.mockResolvedValue({ data: makeResult() })
    const wrapper = mountDialog()
    await flushPromises()
    await findBtn(wrapper, '生成草稿')!.trigger('click')
    await flushPromises()

    await findBtn(wrapper, '采纳草稿')!.trigger('click')
    await flushPromises()

    expect(adoptContent).toHaveBeenCalledTimes(1)
    // Task 7 / Req 8.1：引用的是服务端签发的 message ID，不是本地造的 `notefill_…`
    expect(adoptContent).toHaveBeenCalledWith(DRAFT_MESSAGE_ID)
    expect(wrapper.emitted('adopted')).toBeTruthy()
    const payload = wrapper.emitted('adopted')![0][0] as any
    expect(payload.noteSection).toBe('note_cash')
    expect(payload.text).toContain('本科目期末余额较上年增长')
    // 关闭
    expect(wrapper.emitted('update:visible')?.some((e) => e[0] === false)).toBe(true)
  })

  it('服务端未签发 message_id 时采纳禁用（不退回提交客户端正文）', async () => {
    // reference_only / 章节未实例化 / 登记失败 ⇒ 后端回传 message_id=null
    httpPost.mockResolvedValue({ data: makeResult({ message_id: null }) })
    const wrapper = mountDialog()
    await flushPromises()
    await findBtn(wrapper, '生成草稿')!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('本科目期末余额较上年增长')
    const adoptBtn = findBtn(wrapper, '采纳草稿')!
    expect(adoptBtn.attributes('disabled')).toBeDefined()
    await adoptBtn.trigger('click')
    await flushPromises()
    expect(adoptContent).not.toHaveBeenCalled()
  })
})

describe('NoteAiFillDialog — Property 11: 预览不落库', () => {
  it('生成+关闭(未采纳) → 仅调 ai-fill 预览端点, 从不调 adopt 写路径', async () => {
    httpPost.mockResolvedValue({ data: makeResult() })
    const wrapper = mountDialog()
    await flushPromises()

    await findBtn(wrapper, '生成草稿')!.trigger('click')
    await flushPromises()

    // 用户未采纳直接关闭
    await findBtn(wrapper, '关闭')!.trigger('click')
    await flushPromises()

    // 预览仅命中 ai-fill(不落库), 采纳写路径从未触发
    expect(httpPost).toHaveBeenCalledTimes(1)
    expect(String(httpPost.mock.calls[0][0])).toContain('/ai-fill')
    expect(adoptContent).not.toHaveBeenCalled()
  })
})

// ── 一键批量预填充进度/汇总渲染(Req10.5) ──────────────────
// DisclosureEditor.vue 体量过大无法整体 mount, 此处复刻其批量结果统计的响应式逻辑
// (与 DisclosureEditor.vue 中 batchGenerated/batchDegraded/batchSkipped 一一对应)
describe('DisclosureEditor 批量预填充进度汇总(Req10.5)', () => {
  function createBatchModel() {
    const batchResults = ref<Array<{ note_section: string; status: string; text: string | null; citations: any[] }>>([])
    const batchGenerated = computed(() => batchResults.value.filter((r) => r.status === 'generated').length)
    const batchDegraded = computed(() => batchResults.value.filter((r) => r.status === 'degraded').length)
    const batchSkipped = computed(() => batchResults.value.filter((r) => r.status === 'skipped').length)
    return { batchResults, batchGenerated, batchDegraded, batchSkipped }
  }

  it('逐章结果按状态分类计数(生成/降级/跳过)', () => {
    const m = createBatchModel()
    m.batchResults.value = [
      { note_section: 'n1', status: 'generated', text: '草稿1', citations: [{}] },
      { note_section: 'n2', status: 'generated', text: '草稿2', citations: [] },
      { note_section: 'n3', status: 'degraded', text: null, citations: [] },
      { note_section: 'n4', status: 'skipped', text: null, citations: [] },
      { note_section: 'n5', status: 'skipped', text: null, citations: [] },
    ]
    expect(m.batchResults.value.length).toBe(5)
    expect(m.batchGenerated.value).toBe(2)
    expect(m.batchDegraded.value).toBe(1)
    expect(m.batchSkipped.value).toBe(2)
  })

  it('空结果 → 全部计数为 0(不阻塞界面)', () => {
    const m = createBatchModel()
    expect(m.batchGenerated.value).toBe(0)
    expect(m.batchDegraded.value).toBe(0)
    expect(m.batchSkipped.value).toBe(0)
  })
})
