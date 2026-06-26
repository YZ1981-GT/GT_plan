<!--
  GtA115DisclosureChecklist.vue — A1-15 企业会计准则财务报表列报及披露核对表

  专属组件：双模式渲染（结构化 HTML + Word 编辑）
  - 35 章节导航 + 卡片式核查表 + 进度可视化 + CAS 准则索引号
  - 科目跳转联动（Cross_Reference_Map）
  - 自加载模式（仅需 wpId）

  Task 4.1: 顶层编排组件
-->
<template>
  <div class="gt-a115-disclosure-checklist">
    <!-- ─── 骨架屏（loading 态）─── -->
    <el-skeleton v-if="loading" :rows="12" animated />

    <!-- ─── 错误态 + 重试 ─── -->
    <div v-else-if="error" class="gt-a115-disclosure-checklist__error">
      <el-icon :size="48" color="#f56c6c"><WarningFilled /></el-icon>
      <p class="gt-a115-disclosure-checklist__error-msg">{{ error }}</p>
      <el-button type="primary" @click="loadData()">重试</el-button>
    </div>

    <!-- ─── 主内容 ─── -->
    <template v-else-if="template">
      <!-- 顶部工具栏 -->
      <div class="gt-a115-disclosure-checklist__toolbar">
        <el-tooltip
          :disabled="docxAvailable"
          content="OnlyOffice 服务不可用，Word 编辑暂时无法使用"
          placement="bottom"
        >
          <el-segmented
            v-model="activeMode"
            :options="modeOptions"
            size="default"
          />
        </el-tooltip>

        <el-input
          v-model="searchQuery"
          placeholder="搜索条目..."
          :prefix-icon="Search"
          clearable
          class="gt-a115-disclosure-checklist__search"
        />

        <el-select
          v-model="conclusionFilter"
          placeholder="筛选"
          class="gt-a115-disclosure-checklist__filter"
        >
          <el-option label="全部" value="all" />
          <el-option label="已填" value="filled" />
          <el-option label="未填" value="unfilled" />
          <el-option label="Y" value="Y" />
          <el-option label="N" value="N" />
          <el-option label="NA" value="NA" />
        </el-select>

        <span class="gt-a115-disclosure-checklist__save-indicator">
          <template v-if="saving">
            <el-icon class="is-loading"><Loading /></el-icon>
            保存中...
          </template>
          <template v-else-if="lastSavedAt">
            ○ 已保存 {{ savedAgoText }}
          </template>
        </span>
      </div>

      <!-- 全局进度环 + 统计 -->
      <div class="gt-a115-disclosure-checklist__progress-bar">
        <el-progress
          type="circle"
          :percentage="progressPercent"
          :width="56"
          :stroke-width="5"
          color="#7c3aed"
        />
        <div class="gt-a115-disclosure-checklist__progress-stats">
          <span class="gt-a115-disclosure-checklist__stat gt-a115-disclosure-checklist__stat--y">
            Y:{{ globalProgress.y }}
          </span>
          <span class="gt-a115-disclosure-checklist__stat gt-a115-disclosure-checklist__stat--n">
            N:{{ globalProgress.n }}
          </span>
          <span class="gt-a115-disclosure-checklist__stat gt-a115-disclosure-checklist__stat--na">
            NA:{{ globalProgress.na }}
          </span>
          <span class="gt-a115-disclosure-checklist__stat gt-a115-disclosure-checklist__stat--unfilled">
            未填:{{ globalProgress.total - globalProgress.filled }}
          </span>
          <span class="gt-a115-disclosure-checklist__stat gt-a115-disclosure-checklist__stat--total">
            总计:{{ globalProgress.total }}
          </span>
        </div>
      </div>

      <!-- HTML 结构化视图 -->
      <div v-if="activeMode === 'html'" class="gt-a115-disclosure-checklist__html-view">
        <div class="gt-a115-disclosure-checklist__layout">
          <!-- 左侧章节导航 (Task 4.2) -->
          <aside class="gt-a115-disclosure-checklist__nav">
            <div class="gt-a115-disclosure-checklist__nav-list">
              <div
                v-for="section in template.sections"
                :key="section.id"
                :class="[
                  'gt-a115-disclosure-checklist__nav-item',
                  { 'gt-a115-disclosure-checklist__nav-item--active': activeSectionId === section.id },
                  { 'gt-a115-disclosure-checklist__nav-item--na': responses.toc_applicability[section.id] === false },
                ]"
                @click="scrollToSection(section.id)"
              >
                <span class="gt-a115-disclosure-checklist__nav-icon">
                  {{ getSectionStatusIcon(section.id) }}
                </span>
                <span class="gt-a115-disclosure-checklist__nav-title">{{ section.title }}</span>
                <span class="gt-a115-disclosure-checklist__nav-progress">
                  ({{ sectionProgress(section.id).filled }}/{{ sectionProgress(section.id).total }})
                </span>
                <el-switch
                  v-if="!props.readonly"
                  :model-value="responses.toc_applicability[section.id] !== false"
                  size="small"
                  class="gt-a115-disclosure-checklist__nav-switch"
                  @click.stop
                  @change="(val: any) => setTocApplicability(section.id, !!val)"
                />
              </div>
            </div>
            <!-- 图例 -->
            <div class="gt-a115-disclosure-checklist__nav-legend">
              <span>■ 已完成</span>
              <span>◐ 进行中</span>
              <span>□ 未开始</span>
              <span>▧ 不适用</span>
            </div>
          </aside>

          <!-- 右侧核查表 (Task 4.3) -->
          <main ref="bodyContainerRef" class="gt-a115-disclosure-checklist__body">
            <div
              v-for="section in filteredSections"
              :key="section.id"
              :data-section-id="section.id"
              class="gt-a115-disclosure-checklist__section-sentinel"
            >
              <!-- Lazy rendering: only render content if section is visible -->
              <template v-if="isSectionVisible(section.id)">
                <!-- Section header with progress -->
                <div class="gt-a115-disclosure-checklist__section-header">
                  <div class="gt-a115-disclosure-checklist__section-header-top">
                    <span class="gt-a115-disclosure-checklist__section-title">{{ section.title }}</span>
                    <span
                      v-if="crossRefMap[section.id]"
                      class="gt-a115-disclosure-checklist__section-suggested-ref"
                    >
                      建议关联: {{ crossRefMap[section.id] }}
                    </span>
                  </div>
                  <div class="gt-a115-disclosure-checklist__section-progress">
                    <el-progress
                      :percentage="getSectionPercent(section.id)"
                      :stroke-width="8"
                      :show-text="false"
                      class="gt-a115-disclosure-checklist__section-progress-bar"
                    />
                    <span class="gt-a115-disclosure-checklist__section-progress-text">
                      {{ getSectionProgressText(section.id) }}
                    </span>
                  </div>
                </div>

                <!-- Items: actionable cards, header dividers -->
                <div
                  v-for="item in section.items"
                  :key="item.id"
                  :class="getItemClass(item)"
                >
                  <!-- Header type → divider -->
                  <div
                    v-if="item.type === 'header'"
                    class="gt-a115-disclosure-checklist__item-header"
                  >
                    {{ item.content }}
                  </div>

                  <!-- Actionable type → card -->
                  <div
                    v-else
                    :class="[
                      'gt-a115-disclosure-checklist__card',
                      getCardConclusionClass(item.id),
                    ]"
                  >
                    <div class="gt-a115-disclosure-checklist__card-top">
                      <span class="gt-a115-disclosure-checklist__card-cas-ref">
                        {{ item.standard_ref }}
                      </span>
                    </div>

                    <div class="gt-a115-disclosure-checklist__card-content">
                      {{ item.content }}
                    </div>

                    <div class="gt-a115-disclosure-checklist__card-actions">
                      <!-- Y/N/NA buttons -->
                      <div class="gt-a115-disclosure-checklist__card-buttons">
                        <el-button
                          :type="getItemConclusion(item.id) === 'Y' ? 'success' : 'default'"
                          :plain="getItemConclusion(item.id) !== 'Y'"
                          size="small"
                          :disabled="props.readonly"
                          @click="updateItemResponse(item.id, 'conclusion', getItemConclusion(item.id) === 'Y' ? null : 'Y')"
                        >
                          Y
                        </el-button>
                        <el-button
                          :type="getItemConclusion(item.id) === 'N' ? 'danger' : 'default'"
                          :plain="getItemConclusion(item.id) !== 'N'"
                          size="small"
                          :disabled="props.readonly"
                          @click="updateItemResponse(item.id, 'conclusion', getItemConclusion(item.id) === 'N' ? null : 'N')"
                        >
                          N
                        </el-button>
                        <el-button
                          :type="getItemConclusion(item.id) === 'NA' ? 'info' : 'default'"
                          :plain="getItemConclusion(item.id) !== 'NA'"
                          size="small"
                          :disabled="props.readonly"
                          @click="updateItemResponse(item.id, 'conclusion', getItemConclusion(item.id) === 'NA' ? null : 'NA')"
                        >
                          NA
                        </el-button>
                      </div>

                      <!-- Remark input (shown when conclusion is set) -->
                      <el-input
                        v-if="getItemConclusion(item.id)"
                        :model-value="getItemRemark(item.id)"
                        placeholder="备注"
                        size="small"
                        :disabled="props.readonly"
                        class="gt-a115-disclosure-checklist__card-remark"
                        @blur="(e: FocusEvent) => updateItemResponse(item.id, 'remark', (e.target as HTMLInputElement)?.value ?? '')"
                      />

                      <!-- wp_ref 科目跳转联动 (Task 4.4) -->
                      <div v-if="getItemConclusion(item.id)" class="gt-a115-disclosure-checklist__card-wpref">
                        <!-- Confirmed chip (if wp_ref is set) -->
                        <GtIndexChip
                          v-if="getItemWpRef(item.id)"
                          :value="getItemWpRef(item.id)"
                          :validate="true"
                          :context-project-id="projectId"
                        />
                        <!-- Suggested chip (if no wp_ref but crossRefMap has suggestion) -->
                        <span
                          v-else-if="crossRefMap[section.id]"
                          class="gt-a115-disclosure-checklist__wpref-chip gt-a115-disclosure-checklist__wpref-chip--suggested"
                          @click="updateItemResponse(item.id, 'wp_ref', crossRefMap[section.id])"
                        >
                          {{ crossRefMap[section.id] }}
                        </span>
                        <!-- Manual input -->
                        <el-autocomplete
                          v-if="!props.readonly"
                          :model-value="getItemWpRef(item.id)"
                          placeholder="索引号"
                          size="small"
                          :fetch-suggestions="queryWpCodes"
                          class="gt-a115-disclosure-checklist__wpref-input"
                          @select="(val: any) => updateItemResponse(item.id, 'wp_ref', val.value)"
                          @blur="(e: FocusEvent) => updateItemResponse(item.id, 'wp_ref', (e.target as HTMLInputElement)?.value ?? '')"
                        />
                      </div>
                    </div>

                    <!-- Guidance children (collapsible) -->
                    <div
                      v-if="item.children?.length"
                      class="gt-a115-disclosure-checklist__card-guidance"
                    >
                      <div
                        class="gt-a115-disclosure-checklist__guidance-toggle"
                        @click="toggleGuidance(item.id)"
                      >
                        <span class="gt-a115-disclosure-checklist__guidance-arrow">
                          {{ expandedGuidance.has(item.id) ? '▼' : '▶' }}
                        </span>
                        详细披露要求 ({{ item.children.length }})
                      </div>
                      <div
                        v-show="expandedGuidance.has(item.id)"
                        class="gt-a115-disclosure-checklist__guidance-list"
                      >
                        <div
                          v-for="child in item.children"
                          :key="child.id"
                          class="gt-a115-disclosure-checklist__guidance-item"
                        >
                          <span
                            v-if="child.standard_ref"
                            class="gt-a115-disclosure-checklist__guidance-ref"
                          >
                            {{ child.standard_ref }}
                          </span>
                          {{ child.content }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </template>

              <!-- Placeholder div when not visible (for scroll height estimation) -->
              <div
                v-else
                :style="{ height: section.items.length * 80 + 'px' }"
                class="gt-a115-disclosure-checklist__section-placeholder"
              />
            </div>
          </main>
        </div>
      </div>

      <!-- DOCX Word 编辑模式 (Task 4.5) -->
      <div v-else-if="activeMode === 'docx'" class="gt-a115-disclosure-checklist__docx-view">
        <template v-if="docxAvailable">
          <GtOnlyOfficeSheet
            :wp-id="props.wpId"
            sheet-name="A1-15"
            :project-id="projectId"
            :whole-workbook="true"
            :readonly="props.readonly"
            @fallback="onOnlyofficeFallback"
          />
        </template>
        <el-empty v-else description="Word 编辑不可用，请检查 OnlyOffice 服务状态" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtA115DisclosureChecklist — A1-15 企业会计准则财务报表列报及披露核对表
 *
 * 顶层编排组件：
 * - 双模式切换（el-segmented）
 * - onMounted 自加载 render-config
 * - 全局进度环 + Y/N/NA/未填统计
 * - 搜索 + 结论筛选
 * - "已保存 X秒前" 状态指示
 * - HTML 模式：左 SectionNav + 右 ChecklistBody
 * - DOCX 模式：GtOnlyOfficeSheet
 */
import { ref, computed, onMounted, onBeforeUnmount, watch, toRef } from 'vue'
import { useRoute } from 'vue-router'
import { Search, Loading, WarningFilled } from '@element-plus/icons-vue'
import GtOnlyOfficeSheet from '@/components/workpaper/GtOnlyOfficeSheet.vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useA115Checklist } from './composables/useA115Checklist'
import { useA115Navigation } from './composables/useA115Navigation'
import { api } from '@/services/apiProxy'

// ─── Component Options ──────────────────────────────────────────────────────

defineOptions({ name: 'GtA115DisclosureChecklist' })

// ─── Props ──────────────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
}>(), {
  readonly: false,
})

