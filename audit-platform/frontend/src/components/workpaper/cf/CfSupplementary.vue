<template>
  <div class="cf-supplementary">
    <el-button type="primary" size="small" :loading="loading" @click="fetchData">刷新核查</el-button>
    <template v-if="data">
      <el-table :data="data.items" class="gt-compact-table" style="margin-top: 12px">
        <el-table-column prop="item" label="调整项" min-width="250" />
        <el-table-column prop="row_code" label="行号" width="100" />
        <el-table-column prop="value" label="原始值" align="right" width="130" />
        <el-table-column label="符号" width="60" align="center">
          <template #default="{ row }">{{ row.sign > 0 ? '+' : '−' }}</template>
        </el-table-column>
        <el-table-column prop="signed_value" label="调节值" align="right" width="130" />
      </el-table>
      <div class="cf-summary">
        <span>间接法合计：{{ data.indirect_total }}</span>
        <span>主表经营CF：{{ data.direct_operating }}</span>
        <span :class="{ 'cf-diff-warn': !data.pass }">差异：{{ data.difference }}</span>
        <el-tag :type="data.pass ? 'success' : 'danger'" size="small">{{ data.pass ? '通过' : '有差异' }}</el-tag>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiProxy } from '@/utils/apiProxy'

const props = defineProps<{ projectId: string; year: number }>()
const loading = ref(false)
const data = ref<any>(null)

async function fetchData() {
  loading.value = true
  try {
    data.value = await apiProxy.get(`/api/projects/${props.projectId}/cf-verification/${props.year}/supplementary`)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.cf-summary { margin-top: 12px; display: flex; gap: 16px; align-items: center; }
.cf-diff-warn { color: var(--el-color-danger); font-weight: bold; }
</style>
