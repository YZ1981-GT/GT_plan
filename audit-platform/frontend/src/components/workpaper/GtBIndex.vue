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
    <!-- ─── 编制信息区 ─── -->
    <div class="gt-b-index__preparation">
      <el-descriptions
        title="编制信息"
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
        <el-descriptions-item label="索引号" :span="2">
          {{ preparationInfo.index_no || '—' }}
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
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
const preparationInfo = ref<Record<string, string>>({})
const navigationRows = ref<NavigationRow[]>([])
const projectId = computed(() => (route.params.projectId as string) || '')

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
</style>
