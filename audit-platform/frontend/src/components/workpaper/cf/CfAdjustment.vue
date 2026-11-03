<template>
  <div class="cf-adjustment">
    <p class="cf-adjustment-desc">
      现金流量相关的调整统一在调整分录模块按审计调整 / 重分类录入、提交复核，批准后计入试算表与报表。
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
  // 路由名原写成小写 'adjustments'（不存在）⇒ 点击即报「没有匹配的路由」
  router.push({
    name: 'Adjustments',
    params: { projectId: props.projectId },
    query: props.year ? { year: String(props.year) } : undefined,
  }).catch(() => { /* 导航被取消 */ })
}
</script>

<style scoped>
.cf-adjustment-desc { color: var(--el-text-color-secondary); margin-bottom: 12px; }
</style>
