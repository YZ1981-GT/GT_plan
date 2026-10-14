<script setup lang="ts">
/**
 * NoteDocUploadDialog — 附注文档上传/知识库双栏解析与编辑弹窗
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Phase 6 Task 35~39
 *
 * 左侧来源章节树 + 右侧目标父章分组；折叠懒挂载编辑器；
 * 一键预填只处理 confirmed 映射；关闭有未保存修改必须二次确认。
 */
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { sanitizeHtml } from '@/composables/useSanitize'
import { useNoteTextBatch, type PreviewItem, type ApplyMode } from '@/composables/useNoteTextBatch'

const props = defineProps<{
  visible: boolean
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  'update:visible': [val: boolean]
  'applied': []
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => {
    if (!v && batch.isDirty.value) {
      ElMessageBox.confirm('有未保存的编辑内容，确定关闭？', '提示', {
        confirmButtonText: '确定关闭',
        cancelButtonText: '继续编辑',
        type: 'warning',
      }).then(() => {
        batch.reset()
        emit('update:visible', false)
      }).catch(() => {})
      return
    }
    if (!v) batch.reset()
    emit('update:visible', v)
  },
})

const batch = useNoteTextBatch({
  projectId: computed(() => props.projectId),
  year: computed(() => props.year),
})

// ── 上传 ─────────────────────────────────────────────────────────────────

const fileInput = ref<HTMLInputElement | null>(null)

function triggerUpload() {
  fileInput.value?.click()
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['docx', 'pdf'].includes(ext || '')) {
    ElMessage.error('仅支持 .docx 和 .pdf 文件')
    return
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return
  }
  await batch.parseUpload(file)
  input.value = ''
}

// ── 来源章节（左侧）──────────────────────────────────────────────────────

const expandedSources = ref<Set<string>>(new Set())

function toggleSource(sourceId: string) {
  if (expandedSources.value.has(sourceId)) {
    expandedSources.value.delete(sourceId)
  } else {
    expandedSources.value.add(sourceId)
  }
}

// ── 预览与应用 ──────────────────────────────────────────────────────────

const selectedItems = ref<Set<string>>(new Set())

const previewItems = computed<PreviewItem[]>(() => batch.previewResult.value?.items || [])

const recommendedItems = computed(() => previewItems.value.filter(i => i.category === 'recommended'))
const reviewItems = computed(() => previewItems.value.filter(i => i.category === 'review'))
const unavailableItems = computed(() => previewItems.value.filter(i => i.category === 'unavailable'))

// 默认选中推荐项
watch(() => batch.previewResult.value, (preview) => {
  if (!preview) return
  selectedItems.value.clear()
  for (const item of preview.items) {
    if (item.category === 'recommended') {
      selectedItems.value.add(item.source_id)
    }
  }
})

async function onPreview() {
  await batch.fetchPreview()
}

async function onApply() {
  if (!batch.previewResult.value) return
  const selections = previewItems.value
    .filter(i => selectedItems.value.has(i.source_id) && i.target_note_id)
    .map(i => ({
      source_id: i.source_id,
      target_note_id: i.target_note_id!,
      mode: i.default_mode as ApplyMode,
      before_hash: i.before_hash,
      proposed_hash: i.proposed_hash,
      proposed_html: i.proposed_html,
    }))

  if (!selections.length) {
    ElMessage.warning('请至少选择一个章节')
    return
  }

  const result = await batch.applyBatch(selections)
  if (result) {
    emit('applied')
    dialogVisible.value = false
  }
}

// ── 统计 ─────────────────────────────────────────────────────────────────