// ─── Route Context ──────────────────────────────────────────────────────────

const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')

// ─── Composables ────────────────────────────────────────────────────────────

const {
  template,
  responses,
  crossRefMap,
  loading,
  saving,
  lastSavedAt,
  error,
  searchQuery,
  conclusionFilter,
  loadData,
  updateItemResponse,
  setTocApplicability,
  flushPendingSave,
  globalProgress,
  sectionProgress,
  filteredSections,
} = useA115Checklist(toRef(props, 'wpId'), toRef(props, 'readonly'))

const bodyContainerRef = ref<HTMLElement | null>(null)

const {
  activeSectionId,
  visibleSections,
  initObserver,
  scrollToSection,
  isSectionVisible,
  destroyObserver,
} = useA115Navigation(filteredSections, bodyContainerRef)

// ─── Mode Options ───────────────────────────────────────────────────────────

const activeMode = ref<'html' | 'docx'>('html')
const docxAvailable = ref(true)

async function checkOnlyofficeHealth(): Promise<void> {
  try {
    const res = await api.get<any>('/api/workpapers/onlyoffice/health')
    docxAvailable.value = res?.healthy === true
  } catch {
    docxAvailable.value = false
  }
}

const modeOptions = computed(() => [
  { label: '结构化视图', value: 'html' },
  { label: 'Word 编辑', value: 'docx', disabled: !docxAvailable.value },
])

