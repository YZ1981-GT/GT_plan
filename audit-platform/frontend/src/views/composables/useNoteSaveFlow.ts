/**
 * 附注编辑器一次保存的状态与收尾（spec platform-performance-user-experience-closure 任务 30，从 DisclosureEditor 拆出）。
 *
 * - 状态：saving → saved（3 秒后回 idle）/ error。`save` 返回 false 或抛错都算失败，调用方据此保留 dirty、稍后重试。
 * - 保存期间切了章：旧章节已经持久化，但不能把新章节当成「本次保存成功」去清结构撤销记录或自动跳章 ⇒ 回 idle、不调收尾。
 */
import { ref } from 'vue'

export type NoteSaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export interface NoteSaveFlowOptions {
  /** 当前章节 id：保存开始与完成时各读一次，判断保存期间是否切章 */
  currentNoteId: () => string | undefined
  /** 真正的保存（useNotePersist 的 onSave）；false / 抛错 = 失败 */
  save: (opts: { keepEditing: boolean }) => Promise<boolean>
  /** 本章保存成功后的收尾；auto = 定时自动保存（只存不打断：不退出编辑、不跳章） */
  onSaved: (auto: boolean) => void
}

export function useNoteSaveFlow(options: NoteSaveFlowOptions) {
  const saveStatus = ref<NoteSaveStatus>('idle')

  async function saveCurrentNote({ auto }: { auto: boolean }): Promise<boolean> {
    const savingNoteId = options.currentNoteId()
    if (!savingNoteId) return false
    saveStatus.value = 'saving'
    try {
      if (!(await options.save({ keepEditing: auto }))) {
        saveStatus.value = 'error'
        return false
      }
      if (options.currentNoteId() !== savingNoteId) {
        saveStatus.value = 'idle'
        return true
      }
      options.onSaved(auto)
      saveStatus.value = 'saved'
      setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 3000)
      return true
    } catch {
      saveStatus.value = 'error'
      return false
    }
  }

  return { saveStatus, saveCurrentNote }
}
