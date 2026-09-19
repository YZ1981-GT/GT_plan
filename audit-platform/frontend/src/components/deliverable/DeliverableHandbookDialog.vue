<template>
  <el-dialog
    v-model="visible"
    title="交付件管理中心 · 使用手册"
    width="780px"
    top="5vh"
    :close-on-click-modal="false"
    destroy-on-close
  >
    <div class="handbook-content" v-html="renderedHtml" />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import handbookRaw from '@/components/workpaper/handbooks/deliverable-center-handbook.md?raw'

const visible = defineModel<boolean>('visible', { default: false })

const renderedHtml = computed(() => {
  try {
    const raw = marked(handbookRaw) as string
    return DOMPurify.sanitize(raw)
  } catch {
    return '<p>手册内容加载失败</p>'
  }
})
</script>

<style scoped>
.handbook-content {
  max-height: 72vh;
  overflow-y: auto;
  padding: 0 8px;
  font-size: 14px;
  line-height: 1.75;
}
.handbook-content :deep(h1) {
  font-size: 20px;
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.handbook-content :deep(h2) {
  font-size: 17px;
  margin: 24px 0 10px;
  color: var(--el-color-primary);
}
.handbook-content :deep(h3) {
  font-size: 15px;
  margin: 18px 0 8px;
}
.handbook-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}
.handbook-content :deep(th),
.handbook-content :deep(td) {
  border: 1px solid var(--el-border-color-lighter);
  padding: 6px 10px;
  text-align: left;
}
.handbook-content :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}
.handbook-content :deep(code) {
  background: var(--el-fill-color-lighter);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}
.handbook-content :deep(blockquote) {
  border-left: 3px solid var(--el-color-primary-light-5);
  margin: 12px 0;
  padding: 8px 14px;
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-regular);
}
.handbook-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--el-border-color-lighter);
  margin: 20px 0;
}
.handbook-content :deep(ul),
.handbook-content :deep(ol) {
  padding-left: 20px;
}
.handbook-content :deep(li) {
  margin: 4px 0;
}
.handbook-content :deep(strong) {
  color: var(--el-text-color-primary);
}
</style>
