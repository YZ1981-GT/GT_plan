<!--
  QueryRowActions — 业务视图结果行操作列：「打开」「复制引用」（advanced-query-linkage-closure 任务 28 / 29；R7.1~R7.3、N5）

  弹窗与页面版共用；规则在 useQueryRowLinks / queryResultLinks。复制引用不可用时按钮置灰、悬停显示原因（禁用的按钮不触发
  悬停，提示挂在外层 span 上）。只读：没有回写入口（R7.5）。
-->
<template>
  <span class="gt-qra">
    <el-button
      v-if="drill"
      link
      type="primary"
      size="small"
      :title="drill.label"
      :aria-label="drill.label"
      data-testid="cq-row-open"
      @click="emit('open')"
    >打开</el-button>
    <el-tooltip v-if="refText" :content="refHint" placement="top">
      <span class="gt-qra-ref">
        <el-button
          link
          type="primary"
          size="small"
          :disabled="!refUsable"
          :aria-label="`复制引用 ${refText}`"
          data-testid="cq-row-copy-ref"
          @click="emit('copy-ref')"
        >复制引用</el-button>
      </span>
    </el-tooltip>
    <span v-if="!drill && !refText" class="gt-qra-none">—</span>
  </span>
</template>

<script setup lang="ts">
import type { RowDrill } from './queryResultLinks'

defineProps<{
  drill: RowDrill | null
  refText: string | null
  refUsable: boolean
  refHint: string
}>()
const emit = defineEmits<{ open: []; 'copy-ref': [] }>()
</script>

<style scoped>
.gt-qra { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.gt-qra-ref { display: inline-flex; }
.gt-qra-none { color: var(--gt-color-text-tertiary); }
</style>
