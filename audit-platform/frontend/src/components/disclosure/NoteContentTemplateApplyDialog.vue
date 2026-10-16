<script setup lang="ts">
/**
 * NoteContentTemplateApplyDialog — 按章节选择性引用内容模板（Task 48 / 50 / 51）
 *
 * 第二轮复盘 R-02：首版按上传形态发预览载荷、从不带 template_version_id ⇒ 后端必拒。
 * 现固定 version_id + content_hash 预览与写入；正文只由后端从不可变版本读取。
 */
import { computed, ref, watch } from 'vue'
import {
  toSelection, useNoteTextBatch, type ApplyMode, type ApplyResponse, type PreviewItem,
} from '@/composables/useNoteTextBatch'
import type { ContentTemplateItem, ContentTemplateVersion } from '@/composables/useNoteContentTemplate'
import NoteTextPreviewList from './NoteTextPreviewList.vue'
import NoteTextDiffDialog from './NoteTextDiffDialog.vue'
import { canAppend, REPORT_SCOPE_LABELS, savedByLabel, TEMPLATE_TYPE_LABELS } from './noteTextBatchLabels'

const props = defineProps<{
  visible: boolean
  projectId: string
  year: number
  template: ContentTemplateItem
  version: ContentTemplateVersion
}>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; 'applied': [result: ApplyResponse] }>()

const batch = useNoteTextBatch({ projectId: computed(() => props.projectId), year: computed(() => props.year) })
const selected = ref<string[]>([])
const modes = ref<Record<string, ApplyMode>>({})
const diffItem = ref<PreviewItem | null>(null)
const diffVisible = ref(false)

const items = computed(() => batch.previewResult.value?.items ?? [])
const quality = computed(() => props.version.quality_summary ?? {})
const newerVersion = computed(() => {
  const current = props.template.current_version
  return current && current.id !== props.version.id ? current.version_no : null
})
const crossStandard = computed(() => items.value.some(i => i.quality_flags.includes('cross_standard')))

watch(() => props.visible, async (v) => {
  if (!v) return
  batch.useTemplateVersion(props.version.id, props.version.content_hash)
  await batch.fetchPreview()
}, { immediate: true })

watch(() => batch.previewResult.value, (preview) => {
  const kept = new Set(selected.value)
  selected.value = (preview?.items ?? [])
    .filter(i => i.category !== 'unavailable' && (kept.has(i.source_id) || i.default_selected))
    .map(i => i.source_id)
  modes.value = Object.fromEntries((preview?.items ?? []).map(i =>
    [i.source_id, canAppend(i) && modes.value[i.source_id] === 'append' ? 'append' : 'replace']))
})

function openDiff(item: PreviewItem) {
  diffItem.value = item
  diffVisible.value = true
}

function onDiffConfirm(item: PreviewItem) {
  if (!selected.value.includes(item.source_id)) selected.value = [...selected.value, item.source_id]
}

function setDiffMode(mode: ApplyMode) {
  if (diffItem.value) modes.value = { ...modes.value, [diffItem.value.source_id]: mode }
}

async function onApply() {
  const chosen = new Set(selected.value)
  const result = await batch.applyBatch(items.value
    .filter(i => chosen.has(i.source_id) && i.target_note_id && i.category !== 'unavailable')
    .map(i => toSelection(i, modes.value[i.source_id] ?? 'replace')))
  if (!result) return
  emit('applied', result)
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog :model-value="visible" :title="`📋 引用内容模板：${template.name}`" width="90%" top="5vh" append-to-body
    destroy-on-close :close-on-click-modal="false" @update:model-value="(v: boolean) => emit('update:visible', v)">
    <div class="gt-nta-head">
      版本 v{{ version.version_no }} · 来源 {{ version.source_project_name }} {{ version.source_year }} 年
      · {{ TEMPLATE_TYPE_LABELS[version.template_type] ?? version.template_type }}
      · {{ REPORT_SCOPE_LABELS[version.report_scope] ?? version.report_scope }}
      · 共 {{ quality.total ?? 0 }} 章（有内容 {{ quality.with_content ?? 0 }}，高风险 {{ quality.high_risk ?? 0 }}）
      <template v-if="savedByLabel(version)"> · {{ savedByLabel(version) }}</template>
    </div>
    <el-alert v-if="newerVersion" type="info" :closable="false" show-icon
      :title="`该模板已有更新版本 v${newerVersion}；当前按所选历史版本预览，已引用的项目不会被自动更新`" />
    <el-alert v-if="crossStandard" type="warning" :closable="false" show-icon
      title="模板的标准或报表口径与本项目不一致：跨标准章节已全部归入「需复核」，请逐章核对" />
    <el-alert v-if="batch.previewStale.value" type="warning" :closable="false" show-icon
      title="预览已过期（预览后改过变量替换，或目标章节已被他人修改），请重新预览后再写入" />
    <el-alert v-if="batch.lastError.value" type="error" :closable="false" show-icon :title="batch.lastError.value.message" />
    <div v-if="batch.previewLoading.value" class="gt-nta-loading">正在生成预览…</div>
    <div v-else class="gt-nta-body">
      <NoteTextPreviewList v-model:selected="selected" :items="items" :modes="modes" @open-diff="openDiff" />
    </div>
    <NoteTextDiffDialog v-model="diffVisible" :item="diffItem" :mode="diffItem ? (modes[diffItem.source_id] ?? 'replace') : 'replace'"
      :revoked-ids="[...batch.revokedReplacementIds.value]" :stale="batch.previewStale.value"
      @update:mode="setDiffMode" @toggle-revocation="(id: string) => batch.toggleRevocation(id)" @confirm="onDiffConfirm" />
    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button v-if="batch.previewStale.value" :loading="batch.previewLoading.value" @click="batch.fetchPreview()">🔄 重新预览</el-button>
      <el-button type="success" :loading="batch.applyLoading.value" :disabled="!batch.canApply.value || !selected.length"
        @click="onApply">✅ 确认写入（{{ selected.length }} 章）</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.gt-nta-head { margin-bottom: 12px; font-size: 13px; color: var(--el-text-color-secondary); }
.gt-nta-loading { text-align: center; padding: 40px; color: var(--el-text-color-secondary); }
.gt-nta-body { max-height: 62vh; overflow-y: auto; }
</style>