// ─── 已保存 X秒前 指示 ──────────────────────────────────────────────────────

const savedAgoText = ref('')
let savedAgoTimer: ReturnType<typeof setInterval> | null = null

function updateSavedAgo() {
  if (!lastSavedAt.value) {
    savedAgoText.value = ''
    return
  }
  const diff = Math.floor((Date.now() - lastSavedAt.value.getTime()) / 1000)
  if (diff < 60) {
    savedAgoText.value = `${diff}秒前`
  } else if (diff < 3600) {
    savedAgoText.value = `${Math.floor(diff / 60)}分钟前`
  } else {
    savedAgoText.value = `${Math.floor(diff / 3600)}小时前`
  }
}

// ─── 章节状态图标 ────────────────────────────────────────────────────────────

function getSectionStatusIcon(sectionId: string): string {
  // 不适用
  if (responses.value.toc_applicability[sectionId] === false) return '▧'
  const { filled, total } = sectionProgress(sectionId)
  // 已完成（total > 0 且全部填写）
  if (filled === total && total > 0) return '■'
  // 进行中
  if (filled > 0) return '◐'
  // 未开始
  return '□'
}

// ─── 进度百分比 ─────────────────────────────────────────────────────────────

const progressPercent = computed(() => {
  const { filled, total } = globalProgress.value
  if (total === 0) return 0
  return Math.round((filled / total) * 100)
})

