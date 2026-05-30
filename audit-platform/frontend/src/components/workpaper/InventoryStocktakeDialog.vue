<template>
  <el-dialog
    v-model="visible"
    title="存货监盘记录"
    :fullscreen="true"
    :close-on-press-escape="false"
    :close-on-click-modal="false"
    @close="onCloseAttempt"
    class="gt-fullscreen-dialog"
  >
    <AuditContextHeader
      :procedure-code="wpCode"
      :assertions="['存在', '完整性', '准确性']"
      :risk-level="riskLevel"
    />

    <el-form
      ref="formRef"
      :model="form"
      :rules="formRules"
      label-width="100px"
      size="small"
      class="gt-stocktake-form"
    >
      <el-form-item label="盘点地点" prop="location">
        <el-input v-model="form.location" placeholder="请输入盘点地点（仓库/车间名称）" />
      </el-form-item>

      <el-form-item label="盘点日期" prop="date">
        <el-date-picker
          v-model="form.date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
        />
      </el-form-item>

      <el-form-item label="盘点方式" prop="method">
        <el-select v-model="form.method" placeholder="请选择盘点方式" class="gt-stocktake-method">
          <el-option label="全面盘点" value="full" />
          <el-option label="抽样盘点" value="sampling" />
          <el-option label="循环盘点" value="cycle" />
        </el-select>
      </el-form-item>

      <el-form-item label="盘点人" prop="counter">
        <el-input v-model="form.counter" placeholder="盘点人签字" />
      </el-form-item>

      <el-form-item label="复核人" prop="reviewer">
        <el-input v-model="form.reviewer" placeholder="复核人签字" />
      </el-form-item>

      <el-form-item label="照片附件">
        <el-upload
          :action="uploadAction"
          :headers="uploadHeaders"
          accept="image/*"
          :on-success="onPhotoUploadSuccess"
          :on-remove="onPhotoUploadRemove"
          :file-list="photoFileList"
          :limit="20"
          multiple
        >
          <el-button size="small" type="primary">上传照片</el-button>
          <template #tip>
            <div class="el-upload__tip">支持 jpg/png/heic 等图片格式，最多 20 张</div>
          </template>
        </el-upload>
      </el-form-item>

      <el-form-item label="录像附件">
        <el-upload
          :action="uploadAction"
          :headers="uploadHeaders"
          accept="video/*"
          :on-success="onVideoUploadSuccess"
          :on-remove="onVideoUploadRemove"
          :file-list="videoFileList"
          :limit="5"
          multiple
        >
          <el-button size="small" type="primary">上传录像</el-button>
          <template #tip>
            <div class="el-upload__tip">支持 mp4/mov 等视频格式，最多 5 个</div>
          </template>
        </el-upload>
      </el-form-item>

      <el-form-item label="盘点差异">
        <el-table :data="form.differences" stripe border size="small">
          <el-table-column label="#" type="index" width="50" />
          <el-table-column label="品名" min-width="160">
            <template #default="{ row }">
              <el-input v-model="row.itemName" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="账面数" width="120">
            <template #default="{ row }">
              <el-input-number
                v-model="row.bookQty"
                size="small"
                :controls="false"
                :precision="2"
              />
            </template>
          </el-table-column>
          <el-table-column label="实盘数" width="120">
            <template #default="{ row }">
              <el-input-number
                v-model="row.actualQty"
                size="small"
                :controls="false"
                :precision="2"
              />
            </template>
          </el-table-column>
          <el-table-column label="差异" width="100">
            <template #default="{ row }">
              <el-tag :type="diffTagType(diffOf(row))" size="small">
                {{ diffOf(row).toFixed(2) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="原因/说明" min-width="200">
            <template #default="{ row }">
              <el-input
                v-model="row.reason"
                size="small"
                placeholder="差异原因或处理意见"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ $index }">
              <el-button text type="danger" size="small" @click="removeDiffRow($index)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button text size="small" @click="addDiffRow">+ 新增差异行</el-button>
      </el-form-item>

      <el-form-item label="监盘结论" prop="conclusion">
        <el-input
          v-model="form.conclusion"
          type="textarea"
          :rows="6"
          placeholder="请填写监盘结论（差异是否合理 / 内控是否有效 / 调整建议等）"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="gt-fullscreen-dialog-footer">
        <el-button
          type="success"
          :loading="summarizing"
          :disabled="!canSummarize"
          @click="onLlmSummary"
        >
          LLM 差异分析
        </el-button>
        <el-button @click="onCancel">取消</el-button>
        <el-button
          type="primary"
          :loading="saving"
          :disabled="!doubleSigned"
          @click="onSave"
        >
          保存
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * InventoryStocktakeDialog — F2 存货监盘 D 类弹窗（Sprint 2 Task 2.7 / F-F5）
 *
 * 适用 sheet：F2-21 ~ F2-26 监盘类
 * - fullscreen 模式弹窗
 * - 表单字段：盘点地点/日期/方式（全面/抽样/循环）/盘点人+复核人双签/差异表/结论
 * - 附件：image/* + video/* 双通道（attachment_service 关联 object_type=workpaper_item）
 * - 双签字校验：盘点人 + 复核人 都必须签字才能保存
 * - LLM 差异分析按钮：POST /ai/stocktake-summary 摘要写入结论框
 * - 离线草稿：localStorage 存待提交，恢复网络后保存
 *
 * 与 CustomerInterviewDialog 同模式，仅业务字段差异。
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules, UploadFile, UploadUserFile } from 'element-plus'
import { api } from '@/services/apiProxy'
import AuditContextHeader from './dialogs/AuditContextHeader.vue'
import { confirmLeave } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'

interface StocktakeDiffItem {
  itemName: string
  bookQty: number
  actualQty: number
  reason: string
}

interface AttachmentRef {
  uuid: string
  type: 'image' | 'video'
  name?: string
}

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  wpCode: string
  stocktakeId?: string
}
const props = withDefaults(defineProps<Props>(), {
  stocktakeId: '',
})
const emit = defineEmits<{
  'update:visible': [v: boolean]
  saved: []
}>()

const visible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})

const riskLevel = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const summarizing = ref(false)
const photoFileList = ref<UploadUserFile[]>([])
const videoFileList = ref<UploadUserFile[]>([])

const form = ref({
  location: '',
  date: '',
  method: '' as '' | 'full' | 'sampling' | 'cycle',
  counter: '',
  reviewer: '',
  counter_signed_at: '' as string,
  reviewer_signed_at: '' as string,
  attachments: [] as AttachmentRef[],
  differences: [] as StocktakeDiffItem[],
  conclusion: '',
})

const formRules: FormRules = {
  location: [{ required: true, message: '请输入盘点地点', trigger: 'blur' }],
  date: [{ required: true, message: '请选择盘点日期', trigger: 'change' }],
  method: [{ required: true, message: '请选择盘点方式', trigger: 'change' }],
  counter: [{ required: true, message: '请填写盘点人', trigger: 'blur' }],
  reviewer: [{ required: true, message: '请填写复核人', trigger: 'blur' }],
  conclusion: [{ required: true, message: '请填写监盘结论', trigger: 'blur' }],
}

const sheetKey = computed(() => `stocktake_${props.stocktakeId || props.wpCode}`)
const draftKey = computed(
  () => `gt:stocktake-draft:${props.projectId}:${props.wpId}:${sheetKey.value}`
)

const uploadAction = computed(
  () => `/api/projects/${props.projectId}/attachments/upload`
)
const uploadHeaders = computed(() => {
  const token = localStorage.getItem('token') || ''
  return { Authorization: `Bearer ${token}` }
})

function diffOf(row: StocktakeDiffItem): number {
  return (Number(row.actualQty) || 0) - (Number(row.bookQty) || 0)
}
function diffTagType(d: number): 'success' | 'warning' | 'danger' {
  const abs = Math.abs(d)
  if (abs < 0.01) return 'success'
  if (abs < 10) return 'warning'
  return 'danger'
}

const doubleSigned = computed(
  () => !!form.value.counter?.trim() && !!form.value.reviewer?.trim()
)

const canSummarize = computed(
  () => form.value.differences.length > 0 || !!form.value.conclusion?.trim()
)

function addDiffRow() {
  form.value.differences.push({
    itemName: '',
    bookQty: 0,
    actualQty: 0,
    reason: '',
  })
}
function removeDiffRow(idx: number) {
  form.value.differences.splice(idx, 1)
}

function onPhotoUploadSuccess(response: any, _file: UploadFile) {
  if (response?.id) {
    form.value.attachments.push({
      uuid: response.id,
      type: 'image',
      name: response.filename || _file.name,
    })
  }
}
function onPhotoUploadRemove(_file: UploadFile) {
  form.value.attachments = form.value.attachments.filter(
    (a) => a.type !== 'image' || a.uuid !== (_file as any)?.response?.id
  )
}
function onVideoUploadSuccess(response: any, _file: UploadFile) {
  if (response?.id) {
    form.value.attachments.push({
      uuid: response.id,
      type: 'video',
      name: response.filename || _file.name,
    })
  }
}
function onVideoUploadRemove(_file: UploadFile) {
  form.value.attachments = form.value.attachments.filter(
    (a) => a.type !== 'video' || a.uuid !== (_file as any)?.response?.id
  )
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(draftKey.value)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}
function saveDraft() {
  try {
    localStorage.setItem(draftKey.value, JSON.stringify(form.value))
  } catch {
    /* localStorage quota exceeded — 静默 */
  }
}
function clearDraft() {
  try {
    localStorage.removeItem(draftKey.value)
  } catch {
    /* 静默 */
  }
}

