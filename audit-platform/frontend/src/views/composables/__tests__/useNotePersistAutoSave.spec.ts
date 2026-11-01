/**
 * 附注定时自动保存不打断编辑（spec note-pull-header-formula-closure，批 6 浏览器实测发现）：
 * 原先每次保存（含 2 分钟定时保存）都退出编辑、弹「保存成功」，正在填的格子直接消失。
 * 现行：`onSave({ keepEditing: true })` 只存不退出、不弹提示，脏标记照常清；手工保存不变。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const h = vi.hoisted(() => ({ update: vi.fn(), success: vi.fn() }))
vi.mock('@/services/auditPlatformApi', () => ({ updateDisclosureNote: h.update }))
vi.mock('element-plus', () => ({ ElMessage: { success: h.success, error: vi.fn(), warning: vi.fn(), info: vi.fn() } }))

import { useNotePersist } from '../useNotePersist'

function setup() {
  const currentNote = ref({
    id: 'n-auto', note_section: '五、5', content_type: 'table',
    table_data: { _tables: [{ headers: ['账龄', '应收账款'], rows: [{ label: '1年以内', values: [100] }] }] },
    text_content: '', status: 'draft',
  } as any)
  const editMode = ref(true)
  const flags = { clearEditDirty: vi.fn(), autoSaveClearDirty: vi.fn(), clearAutoSaveDraft: vi.fn() }
  const persist = useNotePersist({ currentNote, textContent: ref(''), editMode, ...flags })
  return { currentNote, editMode, flags, persist }
}

beforeEach(() => {
  h.update.mockReset().mockResolvedValue({})
  h.success.mockReset()
})

describe('useNotePersist keepEditing', () => {
  it('定时保存：只存不退出编辑、不弹「保存成功」，脏标记照常清', async () => {
    const { editMode, flags, persist } = setup()
    await persist.onSave({ keepEditing: true })
    expect(h.update).toHaveBeenCalledTimes(1)
    expect(editMode.value).toBe(true)
    expect(h.success).not.toHaveBeenCalled()
    expect(flags.clearEditDirty).toHaveBeenCalled()
    expect(flags.autoSaveClearDirty).toHaveBeenCalled()
  })

  it('手工保存（默认）：退出编辑并提示', async () => {
    const { editMode, persist } = setup()
    await persist.onSave()
    expect(editMode.value).toBe(false)
    expect(h.success).toHaveBeenCalledWith('保存成功')
  })
})


function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

describe('useNotePersist 保存代际', () => {
  it('同章保存期间继续编辑时旧快照不回放，并立即补存最新正文和表格', async () => {
    const first = deferred<any>()
    const second = deferred<any>()
    h.update
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
    const currentNote = ref({
      id: 'n-race', note_section: '五、8', content_type: 'mixed',
      table_data: { rows: [{ values: ['旧表格'] }] }, text_content: '<p>旧正文</p>', status: 'draft',
    } as any)
    const textContent = ref('<p>第一版</p>')
    const editMode = ref(true)
    const flags = { clearEditDirty: vi.fn(), autoSaveClearDirty: vi.fn(), clearAutoSaveDraft: vi.fn() }
    const persist = useNotePersist({ currentNote, textContent, editMode, ...flags })
    persist.markEdited()

    const pending = persist.onSave({ keepEditing: true })
    await vi.waitFor(() => expect(h.update).toHaveBeenCalledTimes(1))
    currentNote.value.table_data = { rows: [{ values: ['最新表格'] }] }
    textContent.value = '<p>最新版</p>'
    persist.markEdited()

    first.resolve({})
    await vi.waitFor(() => expect(h.update).toHaveBeenCalledTimes(2))
    expect(currentNote.value.table_data).toEqual({ rows: [{ values: ['最新表格'] }] })
    expect(h.update.mock.calls[1][1]).toEqual({
      text_content: '<p>最新版</p>',
      table_data: { rows: [{ values: ['最新表格'] }] },
    })
    expect(flags.clearEditDirty).not.toHaveBeenCalled()

    second.resolve({})
    await expect(pending).resolves.toBe(true)
    expect(currentNote.value.text_content).toBe('<p>最新版</p>')
    expect(currentNote.value.table_data).toEqual({ rows: [{ values: ['最新表格'] }] })
    expect(flags.clearEditDirty).toHaveBeenCalledTimes(1)
    expect(flags.autoSaveClearDirty).toHaveBeenCalledTimes(1)
    expect(editMode.value).toBe(true)
  })

  it('明确放弃编辑会使在途旧回执失效', async () => {
    const gate = deferred<any>()
    h.update.mockImplementationOnce(() => gate.promise)
    const currentNote = ref({
      id: 'n-discard', note_section: '五、9', content_type: 'table',
      table_data: { rows: [{ values: ['请求快照'] }] }, text_content: '', status: 'draft',
    } as any)
    const flags = { clearEditDirty: vi.fn(), autoSaveClearDirty: vi.fn(), clearAutoSaveDraft: vi.fn() }
    const persist = useNotePersist({ currentNote, textContent: ref(''), editMode: ref(true), ...flags })
    persist.markEdited()
    const pending = persist.onSave()
    currentNote.value.table_data = { rows: [{ values: ['放弃后的本地状态'] }] }
    persist.discardEdits()
    gate.resolve({})

    await expect(pending).resolves.toBe(false)
    expect(currentNote.value.table_data).toEqual({ rows: [{ values: ['放弃后的本地状态'] }] })
    expect(flags.clearEditDirty).not.toHaveBeenCalled()
    expect(flags.autoSaveClearDirty).not.toHaveBeenCalled()
  })
})