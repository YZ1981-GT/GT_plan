<script setup lang="ts">
/**
 * GtChecklistTable — 核对表底稿组件
 *
 * A1-15/A1-16 大型 docx 核对表完整渲染。
 * 左侧目录导航(35章节树) + 右侧核对表主体(当前章节)。
 *
 * 条目分类:
 *  - actionable: 主条目，需填 Y/N/NA
 *  - guidance: 提示性子项，默认折叠不可编辑
 *  - header: 小节标题，加粗分隔行
 *
 * 功能: 章节适用性弹窗 / 自动保存(debounce 2s) / 进度统计 / 颜色编码
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtChecklistSection from './GtChecklistSection.vue'
import GtChecklistNav from './GtChecklistNav.vue'
import GtChecklistObjectivePanel from './GtChecklistObjectivePanel.vue'
import { useChecklistResponses } from '@/composables/useChecklistResponses'
import { useChecklistSearch } from '@/composables/useChecklistSearch'
import { useChecklistApplicability } from '@/composables/useChecklistApplicability'
import type {
  ChecklistItem,
  ChecklistHtmlData,
  ReviewSignHint,
} from './checklistTypes'

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName?: string
  schema?: Record<string, unknown>
  htmlData: ChecklistHtmlData
  readonly?: boolean
}>(), {
  sheetName: '',
  schema: () => ({}),
  readonly: false,
})

const emit = defineEmits<{
  (e: 'save'): void
}>()

// ─── Route ───
const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')

// ─── State (kept in main as orchestrator) ───
const activeSection = ref('')
const expandedItems = ref<Set<string>>(new Set())
const reviewSignHints = ref<Record<string, ReviewSignHint>>({})

// ─── Filter state (Task 10) ───
type FilterMode = 'all' | 'unfilled' | 'inapplicable'
const filterMode = ref<FilterMode>('all')

// ─── Composables: 适用性 / 响应填写+自动保存 / 搜索 ───
// 适用性 state 由本 composable 持有；其 confirm 需 markPending+scheduleSave 由 responses 提供
const {
  sectionApplicability,
  showApplicabilityDialog,
  isSectionApplicable,
  openApplicabilityDialog,
  toggleSectionApplicability,
  confirmApplicability,
} = useChecklistApplicability({
  readonly: () => props.readonly,
  markPending: (itemId: string) => responsesApi.pendingChanges.value.add(itemId),
  scheduleSave: () => responsesApi.scheduleSave(),
})

// 响应填写 + 自动保存（debounce 2s）；保存成功 emit('save') 由主组件持有
const responsesApi = useChecklistResponses({
  wpId: () => props.wpId,
  projectId,
  htmlData: () => props.htmlData,
  readonly: () => props.readonly,
  sectionApplicability,
  onSaved: () => emit('save'),
  reinit: () => initFromProps(),
})
const {
  responses,
  saving,
  pendingChanges,
  hasDirtyData,
  getResponse,
  updateConclusion,
  updateRemark,
  updateWpRef,
  scheduleSave,
  handleManualSave,
  handleReset,
  flushBeacon,
} = responsesApi

// 搜索 / 高亮 / 跳转
const {
  searchQuery,
  searchActive,
  searchResults,
  highlightText,
  jumpToSearchResult,
  clearSearch,
} = useChecklistSearch({
  sections: () => sections.value,
  activeSection,
  expandedItems,
})

// ─── Computed: Template data ───
const template = computed(() => props.htmlData?.template)
const isA15_1 = computed(() => template.value?.wp_code === 'A15-1')
const eqcrWorkbenchPath = computed(() =>
  projectId.value ? `/eqcr/projects/${projectId.value}` : '',
)
const sections = computed(() => template.value?.sections ?? [])
const toc = computed(() => template.value?.toc ?? [])
const stats = computed(() => template.value?.stats ?? { total_actionable: 0, total_guidance: 0, total_sections: 0 })

// ─── Computed: Current section ───
const currentSection = computed(() => {
  if (!activeSection.value) return sections.value[0] ?? null
  return sections.value.find(s => s.id === activeSection.value) ?? null
})

// ─── Computed: Progress ───
const filledCount = computed(() => {
  let count = 0
  for (const section of sections.value) {
    for (const item of section.items) {
      if (item.type === 'actionable') {
        const resp = responses.value[item.id]
        if (resp?.conclusion) count++
      }
    }
  }
  return count
})

const totalActionable = computed(() => stats.value.total_actionable)
const progressPercent = computed(() => {
  if (totalActionable.value === 0) return 0
  return Math.round((filledCount.value / totalActionable.value) * 100)
})

// ─── Computed: Section progress for nav ───
function getSectionProgress(sectionId: string) {
  const section = sections.value.find(s => s.id === sectionId)
  if (!section) return { filled: 0, total: 0 }
  let filled = 0
  let total = 0
  for (const item of section.items) {
    if (item.type === 'actionable') {
      total++
      if (responses.value[item.id]?.conclusion) filled++
    }
  }
  return { filled, total }
}

// ─── Computed: TOC tree for nav (with applicability) ───
const navItems = computed(() => {
  return toc.value.map(entry => {
    const applicable = isSectionApplicable(entry.id)
    const progress = getSectionProgress(entry.id)
    return {
      ...entry,
      applicable,
      progress,
      completed: progress.total > 0 && progress.filled === progress.total,
    }
  })
})

// ─── Computed: Search results (Task 8)：搜索逻辑见 useChecklistSearch ───

// ─── A17-5 审计目标→核对程序 映射 (多对多，基于 seq_no 1-50) ───
// 映射依据：A17-5-1 源模板 6 项审计目标描述 × 50 项核对程序内容语义归类
// seq_no = item_id 末尾数字（非源模板 seq_label），全 50 项覆盖
const OBJECTIVE_PROGRAM_MAP: Record<number, { label: string; programs: number[] }> = {
  1: {
    label: '错报评价与处理',
    programs: [33, 34, 35, 36, 37],  // 累积错报/获取调整确认/未更正错报评估/沟通错报/签章确认
  },
  2: {
    label: '获取管理层声明书',
    programs: [44],  // 取得管理层书面声明
  },
  3: {
    label: '内控缺陷及重大事项沟通',
    programs: [7, 25, 32],  // 与治理层沟通审计范围+重大事项+内控/就错报等重大事项沟通/总结会沟通
  },
  4: {
    label: '财务报表合规性',
    programs: [16, 17, 18, 19, 20, 21, 22, 23, 24, 45],  // 政府补助/终止经营/期后/或有/承诺/关联方/持续经营/其他信息/会计估计/列报披露核对
  },
  5: {
    label: '审计意见恰当性',
    programs: [28, 29, 30, 31, 38],  // KAM确定+子项(1)(2)(3)/董事会接受财报
  },
  6: {
    label: '充分证据与复核',
    programs: [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 26, 27, 39, 40, 41, 42, 43, 46, 47, 48, 49],
    // 承接/约定书/策略计划/风险评估/项目组讨论/策略批准/程序执行/询证函/监盘/组成部分/程序完成/范围/风险/舞弊/
    // 总体复核/召开会议确定调整/经理复核/合伙人复核/质量复核/质控复核/技术复核/结转/备忘/追查/重大概要
    // 注：seq_no 50 为签字确认声明行（非可操作程序），不计入任何目标
  },
}
const isA17_5 = computed(() => (template.value?.wp_code || '').startsWith('A17-5'))

/** A17-5：「否」且无备注的开放项（签发阻断提示） */
const openNoItems = computed(() => {
  if (!isA17_5.value) return [] as ChecklistItem[]
  const result: ChecklistItem[] = []
  for (const sec of sections.value) {
    for (const item of sec.items || []) {
      if (item.type !== 'actionable') continue
      const resp = responses.value[item.id]
      const c = String(resp?.conclusion || '').trim()
      const isNo = c === '否' || c === 'N' || c.toLowerCase() === 'no' || c === 'X/W'
      if (isNo && !(resp?.remark || '').trim()) result.push(item)
    }
  }
  return result
})
const activeObjective = ref<number | null>(null)

