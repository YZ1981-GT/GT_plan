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
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import F2StocktakeSectionForm from './F2StocktakeSectionForm.vue'
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
.f2-summary-wrapper { font-size: 13px; padding: 12px; }
.ocr-attach-bar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-top: 1px solid #ebeef5; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
