<template>
  <el-dialog append-to-body
    v-model="dialogVisible"
    :title="isEditMode ? '编辑审计指令' : '新建审计指令'"
    width="600px"
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="formRules"
      label-width="110px"
      class="gt-instruction-form"
    >
      <!-- Instruction Number (auto-generated, read-only) -->
      <el-form-item label="指令编号">
        <el-input
          v-model="formData.instruction_no"
          placeholder="自动生成"
          disabled
          class="gt-input"
        />
      </el-form-item>

      <!-- Component Auditor -->
      <el-form-item label="组成部分审计师" prop="component_auditor_id">
        <el-select
          v-model="formData.component_auditor_id"
          placeholder="请选择审计师"
          filterable
          :disabled="isEditMode || !!componentAuditorId"
          class="gt-select"
        >
          <el-option
            v-for="auditor in auditors"
            :key="auditor.id"
            :label="`${auditor.auditor_name} - ${auditor.component_name}`"
            :value="auditor.id"
          />
        </el-select>
      </el-form-item>

      <!-- Content -->
      <el-form-item label="指令内容" prop="content">
        <el-input
          v-model="formData.content"
          type="textarea"
          :rows="4"
          placeholder="请输入审计指令的详细内容..."
          maxlength="2000"
          show-word-limit
          class="gt-textarea"
        />
      </el-form-item>

      <!-- Dates Row -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="发出日期" prop="issued_date">
            <el-date-picker
              v-model="formData.issued_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%"
              class="gt-date-picker"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="截止日期" prop="due_date">
            <el-date-picker
              v-model="formData.due_date"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%"
              class="gt-date-picker"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- Scope -->
      <el-form-item label="审计范围" prop="scope">
        <el-input
          v-model="formData.scope"
          placeholder="例如：财务报表审计、内部控制审计等"
          class="gt-input"
        />
      </el-form-item>

      <!-- Status -->
      <el-form-item label="状态" prop="status">
        <el-select v-model="formData.status" class="gt-select">
          <el-option label="草稿 (Draft)" value="draft" />
          <el-option label="已发送 (Sent)" value="sent" />
          <el-option label="已确认 (Acknowledged)" value="acknowledged" />
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
          accept=".pdf,.doc,.docx,.xls,.xlsx,.zip"
          class="gt-upload"
        >
          <el-button type="primary" plain size="small">
            <span class="upload-icon">+</span> 上传附件
          </el-button>
          <template #tip>
            <div class="upload-tip">
              支持 PDF、Word、Excel、ZIP 格式，单文件不超过 20MB
            </div>
          </template>
        </el-upload>
      </el-form-item>

      <!-- Sent Warning -->
      <el-alert
        v-if="formData.status === 'sent' && isEditMode"
        title="指令已发送，修改将记录变更日志"
        type="warning"
        :closable="false"
        show-icon
        class="sent-warning"
      />
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button @click="handleSaveDraft" :loading="saving" plain>保存草稿</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="saving">
          {{ isEditMode ? '保存修改' : '创建指令' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, type FormInstance, type FormRules, type UploadInstance, type UploadRawFile } from 'element-plus'
import { createInstruction, updateInstruction, getComponentAuditors } from '@/services/consolidationApi'
import type { ComponentAuditor, Instruction } from '@/services/consolidationApi'

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  visible: boolean
  instruction: Instruction | null
  componentAuditorId?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'saved': [instruction: Instruction]
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const formRef = ref<FormInstance>()
const uploadRef = ref<UploadInstance>()
const saving = ref(false)
const auditors = ref<ComponentAuditor[]>([])
const fileList = ref<{ name: string; url: string }[]>([])

const uploadUrl = '/api/consolidation/instructions/upload'
const uploadHeaders = {
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
}

// ─── Form Data ────────────────────────────────────────────────────────────────
const formData = ref({
  instruction_no: '',
  content: '',
  issued_date: '',
  due_date: '',
  scope: '',
  status: 'draft',
  component_auditor_id: '',
  attachments: [] as string[],
})

// ─── Computed ────────────────────────────────────────────────────────────────
const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

const isEditMode = computed(() => !!props.instruction)

// ─── Validation Rules ────────────────────────────────────────────────────────
const formRules: FormRules = {
  content: [
    { required: true, message: '请输入指令内容', trigger: 'blur' },
    { min: 10, message: '指令内容至少10个字符', trigger: 'blur' },
  ],
  issued_date: [
    { required: true, message: '请选择发出日期', trigger: 'change' },
  ],
  due_date: [
    { required: true, message: '请选择截止日期', trigger: 'change' },
    {
      validator: (_rule, value, callback) => {
        if (value && formData.value.issued_date && value < formData.value.issued_date) {
          callback(new Error('截止日期不能早于发出日期'))
        } else {
          callback()
        }
      },
      trigger: 'change',
    },
  ],
  component_auditor_id: [
    { required: true, message: '请选择组成部分审计师', trigger: 'change' },
  ],
  status: [
    { required: true, message: '请选择状态', trigger: 'change' },
  ],
}

// ─── Load Auditors ────────────────────────────────────────────────────────────
async function loadAuditors(projectId: string) {
  try {
    auditors.value = await getComponentAuditors(projectId)
  } catch {
    ElMessage.error('加载审计师列表失败')
  }
}

// ─── Watchers ───────────────────────────────────────────────────────────────
watch(() => props.visible, (val) => {
  if (val) {
    // Reset form and load data
    resetForm()
    const projectId = formData.value.component_auditor_id || props.componentAuditorId || ''
    if (auditors.value.length === 0 && projectId) {
      loadAuditors(projectId)
    }
  }
})

watch(() => props.instruction, (instr) => {
  if (instr) {
    formData.value = {
      instruction_no: instr.instruction_no || '',
      content: instr.content || '',
      issued_date: instr.issued_date || '',
      due_date: instr.due_date || '',
      scope: '',
      status: instr.status || 'draft',
      component_auditor_id: instr.component_auditor_id || '',
      attachments: [],
    }
    fileList.value = (instr as any).attachments?.map((url: string, i: number) => ({
      name: `附件${i + 1}`,
      url,
    })) || []
  }
})

watch(() => props.componentAuditorId, (id) => {
  if (id) {
    formData.value.component_auditor_id = id
  }
})

// ─── Form Methods ────────────────────────────────────────────────────────────
function resetForm() {
  formData.value = {
    instruction_no: '',
    content: '',
    issued_date: '',
    due_date: '',
    scope: '',
    status: 'draft',
    component_auditor_id: props.componentAuditorId || '',
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

function handleFileRemove(file: any, _fileList: any[]) {
  const idx = formData.value.attachments.indexOf(file.url)
  if (idx > -1) formData.value.attachments.splice(idx, 1)
}

// ─── Submit ──────────────────────────────────────────────────────────────────
async function handleSaveDraft() {
  formData.value.status = 'draft'
  await handleSubmit()
}

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
      instruction_no: formData.value.instruction_no || undefined,
    }

    let saved: Instruction
    if (isEditMode.value && props.instruction) {
      saved = await updateInstruction(props.instruction.id, props.instruction.component_auditor_id || '', payload)
    } else {
      saved = await createInstruction(props.componentAuditorId || formData.value.component_auditor_id, payload as any)
    }

    // Notify if status changed to 'sent'
    if (formData.value.status === 'sent' && !isEditMode.value) {
      ElMessage.success('指令已发送，审计师将收到通知')
    }

    ElMessage.success(isEditMode.value ? '更新成功' : '创建成功')
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
.gt-instruction-form {
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

.sent-warning {
  margin-top: var(--gt-space-3);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--gt-space-2);
}
</style>
