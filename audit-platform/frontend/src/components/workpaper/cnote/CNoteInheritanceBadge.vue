<template>
  <div v-if="statuses.length" class="gt-cnt__rule-status">
    <el-tooltip
      v-for="rs in statuses"
      :key="rs.ruleId"
      :content="rs.tooltip"
      placement="top"
    >
      <el-tag
        size="small"
        :type="ruleStatusTagType(rs)"
        effect="light"
        class="gt-cnt__rule-tag"
      >
        <el-icon><component :is="ruleStatusIcon(rs)" /></el-icon>
        <span>{{ rs.label }}</span>
      </el-tag>
    </el-tooltip>
  </div>
</template>

<script setup lang="ts">
import { ElIcon } from 'element-plus'
import {
  CircleCheckFilled,
  CircleCloseFilled,
  WarningFilled,
  InfoFilled,
} from '@element-plus/icons-vue'
import type { RuleStatus } from '../GtCNoteTable.types'

defineProps<{
  statuses: RuleStatus[]
}>()

function ruleStatusTagType(rs: RuleStatus): 'success' | 'warning' | 'danger' | 'info' {
  if (rs.status === 'ok') return 'success'
  if (rs.status === 'mismatch') return 'danger'
  if (rs.status === 'warning') return 'warning'
  return 'info'
}

function ruleStatusIcon(rs: RuleStatus) {
  if (rs.status === 'ok') return CircleCheckFilled
  if (rs.status === 'mismatch') return CircleCloseFilled
  if (rs.status === 'warning') return WarningFilled
  return InfoFilled
}
</script>

<style scoped>
.gt-cnt__rule-status {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--el-color-info-light-9);
  border-radius: 4px;
}

.gt-cnt__rule-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
