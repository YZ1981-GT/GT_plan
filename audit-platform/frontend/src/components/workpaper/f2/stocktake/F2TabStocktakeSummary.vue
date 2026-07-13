<template>
  <div class="f2-summary-wrapper">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总监盘实施情况与结论，是存货监盘程序的总结底稿（CAS 1311 存货监盘）。</p>
        <p>2. 记录实际监盘范围、抽盘结果、发现的差异及其处理，评价存货存在性与状况。</p>
        <p>3. 对监盘中发现的异常（毁损 / 呆滞 / 第三方保管）应说明后续审计应对措施。</p>
        <p>4. 可通过 📎 附件OCR识别，将现场记录内容填入对应字段。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：总结存货监盘实施情况与结果，评价监盘范围、抽盘差异及异常处理，为存货存在性与状况认定形成整体结论。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"><span class="hint">监盘小结 F2-23</span></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F2-23" :context-project-id="projectId" /></span>
      </div>
    </div>

    <F2StocktakeSectionForm
      ref="sectionFormRef"
      title="监盘小结 F2-23"
      sheet-code="F2-23"
      fields-key="F2-23-fields"
      note-key="F2-23-note"
      :field-defs="F2_23_FIELDS"
      :wp-id="wpId"
      :project-id="projectId"
      :all-responses="allResponses"
      :is-readonly="isReadonly"
      ai-section="stocktake-summary"
      ai-title="AI 生成 · 监盘小结"
      audit-note-label="监盘小结结论"
    />
    <div v-if="wpId && !isReadonly" class="ocr-attach-bar">
      <el-button size="small" plain @click="uploadOcr">📎 附件OCR识别填入</el-button>
      <el-select v-model="ocrTargetField" size="small" placeholder="目标字段" style="width: 200px">
        <el-option
          v-for="f in multilineFields"
          :key="f.id"
          :label="f.label"
          :value="f.id"
        />
      </el-select>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述监盘实施范围、抽盘差异及处理、发现的异常（毁损/呆滞/第三方保管）及后续应对措施等执行情况。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { F2_23_FIELDS } from './f2StocktakeConfigs'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sectionFormRef = ref<InstanceType<typeof F2StocktakeSectionForm> | null>(null)
const ocrTargetField = ref('')

// ─── 审计说明 / 审计结论（标准打磨项，独立持久化） ─────────────────────────────
const NOTE_KEY = 'F2-23-audit-note'
const CONCLUSION_KEY = 'F2-23-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function persistAudit(key: string, val: string): void {
  const item: ChecklistResponse = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistAudit(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const multilineFields = computed(() =>
  F2_23_FIELDS.filter((f) => f.multiline && !f.isSection),
)

function uploadOcr() {
  if (!ocrTargetField.value) {
    ElMessage.warning('请先选择要填入的目标字段')
    return
  }
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      const data = res.data?.data ?? res.data ?? {}
      const text = data.full_text ?? data.extracted_text ?? data.summary ?? data.extracted_fields?.content ?? ''
      if (!text) { ElMessage.warning('OCR 未识别到有效内容'); return }
      const preview = text.length > 200 ? text.slice(0, 200) + '…' : text
      await ElMessageBox.confirm(
        `识别内容预览：\n${preview}`,
        'OCR 识别结果确认',
        { type: 'info', confirmButtonText: '填入字段', cancelButtonText: '取消' },
      )
      // 通过 allResponses 写入字段
      const fieldsKey = 'F2-23-fields'
      const existing = props.allResponses.get(fieldsKey)
      let fields: Record<string, string> = {}
      if (existing?.remark) {
        try { fields = JSON.parse(existing.remark) } catch { /* ignore */ }
      }
      fields[ocrTargetField.value] = text
      const updated: ChecklistResponse = {
        item_id: fieldsKey,
        conclusion: null,
        remark: JSON.stringify(fields),
      }
      props.allResponses.set(fieldsKey, updated)
      window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail: { items: [updated] } }))
      ElMessage.success('OCR 内容已填入')
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('OCR 识别失败')
    }
  }
  input.click()
}
</script>

<style scoped>
.f2-summary-wrapper { font-size: var(--wp-font-size, 13px); padding: 12px; }
.ocr-attach-bar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-top: 1px solid #ebeef5; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.hint { font-size: 12px; color: #909399; }

/* 审计说明 / 审计结论卡片 */
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
