<script setup lang="ts">
/**
 * NoteContentTemplateApplyDialog — 模板选择性引用：三组分类 + 差异预览 + 确认应用
 *
 * spec: disclosure-note-doc-upload-and-batch-fill Phase 8 Task 48~50
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { sanitizeHtml } from '@/composables/useSanitize'
import { useNoteTextBatch, type PreviewItem, type ApplyMode } from '@/composables/useNoteTextBatch'

const props = defineProps<{
  visible: boolean
  projectId: string
  year: number
  templateVersionId: string
  templateName: string
}>()

const emit = defineEmits<{
  'update:visible': [val: boolean]
  'applied': []
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

const batch = useNoteTextBatch({
  projectId: computed(() => props.projectId),
  year: computed(() => props.year),
})

const selectedItems = ref<Set<string>>(new Set())
const showDiffFor = ref<string | null>(null)

const previewItems = computed<PreviewItem[]>(() => batch.previewResult.value?.items || [])
const recommendedItems = computed(() => previewItems.value.filter(i => i.category === 'recommended'))
const reviewItems = computed(() => previewItems.value.filter(i => i.category === 'review'))
const unavailableItems = computed(() => previewItems.value.filter(i => i.category === 'unavailable'))

// 加载预览
watch(() => props.visible, async (v) => {
  if (!v) return
  batch.sourceKind.value = 'content_template'
  await batch.fetchPreview()
})

// 默认选中推荐项
watch(() => batch.previewResult.value, (preview) => {
  if (!preview) return
  selectedItems.value.clear()
  for (const item of preview.items) {
    if (item.category === 'recommended') selectedItems.value.add(item.source_id)
  }
})

async function onApply() {
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
  if (!selections.length) { ElMessage.warning('请至少选择一个章节'); return }
  const result = await batch.applyBatch(selections)
  if (result) { emit('applied'); dialogVisible.value = false }
}

const diffItem = computed(() => previewItems.value.find(i => i.source_id === showDiffFor.value) || null)
const summary = computed(() => batch.previewResult.value?.summary || {})
</script>

<template>
  <el-dialog v-model="dialogVisible" :title="`📋 引用模板：${templateName}`" width="90%" top="10vh" :close-on-click-modal="false" destroy-on-close append-to-body>
    <!-- 顶部信息 -->
    <div style="margin-bottom: 16px; font-size: 13px; color: var(--el-text-color-secondary);">
      版本 ID: {{ templateVersionId?.slice(0, 8) }}...
      · 共 {{ summary.total || 0 }} 章
      · 推荐 {{ summary.recommended || 0 }}
      · 需复核 {{ summary.review || 0 }}
      · 不可用 {{ summary.unavailable || 0 }}
    </div>

    <div v-if="batch.previewLoading.value" style="text-align: center; padding: 40px;">加载预览中...</div>

    <div v-else style="max-height: 60vh; overflow-y: auto;">
      <!-- 🟢 推荐引用 -->
      <template v-if="recommendedItems.length">
        <div style="font-weight: 600; color: var(--el-color-success); margin-bottom: 8px;">🟢 推荐引用（{{ recommendedItems.length }}）</div>
        <div v-for="item in recommendedItems" :key="item.source_id" style="margin-bottom: 6px; padding: 8px; background: var(--el-color-success-light-9); border-radius: 4px;">
          <el-checkbox :model-value="selectedItems.has(item.source_id)" @change="(v: boolean) => v ? selectedItems.add(item.source_id) : selectedItems.delete(item.source_id)">
            {{ item.target_note_section }} — {{ item.evidence }}
          </el-checkbox>
        </div>
      </template>

      <!-- 🟡 需复核 -->
      <template v-if="reviewItems.length">
        <div style="font-weight: 600; color: var(--el-color-warning); margin: 12px 0 8px;">🟡 需复核（{{ reviewItems.length }}）</div>
        <div v-for="item in reviewItems" :key="item.source_id" style="margin-bottom: 6px; padding: 8px; background: var(--el-color-warning-light-9); border-radius: 4px;">
          <el-checkbox :model-value="selectedItems.has(item.source_id)" @change="(v: boolean) => v ? selectedItems.add(item.source_id) : selectedItems.delete(item.source_id)">
            {{ item.target_note_section }} — {{ item.evidence }}
          </el-checkbox>
          <el-button size="small" text type="primary" style="margin-left: 8px;" @click="showDiffFor = item.source_id">查看差异</el-button>
          <el-tag v-for="flag in item.quality_flags" :key="flag" size="small" type="info" style="margin-left: 4px;">{{ flag }}</el-tag>
        </div>
      </template>

      <!-- ⚪ 不可用 -->
      <template v-if="unavailableItems.length">
        <div style="font-weight: 600; color: var(--el-text-color-placeholder); margin: 12px 0 8px;">⚪ 不可用（{{ unavailableItems.length }}）</div>
        <div v-for="item in unavailableItems" :key="item.source_id" style="margin-bottom: 6px; padding: 8px; background: var(--el-fill-color-lighter); border-radius: 4px; color: var(--el-text-color-placeholder);">
          {{ item.source_id }} — {{ item.unavailable_reason }}
        </div>
      </template>
    </div>

    <!-- 底部确认 -->
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="success" :loading="batch.applyLoading.value" @click="onApply">
        ✅ 确认应用（{{ selectedItems.size }} 章）
      </el-button>
    </template>

    <!-- 差异弹窗 -->
    <el-dialog v-model="showDiffFor" title="📝 现有/拟写入对比" width="80%" append-to-body destroy-on-close v-if="diffItem">
      <div style="display: flex; gap: 16px;">
        <div style="flex: 1;">
          <div style="font-weight: 600; margin-bottom: 8px;">现有内容</div>
          <div style="border: 1px solid var(--el-border-color); padding: 12px; border-radius: 4px; min-height: 100px;" v-html="sanitizeHtml(diffItem?.before_html || '（空）')" />
        </div>
        <div style="flex: 1;">
          <div style="font-weight: 600; margin-bottom: 8px;">拟写入内容</div>
          <div style="border: 1px solid var(--el-border-color); padding: 12px; border-radius: 4px; min-height: 100px;" v-html="sanitizeHtml(diffItem?.proposed_html || '')" />
        </div>
      </div>
      <div v-if="diffItem?.replacements?.length" style="margin-top: 12px;">
        <div style="font-weight: 600; margin-bottom: 6px;">变量替换</div>
        <div v-for="r in diffItem.replacements" :key="r.replacement_id" style="font-size: 13px;">
          {{ r.variable }}: <del>{{ r.old_value }}</del> → <strong>{{ r.new_value }}</strong>
        </div>
      </div>
    </el-dialog>
  </el-dialog>
</template>