// ─── Guidance 折叠/展开 ─────────────────────────────────────────────────────

const expandedGuidance = ref<Set<string>>(new Set())

function toggleGuidance(itemId: string): void {
  if (expandedGuidance.value.has(itemId)) {
    expandedGuidance.value.delete(itemId)
  } else {
    expandedGuidance.value.add(itemId)
  }
  // 触发 reactivity（Set 需要替换引用）
  expandedGuidance.value = new Set(expandedGuidance.value)
}

// ─── Card Helpers ───────────────────────────────────────────────────────────

function getItemConclusion(itemId: string): 'Y' | 'N' | 'NA' | null {
  return responses.value.items[itemId]?.conclusion ?? null
}

function getItemRemark(itemId: string): string {
  return responses.value.items[itemId]?.remark ?? ''
}

function getItemWpRef(itemId: string): string {
  return responses.value.items[itemId]?.wp_ref ?? ''
}

/** el-autocomplete 联想已有 wp_code 列表 */
function queryWpCodes(queryString: string, cb: (results: { value: string }[]) => void): void {
  // 从 crossRefMap 值 + 常用底稿编码生成建议列表
  const allCodes = [...new Set(Object.values(crossRefMap.value))]
  const results = queryString
    ? allCodes.filter(c => c.toLowerCase().includes(queryString.toLowerCase())).map(c => ({ value: c }))
    : allCodes.map(c => ({ value: c }))
  cb(results)
}

