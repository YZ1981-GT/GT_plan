<template>
  <div class="gt-email-view" data-testid="email-message-view">
    <dl class="gt-email-view__headers">
      <div><dt>发件人</dt><dd data-field="from">{{ email.from }}</dd></div>
      <div><dt>收件人</dt><dd data-field="to">{{ email.to.join(', ') }}</dd></div>
      <div><dt>抄送</dt><dd data-field="cc">{{ email.cc.join(', ') }}</dd></div>
      <div><dt>主题</dt><dd data-field="subject">{{ email.subject }}</dd></div>
      <div><dt>时间</dt><dd data-field="date">{{ email.date || '—' }}</dd></div>
    </dl>

    <div class="gt-email-view__toolbar">
      <button type="button" data-testid="email-toggle-html" @click="mode = 'html'" :disabled="!safeHtml.html">HTML</button>
      <button type="button" data-testid="email-toggle-text" @click="mode = 'text'">纯文本</button>
    </div>

    <iframe
      v-if="mode === 'html' && srcdoc"
      class="gt-email-view__frame"
      sandbox=""
      :srcdoc="srcdoc"
      title="email-body"
      data-testid="email-html-frame"
    />
    <pre v-else class="gt-email-view__text" data-testid="email-text-body">{{ email.text || '' }}</pre>

    <div v-if="blockedResources.length" class="gt-email-view__blocked" data-testid="email-blocked">
      已阻断远程/危险资源 {{ blockedResources.length }} 项
    </div>

    <ul class="gt-email-view__atts" data-testid="email-attachments">
      <li v-for="(a, i) in email.attachments" :key="i">
        {{ a.filename }} ({{ a.size }})
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { ParsedEmail } from '../email/emailParser'
import { sanitizeEmailHtml, wrapEmailSrcdoc, type BlockedResource } from '../email/emailSanitizer'

const props = defineProps<{
  email: ParsedEmail
  createObjectUrl?: (blob: Blob) => string
  releaseObjectUrl?: (url: string) => void
}>()

const mode = ref<'html' | 'text'>('html')
const blockedResources = ref<BlockedResource[]>([])
const objectUrls = ref<string[]>([])

const createObjectUrl = (blob: Blob): string =>
  props.createObjectUrl?.(blob) ?? URL.createObjectURL(blob)

const releaseObjectUrl = (url: string): void => {
  if (props.releaseObjectUrl) props.releaseObjectUrl(url)
  else {
    try { URL.revokeObjectURL(url) } catch { /* */ }
  }
}

const safeHtml = computed(() => {
  const safe = sanitizeEmailHtml(props.email.html, props.email.inlineParts, createObjectUrl)
  return safe
})

const srcdoc = computed(() => {
  if (!safeHtml.value.html) return ''
  return wrapEmailSrcdoc(safeHtml.value.html)
})

watch(
  safeHtml,
  (v) => {
    for (const url of objectUrls.value) releaseObjectUrl(url)
    objectUrls.value = v.generatedObjectUrls
    blockedResources.value = v.blockedResources
    mode.value = v.html ? 'html' : 'text'
  },
  { immediate: true },
)

onUnmounted(() => {
  for (const url of objectUrls.value) releaseObjectUrl(url)
  objectUrls.value = []
})
</script>

<style scoped>
.gt-email-view { display: flex; flex-direction: column; gap: 8px; }
.gt-email-view__headers { display: grid; gap: 4px; margin: 0; }
.gt-email-view__headers div { display: grid; grid-template-columns: 64px 1fr; gap: 8px; }
.gt-email-view__headers dt { font-weight: 600; margin: 0; }
.gt-email-view__headers dd { margin: 0; }
.gt-email-view__frame { width: 100%; min-height: 280px; border: 1px solid var(--gt-color-border-light, #e5e5e5); }
.gt-email-view__text { white-space: pre-wrap; max-height: 360px; overflow: auto; }
.gt-email-view__blocked { color: var(--gt-color-warning, #b88230); font-size: 12px; }
</style>
