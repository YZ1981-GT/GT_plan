<template>
  <div class="cf-cash-equivalents">
    <el-button type="primary" size="small" :loading="loading" @click="fetchData">刷新核查</el-button>
    <template v-if="data">
      <el-table :data="data.items" class="gt-compact-table" style="margin-top: 12px">
        <el-table-column prop="account_code" label="科目编码" width="120" />
        <el-table-column prop="begin" label="期初余额" align="right" />
        <el-table-column prop="end" label="期末余额" align="right" />
      </el-table>
      <div class="cf-summary">
        <span>TB 合计：{{ data.total }}</span>
        <span>BS 货币资金：{{ data.bs_cash }}</span>
        <span :class="{ 'cf-diff-warn': !data.pass }">差异：{{ data.difference }}</span>
        <el-tag :type="data.pass ? 'success' : 'danger'" size="small">{{ data.pass ? '通过' : '有差异' }}</el-tag>
      </div>
      <p v-if="data.restricted_note" class="cf-note">{{ data.restricted_note }}</p>
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
    data.value = await apiProxy.get(`/api/projects/${props.projectId}/cf-verification/${props.year}/cash-equivalents`)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.cf-summary { margin-top: 12px; display: flex; gap: 16px; align-items: center; }
.cf-diff-warn { color: var(--el-color-danger); font-weight: bold; }
.cf-note { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 8px; }
</style>