function getCardConclusionClass(itemId: string): string {
  const conclusion = getItemConclusion(itemId)
  switch (conclusion) {
    case 'Y':
      return 'gt-a115-disclosure-checklist__card--yes'
    case 'N':
      return 'gt-a115-disclosure-checklist__card--no'
    case 'NA':
      return 'gt-a115-disclosure-checklist__card--na'
    default:
      return 'gt-a115-disclosure-checklist__card--pending'
  }
}

function getItemClass(item: { type: string }): string {
  if (item.type === 'header') {
    return 'gt-a115-disclosure-checklist__item-wrapper gt-a115-disclosure-checklist__item-wrapper--header'
  }
  return 'gt-a115-disclosure-checklist__item-wrapper'
}

// ─── Section Progress Helpers ───────────────────────────────────────────────

function getSectionPercent(sectionId: string): number {
  const { filled, total } = sectionProgress(sectionId)
  if (total === 0) return 0
  return Math.round((filled / total) * 100)
}

function getSectionProgressText(sectionId: string): string {
  const { filled, total } = sectionProgress(sectionId)
  if (total === 0) return '无条目'

  // Count Y/N/NA for this section
  let y = 0, n = 0, na = 0
  const section = template.value?.sections.find((s) => s.id === sectionId)
  if (section) {
    for (const item of section.items) {
      if (item.type !== 'actionable') continue
      const resp = responses.value.items[item.id]
      if (resp?.conclusion === 'Y') y++
      else if (resp?.conclusion === 'N') n++
      else if (resp?.conclusion === 'NA') na++
    }
  }

  const unfilled = total - filled
  return `${Math.round((filled / total) * 100)}% Y:${y} N:${n} NA:${na} 未填:${unfilled}`
}

