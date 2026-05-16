<script setup lang="ts">
/**
 * 结论总览视图
 * Sprint 8 Task 8.8: 按循环展示底稿结论汇总
 */
import { computed } from 'vue'

interface ConclusionItem {
  wp_id: string
  wp_code: string
  wp_name: string
  conclusion_text: string
  conclusion_type: string
  conclusion_label: string
}

interface CycleStat {
  cycle: string
  total: number
  by_type: Record<string, number>
}

const props = defineProps<{
  conclusions: ConclusionItem[]
  cycleSummary: CycleStat[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-wp', wpId: string): void
}>()

const typeColors: Record<string, string> = {
  no_exception: 'success',
  adjusted: 'warning',
  material_misstatement: 'danger',
  scope_limitation: 'info',
  pending: '',
  not_applicable: 'info',
}

const typeLabels: Record<string, string> = {
  no_exception: '无异常',
  adjusted: '已调整',
  material_misstatement: '重大错报',
  scope_limitation: '范围受限',
  pending: '待完成',
  not_applicable: '不适用',
}

const cycleLabels: Record<string, string> = {
  B: '初步业务活动',
  C: '控制测试',
  D: '收入循环',
  E: '货币资金',
  F: '存货',
  G: '投资',
  H: '固定资产',
  I: '无形资产',
  J: '职工薪酬',
  K: '费用',
  L: '债务',
  M: '权益',
  N: '税金',
  A: '完成阶段',
  S: '特定项目',
}

const completionRate = computed(() => {
  if (!props.conclusions.length) return 0
  const done = props.conclusions.filter(c => c.conclusion_type !== 'pending').length
  return Math.round((done / props.conclusions.length) * 100)
})
</script>

<template>
  <div class="conclusion-overview">
    <!-- 汇总统计 -->
    <div class="summary-bar">
      <div class="stat-item">
        <span class="stat-value">{{ conclusions.length }}</span>
        <span class="stat-label">总底稿</span>
      </div>
      <div class="stat-item">
        <el-progress type="circle" :percentage="completionRate" :width="50" :stroke-width="4" />
        <span class="stat-label">结论完成率</span>
      </div>
      <div class="stat-item">
        <span class="stat-value danger">
          {{ conclusions.filter(c => c.conclusion_type === 'material_misstatement').length }}
        </span>
        <span class="stat-label">重大错报</span>
      </div>
    </div>

    <!-- 按循环展示 -->
    <div class="cycle-grid">
      <div v-for="cs in cycleSummary" :key="cs.cycle" class="cycle-card">
        <div class="cycle-header">
          <span class="cycle-code">{{ cs.cycle }}</span>
          <span class="cycle-name">{{ cycleLabels[cs.cycle] || '' }}</span>
          <span class="cycle-count">{{ cs.total }}</span>
        </div>
        <div class="cycle-types">
          <el-tag
            v-for="(count, type) in cs.by_type"
            :key="type"
            :type="(typeColors[type] as any) || 'info'"
            size="small"
            effect="light"
          >
            {{ typeLabels[type] || type }}: {{ count }}
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 详细列表 -->
    <el-table
      :data="conclusions"
      size="small"
      stripe
      max-height="300"
      style="margin-top: 12px"
    >
      <el-table-column label="编码" prop="wp_code" width="80" />
      <el-table-column label="底稿名称" prop="wp_name" min-width="150" show-overflow-tooltip />
      <el-table-column label="结论" width="100">
        <template #default="{ row }">
          <el-tag :type="(typeColors[row.conclusion_type] as any) || 'info'" size="small">
            {{ row.conclusion_label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="结论内容" prop="conclusion_text" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="emit('navigate-wp', row.wp_id)">
            查看
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.conclusion-overview {
  padding: 12px;
}
.summary-bar {
  display: flex;
  gap: 24px;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--gt-color-bg);
  border-radius: 8px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.stat-value {
  font-size: 20px /* allow-px: special */;
  font-weight: 700;
  color: var(--gt-color-text-primary);
}
.stat-value.danger {
  color: var(--gt-color-coral);
}
.stat-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.cycle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}
.cycle-card {
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: 6px;
  padding: 8px 10px;
}
.cycle-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.cycle-code {
  font-weight: 700;
  font-size: var(--gt-font-size-sm);
  color: var(--el-color-primary);
}
.cycle-name {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.cycle-count {
  margin-left: auto;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.cycle-types {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
