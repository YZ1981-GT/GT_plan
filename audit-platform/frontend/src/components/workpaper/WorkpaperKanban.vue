<template>
  <div class="wp-kanban" v-loading="loading">
    <!-- 顶部统计 KPI 卡片（点击联动筛选） -->
    <div class="kanban-stats">
      <div class="kanban-stat-card" :class="{ 'is-active': !focusColumn }" @click="focusColumn = ''">
        <span class="kanban-stat-card__num">{{ stats.total }}</span>
        <span class="kanban-stat-card__label">总数</span>
      </div>
      <div class="kanban-stat-card kanban-stat-card--highlight">
        <span class="kanban-stat-card__num">{{ stats.completion_rate }}%</span>
        <span class="kanban-stat-card__label">完成率</span>
        <el-progress :percentage="Number(stats.completion_rate) || 0" :stroke-width="4" :show-text="false" color="#fff" style="margin-top: 4px" />
      </div>
      <div class="kanban-stat-card" v-for="col in columns" :key="col.key"
        :class="{ 'is-active': focusColumn === col.key }"
        @click="focusColumn = focusColumn === col.key ? '' : col.key">
        <span class="kanban-stat-card__num" :style="{ color: columnColors[col.key] }">{{ columnCounts[col.key] }}</span>
        <span class="kanban-stat-card__label">{{ col.label }}</span>
      </div>
    </div>

    <!-- 看板列 -->
    <div class="kanban-columns" :class="{ 'has-focus': !!focusColumn }">
      <div
        v-for="col in columns"
        :key="col.key"
        class="kanban-column"
        :class="{ 'is-focused': focusColumn === col.key, 'is-dimmed': focusColumn && focusColumn !== col.key }"
      >
        <div class="column-header" :style="{ borderTopColor: columnColors[col.key] }">
          <span class="column-title">{{ col.label }}</span>
          <span class="column-count">{{ kanbanData[col.key]?.length || 0 }}</span>
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
            <!-- 进度条 -->
            <div class="card-progress" v-if="item.total_steps">
              <el-progress
                :percentage="Math.round((item.completed_steps || 0) / item.total_steps * 100)"
                :stroke-width="3"
                :show-text="false"
                :color="columnColors[col.key]"
              />
              <span class="card-progress__text">{{ item.completed_steps || 0 }}/{{ item.total_steps }}</span>
            </div>
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

          <!-- 空态引导 -->
          <div v-if="!kanbanData[col.key]?.length" class="column-empty">
            <div class="column-empty__icon">{{ col.key === 'completed' ? '🎉' : '📋' }}</div>
            <div class="column-empty__text">
              {{ col.key === 'not_started' ? '所有底稿已开始编制' :
                 col.key === 'under_review' ? '暂无待复核底稿' :
                 col.key === 'completed' ? '暂无已通过底稿' : '暂无底稿' }}
            </div>
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
const focusColumn = ref('') // 点击 KPI 卡片聚焦对应列
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
.wp-kanban { height: 100%; display: flex; flex-direction: column; background: var(--gt-color-bg, #f8f6fc); }

/* 统计栏 — KPI 卡片 */
.kanban-stats {
  display: flex; gap: 12px; padding: 14px 16px; flex-wrap: wrap;
}
.kanban-stat-card {
  flex: 1; min-width: 80px; padding: 12px 16px; text-align: center;
  background: var(--gt-color-bg-white); border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04); border: 1px solid var(--gt-color-border-light, #f0f0f0);
  cursor: pointer; transition: all 0.15s;
}
.kanban-stat-card:hover { border-color: var(--gt-color-primary); }
.kanban-stat-card.is-active { border-color: var(--gt-color-primary); box-shadow: 0 0 0 2px rgba(103, 80, 164, 0.15); }
.kanban-stat-card--highlight {
  background: linear-gradient(135deg, #6750A4 0%, #8b5cf6 100%);
  border: none; box-shadow: 0 4px 12px rgba(103, 80, 164, 0.25);
}
.kanban-stat-card--highlight .kanban-stat-card__num { color: #fff; }
.kanban-stat-card--highlight .kanban-stat-card__label { color: rgba(255,255,255,0.85); }
.kanban-stat-card__num { display: block; font-size: 22px; font-weight: 800; color: var(--gt-color-text-primary); line-height: 1.2; }
.kanban-stat-card__label { font-size: 11px; color: var(--gt-color-text-tertiary); margin-top: 2px; }

/* 看板列 */
.kanban-columns {
  flex: 1; display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 14px; padding: 0 16px 16px; overflow: auto;
}

.kanban-column {
  background: var(--gt-color-bg-white); border-radius: 12px; display: flex; flex-direction: column;
  min-height: 200px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  transition: all 0.2s ease;
}
.kanban-column.is-focused { box-shadow: 0 4px 16px rgba(103, 80, 164, 0.12); transform: scale(1.01); }
.kanban-column.is-dimmed { opacity: 0.4; transform: scale(0.98); }

.column-header {
  padding: 12px 14px; display: flex; align-items: center; justify-content: space-between;
  border-top: 4px solid var(--gt-color-info); border-radius: 12px 12px 0 0;
  background: var(--gt-color-bg, #fafafa);
}
.column-title { font-size: 13px; font-weight: 700; color: var(--gt-color-text); }
.column-count {
  font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 10px;
  background: var(--gt-color-bg-white); color: var(--gt-color-text-secondary);
  border: 1px solid var(--gt-color-border-light, #e8e8e8);
}
.column-body { flex: 1; padding: 10px; overflow-y: auto; }

/* 空态 */
.column-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 30px 0; gap: 8px;
}
.column-empty__icon { font-size: 28px; opacity: 0.5; }
.column-empty__text { font-size: 12px; color: var(--gt-color-text-placeholder); }

/* 卡片 */
.kanban-card {
  background: var(--gt-color-bg-white); border-radius: 8px; padding: 12px 14px; margin-bottom: 10px;
  border: 1px solid var(--gt-color-border-light, #f0f0f0); cursor: pointer;
  transition: all 0.2s ease;
}
.kanban-card:hover {
  box-shadow: 0 4px 12px rgba(75, 45, 119, 0.1);
  border-color: var(--gt-color-primary); transform: translateY(-1px);
}

.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.card-code { font-weight: 700; font-size: 13px; color: var(--gt-color-primary); }
.card-cycle-badge {
  font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
  background: var(--gt-color-primary-bg, #f0e6ff); color: var(--gt-color-primary);
}
.card-name { font-size: 13px; color: var(--gt-color-text); line-height: 1.4; }
.card-progress { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.card-progress__text { font-size: 10px; color: var(--gt-color-text-tertiary); white-space: nowrap; }
.card-footer { display: flex; align-items: center; gap: 4px; margin-top: 8px; font-size: 12px; color: var(--gt-color-text-tertiary); }
.card-actions { justify-content: flex-end; }
.card-assignee { color: var(--gt-color-text-secondary); font-weight: 500; }
</style>