// ─── Mode Switch: DOCX→HTML 切回时刷新 ─────────────────────────────────────

let docxDirty = false

watch(activeMode, async (newMode, oldMode) => {
  if (newMode === 'html' && oldMode === 'docx') {
    if (docxDirty) {
      loading.value = true
      docxDirty = false
      await loadData()
      loading.value = false
    }
  }
  if (newMode === 'docx') {
    docxDirty = true
  }
})

// ─── OnlyOffice Fallback ────────────────────────────────────────────────────

function onOnlyofficeFallback() {
  docxDirty = true
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadData()

  // 检查 OnlyOffice 健康状态（非阻塞）
  checkOnlyofficeHealth()

  // 初始化导航 Observer（需等 DOM 渲染后）
  if (activeMode.value === 'html') {
    setTimeout(() => initObserver(), 100)
  }

  // 启动 "已保存" 倒计时
  savedAgoTimer = setInterval(updateSavedAgo, 1000)
})

onBeforeUnmount(() => {
  flushPendingSave()
  destroyObserver()
  if (savedAgoTimer) {
    clearInterval(savedAgoTimer)
    savedAgoTimer = null
  }
})

// ─── Expose ─────────────────────────────────────────────────────────────────

defineExpose({
  template,
  responses,
  activeMode,
  docxAvailable,
  saving,
  reload: loadData,
  flushPendingSave,
})
</script>

<style scoped>
.gt-a115-disclosure-checklist {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ─── 错误态 ─── */
.gt-a115-disclosure-checklist__error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 64px 16px;
  color: #909399;
}

.gt-a115-disclosure-checklist__error-msg {
  font-size: 14px;
  color: #606266;
}

/* ─── 顶部工具栏 ─── */
.gt-a115-disclosure-checklist__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.gt-a115-disclosure-checklist__search {
  width: 200px;
}

.gt-a115-disclosure-checklist__filter {
  width: 100px;
}

.gt-a115-disclosure-checklist__save-indicator {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

/* ─── 全局进度环 ─── */
.gt-a115-disclosure-checklist__progress-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.gt-a115-disclosure-checklist__progress-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 13px;
  font-weight: 500;
}

.gt-a115-disclosure-checklist__stat--y {
  color: #67c23a;
}

.gt-a115-disclosure-checklist__stat--n {
  color: #f56c6c;
}

.gt-a115-disclosure-checklist__stat--na {
  color: #909399;
}

.gt-a115-disclosure-checklist__stat--unfilled {
  color: #e6a23c;
}

.gt-a115-disclosure-checklist__stat--total {
  color: #303133;
}

/* ─── HTML 视图布局 ─── */
.gt-a115-disclosure-checklist__html-view {
  flex: 1;
  min-height: 0;
}

.gt-a115-disclosure-checklist__layout {
  display: flex;
  gap: 0;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  min-height: calc(100vh - 320px);
}

/* 左侧导航 */
.gt-a115-disclosure-checklist__nav {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid #ebeef5;
  overflow-y: auto;
  background: #fafbfc;
  display: flex;
  flex-direction: column;
}

.gt-a115-disclosure-checklist__nav-list {
  flex: 1;
  padding: 8px 0;
  overflow-y: auto;
}

