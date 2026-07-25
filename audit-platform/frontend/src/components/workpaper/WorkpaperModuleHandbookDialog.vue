<script setup lang="ts">
/**
 * 底稿编制模块 · 使用手册弹窗
 * 对齐 E1/G1 PreparationHandbookDialog 范式（marked + DOMPurify 渲染 module-editing-handbook.md）。
 * 说明整个底稿编制模块流程：程序裁剪 → 生成 → 委派 → 编制 → 复核 → 归档 + 看板等视图。
 */
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import handbookMd from './handbooks/module-editing-handbook.md?raw'

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

function renderMd(md: string): string {
  if (!md) return ''
  try {
    const html = marked(md, { async: false }) as string
    return DOMPurify.sanitize(html)
  } catch {
    return `<pre>${md.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`
  }
}

const handbookHtml = computed(() => renderMd(handbookMd))

function close() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="📖 底稿编制模块 · 使用手册"
    width="900px"
    top="4vh"
    destroy-on-close
    append-to-body
    class="wp-module-handbook-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      type="success"
      :closable="false"
      show-icon
      class="mb12"
      title="一页读懂：程序裁剪 → 底稿生成 → 委派执行 → 编制 → 复核 → 归档。含裁剪功能与注意事项、委派人员与步骤、编制界面能力、看板等视图。"
    />
    <div class="guide-body prose" v-html="handbookHtml" />
    <template #footer>
      <el-button type="primary" @click="close">知道了</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.mb12 { margin-bottom: 12px; }
.guide-body {
  max-height: min(70vh, 720px);
  overflow-y: auto;
  padding: 4px 8px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: #303133;
}
.prose :deep(h1) {
  font-size: 18px;
  margin: 0 0 12px;
  color: #1f2a37;
}
.prose :deep(h2) {
  font-size: 15px;
  margin: 18px 0 8px;
  padding-left: 8px;
  border-left: 3px solid #4b2d77;
  color: #4b2d77;
}
.prose :deep(h3) {
  font-size: 14px;
  margin: 14px 0 6px;
  color: #303133;
}
.prose :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0 12px;
  font-size: 12px;
}
.prose :deep(th),
.prose :deep(td) {
  border: 1px solid #ebeef5;
  padding: 6px 8px;
  vertical-align: top;
}
.prose :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}
.prose :deep(ul),
.prose :deep(ol) {
  padding-left: 1.35em;
  margin: 6px 0;
}
.prose :deep(li) { margin: 3px 0; }
.prose :deep(code) {
  background: #f4f4f5;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}
.prose :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #f0a020;
  color: #606266;
  background: #fffbf0;
}
.prose :deep(hr) {
  border: none;
  border-top: 1px solid #ebeef5;
  margin: 16px 0;
}
</style>
