<!--
  EvidenceGroupExpand.vue — 抽凭行展开显示多原始凭证 + 提取字段
  
  Spec: wp-evidence-collection Task 4.2
  用于 el-table 的 expand 行，显示 evidence_group 数组中的多份原始凭证
-->
<template>
  <div class="gt-evidence-group">
    <div v-if="!evidenceGroup || evidenceGroup.length === 0" class="gt-evidence-group__empty">
      暂无关联原始凭证
    </div>
    <div v-else class="gt-evidence-group__list">
      <div class="gt-evidence-group__header">
        关联原始凭证（{{ evidenceGroup.length }} 份）
      </div>
      <el-table :data="evidenceGroup" border size="small" class="gt-evidence-group__table">
        <el-table-column prop="attachment_id" label="附件ID" width="120">
          <template #default="{ row }">
            <span class="gt-evidence-group__att-id">
              {{ row.attachment_id ? row.attachment_id.slice(0, 8) + '...' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="voucher_no" label="凭证号" width="120" />
        <el-table-column prop="voucher_date" label="日期" width="110" />
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{ row }">
            {{ row.amount != null ? Number(row.amount).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="150" show-overflow-tooltip />
        <el-table-column prop="confidence" label="置信度" width="80" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="row.confidence != null"
              :type="row.confidence >= 0.8 ? 'success' : row.confidence >= 0.5 ? 'warning' : 'danger'"
              size="small"
            >
              {{ (row.confidence * 100).toFixed(0) }}%
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="80">
          <template #default="{ row }">
            <el-tag size="small" type="info">
              {{ sourceLabel(row.source) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  evidenceGroup: Array<{
    attachment_id?: string
    voucher_no?: string
    voucher_date?: string
    amount?: number | string
    summary?: string
    confidence?: number
    source?: string
  }>
}>()

function sourceLabel(source?: string) {
  switch (source) {
    case 'ocr': return 'OCR'
    case 'llm': return 'LLM'
    case 'manual': return '手动'
    case 'legacy_migration': return '迁移'
    default: return source || '-'
  }
}
</script>

<style scoped>
.gt-evidence-group {
  padding: 8px 16px;
}
.gt-evidence-group__empty {
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 12px;
}
.gt-evidence-group__header {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.gt-evidence-group__table {
  margin-top: 4px;
}
.gt-evidence-group__att-id {
  font-family: monospace;
  font-size: 11px;
}
</style>
