/**
 * useNoteDetail — 章节详情加载 / 富文本 change 处理
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import {
  getDisclosureNoteDetail,
  type DisclosureNoteDetail,
} from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'

export interface UseNoteDetailOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
  editor: Ref<any>
  editMode: Ref<boolean>
  markEditDirty: () => void
  autoSaveMarkDirty: () => void
}

export interface UseNoteDetailReturn {
  currentNote: Ref<DisclosureNoteDetail | null>
  textContent: Ref<string>
  detailLoading: Ref<boolean>
  priorYearNote: Ref<any>
  fetchDetail: (noteSection: string) => Promise<void>
  onRichTextChange: (html: string) => void
}

export function useNoteDetail(options: UseNoteDetailOptions): UseNoteDetailReturn {
  const { projectId, year, editor, editMode, markEditDirty, autoSaveMarkDirty } = options

  const currentNote = ref<DisclosureNoteDetail | null>(null)
  const textContent = ref('')
  const detailLoading = ref(false)
  const priorYearNote = ref<any>(null)

  async function fetchDetail(noteSection: string) {
    currentNote.value = await getDisclosureNoteDetail(projectId.value, year.value, noteSection)
    textContent.value = currentNote.value.text_content || ''
    if (editor.value) {
      // 将纯文本段落转为HTML段落供TipTap渲染
      const raw = textContent.value
      if (raw && !raw.startsWith('<')) {
        const html = raw.split(/\n\n+/).filter(Boolean).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('')
        editor.value.commands.setContent(html)
      } else {
        editor.value.commands.setContent(raw)
      }
    }
    // 并行加载上年数据
    try {
      priorYearNote.value = await api.get(
        P.disclosureNotes.priorYear(projectId.value, year.value, noteSection)
      )
    } catch { priorYearNote.value = null }
  }

  function onRichTextChange(html: string) {
    textContent.value = html
    if (editMode.value) { markEditDirty(); autoSaveMarkDirty() }
  }

  return {
    currentNote,
    textContent,
    detailLoading,
    priorYearNote,
    fetchDetail,
    onRichTextChange,
  }
}
