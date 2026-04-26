<template>
  <div class="gt-aux-summary gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">辅助余额表汇总匹配</h2>
      <el-input-number v-model="year" :min="2020" :max="2030" @change="fetch" style="width: 120px" />
    </div>
    <el-table :data="items" stripe :row-class-name="rowClass">
      <el-table-column prop="account_code" label="科目编码" width="120" />
      <el-table-column prop="account_name" label="科目名称" />
      <el-table-column prop="tb_balance" label="科目余额" width="140" align="right">
        <template #default="{ row }">{{ row.tb_balance?.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column prop="aux_summary" label="辅助汇总" width="140" align="right">
        <template #default="{ row }">{{ row.aux_summary?.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column prop="diff" label="差异" width="120" align="right">
        <template #default="{ row }">
          <span :style="{ color: row.is_matched ? 'inherit' : 'var(--el-color-danger)' }">{{ row.diff?.toLocaleString() }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_matched ? 'success' : 'danger'" size="small">{{ row.is_matched ? '一致' : '差异' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <div class="gt-summary-stats" v-if="items.length">
      <span>共 {{ items.length }} 个科目，一致 {{ items.filter(i => i.is_matched).length }}，差异 {{ items.filter(i => !i.is_matched).length }}</span>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { auxSummary } from '@/services/enhancedApi'
const route = useRoute()
const projectId = ref(route.params.projectId as string || '')
const year = ref(2025)
const items = ref<any[]>([])
function rowClass({ row }: any) { return row.is_matched ? '' : 'gt-row-mismatch' }
async function fetch() { if (projectId.value) items.value = await auxSummary(projectId.value, year.value) }
onMounted(fetch)
</script>
<style scoped>
.gt-aux-summary { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-summary-stats { margin-top: var(--gt-space-2); font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
:deep(.gt-row-mismatch) { background-color: #fff1f0 !important; }
</style>
