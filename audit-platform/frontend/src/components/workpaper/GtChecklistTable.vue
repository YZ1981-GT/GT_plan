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
  projectId.value ? `/projects/${projectId.value}/eqcr/projects/${projectId.value}` : '',
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
    case 'Y': return 'conclusion-yes'
    case 'X/I': return 'conclusion-xi'
    case 'X/W': return 'conclusion-xw'
    case 'N/A': return 'conclusion-na'
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
        @select="selectSection"
      />

      <!-- 右侧核对表主体（展示型子组件 GtChecklistSection） -->
      <GtChecklistSection
        :current-section="currentSection"
        :filtered-current-items="filteredCurrentItems"
        :section-applicable="currentSection ? isSectionApplicable(currentSection.id) : true"
        :readonly="readonly"
        :get-response="getResponse"
        :get-conclusion-class="getConclusionClass"
        :sign-hint-for-item="signHintForItem"
        :is-expanded="isExpanded"
        :toggle-expand="toggleExpand"
        :update-conclusion="updateConclusion"
        :update-remark="updateRemark"
        :update-wp-ref="updateWpRef"
        :apply-sign-hint="applySignHint"
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
</style>
