<template>
  <div class="f2-plan-wrapper">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表记录存货监盘计划，明确监盘范围、时间、地点、人员分工及抽盘方法（CAS 1311 存货监盘）。</p>
        <p>2. 应涵盖存放地点清单、监盘小组成员、抽盘比例与重点关注品种（高价值 / 易变质 / 账实易差异）。</p>
        <p>3. 对无法实施监盘的存放地点，应设计替代审计程序并说明理由。</p>
        <p>4. 可通过 📎 附件OCR识别，将盘点通知 / 计划文件内容填入对应字段。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：制定充分的存货监盘计划，确保监盘范围与抽样覆盖关键风险，为存货存在性与状况认定提供程序基础。"
      class="objective-alert"
    />

    <F2StocktakeSectionForm
      ref="sectionFormRef"
      title="监盘计划 F2-22"
      sheet-code="F2-22"
      fields-key="F2-22-fields"
      note-key="F2-22-note"
      :field-defs="F2_22_FIELDS"
      :wp-id="wpId"
      :project-id="projectId"
      :all-responses="allResponses"
      :is-readonly="isReadonly"
      ai-section="stocktake-plan"
      ai-title="AI 生成 · 监盘计划"
      audit-note-label="监盘计划结论"
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
import { F2_22_FIELDS } from './f2StocktakeConfigs'
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
  F2_22_FIELDS.filter((f) => f.multiline && !f.isSection),
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
      const fieldsKey = 'F2-22-fields'
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
.f2-plan-wrapper { font-size: var(--wp-font-size, 13px); padding: 12px; }
.ocr-attach-bar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-top: 1px solid #ebeef5; }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
</style>
