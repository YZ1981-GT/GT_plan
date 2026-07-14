<script setup lang="ts">
/**
 * J3TabIndex — 股份支付底稿目录（对齐 D4/b-index 底稿架构范式）
 *
 * 复用 GtBArchitectureTree（阶段泳道卡片），由 J3 各 sheet 构造 navigation_rows 喂入。
 * 点击卡片 → emit('navigate-sheet') → GtJ3 转发 → GtWpRenderer 按 sheet_name.includes 匹配。
 */
import { computed } from 'vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly?: boolean
  allResponses?: Map<string, { item_id: string; conclusion: string | null; remark: string | null }>
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
}>()

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  progressKeys: string[]
}

/** J3 各 sheet → navigation_rows（content=完整 sheet 名，供 includes 匹配）。 */
const NAV_ROWS: NavRow[] = [
  { content: '股份支付实质性程序表 J3A', index_ref: 'J3A', component_type: 'a-program-console', progressKeys: [] },
  { content: '股份支付情况表J3-1', index_ref: 'J3-1', component_type: 'd-form-table', progressKeys: ['J3-detail', 'J3-1'] },
  { content: '股份支付检查表J3-2', index_ref: 'J3-2', component_type: 'd-form-table', progressKeys: ['J3-check', 'J3-2'] },
]

function rowStatus(row: NavRow): string {
  if (row.progressKeys.length === 0) return ''
  const map = props.allResponses
  if (!map || map.size === 0) return 'pending'
  const keys = [...map.keys()]
  const hasData = row.progressKeys.some(pk => map.has(pk) || keys.some(k => k.startsWith(pk)))
  return hasData ? 'completed' : 'pending'
}

const archHtmlData = computed(() => ({
  navigation_rows: NAV_ROWS.map((r, i) => ({
    seq: i + 1,
    content: r.content,
    sheet_name: r.content,
    index_ref: r.index_ref,
    component_type: r.component_type,
    status: rowStatus(r),
  })),
}))

// ─── 编制进度 ─────────────────────────────────────────────────────────
const progressRows = computed(() => NAV_ROWS.filter(r => r.progressKeys.length > 0))
const completedCount = computed(() => progressRows.value.filter(r => rowStatus(r) === 'completed').length)
const applicableCount = computed(() => progressRows.value.length)
const progressPercent = computed(() =>
  applicableCount.value === 0 ? 0 : Math.round((completedCount.value / applicableCount.value) * 100),
)

function handleNavigate(sheetName: string) {
  if (sheetName) emit('navigate-sheet', sheetName)
}
</script>

<template>
  <div class="j3-tab-index">
    <!-- 编制进度条 -->
    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- 底稿架构（阶段泳道卡片，复用 D4/b-index 范式） -->
    <div class="index-header">
      <h4 class="index-title">底稿架构</h4>
      <span class="index-hint">点击卡片可跳转至对应底稿</span>
    </div>
    <GtBArchitectureTree
      :active-sheet="''"
      :html-data="archHtmlData"
      @navigate="handleNavigate"
    />
  </div>
</template>

<style scoped>
.j3-tab-index {
  padding: 12px;
}
.progress-bar-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}
.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.progress-text {
  font-weight: 600;
  color: #303133;
}
.index-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.index-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.index-hint {
  font-size: 12px;
  color: #909399;
}
</style>
