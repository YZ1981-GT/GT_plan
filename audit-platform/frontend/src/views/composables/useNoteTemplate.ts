/**
 * useNoteTemplate — 模板切换 / 转换规则 / 模板配置
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import type { DisclosureNoteTreeItem } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import P from '@/services/apiPaths'

/**
 * 中文数字→阿拉伯数字映射（支持一~二十常见章节编号）
 */
const CN_NUM: Record<string, number> = {
  '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
  '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
  '十一': 11, '十二': 12, '十三': 13, '十四': 14,
  '十五': 15, '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
}

/**
 * 解析 note_section 为可比较的排序键 [大章序号, 子编号(可选)]
 */
function parseNoteSectionKey(section: string): [number, number] {
  const s = section.trim()
  const m = s.match(/^(十[一二三四五六七八九]?|[一二三四五六七八九])(?:[、，,]\s*(\d+)?)?/)
  if (!m) return [Infinity, 0]
  const major = CN_NUM[m[1]] ?? Infinity
  if (m[2] !== undefined) return [major, Number(m[2])]
  if (s.includes('、') || s.includes('，') || s.includes(',')) return [major, 0]
  return [major, -1]
}

/** 比较两个 note_section 的排序顺序 */
function compareNoteSection(a: string, b: string): number {
  const [aMajor, aSub] = parseNoteSectionKey(a)
  const [bMajor, bSub] = parseNoteSectionKey(b)
  return aMajor !== bMajor ? aMajor - bMajor : aSub - bSub
}

/** 对方模板章节选项 */
export interface TargetSectionOption {
  /** 显示标签，如 "八、1 货币资金" */
  label: string
  /** 选中值，同 label */
  value: string
}

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
  /** 对方模板的章节选项列表（供下拉选择器使用） */
  targetSections: Ref<TargetSectionOption[]>
  customTemplateId: Ref<string>
  customTemplateName: Ref<string>
  customTemplateVersion: Ref<string>
  deTemplateOptions: { label: string; value: string }[]
  loadNoteMappingPreset: () => Promise<void>
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
  const targetSections = ref<TargetSectionOption[]>([])
  const customTemplateId = ref('')
  const customTemplateName = ref('')
  const customTemplateVersion = ref('')

  /** 附注模板选项（含自定义模板） */
  const deTemplateOptions = ref([
    { label: '国企版', value: 'soe' },
    { label: '上市版', value: 'listed' },
  ])

  /**
   * 加载映射预设：当前模板章节 ↔ 对方模板章节
   * 左列 = 当前模板（按章节自然序），右列 = 对方模板的章节（按标题自动匹配）
   */
  async function loadNoteMappingPreset() {
    noteMappingLoading.value = true
    try {
      // 确定对方模板类型
      const currentType = templateType.value || 'soe'
      const targetType = currentType === 'listed' ? 'soe' : 'listed'

      // 请求对方模板的完整章节列表
      const targetData = await api.get(P.noteTemplates.list(targetType))
      const targetRawSections: any[] = targetData?.sections || []

      // 构建对方章节选项列表（排序后供下拉选择器使用）
      const targetItems = targetRawSections.map((s: any) => {
        const num = s.section_number || s.note_section || ''
        const title = s.section_title || ''
        const label = num ? `${num} ${title}`.trim() : title
        return { label, value: label, _title: title }
      }).sort((a, b) => compareNoteSection(a.value, b.value))

      targetSections.value = targetItems.map(({ label, value }) => ({ label, value }))

      // 构建按标题的快速索引（用于自动匹配）
      const titleToTarget = new Map<string, string>()
      for (const item of targetItems) {
        if (item._title) titleToTarget.set(item._title, item.value)
      }

      // 当前模板章节排序
      const sorted = [...noteList.value].sort((a, b) =>
        compareNoteSection(a.note_section, b.note_section),
      )

      // 生成映射规则，按标题自动匹配
      noteMappingRules.value = sorted.map(n => {
        const soeLabel = `${n.note_section} ${n.section_title}`.trim()
        // 优先按标题精确匹配对方章节
        const matched = titleToTarget.get(n.section_title || '') || ''
        return {
          soe_section: soeLabel,
          listed_section: matched,
          _editing: false,
        }
      })
    } catch (e) {
      console.error('加载对方模板章节失败', e)
      // 降级：左右同名
      const sorted = [...noteList.value].sort((a, b) =>
        compareNoteSection(a.note_section, b.note_section),
      )
      noteMappingRules.value = sorted.map(n => ({
        soe_section: `${n.note_section} ${n.section_title}`,
        listed_section: `${n.note_section} ${n.section_title}`,
        _editing: false,
      }))
    } finally {
      noteMappingLoading.value = false
    }
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
    targetSections,
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
