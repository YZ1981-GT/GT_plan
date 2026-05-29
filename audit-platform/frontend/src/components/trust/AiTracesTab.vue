<template>
  <div class="trust-ai-traces">
    <el-table v-if="entries && entries.length" :data="entries" border size="small" style="width: 100%">
      <el-table-column prop="model" label="模型" width="120" />
      <el-table-column prop="confirm_action" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusType(row.confirm_action)" size="small">
            {{ statusLabel(row.confirm_action) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="confidence" label="置信度" width="80" align="right">
        <template #default="{ row }">
          {{ row.confidence != null ? (row.confidence * 100).toFixed(1) + '%' : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="generated_at" label="生成时间" width="170">
        <template #default="{ row }">
          {{ row.generated_at ? new Date(row.generated_at).toLocaleString('zh-CN') : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="content_preview" label="内容预览" min-width="200" show-overflow-tooltip />
    </el-table>
    <el-empty v-else description="暂无 AI 介入记录" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  entries: Array<{
    id: string
    model: string
    confidence: number | null
    confirm_action: string
    generated_at: string | null
    target_cell: string | null
    content_preview: string
  }> | undefined
}>()

function statusType(action: string) {
  switch (action) {
    case 'confirmed': return 'success'
    case 'revised': return 'warning'
    case 'rejected': return 'danger'
    default: return 'info'
  }
}

function statusLabel(action: string) {
  switch (action) {
    case 'pending': return '待确认'
    case 'confirmed': return '已确认'
    case 'revised': return '已修订'
    case 'rejected': return '已拒绝'
    default: return action
  }
}
</script>

<style scoped>
.trust-ai-traces {
  padding: 12px 0;
}
</style>
