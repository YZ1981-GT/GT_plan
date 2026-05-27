<template>
  <div class="trust-history">
    <el-table v-if="entries && entries.length" :data="entries" border size="small" style="width: 100%">
      <el-table-column prop="action" label="操作" width="120" />
      <el-table-column prop="timestamp" label="时间" width="180">
        <template #default="{ row }">
          {{ row.timestamp ? new Date(row.timestamp).toLocaleString('zh-CN') : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="user_id" label="用户" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.user_id ? row.user_id.slice(0, 8) + '...' : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="详情" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.details ? JSON.stringify(row.details).slice(0, 80) : '-' }}
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无修改历史" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  entries: Array<{
    id: string
    action: string
    user_id: string | null
    timestamp: string | null
    details: any
  }> | undefined
}>()
</script>

<style scoped>
.trust-history {
  padding: 12px 0;
}
</style>
