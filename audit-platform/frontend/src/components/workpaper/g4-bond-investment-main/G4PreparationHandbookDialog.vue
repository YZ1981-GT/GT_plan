<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import preparationMd from './handbooks/preparation.md?raw'
import usageMd from './handbooks/usage.md?raw'

const props = defineProps<{ modelValue: boolean; initialTab?: 'preparation' | 'usage' }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
const activeTab = ref<'preparation' | 'usage'>(props.initialTab || 'preparation')

watch(
  () => [props.modelValue, props.initialTab] as const,
  ([open, tab]) => { if (open) activeTab.value = tab || 'preparation' },
)

function renderMd(markdown: string): string {
  try {
    return DOMPurify.sanitize(marked(markdown, { async: false }) as string)
  } catch {
    return `<pre>${markdown.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`
  }
}

const preparationHtml = computed(() => renderMd(preparationMd))
const usageHtml = computed(() => renderMd(usageMd))
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="G4 债权投资 · 编制手册"
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
      class="mb12"
      title="主线：G4-2 明细与 G4-1 审定勾稽，分类/SPPI 与盘点取证，ECL 评估后将例外汇入 G4-3。"
    />
    <el-tabs v-model="activeTab">
      <el-tab-pane label="编制手册" name="preparation">
        <div class="guide-body prose" v-html="preparationHtml" />
      </el-tab-pane>
      <el-tab-pane label="使用手册" name="usage">
        <div class="guide-body prose" v-html="usageHtml" />
      </el-tab-pane>
    </el-tabs>
    <template #footer>
      <el-button type="primary" @click="emit('update:modelValue', false)">知道了</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.mb12 { margin-bottom: 12px; }
.guide-body {
  max-height: min(62vh, 640px);
  overflow-y: auto;
  padding: 4px 8px 16px;
  font-size: 13px;
  line-height: 1.65;
  color: #303133;
}
.prose :deep(h1) { margin: 0 0 12px; font-size: 18px; color: #1f2a37; }
.prose :deep(h2) {
  margin: 18px 0 8px;
  padding-left: 8px;
  border-left: 3px solid #4b2d77;
  font-size: 15px;
  color: #4b2d77;
}
.prose :deep(h3) { margin: 14px 0 6px; font-size: 14px; }
.prose :deep(ul),
.prose :deep(ol) { margin: 6px 0; padding-left: 1.35em; }
.prose :deep(li) { margin: 3px 0; }
.prose :deep(code) { padding: 1px 4px; border-radius: 3px; background: #f4f4f5; font-size: 12px; }
.prose :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #c0c4cc;
  background: #fafafa;
  color: #606266;
}
</style>
