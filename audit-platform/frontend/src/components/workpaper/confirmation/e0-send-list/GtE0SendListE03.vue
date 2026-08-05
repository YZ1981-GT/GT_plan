<script setup lang="ts">
/**
 * GtE0SendListE03 — 货币资金发函记录表E0-3 专属 HTML 组件
 *
 * componentType: confirmation-send-list-e03
 * @module e0-send-list-dedicated-components / Wave 3 Task 7
 */
import { ref, watch, onMounted, computed } from 'vue'
import { SEND_LIST_SPECS } from './sendListSpec'
import { useSendListData } from './useSendListData'
import SendListTable from './SendListTable.vue'
import SendListPrefillPanel from './SendListPrefillPanel.vue'

const props = defineProps<{
  htmlData: any
  projectId: string
  wpId: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save', sheetName: string, payload: any): void
}>()

const spec = SEND_LIST_SPECS.e03
const isReadonly = ref(props.isReadonly ?? false)
const htmlDataRef = ref(props.htmlData)

watch(() => props.htmlData, (v) => { htmlDataRef.value = v })
watch(() => props.isReadonly, (v) => { isReadonly.value = v ?? false })

const {
  rows,
  conclusion,
  visibleColumns,
  hasUnmappedCells,
  addRow,
  removeRow,
  moveRow,
  toggleColumn,
  buildPayload,
  loadFromHtmlData,
} = useSendListData(spec, { htmlData: htmlDataRef, isReadonly })

onMounted(() => {
  loadFromHtmlData(props.htmlData)
})

watch(() => props.htmlData, (data) => {
  loadFromHtmlData(data)
})

function handleSave() {
  const payload = buildPayload()
  emit('save', spec.sheetName, payload)
}

// Prefill from render-config _prefill
const prefillData = computed(() => {
  const hd = props.htmlData
  return hd?._prefill ?? null
})

function handlePrefillApplied(_count: number) {
  handleSave()
}

// ─── AI 辅助 ──────────────────────────────────────────────────────────────
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)

async function handleAiNote() {
  await _callAi('e0-3-send-list-audit-note', conclusion.value.audit_explanation, (text) => {
    conclusion.value.audit_explanation = text
  }, aiLoadingNote)
}

async function handleAiConclusion() {
  await _callAi('e0-3-send-list-audit-conclusion', conclusion.value.overall_conclusion, (text) => {
    conclusion.value.overall_conclusion = text
  }, aiLoadingConclusion)
}

async function _callAi(section: string, existingContent: string, onSuccess: (t: string) => void, loadingRef: typeof aiLoadingNote) {
  if (!props.wpId) return
  loadingRef.value = true
  try {
    const { default: axios } = await import('axios')
    const res = await axios.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: '',
      context: { sheet: spec.sheetName, rows_count: String(rows.value.length) },
      existingContent,
    })
    const text = (res.data?.data ?? res.data)?.content
    if (text) {
      onSuccess(text)
      handleSave()
    }
  } catch (e: any) {
    const { ElMessage } = await import('element-plus')
    ElMessage.warning('AI 生成失败：' + (e?.response?.data?.message || e?.message || '未知错误'))
  } finally {
    loadingRef.value = false
  }
}
</script>

<template>
  <div class="e0-send-list e0-send-list-e03">
    <!-- Prefill 面板（仅 E0-3 有） -->
    <SendListPrefillPanel
      :rows="rows"
      :prefill="prefillData"
      :is-readonly="isReadonly"
      @applied="handlePrefillApplied"
    />

    <!-- 未映射单元格提示 -->
    <el-alert
      v-if="hasUnmappedCells"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      存在未识别的历史列数据，已保留（不影响使用）
    </el-alert>

    <!-- 主表格 -->
    <SendListTable
      :spec="spec"
      :rows="rows"
      :visible-columns="visibleColumns"
      :is-readonly="isReadonly"
      @add-row="addRow"
      @remove-row="removeRow"
      @move-row="moveRow"
      @toggle-column="toggleColumn"
      @save="handleSave"
    />

    <!-- 审计说明 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between">
          <span>审计说明</span>
          <el-button
            size="small"
            :loading="aiLoadingNote"
            :disabled="isReadonly"
            @click="handleAiNote"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion.audit_explanation"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="请填写审计说明"
        @blur="handleSave"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" style="margin-top: 12px">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between">
          <span>审计结论</span>
          <el-button
            size="small"
            :loading="aiLoadingConclusion"
            :disabled="isReadonly"
            @click="handleAiConclusion"
          >🤖 AI 辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="conclusion.overall_conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="请填写审计结论"
        @blur="handleSave"
      />
    </el-card>
  </div>
</template>

<style scoped>
.e0-send-list {
  font-size: 13px;
}
</style>