/** 当前选中 section 是否为"审计目标" */
const isObjectiveSection = computed(() => {
  return isA17_5.value && currentSection.value?.title?.includes('审计目标')
})

/** 所有 actionable item 的 id（用于目标面板匹配程序编号） */
const allActionableItemIds = computed(() => {
  const ids: string[] = []
  for (const sec of sections.value) {
    for (const item of sec.items) {
      if (item.type === 'actionable') ids.push(item.id)
    }
  }
  return ids
})

/** 反向索引：程序编号 → 所属目标编号数组 */
const programToObjectives = computed<Record<number, number[]>>(() => {
  const map: Record<number, number[]> = {}
  for (const [key, obj] of Object.entries(OBJECTIVE_PROGRAM_MAP)) {
    const idx = Number(key)
    for (const prog of obj.programs) {
      if (!map[prog]) map[prog] = []
      map[prog].push(idx)
    }
  }
  return map
})

/** 从 itemId 获取所属目标编号列表（用于反向标签） */
function getItemObjectives(itemId: string): number[] {
  const m = itemId.match(/(\d+)$/)
  if (!m) return []
  const num = parseInt(m[1])
  return programToObjectives.value[num] || []
}

/** 定位到指定程序编号的条目（从目标面板点击 chip 跳转） */
function locateProgram(programNum: number) {
  // 找到包含该程序编号的 section 和 item
  for (const sec of sections.value) {
    for (const item of sec.items) {
      if (item.type !== 'actionable') continue
      const m = item.id.match(/(\d+)$/)
      if (m && parseInt(m[1]) === programNum) {
        // 切换到该 section
        activeSection.value = sec.id
        // 清除目标筛选以显示全部
        activeObjective.value = null
        return
      }
    }
  }
}

