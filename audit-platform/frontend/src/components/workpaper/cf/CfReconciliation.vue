<template>
  <div class="cf-reconciliation">
    <el-button type="primary" size="small" :loading="loading" @click="fetchData">刷新核查</el-button>
    <template v-if="data">
      <el-descriptions :column="2" border style="margin-top: 12px">
        <el-descriptions-item label="BS 货币资金期末">{{ data.bs_end }}</el-descriptions-item>
        <el-descriptions-item label="BS 货币资金期初">{{ data.bs_begin }}</el-descriptions-item>
        <el-descriptions-item label="CF 现金净增加额">{{ data.cf_net }}</el-descriptions-item>
        <el-descriptions-item label="BS差异（期末-期初-CF净增加）">
          <span :class="{ 'cf-diff-warn': !data.bs_pass }">{{ data.bs_diff }}</span>
          <el-tag :type="data.bs_pass ? 'success' : 'danger'" size="small" style="margin-left: 8px">
            {{ data.bs_pass ? '通过' : '有差异' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-divider>三项活动勾稽</el-divider>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="经营活动净额">{{ data.operating }}</el-descriptions-item>
        <el-descriptions-item label="投资活动净额">{{ data.investing }}</el-descriptions-item>
        <el-descriptions-item label="筹资活动净额">{{ data.financing }}</el-descriptions-item>
        <el-descriptions-item label="汇率影响">{{ data.exchange }}</el-descriptions-item>
        <el-descriptions-item label="三项合计">{{ data.activity_sum }}</el-descriptions-item>
        <el-descriptions-item label="差异">
          <span :class="{ 'cf-diff-warn': !data.activity_pass }">{{ data.activity_diff }}</span>
          <el-tag :type="data.activity_pass ? 'success' : 'danger'" size="small" style="margin-left: 8px">
            {{ data.activity_pass ? '通过' : '有差异' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
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
    data.value = await apiProxy.get(`/api/projects/${props.projectId}/cf-verification/${props.year}/reconcile`)
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.cf-diff-warn { color: var(--el-color-danger); font-weight: bold; }
</style>
