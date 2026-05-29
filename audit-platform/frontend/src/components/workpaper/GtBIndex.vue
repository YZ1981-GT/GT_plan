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
        <el-descriptions-item label="会计期间" :span="2">
          {{ preparationInfo.accounting_period || '—' }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ─── 索引导航表 ─── -->
    <div class="gt-b-index__navigation">
      <div class="gt-b-index__navigation-header">
        <h4 class="gt-b-index__navigation-title">索引导航</h4>
        <div v-if="!readonly" class="gt-b-index__navigation-actions">
          <!-- Sprint 4 Task 17.9: 底稿架构折叠按钮 -->
          <el-button text size="small" @click="archTreeExpanded = !archTreeExpanded" title="底稿架构">
            🏗️ {{ archTreeExpanded ? '收起' : '底稿架构' }}
          </el-button>
          <el-button
            v-if="selectedRows.length > 0"
            size="small"
            type="warning"
            @click="batchToggleNoPrint"
          >
            批量切换"无需打印" ({{ selectedRows.length }})
          </el-button>
        </div>
      </div>

      <!-- Sprint 4 Task 17.9: 底稿架构树 -->
      <GtBArchitectureTree
        v-if="wpId && projectId"
        :wp-id="wpId"
        :project-id="projectId"
        :expanded="archTreeExpanded"
        :html-data="htmlData"
      />

      <el-table
        ref="tableRef"
        :data="navigationRows"
        border
        row-key="seq"
        @selection-change="handleSelectionChange"
        class="gt-b-index__table"
      >
        <!-- 多选列（非只读时显示） -->
        <el-table-column
          v-if="!readonly"
          type="selection"
          width="40"
        />

        <!-- 序号 -->
        <el-table-column
          label="序号"
          prop="seq"
          width="60"
          align="center"
          resizable
        />

        <!-- 内容 -->
        <el-table-column
          label="内容"
          prop="content"
          min-width="280"
          resizable
        />

        <!-- 索引号（GtIndexChip 渲染） -->
        <el-table-column
          label="索引号"
          min-width="160"
          resizable
        >
          <template #default="{ row }">
            <GtIndexChip
              v-if="row.index_ref"
              :value="row.index_ref"
              @click="handleIndexChipClick(row.index_ref)"
            />
            <span v-else class="gt-b-index__empty-ref">—</span>
          </template>
        </el-table-column>

        <!-- 无需打印 -->
        <el-table-column
          label="无需打印"
          width="100"
          align="center"
          resizable
        >
          <template #default="{ row }">
            <el-switch
              v-model="row.no_print"
              :disabled="readonly"
              size="small"
              @change="handleNoPrintChange(row)"
            />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
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
const selectedRows = ref<NavigationRow[]>([])
const tableRef = ref<any>(null)

// Sprint 4 Task 17.9: 底稿架构树展开状态
const archTreeExpanded = ref(false)
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
function handleSelectionChange(selection: NavigationRow[]) {
  selectedRows.value = selection
}

function handleNoPrintChange(_row: NavigationRow) {
  debounceSave()
}

function batchToggleNoPrint() {
  // Toggle: if any selected row has no_print=false, set all to true; otherwise set all to false
  const anyNotMarked = selectedRows.value.some(r => !r.no_print)
  const targetValue = anyNotMarked

  selectedRows.value.forEach(selected => {
    const idx = navigationRows.value.findIndex(r => r.seq === selected.seq)
    if (idx >= 0) {
      navigationRows.value[idx].no_print = targetValue
    }
  })

  // Clear selection
  selectedRows.value = []
  if (tableRef.value) {
    tableRef.value.clearSelection()
  }

  debounceSave()
}

function handleIndexChipClick(indexRef: string) {
  emit('jump-to-section', indexRef)
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
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.gt-b-index__navigation-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.gt-b-index__navigation-actions {
  display: flex;
  gap: 8px;
}

.gt-b-index__table {
  width: 100%;
}

.gt-b-index__empty-ref {
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
