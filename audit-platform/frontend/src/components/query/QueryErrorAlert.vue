<!--
  QueryErrorAlert — 查询失败的持久提示（advanced-query-linkage-closure 任务 28 / 29；R11.1、R11.2，AQ-09 / AQ-29）

  弹窗与页面版共用：标题「查询失败」+ `describeQueryError` 的中文原因 + 可复制的追踪号。失败不落到「暂无数据」空态；
  请求带 `_silent`，确定性错误不经全局拦截器自动重试、不弹「服务器暂时异常，正在重试...」。
-->
<template>
  <el-alert type="error" :closable="false" show-icon class="gt-qea" data-testid="cq-query-error">
    <template #title>{{ title }}</template>
    <div class="gt-qea-message" data-testid="cq-query-error-message">{{ error.message }}</div>
    <div v-if="error.correlationId" class="gt-qea-trace">
      追踪号：<span class="gt-qea-trace-id">{{ error.correlationId }}</span>
      <el-button link type="primary" size="small" aria-label="复制追踪号" data-testid="cq-copy-trace" @click="copyTrace">
        复制追踪号
      </el-button>
    </div>
  </el-alert>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import type { QueryErrorText } from './queryErrorText'

const props = withDefaults(defineProps<{ error: QueryErrorText; title?: string }>(), { title: '查询失败' })

async function copyTrace() {
  const id = props.error.correlationId
  if (!id) return
  try {
    await navigator.clipboard.writeText(id)
    ElMessage.success('已复制追踪号')
  } catch {
    ElMessage.warning(`复制失败，请手动复制：${id}`)
  }
}
</script>

<style scoped>
.gt-qea { margin-bottom: 8px; }
.gt-qea-message { white-space: pre-wrap; word-break: break-all; }
.gt-qea-trace { margin-top: 4px; font-size: var(--gt-font-size-xs); }
.gt-qea-trace-id { font-family: Consolas, Monaco, monospace; }
</style>
