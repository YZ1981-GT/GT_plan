/**
 * useNoteTemplate — 模板切换 / 转换规则 / 模板配置
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import type { DisclosureNoteTreeItem } from '@/services/auditPlatformApi'

export interface UseNoteTemplateOptions {
  projectId: ComputedRef<string> | Ref<string>
  templateType: Ref<string>
  noteList: Ref<DisclosureNoteTreeItem[]>
  fetchTree: () => Promise<void>
  onGenerate: () => Promise<void>
}

export interface UseNoteTemplateReturn {
  showNoteMappingDialog: Ref<boolean>
  noteMappingLoading: Ref<boolean>
  noteMappingRules: Ref<any[]>
  customTemplateId: Ref<string>
  customTemplateName: Ref<string>
  customTemplateVersion: Ref<string>
  deTemplateOptions: { label: string; value: string }[]
  loadNoteMappingPreset: () => void
  saveNoteMappingRules: () => void
  getNoteMappingData: () => Record<string, any>
  onNoteMappingApplied: (data: Record<string, any>) => void
  getNoteTemplateConfigData: () => Record<string, any>
  onNoteTemplateApplied: (data: Record<string, any>) => void
  handleTemplateChange: (value: string) => Promise<void>
}

export function useNoteTemplate(options: UseNoteTemplateOptions): UseNoteTemplateReturn {
  const { projectId, templateType, noteList, fetchTree, onGenerate } = options

  const showNoteMappingDialog = ref(false)
  const noteMappingLoading = ref(false)
  const noteMappingRules = ref<any[]>([])
  const customTemplateId = ref('')
  const customTemplateName = ref('')
  const customTemplateVersion = ref('')

  /** 附注模板选项（含自定义模板） */
  const deTemplateOptions = ref([
    { label: '国企版', value: 'soe' },
    { label: '上市版', value: 'listed' },
  ])

  function loadNoteMappingPreset() {
    // 从当前附注章节列表生成映射规则
    noteMappingRules.value = noteList.value.map(n => ({
      soe_section: `${n.note_section} ${n.section_title}`,
      listed_section: `${n.note_section} ${n.section_title}`,  // 默认同名
      _editing: false,
    }))
  }

  function saveNoteMappingRules() {
    ElMessage.success('转换规则已保存')
    showNoteMappingDialog.value = false
  }

  function getNoteMappingData(): Record<string, any> {
    return { note_mapping_rules: noteMappingRules.value }
  }

  function onNoteMappingApplied(data: Record<string, any>) {
    const rules = data?.note_mapping_rules || []
    if (rules.length) {
      noteMappingRules.value = rules
      ElMessage.success(`已引用 ${rules.length} 条映射规则`)
    }
  }

  function getNoteTemplateConfigData(): Record<string, any> {
    return {
      template_type: templateType.value,
      note_sections: noteList.value.map(n => ({
        note_section: n.note_section,
        section_title: n.section_title,
      })),
    }
  }

  function onNoteTemplateApplied(data: Record<string, any>) {
    if (data?.template_type) {
      templateType.value = data.template_type
    }
    // 重新加载附注树以应用模板
    fetchTree()
    ElMessage.success('附注模板已应用')
  }

  async function handleTemplateChange(value: string) {
    if (value === 'custom' && !customTemplateId.value) {
      ElMessage.warning('当前项目未绑定自定义附注模板，请先在项目基本信息中选择')
      templateType.value = 'soe'
      return
    }
    await onGenerate()
  }

  return {
    showNoteMappingDialog,
    noteMappingLoading,
    noteMappingRules,
    customTemplateId,
    customTemplateName,
    customTemplateVersion,
    deTemplateOptions: deTemplateOptions.value,
    loadNoteMappingPreset,
    saveNoteMappingRules,
    getNoteMappingData,
    onNoteMappingApplied,
    getNoteTemplateConfigData,
    onNoteTemplateApplied,
    handleTemplateChange,
  }
}
