<template>
  <span
    v-if="props.entryId && presentation.noticeKind !== 'none'"
    class="entry-sync-notice"
    :data-entry-sync-notice="props.entryId"
    :data-entry-sync-state="loadState"
  >
    <el-tag size="small" :type="tagType" effect="plain">
      {{ presentation.noticeLabel }}
    </el-tag>
    <span class="entry-sync-notice__summary" :title="presentation.noticeSummary">
      {{ presentation.noticeSummary }}
    </span>
    <!--
      原因入口必须是**真按钮语义 + 键盘可操作**，且展开后的原因**内联**渲染。
      原实现是 `<span tabindex="0">` + 只在 tooltip 里放原因：
        · 无 role/aria-expanded ⇒ 读屏只念出一段文字，不知道可以操作；
        · 原因只存在于 hover 浮层 ⇒ 触屏与窄屏下「可操作原因」实际拿不到（AC 1.5）；
        · 3.4 任务正文也写明「tooltip 只放补充信息」，原因不该只在 tooltip 里。
    -->
    <button
      type="button"
      class="entry-sync-notice__detail"
      :aria-expanded="expanded ? 'true' : 'false'"
      :aria-controls="reasonDomId"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起原因' : '查看原因' }}
    </button>
    <span
      v-if="expanded"
      :id="reasonDomId"
      class="entry-sync-notice__reason"
      role="note"
    >{{ presentation.noticeReason }}</span>
    <el-button
      v-if="loadState === 'error'"
      size="small"
      text
      type="primary"
      @click="() => refresh()"
    >
      重试
    </el-button>
  </span>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import { useEntrySyncReadiness } from './useEntrySyncReadiness'

const props = defineProps<{
  entryId: string
  projectId?: string
  wpId?: string
}>()

const runtime = inject(WorkpaperRuntimeContextKey, null)
const projectId = computed(() => props.projectId || runtime?.projectId.value || '')
const wpId = computed(() => props.wpId || runtime?.wpId.value || '')
const entryId = computed(() => props.entryId)
const { presentation, loadState, refresh } = useEntrySyncReadiness({
  projectId,
  wpId,
  entryId,
})

const tagType = computed(() => {
  if (presentation.value.noticeKind === 'danger') return 'danger'
  if (presentation.value.noticeKind === 'warning') return 'warning'
  return 'info'
})

const expanded = ref(false)
/**
 * `aria-controls` 需要稳定且唯一的 id。
 *
 * 🔴 不用 `crypto.randomUUID()`：内网 http 不是安全上下文，那里拿不到它（仓库铁律）。
 * entry id 本身在一张底稿内唯一，做字符替换即可。
 */
const reasonDomId = computed(
  () => `entry-sync-reason-${props.entryId.replace(/[^\w-]/g, '-')}`,
)
</script>

<style scoped>
.entry-sync-notice {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex-wrap: wrap;
}
.entry-sync-notice__summary {
  font-size: 12px;
  color: var(--el-color-warning-dark-2);
  /* 窄屏下不撑破工具栏：允许整行折行，过长时截断并由 title 兜底 */
  min-width: 0;
  max-width: min(360px, 60vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry-sync-notice__detail {
  cursor: pointer;
  font-size: 12px;
  color: var(--el-color-primary);
  border: 0;
  border-bottom: 1px dashed currentColor;
  background: transparent;
  padding: 0;
  /* 键盘焦点必须可见 —— 默认 outline 被 border:0 连带弱化时自己补回来 */
  line-height: 1.4;
}
.entry-sync-notice__detail:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 2px;
}
.entry-sync-notice__reason {
  flex: 1 1 100%;
  max-width: min(420px, 80vw);
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  /* 原因是多句中文：窄屏下必须换行而不是横向溢出 */
  white-space: normal;
  word-break: break-word;
}
</style>
