<template>
  <el-drawer
    :model-value="visible"
    title="单元格编辑历史"
    direction="rtl"
    size="380px"
    :destroy-on-close="true"
    @close="$emit('update:visible', false)"
  >
    <template #header>
      <div class="gt-cell-history__header">
        <span class="gt-cell-history__title">编辑历史</span>
        <el-tag v-if="cellRef" size="small" type="info" effect="plain">{{ cellRef }}</el-tag>
      </div>
    </template>

    <div v-if="loading" class="gt-cell-history__loading">
      <el-skeleton :rows="5" animated />
    </div>

    <div v-else-if="!history.length" class="gt-cell-history__empty">
      <el-empty description="暂无编辑记录" :image-size="80" />
    </div>

    <el-timeline v-else class="gt-cell-history__timeline">
      <el-timeline-item
        v-for="item in history"
        :key="item.id"
        :timestamp="formatTime(item.created_at)"
        placement="top"
        :type="getTimelineType(item.action)"
      >
        <div class="gt-cell-history__item">
          <div class="gt-cell-history__user">
            <el-icon><User /></el-icon>
            <span>{{ item.user_name || item.user_id }}</span>
          </div>
          <div class="gt-cell-history__action">
            {{ getActionLabel(item.action) }}
          </div>
          <div v-if="item.details?.old_value != null || item.details?.new_value != null" class="gt-cell-history__diff">
            <div v-if="item.details?.old_value != null" class="gt-cell-history__old">
              <span class="gt-cell-history__label">旧值：</span>
              <span class="gt-cell-history__value gt-cell-history__value--old">{{ item.details.old_value }}</span>
            </div>
            <div v-if="item.details?.new_value != null" class="gt-cell-history__new">
              <span class="gt-cell-history__label">新值：</span>
              <span class="gt-cell-history__value gt-cell-history__value--new">{{ item.details.new_value }}</span>
            </div>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * CellHistoryTimeline — 单元格编辑历史时间线 [wp-frontend-ux-polish Task 8]
 * 点击底稿单元格后查看"谁何时改了什么"。
 */
import { ref, watch } from 'vue'
import { User } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

export interface CellHistoryEntry {
  id: string
  action: string
  user_id: string
  user_name?: string
  details: Record<string, any>
  created_at: string | null
}

interface Props {
  visible: boolean
  wpId: string
  cellRef: string
}

const props = defineProps<Props>()
defineEmits<{ 'update:visible': [val: boolean] }>()

const loading = ref(false)
const history = ref<CellHistoryEntry[]>([])

watch(
  () => [props.visible, props.cellRef],
  ([vis]) => {
    if (vis && props.wpId && props.cellRef) {
      loadHistory()
    }
  },
)

async function loadHistory() {
  loading.value = true
  history.value = []
  try {
    const data: CellHistoryEntry[] = await api.get(
      `/api/workpapers/${encodeURIComponent(props.wpId)}/cell-history`,
      { params: { cell_ref: props.cellRef } },
    )
    history.value = data || []
  } catch (e) {
    handleApiError(e, '加载单元格历史')
  } finally {
    loading.value = false
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function getActionLabel(action: string): string {
  const map: Record<string, string> = {
    'workpaper.cell_edit': '编辑单元格',
    'workpaper.cell_clear': '清空单元格',
    'workpaper.cell_formula': '修改公式',
    'workpaper.cell_paste': '粘贴内容',
    'workpaper.save': '保存底稿',
    'workpaper.auto_fill': '自动填充',
    'workpaper.import': '导入数据',
  }
  return map[action] || action.replace('workpaper.', '')
}

function getTimelineType(action: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' {
  if (action.includes('clear') || action.includes('delete')) return 'danger'
  if (action.includes('auto_fill') || action.includes('import')) return 'success'
  if (action.includes('formula')) return 'warning'
  return 'primary'
}
</script>

<style scoped>
.gt-cell-history__header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-cell-history__title {
  font-weight: 600;
  font-size: 16px;
}

.gt-cell-history__loading,
.gt-cell-history__empty {
  padding: 24px 0;
  text-align: center;
}

.gt-cell-history__timeline {
  padding: 0 4px;
}

.gt-cell-history__item {
  font-size: 13px;
}

.gt-cell-history__user {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
  margin-bottom: 4px;
}

.gt-cell-history__action {
  color: var(--el-text-color-secondary, #909399);
  margin-bottom: 4px;
}

.gt-cell-history__diff {
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  padding: 6px 8px;
  font-family: monospace;
  font-size: 12px;
}

.gt-cell-history__label {
  color: var(--el-text-color-secondary);
}

.gt-cell-history__value--old {
  text-decoration: line-through;
  color: var(--el-color-danger, #f56c6c);
}

.gt-cell-history__value--new {
  color: var(--el-color-success, #67c23a);
}
</style>
