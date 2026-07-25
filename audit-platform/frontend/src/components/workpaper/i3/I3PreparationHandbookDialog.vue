<script setup lang="ts">
/**
 * I3 编制/使用手册弹窗 — 对齐 I1PreparationHandbookDialog，渲染 handbooks/*.md
 */
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
  ([open, tab]) => {
    if (open) activeTab.value = tab || 'preparation'
  },
)

function renderMd(md: string): string {
  if (!md) return ''
  try {
    const html = marked(md, { async: false }) as string
    return DOMPurify.sanitize(html)
  } catch {
    return `<pre>${md.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`
  }
}

const preparationHtml = computed(() => renderMd(preparationMd))
const usageHtml = computed(() => renderMd(usageMd))

function close() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="I3 商誉 · 编制手册"
    width="860px"
    top="4vh"
    destroy-on-close
    append-to-body
    class="i3-handbook-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      type="success"
      :closable="false"
      show-icon
      class="mb12"
      title="一句话：1711 商誉不摊销、仅年度减值；I3-6 资产组CGU减值测试 + I3-7 DCF可收回金额 → I3-1 审定。减值先冲商誉、剩余再按比例分摊至资产组其他资产（不可转回）。审定期末回写 TB(1711) 并驱动附注披露。本弹窗不改各表页内说明。"
    />

    <el-tabs v-model="activeTab">
      <el-tab-pane label="编制手册（目标·逻辑·勾稽）" name="preparation">
        <div class="guide-body prose" v-html="preparationHtml" />
      </el-tab-pane>
      <el-tab-pane label="使用手册（平台操作）" name="usage">
        <div class="guide-body prose" v-html="usageHtml" />
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button type="primary" @click="close">知道了</el-button>
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
.prose :deep(h1) { font-size: 18px; margin: 0 0 12px; color: #1f2a37; }
.prose :deep(h2) { font-size: 15px; margin: 18px 0 8px; padding-left: 8px; border-left: 3px solid #4b2d77; color: #4b2d77; }
.prose :deep(h3) { font-size: 14px; margin: 14px 0 6px; color: #303133; }
.prose :deep(table) { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 12px; }
.prose :deep(th), .prose :deep(td) { border: 1px solid #ebeef5; padding: 6px 8px; vertical-align: top; }
.prose :deep(th) { background: #f5f7fa; font-weight: 600; }
.prose :deep(ul), .prose :deep(ol) { padding-left: 1.35em; margin: 6px 0; }
.prose :deep(li) { margin: 3px 0; }
.prose :deep(code) { background: #f4f4f5; padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.prose :deep(pre) { background: #f8f9fb; padding: 10px; overflow-x: auto; border-radius: 6px; font-size: 12px; }
.prose :deep(blockquote) { margin: 8px 0; padding: 6px 12px; border-left: 3px solid #c0c4cc; color: #606266; background: #fafafa; }
.prose :deep(hr) { border: none; border-top: 1px solid #ebeef5; margin: 16px 0; }
</style>
