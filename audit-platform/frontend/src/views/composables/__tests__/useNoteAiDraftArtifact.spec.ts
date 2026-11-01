import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const mocks = vi.hoisted(() => ({
  continueWrite: vi.fn(),
  rewrite: vi.fn(),
  policy: vi.fn(),
  analysis: vi.fn(),
  emit: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/services/commonApi', () => ({
  noteAiContinueWrite: (...args: any[]) => mocks.continueWrite(...args),
  noteAiRewrite: (...args: any[]) => mocks.rewrite(...args),
  noteAiGeneratePolicy: (...args: any[]) => mocks.policy(...args),
  noteAiGenerateAnalysis: (...args: any[]) => mocks.analysis(...args),
}))
vi.mock('@/composables/useKnowledge', () => ({
  useKnowledge: () => ({ pickDocuments: vi.fn().mockResolvedValue([]) }),
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: (...args: any[]) => mocks.emit(...args) } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...args: any[]) => mocks.success(...args),
    warning: (...args: any[]) => mocks.warning(...args),
  },
}))

import { useNoteAi } from '../useNoteAi'

function make() {
  const insertContent = vi.fn()
  const setContent = vi.fn()
  const run = vi.fn()
  const chain = vi.fn(() => ({
    focus: () => ({
      deleteRange: () => ({ insertContent: () => ({ run }) }),
    }),
  }))
  const editor = ref<any>({
    getText: () => '已保存正文',
    state: { selection: { from: 1, to: 3 }, doc: { textBetween: () => '选中文本' } },
    commands: { insertContent, setContent },
    chain,
  })
  return {
    api: useNoteAi({
      projectId: ref('p1'), year: ref(2025), templateType: ref('soe'),
      currentNote: ref({ note_section: '五、1' }), editor,
    }),
    insertContent, setContent, chain, run,
  }
}

describe('useNoteAi DraftArtifact', () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) mock.mockReset()
  })

  it('续写和政策草稿只送待确认，不直接改编辑器', async () => {
    mocks.continueWrite.mockResolvedValue({ appended: '续写', artifact_id: 'a1', knowledge_count: 0 })
    mocks.policy.mockResolvedValue({ generated_text: '政策', artifact_id: 'a2', reference_count: 1 })
    const { api, insertContent, setContent } = make()
    await api.onAiContinueWrite()
    await api.onAiGeneratePolicy()
    expect(insertContent).not.toHaveBeenCalled()
    expect(setContent).not.toHaveBeenCalled()
    expect(mocks.emit).toHaveBeenCalledWith('ai-content:adopted', { projectId: 'p1' })
  })

  it('改写和变动分析不直接替换选择或插入正文', async () => {
    mocks.rewrite.mockResolvedValue({
      original: '选中文本', rewritten: '改写文本', artifact_id: 'a3', knowledge_count: 0,
    })
    mocks.analysis.mockResolvedValue({ generated_text: '分析', artifact_id: 'a4' })
    const { api, insertContent, chain, run } = make()
    api.onAiRewriteOpen()
    await api.onAiRewriteConfirm()
    await api.onAiGenerateAnalysis()
    expect(chain).not.toHaveBeenCalled()
    expect(run).not.toHaveBeenCalled()
    expect(insertContent).not.toHaveBeenCalled()
    expect(mocks.emit).toHaveBeenCalledTimes(2)
  })
})