function selectObjective(objIdx: number | null) {
  activeObjective.value = activeObjective.value === objIdx ? null : objIdx
}

/** 判断item的序号是否属于当前选中目标对应的程序列表 */
function isItemInObjective(itemId: string): boolean {
  if (!activeObjective.value || !OBJECTIVE_PROGRAM_MAP[activeObjective.value]) return false
  // 从item id中提取序号(格式通常为 "S2-1", "S2-2" ... 其中数字是程序编号)
  const match = itemId.match(/\d+$/)
  if (!match) return false
  const num = parseInt(match[0])
  return OBJECTIVE_PROGRAM_MAP[activeObjective.value].programs.includes(num)
}

// ─── Computed: Filtered items for current section (Task 10) ───
const filteredCurrentItems = computed(() => {
  if (!currentSection.value) return []
  const items = currentSection.value.items
  let result = items

  // A17-5: 排除签字确认项（seq_no 50），单独渲染为结论签字区
  if (isA17_5.value) {
    result = result.filter(item => {
      if (item.type !== 'actionable') return true
      const m = item.id.match(/(\d+)$/)
      if (m && parseInt(m[1]) === 50) return false
      return true
    })
  }

  // 按目标筛选（A17-5专用）
  if (activeObjective.value && isA17_5.value) {
    const programs = OBJECTIVE_PROGRAM_MAP[activeObjective.value]?.programs || []
    result = result.filter(item => {
      if (item.type === 'header') return true
      const match = item.id.match(/\d+$/)
      if (!match) return true
      return programs.includes(parseInt(match[0]))
    })
  }

  // 按填写状态筛选
  if (filterMode.value !== 'all') {
    result = result.filter(item => {
      if (item.type === 'header') return true
      if (item.type !== 'actionable') return false
      const resp = responses.value[item.id]
      if (filterMode.value === 'unfilled') return !resp?.conclusion
      if (filterMode.value === 'inapplicable') return resp?.conclusion === 'N/A'
      return true
    })
  }

  return result
})

