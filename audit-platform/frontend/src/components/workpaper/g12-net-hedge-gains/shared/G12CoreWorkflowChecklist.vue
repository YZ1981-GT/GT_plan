<script setup lang="ts">
import type { G12WorkflowReadiness } from '../composables/g12CoreWorkflowReadiness'

withDefaults(defineProps<{
  readiness: G12WorkflowReadiness
  compact?: boolean
}>(), {
  compact: false,
})
</script>

<template>
  <el-card shadow="never" class="g12-workflow-checklist" data-testid="g12-workflow-checklist">
    <template #header>
      <div class="checklist-head">
        <span>闭环就绪</span>
        <el-tag :type="readiness.allOk ? 'success' : 'warning'" size="small">
          {{ readiness.doneCount }}/{{ readiness.items.length }}
        </el-tag>
        <el-progress
          :percentage="readiness.pct"
          :stroke-width="6"
          :status="readiness.allOk ? 'success' : undefined"
          class="checklist-progress"
        />
      </div>
    </template>
    <ul class="checklist-items" :class="{ compact }">
      <li
        v-for="item in readiness.items"
        :key="item.key"
        class="checklist-item"
        :class="{ ok: item.ok, pending: !item.ok }"
        :data-testid="`g12-workflow-item-${item.stepIndex}`"
      >
        <span class="check-icon" :aria-label="item.ok ? '已完成' : '未完成'">{{ item.ok ? '✓' : '○' }}</span>
        <span class="check-label">{{ item.label }}</span>
        <span v-if="!item.ok && item.hint && !compact" class="check-hint">{{ item.hint }}</span>
      </li>
    </ul>
  </el-card>
</template>

<style scoped>
.g12-workflow-checklist { margin-bottom: 12px; }
.checklist-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-weight: 600;
  font-size: 13px;
}
.checklist-progress { flex: 1; min-width: 120px; max-width: 200px; }
.checklist-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.checklist-items.compact {
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}
.checklist-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  padding: 4px 0;
}
.checklist-item.ok .check-label { color: #529b2e; }
.checklist-item.pending .check-label { color: #606266; }
.check-icon {
  flex-shrink: 0;
  width: 16px;
  text-align: center;
  font-weight: 700;
}
.checklist-item.ok .check-icon { color: #67c23a; }
.checklist-item.pending .check-icon { color: #c0c4cc; }
.check-hint { color: #909399; font-size: 11px; margin-left: auto; text-align: right; max-width: 45%; }
</style>