async function loadData() {
  // 优先恢复离线草稿，避免误覆盖未提交内容
  const draft = loadDraft()
  if (draft) {
    Object.assign(form.value, draft)
    return
  }
  try {
    const detail: any = await api.get(
      `/api/projects/${props.projectId}/working-papers/${props.wpId}`
    )
    const sheet =
      detail?.parsed_data?.[sheetKey.value] ||
      detail?.parsed_data?.stocktake_records?.[props.stocktakeId || props.wpCode] ||
      {}
    form.value = {
      location: sheet.location || '',
      date: sheet.date || new Date().toISOString().slice(0, 10),
      method: sheet.method || '',
      counter: sheet.counter || '',
      reviewer: sheet.reviewer || '',
      counter_signed_at: sheet.counter_signed_at || '',
      reviewer_signed_at: sheet.reviewer_signed_at || '',
      attachments: Array.isArray(sheet.attachments) ? sheet.attachments : [],
      differences: Array.isArray(sheet.differences) ? sheet.differences : [],
      conclusion: sheet.conclusion || '',
    }
    photoFileList.value = (form.value.attachments || [])
      .filter((a) => a.type === 'image')
      .map((a) => ({ name: a.name || a.uuid, url: '', uid: a.uuid as any }))
    videoFileList.value = (form.value.attachments || [])
      .filter((a) => a.type === 'video')
      .map((a) => ({ name: a.name || a.uuid, url: '', uid: a.uuid as any }))
    riskLevel.value = detail?.risk_level || ''
  } catch {
    /* 静默 */
  }
}

