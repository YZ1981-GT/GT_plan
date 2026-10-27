<!--
  OcrStatusBadge — OCR 状态标签 [R7-S3-11 Task 55]
  统一替代各处自写的 .gt-wpb-ocr-badge 内联样式。

  用法：
    <OcrStatusBadge status="ok" />
    <OcrStatusBadge status="processing" />

  后端附件识别状态写的是 completed（attachment_ocr_writeback / ocr_fields_service），
  原样传进来时同样显示「OCR ✓」（spec attachment-inline-preview 需求 3.1）；未知值不显示英文原文。
-->
<template>
  <span class="gt-ocr-badge" :class="`gt-ocr-badge--${key}`">
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: 'ok' | 'processing' | 'failed' | 'pending' | 'completed' | string
}>()

const ALIASES: Record<string, string> = { completed: 'ok', done: 'ok', running: 'processing', error: 'failed' }

const key = computed(() => {
  const raw = String(props.status || '').toLowerCase()
  return ALIASES[raw] || raw
})

const label = computed(() => {
  const map: Record<string, string> = {
    ok: 'OCR ✓',
    processing: 'OCR中',
    failed: 'OCR失败',
    pending: '待OCR',
  }
  return map[key.value] || '识别状态未知'
})
</script>

<style scoped>
.gt-ocr-badge {
  font-size: var(--gt-font-size-xs);
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 600;
  display: inline-block;
}
.gt-ocr-badge--ok { background: var(--gt-color-success-light); color: var(--gt-color-success); }
.gt-ocr-badge--processing { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.gt-ocr-badge--failed { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }
.gt-ocr-badge--pending { background: var(--gt-color-bg); color: var(--gt-color-text-tertiary); }
</style>
