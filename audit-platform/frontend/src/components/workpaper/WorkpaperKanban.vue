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
              <span class="card-cycle-badge">{{ item.audit_cycle }}</span>
            </div>
            <div class="card-name">{{ item.wp_name }}</div>
            <div class="card-footer" v-if="item.assigned_to">
              <el-icon :size="12"><User /></el-icon>
              <span class="card-assignee">{{ item.assigned_to?.slice(0, 8) }}</span>
            </div>
            <div class="card-footer card-actions" v-else>
              <el-button size="small" text type="primary" @click.stop="$emit('assign', item)">
                分配
              </el-button>
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
  'assign': [item: any]
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
.wp-kanban { height: 100%; display: flex; flex-direction: column; background: linear-gradient(135deg, #f8f6fc 0%, #f0ecf8 100%); }

/* 统计栏 — 致同紫色渐变 */
.kanban-stats {
  display: flex; gap: 20px; padding: 16px 20px;
  background: linear-gradient(90deg, #4b2d77 0%, #6b4a9e 100%);
  border-radius: 10px; margin: 12px 16px 0;
  box-shadow: 0 4px 12px rgba(75, 45, 119, 0.25);
  flex-wrap: wrap;
}
.stat-item { text-align: center; min-width: 60px; }
.stat-num { display: block; font-size: 22px; font-weight: 800; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.15); }
.stat-label { font-size: 11px; color: rgba(255,255,255,0.85); letter-spacing: 0.5px; }
.stat-progress .stat-num { color: #ffd700; font-size: 24px; }

/* 看板列 */
.kanban-columns {
  flex: 1; display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; padding: 16px; overflow: auto;
}

.kanban-column {
  background: #fff; border-radius: 12px; display: flex; flex-direction: column;
  min-height: 200px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.kanban-column:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(75, 45, 119, 0.08); }

.column-header {
  padding: 12px 14px; display: flex; align-items: center; justify-content: space-between;
  border-top: 4px solid #909399; border-radius: 12px 12px 0 0;
  background: linear-gradient(180deg, #fafafa 0%, #fff 100%);
}
.column-title { font-size: 14px; font-weight: 700; color: #1a1a2e; letter-spacing: 0.5px; }
.column-body { flex: 1; padding: 10px; overflow-y: auto; max-height: 500px; }
.column-empty { text-align: center; color: #c0c4cc; font-size: 12px; padding: 30px 0; font-style: italic; }

/* 卡片 — 动感交互 */
.kanban-card {
  background: #fff; border-radius: 8px; padding: 12px 14px; margin-bottom: 10px;
  border: 1px solid #f0ebf8; cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative; overflow: hidden;
}
.kanban-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: linear-gradient(180deg, #4b2d77, #8b5cf6); border-radius: 3px 0 0 3px;
  opacity: 0; transition: opacity 0.2s;
}
.kanban-card:hover {
  box-shadow: 0 4px 12px rgba(75, 45, 119, 0.12);
  border-color: #d0c4e8; transform: translateX(3px);
}
.kanban-card:hover::before { opacity: 1; }

.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.card-code { font-weight: 700; font-size: 14px; color: #4b2d77; }
.card-cycle-badge {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
  background: linear-gradient(135deg, #f0e6ff, #e8d9f8); color: #4b2d77;
}
.card-name { font-size: 13px; color: #1a1a2e; line-height: 1.5; font-weight: 500; }
.card-footer { display: flex; align-items: center; gap: 4px; margin-top: 8px; font-size: 11px; color: #909399; }
.card-actions { justify-content: flex-end; }
.card-assignee { color: #606266; font-weight: 500; }
</style>