/** A17-5 签字确认项（seq_no 50）—— 独立渲染为结论签字卡片 */
const conclusionItem = computed(() => {
  if (!isA17_5.value || !currentSection.value) return null
  // 仅在「核对程序」section 中显示
  if (currentSection.value.title?.includes('审计目标')) return null
  for (const item of currentSection.value.items) {
    if (item.type !== 'actionable') continue
    const m = item.id.match(/(\d+)$/)
    if (m && parseInt(m[1]) === 50) return item
  }
  return null
})

// ─── Methods: Navigation ───
function selectSection(sectionId: string) {
  activeSection.value = sectionId
}

// ─── Methods: Item expand/collapse ───
function toggleExpand(itemId: string) {
  if (expandedItems.value.has(itemId)) {
    expandedItems.value.delete(itemId)
  } else {
    expandedItems.value.add(itemId)
  }
}

function isExpanded(itemId: string): boolean {
  return expandedItems.value.has(itemId)
}

// ─── Methods: Response handling / Autosave / 适用性：见 useChecklistResponses + useChecklistApplicability ───

// ─── Methods: Batch mark section (Task 9) ───
function markSectionAll(sectionId: string, conclusion: string) {
  if (props.readonly) return
  const section = sections.value.find(s => s.id === sectionId)
  if (!section) return
  for (const item of section.items) {
    if (item.type === 'actionable') {
      const resp = getResponse(item.id)
      resp.conclusion = conclusion
      pendingChanges.value.add(item.id)
    }
  }
  scheduleSave()
  ElMessage.success(`已将本章节全部标记为 ${conclusion}`)
}

// ─── Methods: Color coding ───
function getConclusionClass(conclusion: string | null): string {
  if (!conclusion) return ''
  switch (conclusion) {
    case 'Y':
    case '是':
      return 'conclusion-yes'
    case 'X/I':
      return 'conclusion-xi'
    case 'X/W':
    case '否':
    case 'N':
      return 'conclusion-xw'
    case 'N/A':
    case '不适用':
    case 'NA':
      return 'conclusion-na'
    default: return ''
  }
}

function presetReviewPrefix(ref: string | undefined): string | null {
  if (!ref) return null
  const m = ref.match(/^A2[1-5]/)
  return m ? m[0] : null
}

function signHintForItem(item: ChecklistItem): ReviewSignHint | null {
  const prefix = presetReviewPrefix(item.preset_wp_ref)
  return prefix ? reviewSignHints.value[prefix] : null
}

async function loadReviewSignHints() {
  const code = template.value?.wp_code || ''
  if (!code.startsWith('A17-5') || !projectId.value) return
  try {
    const res = await api.get('/api/a17/review-sign-hints', {
      params: { project_id: projectId.value },
    })
    reviewSignHints.value = (res?.data ?? res) || {}
  } catch { /* non-critical */ }
}

function applySignHint(itemId: string, hint: ReviewSignHint) {
  if (!hint?.suggested_conclusion) return
  updateConclusion(itemId, hint.suggested_conclusion)
  ElMessage.success('已应用复核签字建议')
}

// ─── Custom items (allow_custom_items = true 时支持用户自定义添加条目) ───
function addCustomItem(sectionId: string) {
  if (props.readonly) return
  const section = sections.value.find(s => s.id === sectionId)
  if (!section) return
  const newItem: ChecklistItem = {
    id: `CUSTOM-${sectionId}-${Date.now().toString(36)}`,
    type: 'actionable',
    standard_ref: '',
    content: '',
    children: [],
  }
  section.items.push(newItem)
  ElMessage.info('已添加新条目，请点击编辑内容')
}

function updateItemContent(itemId: string, content: string) {
  // 找到对应条目并更新 content
  for (const sec of sections.value) {
    const item = sec.items.find(i => i.id === itemId)
    if (item) {
      item.content = content
      // 标记待保存
      responsesApi.pendingChanges.value.add(itemId)
      responsesApi.scheduleSave()
      break
    }
  }
}