watch(visible, (v) => {
  if (v) loadData()
})

// 表单值变更时持续保存离线草稿（debounce 由浏览器输入节流隐式覆盖）
watch(
  form,
  () => {
    if (visible.value) saveDraft()
  },
  { deep: true }
)

async function onLlmSummary() {
  summarizing.value = true
  try {
    const res: any = await api.post(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/ai/stocktake-summary`,
      {
        differences: form.value.differences,
        conclusion: form.value.conclusion,
      }
    )
    if (res?.summary) {
      form.value.conclusion = res.summary
      ElMessage.success('LLM 差异分析已生成并填入结论')
    }
    if (Array.isArray(res?.risk_alerts) && res.risk_alerts.length) {
      ElMessage.warning('风险提示：' + res.risk_alerts.join('; '))
    }
  } catch (err: any) {
    handleApiError(err, 'LLM 差异分析')
  } finally {
    summarizing.value = false
  }
}

async function onSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  if (!doubleSigned.value) {
    ElMessage.error('需要盘点人和复核人均签字后方可提交')
    return
  }

  saving.value = true
  try {
    const now = new Date().toISOString()
    const payload = {
      sheet_key: sheetKey.value,
      data: {
        location: form.value.location,
        date: form.value.date,
        method: form.value.method,
        counter: form.value.counter,
        reviewer: form.value.reviewer,
        counter_signed_at: form.value.counter_signed_at || now,
        reviewer_signed_at: form.value.reviewer_signed_at || now,
        attachments: form.value.attachments,
        differences: form.value.differences,
        conclusion: form.value.conclusion,
      },
    }
    await api.patch(
      `/api/projects/${props.projectId}/working-papers/${props.wpId}/parsed-data`,
      payload
    )
    ElMessage.success('监盘记录已保存')
    clearDraft()
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
    await confirmLeave('存货监盘')
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
.gt-stocktake-form {
  padding: 4px 12px;
}
.gt-stocktake-method {
  width: 200px;
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