.gt-a115-disclosure-checklist__nav-item {
  display: flex;
  align-items: center;
  padding: 6px 10px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: all 0.15s;
  gap: 4px;
  min-height: 32px;
}

.gt-a115-disclosure-checklist__nav-item:hover {
  background: #ecf5ff;
  color: #409eff;
}

.gt-a115-disclosure-checklist__nav-item--active {
  background: #ecf5ff;
  color: #7c3aed;
  border-left-color: #7c3aed;
  font-weight: 600;
}

.gt-a115-disclosure-checklist__nav-item--na {
  color: #c0c4cc;
  background: #f5f7fa;
}

.gt-a115-disclosure-checklist__nav-item--na:hover {
  color: #909399;
  background: #f0f2f5;
}

.gt-a115-disclosure-checklist__nav-icon {
  flex-shrink: 0;
  width: 14px;
  text-align: center;
  font-size: 12px;
}

/* 状态图标颜色 */
.gt-a115-disclosure-checklist__nav-item:not(.gt-a115-disclosure-checklist__nav-item--na) .gt-a115-disclosure-checklist__nav-icon {
  color: #909399;
}

.gt-a115-disclosure-checklist__nav-item--active:not(.gt-a115-disclosure-checklist__nav-item--na) .gt-a115-disclosure-checklist__nav-icon {
  color: #7c3aed;
}

.gt-a115-disclosure-checklist__nav-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.gt-a115-disclosure-checklist__nav-progress {
  flex-shrink: 0;
  font-size: 11px;
  color: #909399;
  margin-left: 2px;
}

.gt-a115-disclosure-checklist__nav-item--na .gt-a115-disclosure-checklist__nav-progress {
  color: #c0c4cc;
}

.gt-a115-disclosure-checklist__nav-switch {
  flex-shrink: 0;
  margin-left: 4px;
  --el-switch-on-color: #7c3aed;
}

.gt-a115-disclosure-checklist__nav-switch :deep(.el-switch__core) {
  height: 16px;
  min-width: 28px;
}

.gt-a115-disclosure-checklist__nav-legend {
  padding: 8px 12px;
  border-top: 1px solid #ebeef5;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #909399;
}

/* 右侧主体 */
.gt-a115-disclosure-checklist__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.gt-a115-disclosure-checklist__section-sentinel {
  margin-bottom: 24px;
}

.gt-a115-disclosure-checklist__section-header {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  padding-bottom: 8px;
  border-bottom: 2px solid #7c3aed;
  margin-bottom: 12px;
}

.gt-a115-disclosure-checklist__section-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.gt-a115-disclosure-checklist__section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.gt-a115-disclosure-checklist__section-suggested-ref {
  font-size: 12px;
  color: #7c3aed;
  background: #f3f0ff;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
}

.gt-a115-disclosure-checklist__section-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.gt-a115-disclosure-checklist__section-progress-bar {
  flex: 1;
  max-width: 300px;
}

.gt-a115-disclosure-checklist__section-progress-text {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}

/* ─── Section Placeholder (lazy rendering) ─── */
.gt-a115-disclosure-checklist__section-placeholder {
  background: #fafbfc;
  border-radius: 6px;
  border: 1px dashed #e4e7ed;
}

/* ─── Item Wrapper ─── */
.gt-a115-disclosure-checklist__item-wrapper {
  margin-bottom: 8px;
}

.gt-a115-disclosure-checklist__item-wrapper--header {
  margin-top: 16px;
  margin-bottom: 8px;
}

/* ─── Header Item (section divider, no interactive buttons) ─── */
.gt-a115-disclosure-checklist__item-header {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  padding: 8px 12px;
  background: #f5f7fa;
  border-left: 3px solid #dcdfe6;
  border-radius: 0 4px 4px 0;
}

/* ─── Actionable Card ─── */
.gt-a115-disclosure-checklist__card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 12px 16px;
  transition: border-color 0.2s, opacity 0.2s, box-shadow 0.2s;
}

