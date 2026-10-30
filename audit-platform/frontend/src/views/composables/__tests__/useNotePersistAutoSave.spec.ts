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
