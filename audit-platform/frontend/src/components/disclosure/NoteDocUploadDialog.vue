<script setup lang="ts">
/**
 * NoteDocUploadDialog — 上传 Word/PDF 或选知识库文档，双栏核对来源与目标，服务端预览后原子写入。
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Task 35~39（第二轮复盘：对齐后端契约、
 * 知识库来源 AC-5.1、候选人工确认 AC-3.3、单实例懒挂载编辑器 AC-2.4、改动后必须重新预览）
 *
 * 左栏是来源章节：可展开核对、可二次编辑（编辑的是来源正文，重新预览后由服务端消毒 / 替换变量再生成拟写入内容）；
 * 右栏是服务端预览的三分组。写入只提交「来源 + 映射 + 撤销项 + 选择」，拟写入正文一律以服务端重算为准。
 */
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { sanitizeHtml } from '@/composables/useSanitize'
import { useKnowledge } from '@/composables/useKnowledge'
import {
  toSelection, useNoteTextBatch, type ApplyMode, type ApplyResponse, type ParsedSection, type PreviewItem,
  type TargetSection,
} from '@/composables/useNoteTextBatch'
import NoteTextPreviewList from './NoteTextPreviewList.vue'
import NoteTextDiffDialog from './NoteTextDiffDialog.vue'
import { CONFIDENCE_LABELS, describeSource } from './noteTextBatchLabels'

const NoteRichTextEditor = defineAsyncComponent(() => import('@/components/NoteRichTextEditor.vue'))

const props = defineProps<{ visible: boolean; projectId: string; year: number }>()
const emit = defineEmits<{ 'update:visible': [value: boolean]; 'applied': [result: ApplyResponse] }>()

const batch = useNoteTextBatch({ projectId: computed(() => props.projectId), year: computed(() => props.year) })
const { pickDocuments } = useKnowledge()

const selected = ref<string[]>([])
const modes = ref<Record<string, ApplyMode>>({})
const targets = ref<TargetSection[]>([])
const expanded = ref<Set<string>>(new Set())
const diffItem = ref<PreviewItem | null>(null)
const diffVisible = ref(false)
const editing = ref<{ sourceId: string; title: string; html: string } | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

const items = computed(() => batch.previewResult.value?.items ?? [])
const mappings = computed(() => Object.fromEntries(batch.manualMappings.value))
const sourceLabel = computed(() => describeSource(batch.sourceKind.value,
  batch.parsedSource.value?.source_metadata as Parameters<typeof describeSource>[1]))

// 重新预览后保留用户已做的选择（仍可用的），首轮只勾服务端推荐项
watch(() => batch.previewResult.value, (preview) => {
  if (!preview) { selected.value = []; modes.value = {}; return }
  const kept = new Set(selected.value)
  selected.value = preview.items
    .filter(i => i.category !== 'unavailable' && (kept.has(i.source_id) || i.default_selected))
    .map(i => i.source_id)
  modes.value = Object.fromEntries(preview.items.map(i =>
    [i.source_id, i.append_html !== null && modes.value[i.source_id] === 'append' ? 'append' : 'replace']))
})

async function confirmDiscard(message: string): Promise<boolean> {
  if (!batch.isDirty.value) return true
  try {
    await ElMessageBox.confirm(message, '提示', { confirmButtonText: '放弃修改', cancelButtonText: '继续编辑', type: 'warning' })
    return true
  } catch {
    return false
  }
}

function resetAll() {
  batch.reset()
  targets.value = []
  expanded.value = new Set()
  editing.value = null
}

async function onBeforeClose(done: () => void) {
  if (!(await confirmDiscard('有未写入的编辑内容，确定关闭？'))) return
  resetAll()
  done()
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!/\.(docx|pdf)$/i.test(file.name)) { batch.rejectFile(file.name, '仅支持 .docx 和 .pdf 文件'); return }
  if (file.size > 50 * 1024 * 1024) { batch.rejectFile(file.name, '文件大小不能超过 50MB'); return }
  if (!(await confirmDiscard('切换来源会丢弃当前未写入的编辑，确定继续？'))) return
  targets.value = []
  await batch.parseUpload(file)
}

async function onPickKnowledge() {
  if (!(await confirmDiscard('切换来源会丢弃当前未写入的编辑，确定继续？'))) return
  let docs: Array<{ id: string }> = []
  try {
    docs = await pickDocuments({ title: '选择知识库文档作为附注来源（最多 5 篇）', maxSelect: 5 })
  } catch {
    return
  }
  if (!docs.length) return
  targets.value = []
  await batch.parseKnowledge(docs.map(d => d.id))
}

async function onPreview() {
  if (await batch.fetchPreview() && !targets.value.length) targets.value = await batch.fetchTargetSections()
}

async function onApply() {
  const chosen = new Set(selected.value)
  const selections = items.value
    .filter(i => chosen.has(i.source_id) && i.target_note_id && i.category !== 'unavailable')
    .map(i => toSelection(i, modes.value[i.source_id] ?? 'replace'))
  const result = await batch.applyBatch(selections)
  if (!result) return  // 失败保留全部草稿与选择（AC-4.3）
  emit('applied', result)
  resetAll()
  emit('update:visible', false)
}

function toggleExpand(sourceId: string) {
  const next = new Set(expanded.value)
  if (next.has(sourceId)) next.delete(sourceId)
  else next.add(sourceId)
  expanded.value = next
}

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

function startEdit(section: ParsedSection) {
  editing.value = { sourceId: section.source_id, title: section.title, html: section.html }
}

