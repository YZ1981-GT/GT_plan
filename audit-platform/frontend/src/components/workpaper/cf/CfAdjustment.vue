<template>
  <div class="cf-adjustment">
    <p class="cf-adjustment-desc">
      CF 调整分录复用调整分录模块（adjustment_type='cf'）。
      请前往调整分录页面录入 CF 调整。
    </p>
    <el-button type="primary" size="small" @click="goToAdjustments">
      前往调整分录
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const props = defineProps<{ projectId: string; year: number }>()
const router = useRouter()

function goToAdjustments() {
  router.push({
    name: 'adjustments',
    params: { projectId: props.projectId },
    query: { type: 'cf' },
  })
}
</script>

<style scoped>
.cf-adjustment-desc { color: var(--el-text-color-secondary); margin-bottom: 12px; }
</style>
