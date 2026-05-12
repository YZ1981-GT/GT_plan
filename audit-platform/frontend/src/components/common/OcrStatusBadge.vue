<!--
  OcrStatusBadge — OCR 状态标签 [R7-S3-11 Task 55]
  统一替代各处自写的 .gt-wpb-ocr-badge 内联样式。

  用法：
    <OcrStatusBadge status="ok" />
    <OcrStatusBadge status="processing" />
-->
<template>
  <span class="gt-ocr-badge" :class="`gt-ocr-badge--${status}`">
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: 'ok' | 'processing' | 'failed' | 'pending'
}>()

const label = computed(() => {
  const map: Record<string, string> = {
    ok: 'OCR ✓',
    processing: 'OCR中',
    failed: 'OCR失败',
    pending: '待OCR',
  }
  return map[props.status] || props.status
})
</script>

<style scoped>
.gt-ocr-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 600;
  display: inline-block;
}
.gt-ocr-badge--ok { background: var(--gt-color-success-light); color: var(--gt-color-success); }
.gt-ocr-badge--processing { background: var(--gt-color-wheat-light); color: #b88a00; }
.gt-ocr-badge--failed { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }
.gt-ocr-badge--pending { background: var(--gt-color-bg); color: var(--gt-color-text-tertiary); }
</style>
