<!--
  GtBIndex.vue — B 类底稿目录组件

  按 design §3.4 实现：
  - 编制信息从 project meta + user profile 自动填充（首次加载）
  - 索引导航行可点跳转（同底稿 sheet 切换 / 跨底稿 router.push）
  - "无需打印"批量切换（导出时保留原合并区，但 cell 写入空字符串 + 加批注"已标记不打印"）
  - Debounced auto-save (1.5s)

  锚定 spec workpaper-html-renderer Task 5.2
  Validates: Requirements 3.3（B 类 148 sheet）

  ─── cross-ref:updated 订阅契约（Task 13.2）──────────────────────────────────
  本组件**不直接订阅** eventBus 'cross-ref:updated' 事件。跨底稿引用变化由
  `useWpRenderer.ts`（GtWpRenderer 父组件持有）统一监听 + 重拉 renderConfig，
  本组件通过 props 接收最新 htmlData 自动更新（单一订阅入口避免内存泄漏）。
-->

<template>
  <div class="gt-b-index">
    <!-- ─── 编制信息区（可折叠） ─── -->
    <div class="gt-b-index__preparation" :class="{ 'is-collapsed': prepCollapsed }">
      <div class="gt-b-index__preparation-bar" @click="prepCollapsed = !prepCollapsed">
        <span class="gt-b-index__preparation-title">编制信息</span>
        <span v-if="prepCollapsed" class="gt-b-index__preparation-summary">{{ prepSummary }}</span>
        <span v-if="indexNo" class="gt-b-index__preparation-index">索引号：{{ indexNo }}</span>
        <el-button
          class="gt-b-index__preparation-toggle"
          link
          type="primary"
          size="small"
          @click.stop="prepCollapsed = !prepCollapsed"
        >
          {{ prepCollapsed ? '展开' : '收起' }}
        </el-button>
      </div>
      <el-descriptions
        v-show="!prepCollapsed"
        :column="2"
        border
        size="default"
      >
        <el-descriptions-item label="被审计单位">
          {{ preparationInfo.entity_name || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="截止日">
          {{ preparationInfo.period_end || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="编制人">
          {{ preparationInfo.preparer || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="编制日期">
          {{ preparationInfo.prep_date || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="复核人">
          {{ preparationInfo.reviewer || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="复核日期">
          {{ preparationInfo.review_date || '—' }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ─── 底稿架构导航（流程图，取代表格式索引导航） ─── -->
    <div class="gt-b-index__navigation">
      <div class="gt-b-index__navigation-header">
        <h4 class="gt-b-index__navigation-title">底稿架构</h4>
        <span class="gt-b-index__navigation-hint">点击程序卡片可跳转至对应底稿</span>
      </div>

      <GtBArchitectureTree
        :wp-id="wpId"
        :project-id="projectId"
        :active-sheet="sheetName"
        :html-data="htmlData"
        @navigate="handleNavigate"
      />
    </div>

    <!-- ─── 循环底稿目录（跨底稿，同审计循环全部底稿） ─── -->
    <div v-if="cycleWorkpapers.length > 0" class="gt-b-index__cycle">
      <div class="gt-b-index__cycle-header">
        <h4 class="gt-b-index__cycle-title">本循环底稿目录</h4>
        <span class="gt-b-index__cycle-hint">点击可跳转至同循环其他底稿（灰色表示尚未生成）</span>
      </div>
      <div class="gt-b-index__cycle-grid">
        <div
          v-for="wp in cycleWorkpapers"
          :key="wp.wp_code"
          class="gt-b-index__cycle-card"
          :class="{
            'is-current': wp.is_current,
            'is-disabled': !wp.wp_id,
          }"
          @click="onCycleCardClick(wp)"
        >
          <div class="gt-b-index__cycle-card-top">
            <span class="gt-b-index__cycle-code">{{ wp.wp_code }}</span>
            <el-tag
              v-if="wp.is_current"
              size="small"
              effect="plain"
              class="gt-b-index__cycle-current-tag"
            >当前</el-tag>
          </div>
          <span class="gt-b-index__cycle-name" :title="wp.wp_name">{{ wp.wp_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GtBArchitectureTree from '@/components/workpaper/GtBArchitectureTree.vue'

// ─── Types ───
interface NavigationRow {
  seq: number
  content: string
  index_ref: string
  no_print: boolean
}

export interface BIndexSchema {
  /** 编制信息字段（字符串数组或 {field, label} 对象数组） */
  preparation_info_fields?: Array<string | { field: string; label: string }>
  navigation_table?: { columns: string[] }
  [key: string]: any
}

interface BIndexHtmlData {
  preparation_info: Record<string, string>
  navigation_rows: NavigationRow[]
  cycle_workpapers?: CycleWorkpaper[]
}

interface CycleWorkpaper {
  wp_code: string
  wp_name: string
  wp_id: string | null
  status: string
  is_current: boolean
}

// ─── Props / Emits ───
const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: BIndexSchema
  htmlData: BIndexHtmlData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'jump-to-section': [indexRef: string]
  'review-status-change': [status: string]
  'save': [data: BIndexHtmlData]
}>()

// ─── State ───
const route = useRoute()
const router = useRouter()
const preparationInfo = ref<Record<string, string>>({})
const navigationRows = ref<NavigationRow[]>([])
const projectId = computed(() => (route.params.projectId as string) || '')

// 循环底稿目录（跨底稿）——同审计循环全部底稿，点击 router.push 跳转
const cycleWorkpapers = computed<CycleWorkpaper[]>(
  () => props.htmlData?.cycle_workpapers ?? [],
)

// 编制信息折叠状态（默认展开）；收起时在标题栏显示概要
const prepCollapsed = ref(false)
// 索引号置于标题栏右上角常显（取代表内单独的索引号行）
const indexNo = computed(() => {
  const v = preparationInfo.value.index_no
  return v != null && String(v).trim() !== '' ? String(v) : ''
})
const prepSummary = computed(() => {
  const parts = [preparationInfo.value.entity_name, preparationInfo.value.index_no].filter(
    (p) => p != null && String(p).trim() !== '',
  )
  return parts.length ? parts.join(' · ') : '—'
})

// Auto-save debounce
let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Initialize data from props ───
function initData() {
  if (props.htmlData?.preparation_info) {
    preparationInfo.value = { ...props.htmlData.preparation_info }
  } else {
    preparationInfo.value = {}
  }

  if (props.htmlData?.navigation_rows) {
    navigationRows.value = JSON.parse(JSON.stringify(props.htmlData.navigation_rows))
  } else {
    navigationRows.value = []
  }
}

initData()

watch(() => props.htmlData, () => {
  initData()
}, { deep: true })

// ─── Methods ───
function handleNavigate(sheetName: string) {
  // 架构图节点点击 → 冒泡给父组件切换 sheet
  emit('jump-to-section', sheetName)
}

function onCycleCardClick(wp: CycleWorkpaper) {
  // 跨底稿跳转：同循环其他底稿用 router.push 打开对应 WorkpaperEditor。
  // wp_id 为空（底稿未生成文件）→ 不可跳转。当前底稿 → 不重复跳。
  if (!wp.wp_id || wp.is_current) return
  const pid = projectId.value
  if (!pid) return
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: pid, wpId: wp.wp_id },
  })
}

function debounceSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    const data: BIndexHtmlData = {
      preparation_info: preparationInfo.value,
      navigation_rows: navigationRows.value,
    }
    emit('save', data)
  }, 1500)
}

// ─── Cleanup ───
onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
})
</script>

<style scoped>
.gt-b-index {
  padding: 16px;
}

.gt-b-index__preparation {
  margin-bottom: 24px;
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  border-radius: 6px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  overflow: hidden;
}
.gt-b-index__preparation.is-collapsed {
  min-height: 36px;
}
.gt-b-index__preparation-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  user-select: none;
}
.gt-b-index__preparation-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-b-index__preparation-summary {
  flex: 1;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 索引号常显于标题栏右上角（取代表内单独索引号行）；用 margin-left:auto 顶到右侧、紧邻收起按钮 */
.gt-b-index__preparation-index {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  white-space: nowrap;
}
/* 概要已占据 flex:1 时，索引号紧随其后即可，无需再 auto 顶（避免双 auto 冲突） */
.gt-b-index__preparation-summary ~ .gt-b-index__preparation-index {
  margin-left: 8px;
}
.gt-b-index__preparation-toggle {
  margin-left: 8px;
}
/* el-descriptions 嵌入折叠容器：去掉自身外边距，留出内边距 */
.gt-b-index__preparation :deep(.el-descriptions) {
  padding: 0 12px 10px;
}
.gt-b-index__preparation :deep(.el-descriptions__label) {
  color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
}
.gt-b-index__preparation :deep(.gt-b-index__preparation-toggle.el-button.is-link) {
  color: var(--gt-color-primary, #4b2d77);
}

.gt-b-index__navigation {
  margin-top: 16px;
}

.gt-b-index__navigation-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.gt-b-index__navigation-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.gt-b-index__navigation-hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

/* ─── 循环底稿目录（跨底稿） ─── */
.gt-b-index__cycle {
  margin-top: 28px;
}
.gt-b-index__cycle-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.gt-b-index__cycle-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-b-index__cycle-hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}
.gt-b-index__cycle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.gt-b-index__cycle-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: var(--gt-color-bg-white, #fff);
  cursor: pointer;
  transition: all 0.2s;
}
.gt-b-index__cycle-card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}
.gt-b-index__cycle-card.is-current {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77);
  cursor: default;
}
.gt-b-index__cycle-card.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.gt-b-index__cycle-card.is-disabled:hover {
  border-color: var(--gt-color-border-purple, #e8e4f0);
  box-shadow: none;
  transform: none;
}
.gt-b-index__cycle-card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}
.gt-b-index__cycle-code {
  font-size: 13px;
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-b-index__cycle-current-tag {
  margin-left: auto;
}
.gt-b-index__cycle-card :deep(.gt-b-index__cycle-current-tag.el-tag) {
  --el-tag-bg-color: var(--gt-color-primary-bg, #f4f0fa);
  --el-tag-border-color: var(--gt-color-border-purple-light, #d8b8ee);
  --el-tag-text-color: var(--gt-color-primary, #4b2d77);
  background-color: var(--gt-color-primary-bg, #f4f0fa) !important;
  border-color: var(--gt-color-border-purple-light, #d8b8ee) !important;
  color: var(--gt-color-primary, #4b2d77) !important;
}
.gt-b-index__cycle-name {
  font-size: 13px;
  line-height: 1.4;
  color: var(--gt-color-text-primary, #303133);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
