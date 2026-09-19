<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import usageMd from '../handbooks/g6-10-usage.md?raw'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const usageHtml = computed(() => {
  try {
    return DOMPurify.sanitize(marked(usageMd, { async: false }) as string)
  } catch {
    return `<pre>${usageMd.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`
  }
})
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="G6-10 盘点倒轧表 · 使用说明"
    width="860px"
    top="4vh"
    destroy-on-close
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      type="success"
      :closable="false"
      show-icon
      class="guide-alert"
      title="推荐路径：G6-2 维护账面持仓 → G6-9 完成盘点 → G6-10 带入盘点和账面 → 维护增减明细 → 闭环差异。"
    />
    <div class="guide-body prose" v-html="usageHtml" />
    <template #footer>
      <el-button type="primary" @click="emit('update:modelValue', false)">知道了</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.guide-alert {
  margin-bottom: 12px;
}

.guide-body {
  max-height: min(68vh, 700px);
  overflow-y: auto;
  padding: 4px 10px 18px;
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
}

.prose :deep(h1) {
  margin: 0 0 12px;
  font-size: 19px;
  color: #1f2a37;
}

.prose :deep(h2) {
  margin: 20px 0 8px;
  padding-left: 9px;
  border-left: 3px solid #4b2d77;
  font-size: 15px;
  color: #4b2d77;
}

.prose :deep(h3) {
  margin: 14px 0 6px;
  font-size: 14px;
}

.prose :deep(p) {
  margin: 6px 0;
}

.prose :deep(ul),
.prose :deep(ol) {
  margin: 6px 0;
  padding-left: 1.5em;
}

.prose :deep(li) {
  margin: 3px 0;
}

.prose :deep(blockquote) {
  margin: 8px 0;
  padding: 7px 12px;
  border-left: 3px solid #c0c4cc;
  background: #fafafa;
  color: #606266;
}
</style>