function saveEdit() {
  if (!editing.value) return
  batch.updateSectionHtml(editing.value.sourceId, editing.value.html)
  editing.value = null
}
</script>

<template>
  <el-dialog :model-value="visible" title="📄 上传附注文档" width="90%" top="5vh" append-to-body destroy-on-close
    :close-on-click-modal="false" :before-close="onBeforeClose" @update:model-value="(v: boolean) => emit('update:visible', v)">
    <div class="gt-ndu-bar">
      <el-button type="primary" size="small" :loading="batch.loading.value" @click="fileInput?.click()">📄 上传 Word/PDF</el-button>
      <el-button size="small" :loading="batch.loading.value" @click="onPickKnowledge">📚 从知识库选择</el-button>
      <input ref="fileInput" type="file" accept=".docx,.pdf" style="display: none" @change="onFileSelected" />
      <span v-if="batch.parsedSections.value.length" class="gt-ndu-muted">
        {{ sourceLabel }} · 已解析 {{ batch.parsedSections.value.length }} 个章节
        <template v-if="batch.editedSourceIds.value.length"> · 已编辑 {{ batch.editedSourceIds.value.length }} 章</template>
      </span>
      <div style="flex: 1" />
      <el-button v-if="batch.parsedSections.value.length" size="small" :loading="batch.previewLoading.value" @click="onPreview">
        {{ batch.previewResult.value ? '🔄 重新预览' : '🔍 预览匹配' }}
      </el-button>
      <el-button type="success" size="small" :loading="batch.applyLoading.value"
        :disabled="!batch.canApply.value || !selected.length" @click="onApply">✅ 确认写入（{{ selected.length }} 章）</el-button>
    </div>
    <el-alert v-if="batch.previewStale.value" type="warning" :closable="false" show-icon
      title="预览已过期（预览后改过来源正文、手工映射或变量替换，或目标章节已被他人修改），请重新预览后再写入" />
    <el-alert v-if="batch.lastError.value" type="error" :closable="false" show-icon :title="batch.lastError.value.message" />
    <div class="gt-ndu-columns">
      <section class="gt-ndu-pane">
        <div v-if="!batch.parsedSections.value.length" class="gt-ndu-empty">请上传 Word / PDF 附注文档，或从知识库选择文档</div>
        <div v-for="section in batch.parsedSections.value" :key="section.source_id" class="gt-ndu-source"
          :style="{ marginLeft: `${Math.min(section.level - 1, 4) * 12}px` }">
          <div class="gt-ndu-source-head" @click="toggleExpand(section.source_id)">
            <span>{{ expanded.has(section.source_id) ? '▼' : '▶' }}</span>
            <strong>{{ section.title }}</strong>
            <el-tag v-if="section.confidence !== 'candidate'" size="small" type="warning">{{ CONFIDENCE_LABELS[section.confidence] }}</el-tag>
            <el-tag v-if="batch.editedSourceIds.value.includes(section.source_id)" size="small" type="success">已编辑</el-tag>
            <el-button size="small" link type="primary" @click.stop="startEdit(section)">编辑</el-button>
          </div>
          <div v-for="w in section.warnings" :key="w" class="gt-ndu-warning">⚠️ {{ w }}</div>
          <div v-if="expanded.has(section.source_id)" class="gt-ndu-html" v-html="sanitizeHtml(section.html)" />
        </div>
      </section>
      <section class="gt-ndu-pane">
        <div v-if="!batch.previewResult.value" class="gt-ndu-empty">解析后点击「预览匹配」，由服务端给出章节对应关系与拟写入内容</div>
        <NoteTextPreviewList v-else v-model:selected="selected" :items="items" :modes="modes"
          :edited-ids="batch.editedSourceIds.value" :targets="targets" :mappings="mappings"
          @open-diff="openDiff" @map="(sid: string, tid: string | null) => batch.setManualMapping(sid, tid)" />
      </section>
    </div>
    <NoteTextDiffDialog v-model="diffVisible" :item="diffItem" :mode="diffItem ? (modes[diffItem.source_id] ?? 'replace') : 'replace'"
      :revoked-ids="[...batch.revokedReplacementIds.value]" :stale="batch.previewStale.value"
      @update:mode="setDiffMode"
      @toggle-revocation="(id: string) => batch.toggleRevocation(id)" @confirm="onDiffConfirm" />
    <el-dialog v-if="editing" :model-value="true" :title="`编辑来源正文：${editing.title}`" width="70%" append-to-body
      @close="editing = null">
      <NoteRichTextEditor v-model="editing.html" />
      <template #footer>
        <el-button @click="editing = null">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存修改（需重新预览）</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<style scoped>
.gt-ndu-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.gt-ndu-muted { color: var(--el-text-color-secondary); font-size: 13px; }
.gt-ndu-columns { display: flex; gap: 16px; height: 70vh; margin-top: 8px; }
.gt-ndu-pane { flex: 1; min-width: 0; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 12px; }
.gt-ndu-empty { text-align: center; color: var(--el-text-color-placeholder); padding: 40px 0; }
.gt-ndu-source { margin-bottom: 6px; }
.gt-ndu-source-head { display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 6px 8px; border-radius: 4px; background: var(--el-fill-color-lighter); }
.gt-ndu-warning { font-size: 12px; color: var(--el-color-warning); padding: 2px 8px; }
.gt-ndu-html { padding: 8px 12px; font-size: 13px; }
</style>