async function polishWithLLM(itemId: string, selectedText: string) {
  if (!selectedText.trim()) return
  try {
    const resp = await api.post<{ text: string }>(`/api/workpapers/${props.wpId}/ai-suggest`, {
      field_name: 'checklist_custom_item',
      existing_content: selectedText,
      context: `核查表自定义事项润色，要求：保持审计专业措辞、简洁准确、不改变原意`,
    })
    if (resp?.text) {
      // 替换条目内容中选中部分（如果是全文则直接替换）
      for (const sec of sections.value) {
        const item = sec.items.find(i => i.id === itemId)
        if (item) {
          if (selectedText === item.content) {
            item.content = resp.text
          } else {
            item.content = item.content.replace(selectedText, resp.text)
          }
          responsesApi.pendingChanges.value.add(itemId)
          responsesApi.scheduleSave()
          ElMessage.success('AI 润色完成')
          break
        }
      }
    }
  } catch (e: any) {
    if (e?.response?.status === 403) {
      ElMessage.warning('AI 服务未启用')
    } else {
      ElMessage.error('AI 润色失败，请重试')
    }
  }
}

// ─── Initialization ───
function initFromProps() {
  // Load responses from htmlData
  if (props.htmlData?.responses) {
    responses.value = JSON.parse(JSON.stringify(props.htmlData.responses))
  }

  // Load section applicability from responses (TOC-Sxx entries)
  for (const [key, resp] of Object.entries(responses.value)) {
    if (key.startsWith('TOC-')) {
      const sectionId = key.replace('TOC-', '')
      sectionApplicability.value[sectionId] = resp.conclusion === 'Y'
    }
  }

  // Default to first section
  if (sections.value.length > 0 && !activeSection.value) {
    activeSection.value = sections.value[0].id
  }
}

// ─── Lifecycle ───
onMounted(() => {
  initFromProps()
  loadReviewSignHints()
  // Show applicability dialog on first open if no applicability data exists
  // A17-5 系列只有 2 section（审计目标+核对程序）且都必须适用，不弹窗
  const hasApplicabilityData = Object.keys(sectionApplicability.value).length > 0
  if (!hasApplicabilityData && toc.value.length > 0 && !isA17_5.value) {
    nextTick(() => {
      showApplicabilityDialog.value = true
    })
  }
})

watch(() => props.htmlData, () => {
  initFromProps()
}, { deep: true })

onBeforeUnmount(() => {
  // 离开页面时自动保存（使用 sendBeacon 确保不被 cancel）
  flushBeacon()
})
</script>

