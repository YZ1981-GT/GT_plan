/**
 * useNoteSectionManage — 章节管理（新增/删除自定义章节 + 树右键菜单）
 *
 * 从 DisclosureEditor.vue 抽取
 */
import { ref, reactive, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { refreshDisclosureFromWorkpapers } from '@/services/commonApi'
import { addOrUpdateCustomSection, removeCustomSection } from '@/composables/useNoteCustomTemplate'
import { handleApiError } from '@/utils/errorHandler'

export interface UseNoteSectionManageOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
  currentNote: Ref<any>
  fetchTree: () => Promise<void>
  fetchDetail: (noteSection: string) => Promise<void>
  noteStale: { dismissStale: (section: string) => void }
}

export function useNoteSectionManage(options: UseNoteSectionManageOptions) {
  const { projectId, year, currentNote, fetchTree, fetchDetail, noteStale } = options

  // ── 新增章节 ──
  const showAddSectionDialog = ref(false)
  const addSectionLoading = ref(false)
  const addSectionForm = ref({ section_number: '', section_title: '', account_name: '', sort_order: 9000 })

  function openAddSectionDialog() {
    addSectionForm.value = { section_number: '', section_title: '', account_name: '', sort_order: 9000 }
    showAddSectionDialog.value = true
  }

  async function onAddSectionConfirm() {
    const form = addSectionForm.value
    if (!form.section_number.trim()) { ElMessage.warning('请填写章节编号（如：五、X1）'); return }
    if (!form.section_title.trim()) { ElMessage.warning('请填写章节标题'); return }
    addSectionLoading.value = true
    try {
      await addOrUpdateCustomSection(projectId.value, {
        section_number: form.section_number.trim(),
        section_title: form.section_title.trim(),
        account_name: form.account_name.trim() || form.section_title.trim(),
        sort_order: form.sort_order,
        _custom: true,
      })
      ElMessage.success(`已新增章节「${form.section_title}」`)
      showAddSectionDialog.value = false
      await fetchTree()
    } catch (e: any) { handleApiError(e, '新增章节失败') }
    finally { addSectionLoading.value = false }
  }

  // ── 树右键菜单 ──
  const treeContextMenu = reactive<{ visible: boolean; x: number; y: number; section: any | null }>({
    visible: false, x: 0, y: 0, section: null,
  })

  function onTreeNodeContextMenu(event: Event, data: any) {
    if (!data || data.isGroup || !data.data?.note_section) return
    const mouseEvent = event as MouseEvent
    mouseEvent.preventDefault()
    treeContextMenu.visible = true
    treeContextMenu.x = mouseEvent.clientX
    treeContextMenu.y = mouseEvent.clientY
    treeContextMenu.section = data.data
  }

  function closeTreeContextMenu() {
    treeContextMenu.visible = false
    treeContextMenu.section = null
  }

  async function onTreeCtxRecalc() {
    const sec = treeContextMenu.section
    closeTreeContextMenu()
    if (!sec?.note_section) return
    try {
      await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      noteStale.dismissStale(sec.note_section)
      ElMessage.success(`章节「${sec.section_title || sec.note_section}」已重算`)
      if (currentNote.value?.note_section === sec.note_section) await fetchDetail(sec.note_section)
    } catch (e: any) { handleApiError(e, '重算章节失败') }
  }

  async function onTreeCtxDeleteCustom() {
    const sec = treeContextMenu.section
    closeTreeContextMenu()
    if (!sec?.note_section || !sec?._custom) { ElMessage.warning('仅可删除自定义章节'); return }
    try {
      const { confirmDangerous } = await import('@/utils/confirm')
      await confirmDangerous(`确认删除自定义章节「${sec.section_title || sec.note_section}」？`, '删除自定义章节')
    } catch { return }
    try {
      const result = await removeCustomSection(projectId.value, sec.note_section)
      if (result === null) { ElMessage.warning('当前自定义模板未包含此章节'); return }
      ElMessage.success(`已删除自定义章节「${sec.section_title || sec.note_section}」`)
      await fetchTree()
    } catch (e: any) { handleApiError(e, '删除自定义章节失败') }
  }

  return {
    showAddSectionDialog, addSectionLoading, addSectionForm,
    openAddSectionDialog, onAddSectionConfirm,
    treeContextMenu, onTreeNodeContextMenu, closeTreeContextMenu,
    onTreeCtxRecalc, onTreeCtxDeleteCustom,
  }
}
