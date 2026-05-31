<template>
  <el-dialog
    v-model="visible"
    title="客户访谈记录"
    :fullscreen="true"
    :close-on-press-escape="false"
    :close-on-click-modal="false"
    @close="onCloseAttempt"
    class="gt-fullscreen-dialog"
  >
    <AuditContextHeader
      :procedure-code="wpCode"
      :assertions="['存在', '完整性', '发生']"
      :risk-level="riskLevel"
    />

    <el-form
      ref="formRef"
      :model="form"
      :rules="formRules"
      label-width="100px"
      size="small"
      class="gt-interview-form"
    >
      <el-form-item label="客户名称" prop="customer_name">
        <el-input v-model="form.customer_name" placeholder="请输入客户名称" />
      </el-form-item>

      <el-form-item label="访谈方式" prop="interview_method">
        <el-select v-model="form.interview_method" placeholder="请选择访谈方式">
          <el-option label="现场" value="现场" />
          <el-option label="电话" value="电话" />
          <el-option label="视频" value="视频" />
          <el-option label="书面" value="书面" />
        </el-select>
      </el-form-item>

      <el-form-item label="访谈日期" prop="interview_date">
        <el-date-picker
          v-model="form.interview_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
        />
      </el-form-item>

      <el-form-item label="录音附件">
        <el-upload
          :action="uploadAction"
          :headers="uploadHeaders"
          accept="audio/*"
          :on-success="onUploadSuccess"
          :on-remove="onUploadRemove"
          :file-list="fileList"
          :limit="5"
        >
          <el-button size="small" type="primary">上传录音</el-button>
          <template #tip>
            <div class="el-upload__tip">支持 mp3/wav/m4a 等音频格式</div>
          </template>
        </el-upload>
      </el-form-item>

      <el-form-item label="访谈记录" prop="transcript">
        <div class="gt-interview-transcript-row">
          <el-input
            v-model="form.transcript"
            type="textarea"
            :rows="8"
            placeholder="请记录访谈内容要点"
          />
        </div>
      </el-form-item>

      <el-form-item label="发现问题">
        <el-input
          v-model="form.issues_found"
          type="textarea"
          :rows="4"
          placeholder="访谈中发现的问题或异常"
        />
      </el-form-item>

      <el-form-item label="访谈人" prop="interviewer">
        <el-input v-model="form.interviewer" placeholder="访谈人签字" />
      </el-form-item>

      <el-form-item label="复核人" prop="reviewer">
        <el-input v-model="form.reviewer" placeholder="复核人签字" />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="gt-fullscreen-dialog-footer">
        <el-button
          type="success"
          :loading="summarizing"
          :disabled="!form.transcript"
          @click="onLlmSummary"
        >
          LLM 摘要
        </el-button>
        <el-button @click="onCancel">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * CustomerInterviewDialog — D4 客户访谈 D 类弹窗
 *
 * D 循环专属组件（D4-30/D4-31 客户访谈）
 * - fullscreen el-dialog + 审计上下文头部
 * - 表单：客户/访谈方式/日期/录音附件/访谈记录/发现问题/双人签字
 * - LLM 摘要按钮调 POST interview-summary API
 * - 录音附件关联 object_type=workpaper_item
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules, UploadFile, UploadUserFile } from 'element-plus'
import { api } from '@/services/apiProxy'
import AuditContextHeader from './dialogs/AuditContextHeader.vue'
import { confirmLeave } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  wpCode: string
  itemId?: string
}
const props = withDefaults(defineProps<Props>(), {
  itemId: '',
})
const emit = defineEmits<{
  'update:visible': [v: boolean]
  saved: []
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})
const visible = dialogVisible

const riskLevel = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const summarizing = ref(false)
const fileList = ref<UploadUserFile[]>([])

const form = ref({
  customer_name: '',
  interview_method: '',
  interview_date: '',
  transcript: '',
  issues_found: '',
  interviewer: '',
  reviewer: '',
  audio_attachments: [] as string[],
})