<template>
  <div class="gt-checklist-table">
    <!-- ─── 顶部标题栏 + 进度 ─── -->
    <div class="gt-checklist-table__header">
      <div class="gt-checklist-table__title">
        <span class="gt-checklist-table__icon">📋</span>
        <span>{{ template?.title || '核对表' }}</span>
      </div>
      <div class="gt-checklist-table__progress">
        <el-progress
          :percentage="progressPercent"
          :stroke-width="16"
          :text-inside="true"
          :format="() => `${filledCount}/${totalActionable} (${progressPercent}%)`"
          style="width: 240px"
        />
        <span v-if="saving" class="gt-checklist-table__saving">保存中...</span>
      </div>
      <!-- 操作按钮组 -->
      <div class="gt-checklist-table__actions">
        <el-button
          size="small"
          type="primary"
          :loading="saving"
          :disabled="pendingChanges.size === 0 && !hasDirtyData"
          @click="handleManualSave"
        >
          保存
        </el-button>
        <el-button
          size="small"
          :disabled="readonly || !hasDirtyData"
          @click="handleReset"
        >
          恢复
        </el-button>
        <el-button
          v-if="readonly"
          size="small"
          @click="$emit('save')"
        >
          编辑
        </el-button>
      </div>
      <el-button
        v-if="!isA17_5"
        size="small"
        :disabled="readonly"
        @click="openApplicabilityDialog"
      >
        章节适用性设置
      </el-button>
      <el-popover placement="bottom" :width="360" trigger="hover">
        <template #reference>
          <el-button size="small" text>标识说明</el-button>
        </template>
        <div class="legend-content">
          <template v-if="isA17_5">
            <div class="legend-item"><span class="legend-tag tag-y">是</span> 已完成 / 已确认</div>
            <div class="legend-item"><span class="legend-tag tag-xw">否</span> 未完成 — 须备注说明，并可跳转上游底稿补做</div>
            <div class="legend-item"><span class="legend-tag tag-na">不适用</span> 本项目不适用该项</div>
          </template>
          <template v-else>
            <div class="legend-item"><span class="legend-tag tag-y">Y</span> 适用于被审计单位财务报表并已在财务报表中披露</div>
            <div class="legend-item"><span class="legend-tag tag-xi">X/I</span> 适用但不重大，未在财务报表中披露</div>
            <div class="legend-item"><span class="legend-tag tag-xw">X/W</span> 适用且重大，未在财务报表中披露，已在另附工作底稿说明原因</div>
            <div class="legend-item"><span class="legend-tag tag-na">N/A</span> 不适用于被审计单位财务报表</div>
          </template>
        </div>
      </el-popover>
    </div>

    <el-alert
      v-if="isA17_5 && openNoItems.length"
      type="warning"
      :closable="false"
      show-icon
      class="gt-checklist-table__no-banner"
      :title="`有 ${openNoItems.length} 项勾选「否」但未填备注，签发前须闭环`"
    >
      <ul class="gt-checklist-table__no-list">
        <li v-for="it in openNoItems.slice(0, 8)" :key="it.id">
          {{ it.standard_ref || it.id }} · {{ (it.content || '').slice(0, 48) }}{{ (it.content || '').length > 48 ? '…' : '' }}
          <template v-if="it.preset_wp_ref"> → {{ it.preset_wp_ref }}</template>
        </li>
      </ul>
    </el-alert>

    <!-- ─── 工具栏: 搜索 + 筛选 + 批量 ─── -->
    <div class="gt-checklist-table__toolbar">
      <!-- 搜索框 (Task 8) -->
      <div class="toolbar__search">
        <el-input
          v-model="searchQuery"
          placeholder="搜索条目文本/准则索引..."
          size="small"
          clearable
          prefix-icon="Search"
          style="width: 280px"
          @focus="searchActive = true"
          @clear="clearSearch"
        />
        <span v-if="searchQuery && searchResults.length > 0" class="toolbar__search-count">
          {{ searchResults.length }} 条匹配
        </span>
      </div>
      <!-- 筛选按钮 (Task 10) -->
      <div class="toolbar__filters">
        <el-radio-group v-model="filterMode" size="small">
          <el-radio-button value="all">全部</el-radio-button>
          <el-radio-button value="unfilled">未填</el-radio-button>
          <el-radio-button value="inapplicable">不适用</el-radio-button>
        </el-radio-group>
      </div>
      <!-- 审计目标筛选 (A17-5专用) -->
      <div v-if="isA17_5" class="toolbar__objectives">
        <el-dropdown size="small" @command="(cmd: number | null) => selectObjective(cmd)">
          <el-button size="small" :type="activeObjective ? 'primary' : ''">
            {{ activeObjective ? `目标${activeObjective}` : '按目标筛选' }} ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :command="null">全部程序</el-dropdown-item>
              <el-dropdown-item v-for="(obj, idx) in OBJECTIVE_PROGRAM_MAP" :key="idx" :command="Number(idx)">
                目标{{ idx }}：{{ obj.label }}（{{ obj.programs.length }}项）
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <!-- 批量标记 (Task 9) -->
      <div v-if="currentSection && !readonly" class="toolbar__batch">
        <el-dropdown size="small" @command="(cmd: string) => markSectionAll(currentSection!.id, cmd as any)">
          <el-button size="small">
            本章节批量标记 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="Y">全部标记 Y (适用已披露)</el-dropdown-item>
              <el-dropdown-item command="X/I">全部标记 X/I (适用不重大)</el-dropdown-item>
              <el-dropdown-item command="X/W">全部标记 X/W (适用重大未披露)</el-dropdown-item>
              <el-dropdown-item command="N/A">全部标记 N/A (不适用)</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- ─── 搜索结果面板 (Task 8) ─── -->
    <div v-if="searchActive && searchQuery && searchResults.length > 0" class="gt-checklist-table__search-results">
      <div class="search-results__header">
        <span>搜索结果 ({{ searchResults.length }})</span>
        <el-button size="small" text @click="clearSearch">关闭</el-button>
      </div>
      <div class="search-results__list">
        <div
          v-for="(result, idx) in searchResults.slice(0, 50)"
          :key="idx"
          class="search-results__item"
          @click="jumpToSearchResult(result)"
        >
          <span class="search-result__section">{{ result.sectionTitle }}</span>
          <span class="search-result__ref">{{ result.item.standard_ref }}</span>
          <span class="search-result__content" v-html="highlightText(result.item.content.slice(0, 80), searchQuery)" />
        </div>
      </div>
    </div>

    <el-alert
      v-if="isA15_1"
      class="gt-checklist-table__eqcr-ref"
      type="info"
      show-icon
      :closable="false"
      title="EQCR 只读引用"
    >
      EQCR「持续经营」Tab 只读引用本底稿
      <strong>A15-1-conclusion</strong>
      调查结论；请先完成本节填写。
      <router-link
        v-if="eqcrWorkbenchPath"
        class="gt-checklist-table__eqcr-link"
        :to="eqcrWorkbenchPath"
      >
        打开 EQCR 工作台 →
      </router-link>
    </el-alert>

    <!-- ─── 主体: 左侧导航 + 右侧表格 ─── -->
    <div class="gt-checklist-table__body">
      <!-- 左侧目录导航（展示型子组件 GtChecklistNav） -->
      <GtChecklistNav
        :nav-items="navItems"
        :active-section="activeSection"
        :active-objective="activeObjective"
        :show-objectives="isA17_5"
        @select="selectSection"
        @select-objective="selectObjective"
      />

      <!-- 右侧：审计目标追溯面板 (A17-5 专用，当选中"审计目标"section 时) -->
      <GtChecklistObjectivePanel
        v-if="isObjectiveSection"
        :responses="responses"
        :all-item-ids="allActionableItemIds"
        @locate-program="locateProgram"
      />

      <!-- 右侧核对表主体（展示型子组件 GtChecklistSection） -->
      <GtChecklistSection
        v-else
        :current-section="currentSection"
        :filtered-current-items="filteredCurrentItems"
        :section-applicable="currentSection ? isSectionApplicable(currentSection.id) : true"
        :readonly="readonly"
        :has-standard-ref="template?.has_standard_ref !== false"
        :allow-custom-items="!!template?.allow_custom_items"
        :conclusion-mode="isA17_5 ? 'completion' : 'disclosure'"
        :project-id="projectId"
        :get-response="getResponse"
        :get-conclusion-class="getConclusionClass"
        :sign-hint-for-item="signHintForItem"
        :is-expanded="isExpanded"
        :toggle-expand="toggleExpand"
        :update-conclusion="updateConclusion"
        :update-remark="updateRemark"
        :update-wp-ref="updateWpRef"
        :apply-sign-hint="applySignHint"
        :add-custom-item="addCustomItem"
        :update-item-content="updateItemContent"
        :polish-with-l-l-m="polishWithLLM"
        :item-objectives="isA17_5 ? getItemObjectives : undefined"
        :conclusion-item="conclusionItem"
      />
    </div>

    <!-- ─── 章节适用性弹窗 ─── -->
    <el-dialog
      v-model="showApplicabilityDialog"
      title="章节适用性设置"
      width="600px"
      :close-on-click-modal="false"
    >
      <p class="applicability-dialog__hint">
        请根据本项目实际情况勾选适用的章节。不适用的章节将灰显折叠，节省操作时间。
      </p>
      <div class="applicability-dialog__list">
        <div
          v-for="entry in toc"
          :key="entry.id"
          class="applicability-dialog__item"
        >
          <el-checkbox
            :model-value="isSectionApplicable(entry.id)"
            :disabled="readonly"
            @change="() => toggleSectionApplicability(entry.id)"
          >
            {{ entry.title }}
          </el-checkbox>
        </div>
      </div>
      <template #footer>
        <el-button @click="showApplicabilityDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmApplicability">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gt-checklist-table {
  display: flex;
  flex-direction: column;
  height: 100%;
  font-family: var(--gt-font-family);
  background: var(--gt-color-bg-white);
}