const summary = computed(() => batch.previewResult.value?.summary || {})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="📥 上传附注文档"
    width="90%"
    top="10vh"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    destroy-on-close
    append-to-body
  >
    <!-- 顶部操作栏 -->
    <div style="display: flex; gap: 12px; margin-bottom: 16px; align-items: center;">
      <el-button type="primary" size="small" @click="triggerUpload" :loading="batch.loading.value">
        📄 上传 Word/PDF
      </el-button>
      <input
        ref="fileInput"
        type="file"
        accept=".docx,.pdf"
        style="display: none"
        @change="onFileSelected"
      />
      <span v-if="batch.parsedSections.value.length" style="color: var(--el-text-color-secondary); font-size: 13px;">
        已解析 {{ batch.parsedSections.value.length }} 个章节
      </span>
      <div style="flex: 1;" />
      <el-button
        v-if="batch.parsedSections.value.length && !batch.previewResult.value"
        type="primary"
        size="small"
        :loading="batch.previewLoading.value"
        @click="onPreview"
      >
        🔍 预览匹配
      </el-button>
      <el-button
        v-if="batch.previewResult.value"
        type="success"
        size="small"
        :loading="batch.applyLoading.value"
        @click="onApply"
      >
        ✅ 确认应用（{{ selectedItems.size }} 章）
      </el-button>
    </div>

    <!-- 双栏布局 -->
    <div style="display: flex; gap: 16px; min-height: 60vh;">
      <!-- 左侧：来源章节 -->
      <div style="flex: 1; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 12px;">
        <div v-if="!batch.parsedSections.value.length" style="text-align: center; color: var(--el-text-color-placeholder); padding: 40px 0;">
          请上传 Word 或 PDF 附注文档
        </div>
        <div v-for="section in batch.parsedSections.value" :key="section.source_id" style="margin-bottom: 8px;">
          <div
            style="cursor: pointer; padding: 6px 8px; border-radius: 4px; background: var(--el-fill-color-lighter);"
            @click="toggleSource(section.source_id)"
          >
            <span style="margin-right: 6px;">{{ expandedSources.has(section.source_id) ? '▼' : '▶' }}</span>
            <strong>{{ section.title }}</strong>
            <el-tag v-if="section.confidence === 'manual_required'" size="small" type="warning" style="margin-left: 8px;">需确认</el-tag>
          </div>
          <div
            v-if="expandedSources.has(section.source_id)"
            style="padding: 8px 12px; font-size: 13px; color: var(--el-text-color-regular);"
            v-html="sanitizeHtml(section.html)"
          />
        </div>
      </div>

      <!-- 右侧：预览结果 -->
      <div style="flex: 1; overflow-y: auto; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 12px;">
        <div v-if="!batch.previewResult.value" style="text-align: center; color: var(--el-text-color-placeholder); padding: 40px 0;">
          解析后点击"预览匹配"查看章节对应关系
        </div>

        <!-- 推荐引用 -->
        <template v-if="recommendedItems.length">
          <div style="font-weight: 600; margin-bottom: 8px; color: var(--el-color-success);">🟢 推荐引用（{{ recommendedItems.length }}）</div>
          <div v-for="item in recommendedItems" :key="item.source_id" style="margin-bottom: 6px; padding: 6px; border-radius: 4px; background: var(--el-color-success-light-9);">
            <el-checkbox
              :model-value="selectedItems.has(item.source_id)"
              @change="(v: boolean) => v ? selectedItems.add(item.source_id) : selectedItems.delete(item.source_id)"
            >
              {{ item.target_note_section }} — {{ item.evidence }}
            </el-checkbox>
          </div>
        </template>

        <!-- 需复核 -->
        <template v-if="reviewItems.length">
          <div style="font-weight: 600; margin: 12px 0 8px; color: var(--el-color-warning);">🟡 需复核（{{ reviewItems.length }}）</div>
          <div v-for="item in reviewItems" :key="item.source_id" style="margin-bottom: 6px; padding: 6px; border-radius: 4px; background: var(--el-color-warning-light-9);">
            <el-checkbox
              :model-value="selectedItems.has(item.source_id)"
              @change="(v: boolean) => v ? selectedItems.add(item.source_id) : selectedItems.delete(item.source_id)"
            >
              {{ item.target_note_section }} — {{ item.evidence }}
              <el-tag v-for="flag in item.quality_flags" :key="flag" size="small" type="info" style="margin-left: 4px;">{{ flag }}</el-tag>
            </el-checkbox>
          </div>
        </template>

        <!-- 不可用 -->
        <template v-if="unavailableItems.length">
          <div style="font-weight: 600; margin: 12px 0 8px; color: var(--el-text-color-placeholder);">⚪ 不可用（{{ unavailableItems.length }}）</div>
          <div v-for="item in unavailableItems" :key="item.source_id" style="margin-bottom: 6px; padding: 6px; border-radius: 4px; background: var(--el-fill-color-lighter); color: var(--el-text-color-placeholder);">
            {{ item.source_id }} — {{ item.unavailable_reason }}
          </div>
        </template>

        <!-- 统计 -->
        <div v-if="batch.previewResult.value" style="margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); font-size: 13px; color: var(--el-text-color-secondary);">
          共 {{ summary.total || 0 }} 章 · 推荐 {{ summary.recommended || 0 }} · 需复核 {{ summary.review || 0 }} · 不可用 {{ summary.unavailable || 0 }}
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="batch.lastError.value" style="margin-top: 12px; color: var(--el-color-danger); font-size: 13px;">
      ⚠️ {{ batch.lastError.value }}
    </div>
  </el-dialog>
</template>
