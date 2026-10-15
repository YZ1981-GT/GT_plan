<script setup lang="ts">
/**
 * NoteSourceBadge — 编辑器章节标题旁的「来源」标记（Task 50 / AC-11.3）
 *
 * 显示当前章最近一次批量写入的来源（内容模板版本 / 上传文档 / 知识库文档）与写入人、时间；写入后被改过另行标出。
 * 只在平台界面显示，不进附注正文、不进导出。按项目年度一次取回（只读端点），批量写入成功后自动刷新；
 * 取数失败不打扰用户（标记只是辅助信息），直接不显示。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { NOTE_TEXT_BATCH_PATHS, silent, type NoteTextSource } from '@/composables/useNoteTextBatch'
import { sourceBadgeText } from './noteTextBatchLabels'

const props = defineProps<{ projectId: string; year: number; noteId?: string | null }>()
const sources = ref<Record<string, NoteTextSource>>({})
/** 只有最后一发请求能落状态：切项目 / 年度时迟到的旧结果不得覆盖 */
let seq = 0

async function load() {
  const mine = ++seq
  if (!props.projectId || !props.year) {
    sources.value = {}
    return
  }
  try {
    const result = await api.get<{ items: Record<string, NoteTextSource> }>(
      NOTE_TEXT_BATCH_PATHS.sources(props.projectId), silent({ params: { year: props.year } }))
    if (mine === seq) sources.value = result?.items ?? {}
  } catch {
    if (mine === seq) sources.value = {}
  }
}

function onApplied(payload: { projectId: string; year: number }) {
  if (payload.projectId === props.projectId && payload.year === props.year) load()
}

onMounted(() => {
  eventBus.on('note-text-batch:applied', onApplied)
  load()
})
onUnmounted(() => eventBus.off('note-text-batch:applied', onApplied))
watch(() => [props.projectId, props.year], load)

const badge = computed(() => {
  const source = props.noteId ? sources.value[props.noteId] : undefined
  return source ? sourceBadgeText(source) : null
})
</script>

<template>
  <span v-if="badge" :class="['gt-nsb', { 'is-modified': badge.modified }]" :title="badge.hint">{{ badge.text }}</span>
</template>

<style scoped>
.gt-nsb { display: inline-block; margin-left: 8px; padding: 0 6px; font-size: 12px; line-height: 20px; border-radius: 4px;
  color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.gt-nsb.is-modified { color: var(--el-color-warning-dark-2); background: var(--el-color-warning-light-9); }
</style>