/* ─── Header ─── */
.gt-checklist-table__eqcr-ref {
  margin: 0 16px 12px;
}

.gt-checklist-table__eqcr-link {
  margin-left: 8px;
  color: var(--el-color-primary);
  text-decoration: none;
}

.gt-checklist-table__eqcr-link:hover {
  text-decoration: underline;
}

.gt-checklist-table__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gt-color-border);
  background: var(--gt-color-primary-bg);
}

.gt-checklist-table__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--gt-font-size-lg);
  font-weight: 600;
  color: var(--gt-color-primary);
}

.gt-checklist-table__icon {
  font-size: 20px;
}

.gt-checklist-table__progress {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gt-checklist-table__saving {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}

.gt-checklist-table__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* ─── Body layout ─── */
.gt-checklist-table__body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ─── Nav sidebar 样式已迁入 GtChecklistNav.vue ─── */

/* ─── 右侧主体（主内容区/表头/列宽/条目/子项/空态）样式已迁入 GtChecklistSection.vue ─── */

/* ─── Applicability dialog ─── */
.applicability-dialog__hint {
  margin-bottom: 16px;
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
}

.applicability-dialog__list {
  max-height: 400px;
  overflow-y: auto;
}

.applicability-dialog__item {
  padding: 6px 0;
  border-bottom: 1px solid var(--gt-color-border-lighter);
}

/* ─── select/input 列宽与 cell-display 样式已迁入 GtChecklistSection.vue ─── */

/* ─── Progress bar override ─── */
.gt-checklist-table__header :deep(.el-progress-bar__inner) {
  background: var(--gt-color-primary);
}

/* ─── Toolbar ─── */
.gt-checklist-table__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--gt-color-border-light);
  background: var(--gt-color-bg-white);
}