.gt-a115-disclosure-checklist__card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

/* Conclusion-based card borders */
.gt-a115-disclosure-checklist__card--yes {
  border-left: 3px solid #67c23a;
}

.gt-a115-disclosure-checklist__card--no {
  border-left: 3px solid #f56c6c;
}

.gt-a115-disclosure-checklist__card--na {
  border-left: 3px solid #909399;
  opacity: 0.6;
}

.gt-a115-disclosure-checklist__card--pending {
  border-left: 3px solid transparent;
}

/* Card top (CAS ref tag) */
.gt-a115-disclosure-checklist__card-top {
  margin-bottom: 6px;
}

.gt-a115-disclosure-checklist__card-cas-ref {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  color: #7c3aed;
  background: #f3f0ff;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* Card content */
.gt-a115-disclosure-checklist__card-content {
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Card actions area */
.gt-a115-disclosure-checklist__card-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.gt-a115-disclosure-checklist__card-buttons {
  display: flex;
  gap: 4px;
}

.gt-a115-disclosure-checklist__card-buttons .el-button {
  min-width: 36px;
  padding: 4px 10px;
}

.gt-a115-disclosure-checklist__card-remark {
  flex: 1;
  min-width: 140px;
  max-width: 300px;
}

.gt-a115-disclosure-checklist__card-wpref {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.gt-a115-disclosure-checklist__wpref-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.gt-a115-disclosure-checklist__wpref-chip--suggested {
  border: 1px dashed #c4b5fd;
  color: #7c3aed;
  background: #faf5ff;
  opacity: 0.75;
}

.gt-a115-disclosure-checklist__wpref-chip--suggested:hover {
  opacity: 1;
  background: #f3f0ff;
  border-color: #7c3aed;
}

.gt-a115-disclosure-checklist__wpref-input {
  width: 80px;
}

.gt-a115-disclosure-checklist__wpref-input :deep(.el-input__inner) {
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* ─── Guidance Children (collapsible) ─── */
.gt-a115-disclosure-checklist__card-guidance {
  margin-top: 10px;
  border-top: 1px solid #f0f2f5;
  padding-top: 8px;
}

.gt-a115-disclosure-checklist__guidance-toggle {
  font-size: 12px;
  color: #7c3aed;
  cursor: pointer;
  user-select: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
  font-weight: 500;
}

.gt-a115-disclosure-checklist__guidance-toggle:hover {
  color: #5b21b6;
}

.gt-a115-disclosure-checklist__guidance-arrow {
  font-size: 10px;
  width: 12px;
  text-align: center;
  transition: transform 0.15s;
}

.gt-a115-disclosure-checklist__guidance-list {
  margin-top: 6px;
  padding-left: 16px;
  border-left: 2px solid #f0f2f5;
}

.gt-a115-disclosure-checklist__guidance-item {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  padding: 4px 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.gt-a115-disclosure-checklist__guidance-ref {
  display: inline-block;
  font-size: 10px;
  color: #909399;
  background: #f5f7fa;
  padding: 1px 4px;
  border-radius: 2px;
  margin-right: 4px;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* ─── DOCX 视图 ─── */
.gt-a115-disclosure-checklist__docx-view {
  min-height: calc(100vh - 280px);
  height: calc(100vh - 280px);
  display: flex;
  flex-direction: column;
}

.gt-a115-disclosure-checklist__docx-view :deep(.gt-onlyoffice-sheet) {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.gt-a115-disclosure-checklist__docx-view :deep(.gt-onlyoffice-sheet__editor-container) {
  flex: 1;
  height: 100%;
}

.gt-a115-disclosure-checklist__docx-view :deep(.gt-onlyoffice-sheet__editor-container iframe) {
  width: 100%;
  height: 100% !important;
  min-height: calc(100vh - 340px);
  border: none;
}
</style>
