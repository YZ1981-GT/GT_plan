<template>
  <!-- E1 Sprint 2 Task 2.31: 弹窗顶部审计上下文（认定 + 风险等级 + E1A 程序编号） -->
  <div class="gt-audit-ctx-header">
    <div class="gt-audit-ctx-row">
      <span class="gt-audit-ctx-label">📋 程序编号:</span>
      <el-tag v-if="procedureCode" size="small" type="primary">{{ procedureCode }}</el-tag>
      <span v-else class="gt-audit-ctx-empty">—</span>
    </div>
    <div class="gt-audit-ctx-row">
      <span class="gt-audit-ctx-label">🎯 财务报表认定:</span>
      <el-tag
        v-for="a in assertions || []"
        :key="a"
        size="small"
        type="info"
        effect="plain"
      >{{ a }}</el-tag>
      <span v-if="!assertions || assertions.length === 0" class="gt-audit-ctx-empty">—</span>
    </div>
    <div class="gt-audit-ctx-row">
      <span class="gt-audit-ctx-label">⚠️ 风险等级:</span>
      <el-tag :type="riskTagType" size="small">{{ riskLevel || '—' }}</el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
/** Task 2.31 共享审计上下文头部 */
import { computed } from 'vue'

interface Props {
  procedureCode?: string
  assertions?: string[]
  riskLevel?: string
}
const props = defineProps<Props>()

const riskTagType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  const r = (props.riskLevel || '').toLowerCase()
  if (r.includes('高') || r === 'high') return 'danger'
  if (r.includes('中') || r === 'medium') return 'warning'
  if (r.includes('低') || r === 'low') return 'success'
  return 'info'
})
</script>

<style scoped>
.gt-audit-ctx-header {
  background: var(--gt-color-bg-page, #f8f7fc);
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
  padding: 6px 10px;
  margin-bottom: 8px;
  border-radius: 0 4px 4px 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.gt-audit-ctx-row {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
}
.gt-audit-ctx-label {
  color: var(--gt-color-text-secondary, #606266);
  min-width: 96px;
}
.gt-audit-ctx-empty {
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
