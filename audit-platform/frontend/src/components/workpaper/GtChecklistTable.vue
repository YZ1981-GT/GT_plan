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

// ─── Types ───
interface ChecklistChild {
  id: string
  content: string
  standard_ref: string
}

interface ChecklistItem {
  id: string
  type: 'actionable' | 'guidance' | 'header'
  standard_ref: string
  content: string
  children: ChecklistChild[]
}

interface ChecklistSection {
  id: string
  title: string
  items: ChecklistItem[]
}

interface TocEntry {
  id: string
  title: string
  applicable: boolean | null
}

interface ChecklistStats {
  total_actionable: number
  total_guidance: number
  total_sections: number
}

interface ChecklistTemplate {
  wp_code: string
  title: string
  sections: ChecklistSection[]
  toc: TocEntry[]
  stats: ChecklistStats
}

interface ResponseData {
  conclusion: string | null
  remark: string | null
  wp_ref: string | null
}

interface ChecklistHtmlData {
  template: ChecklistTemplate
  responses: Record<string, ResponseData>
}

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

// ─── State ───
const activeSection = ref('')
const expandedItems = ref<Set<string>>(new Set())
const responses = ref<Record<string, ResponseData>>({})
const sectionApplicability = ref<Record<string, boolean>>({})
const showApplicabilityDialog = ref(false)
const saving = ref(false)
const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const pendingChanges = ref<Set<string>>(new Set())

// ─── Search state (Task 8) ───
const searchQuery = ref('')
const searchActive = ref(false)

// ─── Filter state (Task 10) ───
type FilterMode = 'all' | 'unfilled' | 'inapplicable'
const filterMode = ref<FilterMode>('all')

// ─── Active cell state (click-to-activate editing) ───
const activeCell = ref('')

function activateCell(itemId: string, field: string) {
  if (props.readonly) return
  activeCell.value = `${itemId}:${field}`
}

// ─── Computed: Template data ───
const template = computed(() => props.htmlData?.template)
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

function isSectionApplicable(sectionId: string): boolean {
  if (sectionId in sectionApplicability.value) {
    return sectionApplicability.value[sectionId]
  }
  return true // default applicable
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

// ─── Computed: Search results (Task 8) ───
interface SearchMatch {
  sectionId: string
  sectionTitle: string
  item: ChecklistItem
  matchField: 'content' | 'standard_ref' | 'child'
}

const searchResults = computed<SearchMatch[]>(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return []
  const results: SearchMatch[] = []
  for (const section of sections.value) {
    for (const item of section.items) {
      if (item.type !== 'actionable') continue
      if (item.content.toLowerCase().includes(q) || item.standard_ref.toLowerCase().includes(q)) {
        results.push({ sectionId: section.id, sectionTitle: section.title, item, matchField: item.standard_ref.toLowerCase().includes(q) ? 'standard_ref' : 'content' })
      } else if (item.children?.some(c => c.content.toLowerCase().includes(q) || c.standard_ref.toLowerCase().includes(q))) {
        results.push({ sectionId: section.id, sectionTitle: section.title, item, matchField: 'child' })
      }
    }
  }
  return results
})

// ─── Computed: Filtered items for current section (Task 10) ───
const filteredCurrentItems = computed(() => {
  if (!currentSection.value) return []
  const items = currentSection.value.items
  if (filterMode.value === 'all') return items
  return items.filter(item => {
    if (item.type === 'header') return true // always show headers for context
    if (item.type !== 'actionable') return false
    const resp = responses.value[item.id]
    if (filterMode.value === 'unfilled') {
      return !resp?.conclusion
    }
    if (filterMode.value === 'inapplicable') {
      return resp?.conclusion === 'N/A'
    }
    return true
  })
})

