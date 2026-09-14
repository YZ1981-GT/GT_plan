<script setup lang="ts">
/**
 * 账套导入 · 使用文档弹窗
 * 覆盖 上传 → 识别预检 → 列映射 → 解析入库 全流程 + 映射规则 + 各功能点说明。
 * 渲染 handbooks/ledger-import-guide.md（marked + DOMPurify，单页可滚动）。
 */
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import guideMd from './handbooks/ledger-import-guide.md?raw'

const props = defineProps<{ modelValue: boolean }>()
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

const guideHtml = computed(() => renderMd(guideMd))

function close() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="账套导入 · 使用文档"
    width="900px"
    top="4vh"
    destroy-on-close
    append-to-body
    class="ledger-import-guide-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      type="success"
      :closable="false"
      show-icon
      class="mb12"
      title="一句话：上传账套文件 → 系统自动识别表类型与列 → 人工核对列映射 → 解析校验后入库为四表 → 自动完成科目映射与试算表。本文档说明每一步操作、映射规则与背后机制。"
    />
    <div class="guide-body prose" v-html="guideHtml" />
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
  padding: 4px 10px 16px;
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
}
.prose :deep(h1) {
  font-size: 18px;
  margin: 0 0 12px;
  color: #1f2a37;
}
.prose :deep(h2) {
  font-size: 15px;
  margin: 20px 0 8px;
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
.prose :deep(strong) { color: #4b2d77; }
.prose :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #e6a23c;
  color: #7c5c1e;
  background: #fdf6ec;
}
.prose :deep(hr) {
  border: none;
  border-top: 1px solid #ebeef5;
  margin: 18px 0;
}
</style>
