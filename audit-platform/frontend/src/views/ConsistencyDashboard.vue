<template>
  <div class="gt-consistency gt-fade-in">
    <div class="gt-cons-header">
      <h2 class="gt-page-title">全链路一致性校验</h2>
      <el-button type="primary" @click="runCheck" :loading="loading">运行校验</el-button>
    </div>

    <!-- 整体状态 -->
    <el-alert v-if="result && result.all_consistent" type="success" title="全部校验通过" show-icon
      style="margin-bottom: 16px" />
    <el-alert v-else-if="result && !result.all_consistent" type="warning" show-icon
      style="margin-bottom: 16px">
      <template #title>
        {{ result.checks.filter((c: any) => !c.passed).length }} 项校验未通过
      </template>
    </el-alert>

    <!-- 5 个校验卡片 -->
    <el-row :gutter="16">
      <el-col :span="8" v-for="check in (result?.checks || [])" :key="check.check_name" style="margin-bottom: 16px">
        <div class="gt-check-card" :class="{ 'gt-check-pass': check.passed, 'gt-check-fail': !check.passed }">
          <div class="gt-check-icon">{{ check.passed ? '✅' : '⚠️' }}</div>
          <div class="gt-check-name">{{ check.check_name }}</div>
          <div class="gt-check-detail">
            {{ check.passed ? '全部一致' : `${check.failed_items.length} 项不一致` }}
          </div>
          <div class="gt-check-count">{{ check.passed_items }} / {{ check.total_items }}</div>
          <!-- 不一致明细 -->
          <div v-if="!check.passed && check.failed_items.length" class="gt-check-failures">
            <div v-for="(f, i) in check.failed_items.slice(0, 5)" :key="i" class="gt-failure-item">
              {{ f.message || f.entity_id }}
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div v-if="result" class="gt-cons-footer">
      校验时间：{{ result.checked_at }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { runConsistencyCheck, getConsistencyCheck } from '@/services/commonApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const loading = ref(false)
const result = ref<any>(null)

async function runCheck() {
  loading.value = true
  try {
    result.value = await runConsistencyCheck(projectId.value)
  } finally { loading.value = false }
}

onMounted(async () => {
  loading.value = true
  try {
    result.value = await getConsistencyCheck(projectId.value)
  } catch { /* first time, no data */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.gt-consistency { padding: var(--gt-space-4); }
.gt-cons-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
.gt-check-card {
  background: white; border-radius: var(--gt-radius-md); padding: 20px; text-align: center;
  box-shadow: var(--gt-shadow-sm); border-top: 3px solid #ddd; min-height: 140px;
}
.gt-check-pass { border-top-color: #28a745; }
.gt-check-fail { border-top-color: #FF5149; }
.gt-check-icon { font-size: 28px; margin-bottom: 8px; }
.gt-check-name { font-size: 14px; font-weight: 600; color: #333; margin-bottom: 4px; }
.gt-check-detail { font-size: 13px; color: #666; }
.gt-check-count { font-size: 12px; color: #999; margin-top: 4px; }
.gt-check-failures { margin-top: 8px; text-align: left; }
.gt-failure-item { font-size: 12px; color: #FF5149; padding: 2px 0; }
.gt-cons-footer { margin-top: 16px; font-size: 12px; color: #999; text-align: right; }
</style>
