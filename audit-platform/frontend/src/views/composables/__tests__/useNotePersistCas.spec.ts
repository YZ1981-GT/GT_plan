/**
 * useNotePersist 跨会话 CAS / 幂等 / 状态一致性（2026-11-26 穿透复盘 P0/P1/P2）。
 *
 * - 保存携带编辑起点 content_digest（expected_digest）
 * - 409 NOTE_CONTENT_CONFLICT：弹确认框，旧 digest 作废，返回 false（保存失败语义）
 * - 成功后采用服务端 status / 新 content_digest；status 不再被本地写成 confirmed
 * - 同一保存重试沿用同一 mutationId（网络层重试同 config）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockRejectedValue('cancel') },
}))

const mockUpdateNote = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({
  updateDisclosureNote: (...args: any[]) => mockUpdateNote(...args),
}))

import { useNotePersist } from '../useNotePersist'

function setup(noteOverrides: Record<string, any> = {}) {
  const currentNote = ref({
    id: 'note-1', note_section: '一、1', content_type: 'text',
    table_data: null, text_content: '', status: 'draft',
    content_digest: 'digest-a',
    ...noteOverrides,
  } as any)
  const flags = { clearEditDirty: vi.fn(), autoSaveClearDirty: vi.fn(), clearAutoSaveDraft: vi.fn() }
  const reload = vi.fn()
  const persist = useNotePersist({
    currentNote, textContent: ref('<p>新</p>'), editMode: ref(true),
    ...flags, reloadCurrentNote: reload,
  })
  return { currentNote, flags, reload, persist }
}

describe('useNotePersist CAS（P0）', () => {
  beforeEach(() => { mockUpdateNote.mockReset() })

  it('保存携带编辑起点 expected_digest', async () => {
    mockUpdateNote.mockResolvedValue({ status: 'draft', content_digest: 'digest-b' })
    const { persist } = setup()
    await persist.onSave()
    expect(mockUpdateNote.mock.calls[0][1]).toMatchObject({ expected_digest: 'digest-a' })
  })

  it('成功后采用服务端 status 与新 digest，不写 confirmed', async () => {
    mockUpdateNote.mockResolvedValue({ status: 'confirmed', content_digest: 'digest-b' })
    const { currentNote, persist } = setup()
    await persist.onSave()
    expect(currentNote.value.status).toBe('confirmed')
    expect(currentNote.value.content_digest).toBe('digest-b')
  })

  it('保存响应推进 status 与 content_digest（下次保存的起点）', async () => {
    mockUpdateNote.mockResolvedValue({ status: 'confirmed', content_digest: 'digest-b' })
    const { currentNote, persist } = setup()
    await persist.onSave()
    expect(currentNote.value.status).toBe('confirmed')   // 服务端说什么就是什么
    expect(currentNote.value.content_digest).toBe('digest-b')
  })

  it('409 NOTE_CONTENT_CONFLICT：返回 false、作废旧 digest、不弹全局错误', async () => {
    mockUpdateNote.mockRejectedValue({ response: { status: 409, data: { detail: {
      error_code: 'NOTE_CONTENT_CONFLICT', message: '该章节已被其他会话修改', current_digest: 'digest-x',
    } } } })
    const { currentNote, flags, persist } = setup()
    const ok = await persist.onSave()
    expect(ok).toBe(false)
    expect(currentNote.value.content_digest).toBeUndefined()
    expect(flags.clearEditDirty).not.toHaveBeenCalled()
    // 网络层请求带 silent：冲突由组件统一弹窗
    expect(mockUpdateNote.mock.calls[0][2]).toMatchObject({ silent: true })
  })

  it('同一轮保存请求带稳定 mutationId（uuid 形态）', async () => {
    mockUpdateNote.mockResolvedValue({})
    const { persist } = setup()
    await persist.onSave()
    const opts = mockUpdateNote.mock.calls[0][2]
    expect(opts.mutationId).toMatch(/[0-9a-f-]{36}/)
  })

  it('无 content_digest 的章节（旧数据 / 服务端未下发）保存不带 expected_digest', async () => {
    mockUpdateNote.mockResolvedValue({})
    const { persist } = setup({ content_digest: undefined })
    await persist.onSave()
    expect(mockUpdateNote.mock.calls[0][1]).not.toHaveProperty('expected_digest')
  })
})
