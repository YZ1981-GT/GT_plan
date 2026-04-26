<template>
  <el-dialog append-to-body
    v-model="dialogVisible"
    :title="isEditMode ? '编辑审计结果' : '新建审计结果'"
    width="680px"
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="120px"
      class="result-form"
    >
      <!-- Result Number (auto-generated) -->
      <el-form-item label="结果编号">
        <el-input
          v-model="formData.result_no"
          placeholder="自动生成"
          disabled
          class="gt-input"
        />
      </el-form-item>

      <!-- Instruction Reference -->
      <el-form-item label="关联指令" prop="instruction_id">
        <el-select
          v-model="formData.instruction_id"
          placeholder="请选择关联的审计指令"
          filterable
          :disabled="isEditMode"
          class="gt-select"
        >
          <el-option
            v-for="instr in instructions"
            :key="instr.id"
            :label="`${instr.instruction_no} - ${instr.content?.substring(0, 40)}...`"
            :value="instr.id"
          />
        </el-select>
      </el-form-item>

      <!-- Received Date -->
      <el-form-item label="收到日期" prop="received_date">
        <el-date-picker
          v-model="formData.received_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          style="width: 100%"
          class="gt-date-picker"
        />
      </el-form-item>

      <!-- Status -->
      <el-form-item label="状态" prop="status">
        <el-select v-model="formData.status" class="gt-select">
          <el-option label="待处理 (Pending)" value="pending" />
          <el-option label="已收到 (Received)" value="received" />
          <el-option label="已审核 (Reviewed)" value="reviewed" />
        </el-select>
      </el-form-item>

      <!-- Opinion Type -->
      <el-form-item label="审计意见类型" prop="opinion_type">
        <el-select v-model="formData.opinion_type" class="gt-select" @change="handleOpinionChange">
          <el-option label="标准无保留 (Standard)" value="standard" />
          <el-option label="非标准 - 带说明段 (Unqualified w/ Emphasis)" value="unqualified" />
          <el-option label="非标准 - 保留意见 (Qualified)" value="qualified" />
          <el-option label="非标准 - 否定意见 (Adverse)" value="adverse" />
          <el-option label="非标准 - 无法表示意见 (Disclaimer)" value="disclaimer" />
        </el-select>
      </el-form-item>

      <!-- Non-standard Opinion Alert -->
      <el-alert
        v-if="isNonStandardOpinion"
        title="非标准审计意见"
        description="本结果包含非标准审计意见（保留/否定/无法表示），请重点关注并与审计项目经理确认。"
        type="error"
        show-icon
        :closable="false"
        class="opinion-alert"
      />

      <!-- Summary -->
      <el-form-item label="结果摘要" prop="summary">
        <el-input
          v-model="formData.summary"
          type="textarea"
          :rows="3"
          placeholder="请输入审计结果摘要..."
          maxlength="1000"
          show-word-limit
          class="gt-textarea"
        />
      </el-form-item>

      <!-- Findings -->
      <el-form-item label="审计发现" prop="findings">
        <el-input
          v-model="formData.findings"
          type="textarea"
          :rows="3"
          placeholder="请描述审计过程中发现的问题..."
          class="gt-textarea"
        />
      </el-form-item>

      <!-- Recommendations -->
      <el-form-item label="建议" prop="recommendations">
        <el-input
          v-model="formData.recommendations"
          type="textarea"
          :rows="3"
          placeholder="请输入改进建议..."
          class="gt-textarea"
        />
      </el-form-item>

      <!-- Evaluation Rating -->
      <el-form-item label="评价等级" prop="evaluation_rating">
        <el-select v-model="formData.evaluation_rating" class="gt-select">
          <el-option label="优秀 (Excellent)" value="excellent">
            <span class="rating-option excellent">优秀</span>
          </el-option>
          <el-option label="良好 (Good)" value="good">
            <span class="rating-option good">良好</span>
          </el-option>
          <el-option label="一般 (Fair)" value="fair">
            <span class="rating-option fair">一般</span>
          </el-option>
          <el-option label="较差 (Poor)" value="poor">
            <span class="rating-option poor">较差</span>
          </el-option>
        </el-select>
      </el-form-item>

      <!-- Attachments -->
      <el-form-item label="附件">
        <el-upload
          ref="uploadRef"
          :action="uploadUrl"
          :headers="uploadHeaders"
          :file-list="fileList"
          :before-upload="handleBeforeUpload"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :on-remove="handleFileRemove"
          multiple
          accept=".pdf,.doc,.docx,.xls,.xlsx,.zip,.jpg,.jpeg,.png"
          class="gt-upload"
        >
          <el-button type="primary" plain size="small">
            <span class="upload-icon">+</span> 上传附件
          </el-button>
          <template #tip>
            <div class="upload-tip">
              支持 PDF、Word、Excel、图片、ZIP 格式，单文件不超过 20MB
            </div>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="saving">
          {{ isEditMode ? '保存修改' : '创建结果' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules, type UploadInstance, type UploadRawFile } from 'element-plus'
import { createResult, updateResult, getInstructions } from '@/services/consolidationApi'
import type { InstructionResult, Instruction } from '@/services/consolidationApi'

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  visible: boolean
  result: InstructionResult | null
  projectId?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'saved': [result: InstructionResult]
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const formRef = ref<FormInstance>()
const uploadRef = ref<UploadInstance>()
const saving = ref(false)
const instructions = ref<Instruction[]>([])
const fileList = ref<{ name: string; url: string }[]>([])

const uploadUrl = '/api/consolidation/instruction-results/upload'
const uploadHeaders = {
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
}

// ─── Form Data ────────────────────────────────────────────────────────────────
const formData = ref({
  result_no: '',
  instruction_id: '',
  component_auditor_id: '',
  summary: '',
  received_date: '',
  status: 'pending',
  opinion_type: 'standard',
  findings: '',
  recommendations: '',
  evaluation_rating: 'good',
  attachments: [] as string[],
})

// ─── Computed ────────────────────────────────────────────────────────────────
const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const isEditMode = computed(() => !!props.result)

const isNonStandardOpinion = computed(() => {
  const nonStandard = ['qualified', 'adverse', 'disclaimer', 'unqualified']
  return nonStandard.includes(formData.value.opinion_type)
})

// ─── Validation Rules ────────────────────────────────────────────────────────
const formRules: FormRules = {
  instruction_id: [
    { required: true, message: '请选择关联的审计指令', trigger: 'change' },
  ],
  received_date: [
    { required: true, message: '请选择收到日期', trigger: 'change' },
  ],
  status: [
    { required: true, message: '请选择状态', trigger: 'change' },
  ],
  opinion_type: [
    { required: true, message: '请选择审计意见类型', trigger: 'change' },
  ],
  summary: [
    { required: true, message: '请输入结果摘要', trigger: 'blur' },
    { min: 5, message: '摘要至少5个字符', trigger: 'blur' },
  ],
  evaluation_rating: [
    { required: true, message: '请选择评价等级', trigger: 'change' },
  ],
}

// ─── Load Instructions ────────────────────────────────────────────────────────
async function loadInstructions(projectId: string) {
  try {
    const all = await getInstructions(projectId)
    instructions.value = all.filter(i => i.status === 'acknowledged' || i.status === 'responded')
  } catch {
    ElMessage.error('加载指令列表失败')
  }
}

// ─── Watchers ───────────────────────────────────────────────────────────────
watch(() => props.visible, (val) => {
  if (val) {
    resetForm()
    if (instructions.value.length === 0 && props.projectId) {
      loadInstructions(props.projectId)
    }
  }
})

watch(() => props.result, (res) => {
  if (res) {
    formData.value = {
      result_no: res.result_no || '',
      instruction_id: res.instruction_id || '',
      component_auditor_id: res.component_auditor_id || '',
      summary: res.summary || '',
      received_date: res.received_date || '',
      status: res.status || 'pending',
      opinion_type: (res as any).opinion_type || 'standard',
      findings: (res as any).findings || '',
      recommendations: (res as any).recommendations || '',
      evaluation_rating: (res as any).evaluation_rating || 'good',
      attachments: res.attachments || [],
    }
    fileList.value = res.attachments?.map((url: string, i: number) => ({
      name: `附件${i + 1}`,
      url,
    })) || []
  }
})

// ─── Opinion Change Handler ─────────────────────────────────────────────────
function handleOpinionChange() {
  if (isNonStandardOpinion.value) {
    ElMessage.warning('非标准审计意见需要额外关注和审批')
  }
}

// ─── Form Methods ───────────────────────────────────────────────────────────
function resetForm() {
  formData.value = {
    result_no: '',
    instruction_id: '',
    component_auditor_id: '',
    summary: '',
    received_date: '',
    status: 'pending',
    opinion_type: 'standard',
    findings: '',
    recommendations: '',
    evaluation_rating: 'good',
    attachments: [],
  }
  fileList.value = []
  formRef.value?.resetFields()
}

function handleClosed() {
  formRef.value?.resetFields()
  fileList.value = []
}

// ─── Upload Handlers ─────────────────────────────────────────────────────────
function handleBeforeUpload(file: UploadRawFile) {
  const maxSize = 20 * 1024 * 1024 // 20MB
  if (file.size > maxSize) {
    ElMessage.error('文件大小不能超过 20MB')
    return false
  }
  return true
}

function handleUploadSuccess(response: any, file: any) {
  const url = response.data?.url || response.url || URL.createObjectURL(file.raw)
  formData.value.attachments.push(url)
  ElMessage.success(`${file.name} 上传成功`)
}

function handleUploadError(err: any) {
  ElMessage.error('文件上传失败: ' + (err.message || '未知错误'))
}

function handleFileRemove(file: any) {
  const idx = formData.value.attachments.indexOf(file.url)
  if (idx > -1) formData.value.attachments.splice(idx, 1)
}

// ─── Submit ──────────────────────────────────────────────────────────────────
async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    ElMessage.warning('请完善表单信息')
    return
  }

  saving.value = true
  try {
    const payload = {
      ...formData.value,
      result_no: formData.value.result_no || undefined,
    }

    let saved: InstructionResult
    if (isEditMode.value && props.result) {
      saved = await updateResult(props.result.id, props.result.component_auditor_id || '', payload as any)
    } else {
      saved = await createResult(props.projectId || '', payload as any)
    }

    if (isNonStandardOpinion.value) {
      ElMessage.warning('非标准审计意见已记录，请通知项目经理')
    } else {
      ElMessage.success(isEditMode.value ? '更新成功' : '创建成功')
    }

    emit('saved', saved)
    dialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.result-form {
  padding: var(--gt-space-2) 0;
}

.gt-input :deep(.el-input__wrapper),
.gt-textarea :deep(.el-textarea__inner),
.gt-select :deep(.el-select__wrapper),
.gt-date-picker :deep(.el-date-editor) {
  border-radius: var(--gt-radius-sm);
  box-shadow: none;
  border-color: rgba(75, 45, 119, 0.25);
}

.gt-input :deep(.el-input__wrapper:hover),
.gt-textarea :deep(.el-textarea__inner:hover),
.gt-select :deep(.el-select__wrapper:hover),
.gt-date-picker :deep(.el-date-editor:hover) {
  border-color: var(--gt-color-primary-light);
}

.gt-input :deep(.el-input__wrapper:focus),
.gt-textarea :deep(.el-textarea__inner:focus),
.gt-select :deep(.el-select__wrapper.is-focus),
.gt-date-picker :deep(.el-date-editor.is-active) {
  border-color: var(--gt-color-primary);
  box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.1);
}

.opinion-alert {
  margin-bottom: var(--gt-space-3);
  border-radius: var(--gt-radius-sm);
}

.gt-upload :deep(.el-upload-list) {
  max-height: 120px;
  overflow-y: auto;
}

.upload-icon {
  margin-right: 4px;
  font-weight: 700;
}

.upload-tip {
  margin-top: var(--gt-space-1);
  font-size: 12px;
  color: #999;
}

.rating-option {
  font-weight: 500;
}

.rating-option.excellent {
  color: var(--gt-color-success);
}

.rating-option.good {
  color: var(--gt-color-teal);
}

.rating-option.fair {
  color: #e07b00;
}

.rating-option.poor {
  color: var(--gt-color-coral);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--gt-space-2);
}
</style>
