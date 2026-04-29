<template>
  <div class="wp-kanban" v-loading="loading">
    <!-- 顶部统计 -->
    <div class="kanban-stats">
      <div class="stat-item">
        <span class="stat-num">{{ stats.total }}</span>
        <span class="stat-label">总数</span>
      </div>
      <div class="stat-item stat-progress">
        <span class="stat-num">{{ stats.completion_rate }}%</span>
        <span class="stat-label">完成率</span>
      </div>
      <div class="stat-item" v-for="(count, key) in columnCounts" :key="key">
        <span class="stat-num" :style="{color: columnColors[key]}">{{ count }}</span>
        <span class="stat-label">{{ columnLabels[key] }}</span>
      </div>
    </div>

    <!-- 看板列 -->
    <div class="kanban-columns">
      <div
        v-for="col in columns"
        :key="col.key"
        class="kanban-column"
      >
        <div class="column-header" :style="{borderTopColor: columnColors[col.key]}">
          <span class="column-title">{{ col.label }}</span>
          <el-badge :value="kanbanData[col.key]?.length || 0" :type="col.badgeType" />
        </div>

        <div class="column-body">
          <div
            v-for="item in kanbanData[col.key] || []"
            :key="item.wp_code"
            class="kanban-card"
            @click="$emit('select', item)"
          >
            <div class="card-header">
              <span class="card-code">{{ item.wp_code }}</span>
              <el-tag size="small" effect="plain">{{ item.audit_cycle }}</el-tag>
            </div>
            <div class="card-name">{{ item.wp_name }}</div>
            <div class="card-footer" v-if="item.assigned_to">
              <el-icon :size="12"><User /></el-icon>
              <span class="card-assignee">{{ item.assigned_to?.slice(0, 8) }}</span>
            </div>
          </div>

          <div v-if="!kanbanData[col.key]?.length" class="column-empty">
            暂无底稿
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { User } from '@element-plus/icons-vue'
import { getWorkpapersKanban } from '@/services/commonApi'

const props = defineProps<{
  projectId: string
  auditCycle?: string
}>()

defineEmits<{
  'select': [item: any]
}>()

const loading = ref(false)
const kanbanData = ref<Record<string, any[]>>({
  not_started: [],
  in_progress: [],
  under_review: [],
  completed: [],
})
const stats = ref<any>({ total: 0, completion_rate: 0 })

const columns = [
  { key: 'not_started', label: '待编制', badgeType: 'info' as const },
  { key: 'in_progress', label: '编制中', badgeType: 'warning' as const },
  { key: 'under_review', label: '待复核', badgeType: '' as const },
  { key: 'completed', label: '已通过', badgeType: 'success' as const },
]

const columnLabels: Record<string, string> = {
  not_started: '待编制', in_progress: '编制中', under_review: '待复核', completed: '已通过',
}
const columnColors: Record<string, string> = {
  not_started: '#909399', in_progress: '#e6a23c', under_review: '#4b2d77', completed: '#67c23a',
}
const columnCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const col of columns) {
    counts[col.key] = kanbanData.value[col.key]?.length || 0
  }
  return counts
})

async function loadKanban() {
  loading.value = true
  try {
    const result = await getWorkpapersKanban(props.projectId, props.auditCycle)
    kanbanData.value = result.kanban || {}
    stats.value = result.stats || { total: 0, completion_rate: 0 }
  } catch {
    kanbanData.value = { not_started: [], in_progress: [], under_review: [], completed: [] }
  } finally {
    loading.value = false
  }
}

onMounted(loadKanban)

defineExpose({ refresh: loadKanban })
</script>

<style scoped>
.wp-kanban { height: 100%; display: flex; flex-direction: column; }

.kanban-stats {
  display: flex; gap: 16px; padding: 12px 16px; background: #f9f7fc;
  border-bottom: 1px solid #e8e0f0; flex-wrap: wrap;
}
.stat-item { text-align: center; }
.stat-num { display: block; font-size: 20px; font-weight: 700; color: #303133; }
.stat-label { font-size: 11px; color: #909399; }
.stat-progress .stat-num { color: #4b2d77; }

.kanban-columns {
  flex: 1; display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 12px; padding: 12px; overflow: auto;
}

.kanban-column {
  background: #f5f5f5; border-radius: 8px; display: flex; flex-direction: column;
  min-height: 200px;
}
.column-header {
  padding: 10px 12px; display: flex; align-items: center; justify-content: space-between;
  border-top: 3px solid #909399; border-radius: 8px 8px 0 0;
  background: #fff;
}
.column-title { font-size: 13px; font-weight: 600; }
.column-body { flex: 1; padding: 8px; overflow-y: auto; max-height: 500px; }
.column-empty { text-align: center; color: #c0c4cc; font-size: 12px; padding: 20px 0; }

.kanban-card {
  background: #fff; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px;
  border: 1px solid #ebeef5; cursor: pointer; transition: box-shadow 0.2s;
}
.kanban-card:hover { box-shadow: 0 2px 8px rgba(75, 45, 119, 0.1); border-color: #d0c4e8; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.card-code { font-weight: 600; font-size: 13px; color: #4b2d77; }
.card-name { font-size: 12px; color: #606266; line-height: 1.4; }
.card-footer { display: flex; align-items: center; gap: 4px; margin-top: 6px; font-size: 11px; color: #909399; }
</style>