.toolbar__search {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar__search-count {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}

.toolbar__filters {
  margin-left: auto;
}

.toolbar__batch {
  flex-shrink: 0;
}

/* ─── Search results panel ─── */
.gt-checklist-table__search-results {
  border-bottom: 1px solid var(--gt-color-border);
  background: var(--gt-color-bg-elevated);
  max-height: 240px;
  overflow-y: auto;
}

.search-results__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-secondary);
  border-bottom: 1px solid var(--gt-color-border-light);
  position: sticky;
  top: 0;
  background: var(--gt-color-bg-elevated);
}

.search-results__list {
  padding: 4px 0;
}

.search-results__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
  transition: background var(--gt-transition-fast);
}

.search-results__item:hover {
  background: var(--gt-color-primary-bg);
}

.search-result__section {
  flex-shrink: 0;
  color: var(--gt-color-primary);
  font-weight: 500;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-result__ref {
  flex-shrink: 0;
  color: var(--gt-color-text-tertiary);
  width: 80px;
}

.search-result__content {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--gt-color-text);
}

/* ─── Search highlight ─── */
:deep(.search-highlight) {
  background: #fff3cd;
  color: inherit;
  padding: 0 1px;
  border-radius: 2px;
}

/* ─── Legend popover ─── */
.legend-content {
  font-size: 12px;
  line-height: 1.8;
}
.legend-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 2px 0;
}
.legend-tag {
  display: inline-block;
  min-width: 32px;
  text-align: center;
  font-weight: 700;
  font-size: 11px;
  padding: 1px 4px;
  border-radius: 3px;
}
.tag-y { background: #e6f7e6; color: #2d8a2d; }
.tag-xi { background: #fff8e6; color: #996b00; }
.tag-xw { background: #fde8e8; color: #c53030; }
.tag-na { background: #f5f5f5; color: #666; }

.gt-checklist-table__no-banner {
  margin: 0 12px 8px;
}
.gt-checklist-table__no-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.5;
}
</style>
