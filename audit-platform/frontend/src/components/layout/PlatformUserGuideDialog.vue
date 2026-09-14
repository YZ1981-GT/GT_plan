<template>
  <el-dialog
    v-model="visible"
    title="📖 审计平台使用手册"
    width="800px"
    top="5vh"
    append-to-body
    destroy-on-close
    class="gt-platform-guide-dialog"
  >
    <div class="gt-platform-guide" v-html="renderedContent"></div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import guideRaw from './handbooks/platform-user-guide.md?raw'

const visible = ref(false)

const renderedContent = computed(() => {
  const html = marked(guideRaw) as string
  return DOMPurify.sanitize(html)
})

function open() {
  visible.value = true
}

defineExpose({ open })
</script>

<style scoped>
.gt-platform-guide-dialog :deep(.el-dialog__body) {
  max-height: 75vh;
  overflow-y: auto;
  padding: 16px 24px;
}

.gt-platform-guide {
  font-size: 14px;
  line-height: 1.8;
  color: var(--el-text-color-primary);
}

.gt-platform-guide :deep(h1) {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--el-color-primary);
}

.gt-platform-guide :deep(h2) {
  font-size: 18px;
  font-weight: 600;
  margin: 28px 0 12px;
  padding-left: 10px;
  border-left: 4px solid var(--el-color-primary);
}

.gt-platform-guide :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  margin: 20px 0 8px;
  color: var(--el-color-primary);
}

.gt-platform-guide :deep(h4) {
  font-size: 14px;
  font-weight: 600;
  margin: 16px 0 6px;
}

.gt-platform-guide :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}

.gt-platform-guide :deep(th),
.gt-platform-guide :deep(td) {
  border: 1px solid var(--el-border-color-lighter);
  padding: 8px 12px;
  text-align: left;
}

.gt-platform-guide :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.gt-platform-guide :deep(tr:hover td) {
  background: var(--el-fill-color-lighter);
}

.gt-platform-guide :deep(code) {
  background: var(--el-fill-color-light);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
  font-family: 'Consolas', 'Monaco', monospace;
}

.gt-platform-guide :deep(pre) {
  background: #f8f9fa;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 14px 16px;
  overflow-x: auto;
  margin: 12px 0;
  font-size: 12px;
  line-height: 1.6;
}

.gt-platform-guide :deep(pre code) {
  background: none;
  padding: 0;
}

.gt-platform-guide :deep(blockquote) {
  margin: 12px 0;
  padding: 10px 16px;
  border-left: 4px solid var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
  border-radius: 0 6px 6px 0;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.gt-platform-guide :deep(ol),
.gt-platform-guide :deep(ul) {
  padding-left: 20px;
  margin: 8px 0;
}

.gt-platform-guide :deep(li) {
  margin: 4px 0;
}

.gt-platform-guide :deep(hr) {
  border: none;
  border-top: 1px solid var(--el-border-color-lighter);
  margin: 20px 0;
}

.gt-platform-guide :deep(strong) {
  color: var(--el-text-color-primary);
}

.gt-platform-guide :deep(a) {
  color: var(--el-color-primary);
  text-decoration: none;
}

.gt-platform-guide :deep(a:hover) {
  text-decoration: underline;
}
</style>
