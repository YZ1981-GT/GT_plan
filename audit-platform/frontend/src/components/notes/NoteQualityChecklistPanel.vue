<template>
  <div class="quality-checklist-panel">
    <!-- 顶部筛选栏 -->
    <div class="quality-checklist-panel__toolbar">
      <el-radio-group v-model="filterLevel" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="blocking">阻止签发</el-radio-button>
        <el-radio-button value="warning">需关注</el-radio-button>
        <el-radio-button value="info">信息</el-radio-button>
      </el-radio-group>
      <el-select
        v-model="filterCategory"
        placeholder="按分类筛选"
        size="small"
        clearable
        style="width: 160px; margin-left: 12px"
      >
        <el-option
          v-for="cat in categoryOptions"
          :key="cat.value"
          :label="cat.label"
          :value="cat.value"
        />
      </el-select>
      <span class="quality-checklist-panel__count">
        共 {{ filteredItems.length }} 项
        <template v-if="blockingCount > 0">
          （<span class="count-blocking">{{ blockingCount }} 项阻止签发</span>）
        </template>
      </span>
    </div>

    <!-- 清单列表 -->
    <div class="quality-checklist-panel__body">
      <el-empty v-if="filteredItems.length === 0" description="暂无质量问题" />
      <ul v-else class="checklist-list">
        <li
          v-for="(item, idx) in filteredItems"
          :key="idx"
          class="checklist-item"
        >
          <el-tag
            :type="levelTagType(item.level)"
            size="small"
            class="checklist-item__level"
          >
            {{ levelLabel(item.level) }}
          </el-tag>
          <el-tag
            size="small"
            class="checklist-item__category"
            effect="plain"
          >
            {{ categoryLabel(item.category) }}
          </el-tag>
          <span class="checklist-item__message">{{ item.message }}</span>
          <el-button
            v-if="item.route"
            type="primary"
            size="small"
            link
            class="checklist-item__jump"
            @click="handleNavigate(item)"
          >
            跳转
          </el-button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

export interface QualityChecklistItem {
  level: string
  category: string
  section_id?: string | null
  table_id?: string | null
  row_id?: string | null
  col_id?: string | null
  message: string
  route?: string | null
  evidence?: Record<string, any> | null
}

interface Props {
  items: QualityChecklistItem[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  navigate: [payload: { route: string; section_id?: string | null; table_id?: string | null; row_id?: string | null; col_id?: string | null }]
}>()

const filterLevel = ref<'all' | 'blocking' | 'warning' | 'info'>('all')
const filterCategory = ref<string>('')

const categoryOptions = [
  { value: 'formula', label: '公式错误' },
  { value: 'stale', label: '数据陈旧' },
  { value: 'manual_override', label: '手工覆盖' },
  { value: 'ai', label: 'AI 未确认' },
  { value: 'tieout', label: '披露不一致' },
  { value: 'style', label: '样式问题' },
  { value: 'completeness', label: '完整性' },
]

const filteredItems = computed(() => {
  let result = props.items
  if (filterLevel.value !== 'all') {
    result = result.filter(item => item.level === filterLevel.value)
  }
  if (filterCategory.value) {
    result = result.filter(item => item.category === filterCategory.value)
  }
  return result
})

const blockingCount = computed(() => {
  return props.items.filter(item => item.level === 'blocking').length
})

function handleNavigate(item: QualityChecklistItem) {
  if (item.route) {
    emit('navigate', {
      route: item.route,
      section_id: item.section_id,
      table_id: item.table_id,
      row_id: item.row_id,
      col_id: item.col_id,
    })
  }
}

function levelTagType(level: string): string {
  const map: Record<string, string> = {
    blocking: 'danger',
    warning: 'warning',
    info: 'info',
  }
  return map[level] || 'info'
}

function levelLabel(level: string): string {
  const map: Record<string, string> = {
    blocking: '阻止签发',
    warning: '需关注',
    info: '信息',
  }
  return map[level] || level
}

function categoryLabel(category: string): string {
  const map: Record<string, string> = {
    formula: '公式错误',
    stale: '数据陈旧',
    manual_override: '手工覆盖',
    ai: 'AI 未确认',
    tieout: '披露不一致',
    style: '样式问题',
    completeness: '完整性',
  }
  return map[category] || category
}
</script>

<style scoped>
.quality-checklist-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.quality-checklist-panel__toolbar {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.quality-checklist-panel__count {
  margin-left: auto;
  font-size: 13px;
  color: #909399;
}

.count-blocking {
  color: var(--el-color-danger, #f56c6c);
  font-weight: 500;
}

.quality-checklist-panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.checklist-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.checklist-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.checklist-item:last-child {
  border-bottom: none;
}

.checklist-item__level {
  flex-shrink: 0;
}

.checklist-item__category {
  flex-shrink: 0;
}

.checklist-item__message {
  flex: 1;
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.checklist-item__jump {
  flex-shrink: 0;
}
</style>