// ─── Methods: Search (Task 8) ───
function highlightText(text: string, query: string): string {
  if (!query) return text
  const q = query.trim()
  if (!q) return text
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(${escaped})`, 'gi')
  return text.replace(re, '<mark class="search-highlight">$1</mark>')
}

function jumpToSearchResult(result: SearchMatch) {
  activeSection.value = result.sectionId
  searchActive.value = false
  // Expand the item's children if match was in child
  if (result.matchField === 'child') {
    expandedItems.value.add(result.item.id)
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchActive.value = false
}

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

// ─── Methods: Response handling ───
function getResponse(itemId: string): ResponseData {
  if (!responses.value[itemId]) {
    responses.value[itemId] = { conclusion: null, remark: null, wp_ref: null }
  }
  return responses.value[itemId]
}

function updateConclusion(itemId: string, value: string | null) {
  if (props.readonly) return
  const resp = getResponse(itemId)
  resp.conclusion = value || null
  pendingChanges.value.add(itemId)
  scheduleSave()
}

function updateRemark(itemId: string, value: string) {
  if (props.readonly) return
  const resp = getResponse(itemId)
  resp.remark = value || null
  pendingChanges.value.add(itemId)
  scheduleSave()
}

function updateWpRef(itemId: string, value: string) {
  if (props.readonly) return
  const resp = getResponse(itemId)
  resp.wp_ref = value || null
  pendingChanges.value.add(itemId)
  scheduleSave()
}

// ─── Methods: Autosave (debounce 2s) ───
function scheduleSave() {
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
  }
  saveTimer.value = setTimeout(() => {
    doSave()
  }, 2000)
}

async function doSave() {
  if (pendingChanges.value.size === 0) return
  if (!projectId.value) {
    console.warn('[GtChecklistTable] projectId 为空，跳过保存')
    return
  }
  saving.value = true
  const items: Array<{ item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null }> = []

  for (const itemId of pendingChanges.value) {
    const resp = responses.value[itemId]
    if (resp) {
      items.push({
        item_id: itemId,
        conclusion: resp.conclusion,
        remark: resp.remark,
        wp_ref: resp.wp_ref,
      })
    }
  }

  // Also include section applicability changes
  for (const [sectionId, applicable] of Object.entries(sectionApplicability.value)) {
    const tocItemId = `TOC-${sectionId}`
    items.push({
      item_id: tocItemId,
      conclusion: applicable ? 'Y' : 'N',
      remark: null,
      wp_ref: null,
    })
  }

  if (items.length === 0) {
    pendingChanges.value.clear()
    saving.value = false
    return
  }

  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: projectId.value,
      items,
    })
    pendingChanges.value.clear()
    emit('save')
  } catch (err: any) {
    // 忽略因页面导航导致的请求取消
    const msg = err?.message || ''
    if (msg === 'canceled' || err?.code === 'ERR_CANCELED') return
    ElMessage.error('保存失败: ' + msg)
  } finally {
    saving.value = false
  }
}

// ─── Methods: Applicability dialog ───
function openApplicabilityDialog() {
  showApplicabilityDialog.value = true
}

// ─── Computed: dirty state (for save/reset buttons) ───
const hasDirtyData = computed(() => {
  // 当前响应数据与初始数据不同则 dirty
  const initial = props.htmlData?.responses || {}
  for (const [key, resp] of Object.entries(responses.value)) {
    if (key.startsWith('TOC-')) continue
    const orig = initial[key]
    if (!orig && resp.conclusion) return true
    if (orig && orig.conclusion !== resp.conclusion) return true
    if (orig && orig.remark !== resp.remark) return true
    if (orig && orig.wp_ref !== resp.wp_ref) return true
  }
  return pendingChanges.value.size > 0
})

// ─── Methods: Manual save / reset ───
async function handleManualSave() {
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
    saveTimer.value = null
  }
  // 把所有有值的条目都加入 pending（全量保存）
  for (const [key, resp] of Object.entries(responses.value)) {
    if (resp.conclusion || resp.remark || resp.wp_ref) {
      pendingChanges.value.add(key)
    }
  }
  await doSave()
  ElMessage.success('保存成功')
}

function handleReset() {
  // 恢复到 props 中的初始数据
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
    saveTimer.value = null
  }
  pendingChanges.value.clear()
  initFromProps()
  ElMessage.info('已恢复到上次保存的状态')
}

function toggleSectionApplicability(sectionId: string) {
  if (props.readonly) return
  const current = sectionApplicability.value[sectionId]
  sectionApplicability.value[sectionId] = current === undefined ? false : !current
}

function confirmApplicability() {
  showApplicabilityDialog.value = false
  // Mark all applicability changes as pending
  for (const sectionId of Object.keys(sectionApplicability.value)) {
    pendingChanges.value.add(`TOC-${sectionId}`)
  }
  scheduleSave()
}

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
    case 'Y': return 'conclusion-yes'
    case 'X/I': return 'conclusion-xi'
    case 'X/W': return 'conclusion-xw'
    case 'N/A': return 'conclusion-na'
    default: return ''
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
  // Show applicability dialog on first open if no applicability data exists
  const hasApplicabilityData = Object.keys(sectionApplicability.value).length > 0
  if (!hasApplicabilityData && toc.value.length > 0) {
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
  if (saveTimer.value) {
    clearTimeout(saveTimer.value)
    saveTimer.value = null
  }
  const hasRealChanges = [...pendingChanges.value].some(id => !id.startsWith('TOC-'))
  if (hasRealChanges) {
    const items: Array<{ item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null }> = []
    for (const itemId of pendingChanges.value) {
      const resp = responses.value[itemId]
      if (resp) {
        items.push({ item_id: itemId, conclusion: resp.conclusion, remark: resp.remark, wp_ref: resp.wp_ref })
      }
    }
    for (const [sectionId, applicable] of Object.entries(sectionApplicability.value)) {
      items.push({ item_id: `TOC-${sectionId}`, conclusion: applicable ? 'Y' : 'N', remark: null, wp_ref: null })
    }
    if (items.length > 0 && projectId.value) {
      const payload = JSON.stringify({ project_id: projectId.value, items })
      const url = `/api/workpapers/${props.wpId}/checklist-responses`
      // sendBeacon 可靠发送（页面卸载后请求仍能完成，不会被 cancel）
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }))
      }
    }
  }
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
          <div class="legend-item"><span class="legend-tag tag-y">Y</span> 适用于被审计单位财务报表并已在财务报表中披露</div>
          <div class="legend-item"><span class="legend-tag tag-xi">X/I</span> 适用但不重大，未在财务报表中披露</div>
          <div class="legend-item"><span class="legend-tag tag-xw">X/W</span> 适用且重大，未在财务报表中披露，已在另附工作底稿说明原因</div>
          <div class="legend-item"><span class="legend-tag tag-na">N/A</span> 不适用于被审计单位财务报表</div>
        </div>
      </el-popover>
    </div>

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

    <!-- ─── 主体: 左侧导航 + 右侧表格 ─── -->
    <div class="gt-checklist-table__body">
      <!-- 左侧目录导航 -->
      <div class="gt-checklist-table__nav">
        <div class="gt-checklist-table__nav-title">目录导航</div>
        <div class="gt-checklist-table__nav-list">
          <div
            v-for="item in navItems"
            :key="item.id"
            class="gt-checklist-table__nav-item"
            :class="{
              'is-active': activeSection === item.id,
              'is-completed': item.completed,
              'is-inapplicable': !item.applicable,
            }"
            @click="selectSection(item.id)"
          >
            <span class="nav-item__title">{{ item.title }}</span>
            <span v-if="item.completed" class="nav-item__check">✓</span>
            <span v-else-if="item.progress.total > 0" class="nav-item__count">
              {{ item.progress.filled }}/{{ item.progress.total }}
            </span>
            <span v-if="!item.applicable" class="nav-item__na">不适用</span>
          </div>
        </div>
      </div>

      <!-- 右侧核对表主体 -->
      <div class="gt-checklist-table__main">
        <template v-if="currentSection">
          <!-- 章节标题 -->
          <div class="gt-checklist-table__section-header">
            <span>§ {{ currentSection.title }}</span>
            <el-tag
              v-if="!isSectionApplicable(currentSection.id)"
              type="info"
              size="small"
            >
              不适用
            </el-tag>
          </div>

          <!-- 表头 -->
          <div class="gt-checklist-table__table-header">
            <div class="col-ref">准则索引号</div>
            <div class="col-content">核对条目</div>
            <div class="col-conclusion">适用</div>
            <div class="col-remark">备注</div>
            <div class="col-wpref">底稿索引</div>
          </div>

          <!-- 条目列表 -->
          <div
            class="gt-checklist-table__items"
            :class="{ 'is-inapplicable-section': !isSectionApplicable(currentSection.id) }"
          >
            <template v-for="item in filteredCurrentItems" :key="item.id">
              <!-- 小节标题 (header) -->
              <div v-if="item.type === 'header'" class="gt-checklist-table__header-row">
                <span class="header-row__text">{{ item.content }}</span>
              </div>

              <!-- 主条目 (actionable) -->
              <div
                v-else-if="item.type === 'actionable'"
                class="gt-checklist-table__item-row"
                :class="getConclusionClass(getResponse(item.id).conclusion)"
              >
                <div class="col-ref">
                  <span class="item-ref__text">{{ item.standard_ref }}</span>
                </div>
                <div class="col-content">
                  <div class="item-content__wrapper">
                    <span
                      v-if="item.children && item.children.length > 0"
                      class="item-content__expand"
                      @click="toggleExpand(item.id)"
                    >
                      {{ isExpanded(item.id) ? '▼' : '▶' }}
                    </span>
                    <span class="item-content__text">{{ item.content }}</span>
                  </div>
                </div>
                <div class="col-conclusion" @click.stop="activateCell(item.id, 'conclusion')">
                  <el-select
                    v-if="activeCell === `${item.id}:conclusion`"
                    :model-value="getResponse(item.id).conclusion || ''"
                    placeholder="—"
                    size="small"
                    :disabled="readonly"
                    automatic-dropdown
                    @change="(val: string) => { updateConclusion(item.id, val || null); activeCell = '' }"
                    @visible-change="(visible: boolean) => { if (!visible) activeCell = '' }"
                  >
                    <el-option label="Y" value="Y">
                      <el-tooltip content="适用并已在财务报表中披露" placement="left" :show-after="300">
                        <span>Y</span>
                      </el-tooltip>
                    </el-option>
                    <el-option label="X/I" value="X/I">
                      <el-tooltip content="适用但不重大，未在财务报表中披露" placement="left" :show-after="300">
                        <span>X/I</span>
                      </el-tooltip>
                    </el-option>
                    <el-option label="X/W" value="X/W">
                      <el-tooltip content="适用且重大，未在报表中披露，已在另附工作底稿说明原因" placement="left" :show-after="300">
                        <span>X/W</span>
                      </el-tooltip>
                    </el-option>
                    <el-option label="N/A" value="N/A">
                      <el-tooltip content="不适用于被审计单位财务报表" placement="left" :show-after="300">
                        <span>N/A</span>
                      </el-tooltip>
                    </el-option>
                  </el-select>
                  <span v-else class="cell-display cell-conclusion" :class="{ 'cell-empty': !getResponse(item.id).conclusion }">
                    {{ getResponse(item.id).conclusion || '—' }}
                  </span>
                </div>
                <div class="col-remark" @click.stop="activateCell(item.id, 'remark')">
                  <el-input
                    v-if="activeCell === `${item.id}:remark`"
                    :model-value="getResponse(item.id).remark || ''"
                    size="small"
                    placeholder="备注"
                    :disabled="readonly"
                    @change="(val: string) => updateRemark(item.id, val)"
                    @blur="activeCell = ''"
                  />
                  <span v-else class="cell-display" :class="{ 'cell-empty': !getResponse(item.id).remark }">
                    {{ getResponse(item.id).remark || '备注' }}
                  </span>
                </div>
                <div class="col-wpref" @click.stop="activateCell(item.id, 'wpref')">
                  <el-input
                    v-if="activeCell === `${item.id}:wpref`"
                    :model-value="getResponse(item.id).wp_ref || ''"
                    size="small"
                    placeholder="索引"
                    :disabled="readonly"
                    @change="(val: string) => updateWpRef(item.id, val)"
                    @blur="activeCell = ''"
                  />
                  <span v-else class="cell-display" :class="{ 'cell-empty': !getResponse(item.id).wp_ref }">
                    {{ getResponse(item.id).wp_ref || '索引' }}
                  </span>
                </div>
              </div>

              <!-- 提示性子项 (children of actionable, collapsed by default) -->
              <div
                v-if="item.type === 'actionable' && item.children && item.children.length > 0 && isExpanded(item.id)"
                class="gt-checklist-table__children"
              >
                <div
                  v-for="child in item.children"
                  :key="child.id"
                  class="gt-checklist-table__child-row"
                >
                  <div class="col-ref child-ref">{{ child.standard_ref }}</div>
                  <div class="col-content child-content">{{ child.content }}</div>
                  <div class="col-conclusion" />
                  <div class="col-remark" />
                  <div class="col-wpref" />
                </div>
              </div>
            </template>
          </div>
        </template>

        <div v-else class="gt-checklist-table__empty">
          <p>请从左侧目录选择一个章节</p>
        </div>
      </div>
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

/* ─── Nav sidebar ─── */
.gt-checklist-table__nav {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid var(--gt-color-border);
  display: flex;
  flex-direction: column;
  background: var(--gt-color-bg-elevated);
}

.gt-checklist-table__nav-title {
  padding: 12px 16px;
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  border-bottom: 1px solid var(--gt-color-border-light);
}

.gt-checklist-table__nav-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.gt-checklist-table__nav-item {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  transition: background var(--gt-transition-fast);
  gap: 6px;
}

.gt-checklist-table__nav-item:hover {
  background: var(--gt-color-primary-bg);
}

.gt-checklist-table__nav-item.is-active {
  background: var(--gt-color-primary-bg);
  border-left: 3px solid var(--gt-color-primary);
  font-weight: 500;
}

.gt-checklist-table__nav-item.is-completed .nav-item__title {
  color: var(--gt-color-success);
}

.gt-checklist-table__nav-item.is-inapplicable {
  opacity: 0.5;
}

.nav-item__title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-item__check {
  color: var(--gt-color-success);
  font-weight: 700;
}

.nav-item__count {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}

.nav-item__na {
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
  background: var(--gt-color-border-light);
  padding: 1px 4px;
  border-radius: var(--gt-radius-xs);
}

/* ─── Main content area ─── */
.gt-checklist-table__main {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.gt-checklist-table__section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--gt-font-size-lg);
  font-weight: 600;
  color: var(--gt-color-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--gt-color-primary);
}

/* ─── Table header ─── */
.gt-checklist-table__table-header {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 2px solid var(--gt-color-border);
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  position: sticky;
  top: 0;
  background: var(--gt-color-bg-white);
  z-index: 1;
}

/* ─── Column widths ─── */
.col-ref { width: 100px; min-width: 100px; padding: 0 8px; }
.col-content { flex: 1; padding: 0 8px; }
.col-conclusion { width: 80px; min-width: 80px; padding: 0 4px; }
.col-remark { width: 140px; min-width: 140px; padding: 0 4px; }
.col-wpref { width: 90px; min-width: 90px; padding: 0 4px; }

/* ─── Items container ─── */
.gt-checklist-table__items {
  /* items styling */
}

.gt-checklist-table__items.is-inapplicable-section {
  opacity: 0.5;
  pointer-events: none;
}

/* ─── Header row (section subtitle) ─── */
.gt-checklist-table__header-row {
  padding: 10px 8px;
  font-weight: 700;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  border-bottom: 1px solid var(--gt-color-border-light);
  background: var(--gt-bg-subtle);
}

.header-row__text {
  padding-left: 108px; /* align with content column */
}

/* ─── Actionable item row ─── */
.gt-checklist-table__item-row {
  display: flex;
  align-items: flex-start;
  padding: 6px 0;
  border-bottom: 1px solid var(--gt-color-border-lighter);
  transition: background var(--gt-transition-fast);
}

.gt-checklist-table__item-row:hover {
  background: var(--gt-color-bg-purple-hover);
}

/* Color coding */
.gt-checklist-table__item-row.conclusion-yes {
  background: #e6f7e6;
}
.gt-checklist-table__item-row.conclusion-xi {
  background: #fff8e6;
}
.gt-checklist-table__item-row.conclusion-xw {
  background: #fde8e8;
}
.gt-checklist-table__item-row.conclusion-na {
  background: #f5f5f5;
}

.item-ref__text {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.4;
  word-break: break-all;
}

.item-content__wrapper {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.item-content__expand {
  cursor: pointer;
  color: var(--gt-color-primary);
  font-size: 11px;
  margin-top: 2px;
  user-select: none;
  flex-shrink: 0;
}

.item-content__text {
  font-size: var(--gt-font-size-sm);
  line-height: 1.5;
  color: var(--gt-color-text);
}

/* ─── Children (guidance sub-items) ─── */
.gt-checklist-table__children {
  padding-left: 108px; /* align under content column */
  padding-bottom: 4px;
  border-bottom: 1px solid var(--gt-color-border-lighter);
}

.gt-checklist-table__child-row {
  display: flex;
  align-items: flex-start;
  padding: 4px 8px;
  background: var(--gt-bg-subtle);
  border-left: 3px solid var(--gt-color-border-purple-light);
  margin: 2px 0;
  border-radius: 0 var(--gt-radius-xs) var(--gt-radius-xs) 0;
}

.child-ref {
  width: 80px;
  min-width: 80px;
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
}

.child-content {
  flex: 1;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.5;
}

/* ─── Empty state ─── */
.gt-checklist-table__empty {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
  color: var(--gt-color-text-tertiary);
}

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

/* ─── Override Element Plus select width ─── */
.col-conclusion :deep(.el-select) {
  width: 100%;
}

.col-remark :deep(.el-input) {
  width: 100%;
}

.col-wpref :deep(.el-input) {
  width: 100%;
}

/* ─── Click-to-activate cell display ─── */
.cell-display {
  display: block;
  padding: 2px 6px;
  min-height: 22px;
  line-height: 20px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text);
  cursor: pointer;
  border: 1px dashed transparent;
  border-radius: var(--gt-radius-xs);
  transition: border-color var(--gt-transition-fast);
}

.cell-display:hover {
  border-color: var(--gt-color-border-purple-light);
}

.cell-display.cell-empty {
  color: var(--gt-color-text-tertiary);
}

.cell-conclusion {
  text-align: center;
  font-weight: 500;
}

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
</style>