const formRules: FormRules = {
  customer_name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }],
  interview_method: [{ required: true, message: '请选择访谈方式', trigger: 'change' }],
  interview_date: [{ required: true, message: '请选择访谈日期', trigger: 'change' }],
  transcript: [{ required: true, message: '请填写访谈记录', trigger: 'blur' }],
  interviewer: [{ required: true, message: '请填写访谈人', trigger: 'blur' }],
  reviewer: [{ required: true, message: '请填写复核人', trigger: 'blur' }],
}

const uploadAction = computed(() =>
  `/api/projects/${props.projectId}/attachments/upload`
)
const uploadHeaders = computed(() => {
  const token = localStorage.getItem('token') || ''
  return { Authorization: `Bearer ${token}` }
})

function onUploadSuccess(response: any, _file: UploadFile) {
  if (response?.id) {
    form.value.audio_attachments.push(response.id)
  }
}

function onUploadRemove(_file: UploadFile) {
  // Simplified: remove last added attachment
  form.value.audio_attachments.pop()
}

async function loadData() {
  try {
    const detail: any = await api.get(
      `/api/projects/${props.projectId}/working-papers/${props.wpId}`
    )
    const sheetKey = props.itemId || `interview_${props.wpCode}`
    const sheet = detail?.parsed_data?.[sheetKey] || {}
    form.value = {
      customer_name: sheet.customer_name || '',
      interview_method: sheet.interview_method || '',
      interview_date: sheet.interview_date || new Date().toISOString().slice(0, 10),
      transcript: sheet.transcript || '',
      issues_found: sheet.issues_found || '',
      interviewer: sheet.interviewer || '',
      reviewer: sheet.reviewer || '',
      audio_attachments: sheet.audio_attachments || [],
    }
    riskLevel.value = detail?.risk_level || ''
  } catch {
    /* 静默 */
  }
}

watch(visible, (v) => {
  if (v) loadData()
})

async function onLlmSummary() {
  if (!form.value.transcript) {
    ElMessage.warning('请先填写访谈记录')
    return
  }
  summarizing.value = true
  try {
    const res: any = await api.post(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/ai/interview-summary`,
      {
        transcript: form.value.transcript,
        audio_recording_uuid: form.value.audio_attachments[0] || undefined,
      }
    )
    if (res?.summary) {
      form.value.transcript = res.summary
      ElMessage.success('LLM 摘要已生成并填入访谈记录')
    }
    if (res?.issues_found?.length) {
      form.value.issues_found = res.issues_found.join('\n')
    }
  } catch (err: any) {
    handleApiError(err, 'LLM 摘要')
  } finally {
    summarizing.value = false
  }
}

async function onSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    const sheetKey = props.itemId || `interview_${props.wpCode}`
    await api.patch(
      `/api/projects/${props.projectId}/working-papers/${props.wpId}/parsed-data`,
      {
        sheet_key: sheetKey,
        data: {
          customer_name: form.value.customer_name,
          interview_method: form.value.interview_method,
          interview_date: form.value.interview_date,
          transcript: form.value.transcript,
          issues_found: form.value.issues_found,
          interviewer: form.value.interviewer,
          reviewer: form.value.reviewer,
          audio_attachments: form.value.audio_attachments,
        },
      }
    )
    ElMessage.success('访谈记录已保存')
    emit('saved')
    emit('update:visible', false)
  } catch (err: any) {
    handleApiError(err, '保存')
  } finally {
    saving.value = false
  }
}

async function onCancel() {
  try {
    await confirmLeave('客户访谈')
    emit('update:visible', false)
  } catch {
    /* user cancelled */
  }
}

function onCloseAttempt() {
  onCancel()
}
</script>

<style scoped>
.gt-interview-form {
  padding: 4px 12px;
}
.gt-interview-transcript-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.gt-interview-transcript-row :deep(.el-textarea) {
  flex: 1;
}
.gt-fullscreen-dialog :deep(.el-dialog__body) {
  padding: 8px 16px;
  height: calc(100vh - 110px);
  overflow-y: auto;
}
.gt-fullscreen-dialog-footer {
  position: sticky;
  bottom: 0;
  background: var(--gt-color-bg-white, #fff);
  padding: 8px 0;
  border-top: 1px solid var(--gt-color-border-lighter, #ebeef5);
  text-align: right;
}
</style>
