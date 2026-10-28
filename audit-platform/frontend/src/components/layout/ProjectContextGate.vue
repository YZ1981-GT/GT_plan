<template>
  <slot v-if="!pending && !failed" />
  <div v-else-if="pending" class="gt-project-context-gate" role="status" aria-live="polite">
    <el-icon class="is-loading"><Loading /></el-icon>
    <span>正在读取项目信息…</span>
  </div>
  <el-result
    v-else
    icon="warning"
    title="读取项目信息失败"
    sub-title="没取到项目的审计年度，页面先不加载，免得按错误的年度取数"
  >
    <template #extra>
      <el-button type="primary" :loading="retrying" @click="onRetry">重试</el-button>
    </template>
  </el-result>
</template>

<script setup lang="ts">
/**
 * 项目页挂载闸门（spec post-push-residual-defect-closure 6.5.2）。
 *
 * 换项目且路由没带年度时，项目 store 先把年度清成 null，取到项目信息后才定（审计年度，没填为 null）。
 * 页面若在这之前挂载，读到的 null 是「还没取到」而不是「没填」，提示「未设置审计年度」是误导；
 * 原先更糟：store 年度初值是去年，页面就静默按去年 / 上一个项目的年度取数。
 * 这里在年度定下来之前不渲染页面；取失败给重试，不让页面把它当成没填。
 */
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const projectStore = useProjectStore()

const onProjectPage = computed(() => !!route.params.projectId)
const pending = computed(() => onProjectPage.value && projectStore.yearStatus === 'loading')
const failed = computed(() => onProjectPage.value && projectStore.yearStatus === 'failed')
const retrying = ref(false)

async function onRetry() {
  retrying.value = true
  try {
    await projectStore.retryProjectContext()
  } finally {
    retrying.value = false
  }
}
</script>

<style scoped>
.gt-project-context-gate {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--gt-space-2, 8px);
  padding: var(--gt-space-8, 48px) 0;
  color: var(--gt-color-text-secondary);
}
</style>
