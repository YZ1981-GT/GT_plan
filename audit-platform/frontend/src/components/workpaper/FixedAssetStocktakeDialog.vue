<template>
  <el-dialog
    v-model="visible"
    title="固定资产监盘记录"
    :fullscreen="true"
    :close-on-press-escape="false"
    :close-on-click-modal="false"
    @close="onCloseAttempt"
    class="gt-fullscreen-dialog"
  >
    <AuditContextHeader
      :procedure-code="wpCode"
      :assertions="['存在', '完整性', '准确性', '权利和义务']"
      :risk-level="riskLevel"
    />

    <el-form
      ref="formRef"
      :model="form"
      :rules="formRules"
      label-width="120px"
      size="small"
      class="gt-stocktake-form"
    >
      <el-form-item label="盘点地点" prop="location">
        <el-input v-model="form.location" placeholder="请输入盘点地点（含GPS坐标）">
          <template #append>
            <el-button @click="captureGPS" :loading="gpsLoading">📍 GPS</el-button>
          </template>
        </el-input>
      </el-form-item>

      <el-form-item label="盘点日期" prop="date">
        <el-date-picker
          v-model="form.date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
        />
      </el-form-item>

      <el-form-item label="盘点人" prop="counter">
        <el-input v-model="form.counter" placeholder="盘点人签字" />
      </el-form-item>

      <el-form-item label="复核人" prop="reviewer">
        <el-input v-model="form.reviewer" placeholder="复核人签字" />
      </el-form-item>

      <el-form-item label="资产编号清单" prop="asset_list">
        <el-input
          v-model="form.asset_list"
          type="textarea"
          :rows="4"
          placeholder="请输入资产编号清单（每行一个编号，或逗号分隔）"
        />
      </el-form-item>

      <el-form-item label="盘点状态" prop="status">
        <el-select v-model="form.status" placeholder="请选择盘点状态" class="gt-stocktake-status">
          <el-option label="在用" value="in_use" />
          <el-option label="闲置" value="idle" />
          <el-option label="报废" value="scrapped" />
          <el-option label="盘亏" value="shortage" />
        </el-select>
      </el-form-item>

      <!-- 盘亏时强制填写原因 + 责任认定 -->
      <el-form-item
        v-if="form.status === 'shortage'"
        label="盘亏原因"
        prop="shortage_reason"
      >
        <el-input
          v-model="form.shortage_reason"
          type="textarea"
          :rows="3"
          placeholder="请填写盘亏原因（必填）"
        />
      </el-form-item>

      <el-form-item
        v-if="form.status === 'shortage'"
        label="责任认定"
        prop="shortage_responsibility"
      >
        <el-input
          v-model="form.shortage_responsibility"
          type="textarea"
          :rows="2"
          placeholder="请填写责任认定（必填）"
        />
      </el-form-item>

      <el-form-item label="照片/视频附件">
        <el-upload
          :action="uploadAction"
          :headers="uploadHeaders"
          accept="image/*,video/*"
          :on-success="onAttachmentUploadSuccess"
          :on-remove="onAttachmentUploadRemove"
          :file-list="attachmentFileList"
          :limit="30"
          multiple
        >
          <el-button size="small" type="primary">上传照片/视频</el-button>
          <template #tip>
            <div class="el-upload__tip">支持 jpg/png/heic/mp4/mov 等格式，最多 30 个</div>
          </template>
        </el-upload>
      </el-form-item>

      <el-form-item label="监盘结论" prop="conclusion">
        <el-input
          v-model="form.conclusion"
          type="textarea"
          :rows="6"
          placeholder="请填写监盘结论（资产实物状态/标签完整性/使用情况/调整建议等）"
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
 * FixedAssetStocktakeDialog — H 固定资产循环监盘 D 类弹窗（Sprint 2 Task 2.7 / H-F5）
 *
 * 适用 sheet：13 处监盘类 sheet（H1-9~H1-11 / H2-12~H2-14 / H3-9 / H5-9~H5-11 / H7-8~H7-10）
 * - fullscreen 模式弹窗
 * - 表单字段：盘点地点(含GPS)/日期/盘点人+复核人双签/资产编号清单/盘点状态/照片视频附件/结论
 * - 盘亏项强制填写盘亏原因 + 责任认定
 * - 双签字校验：盘点人 + 复核人 都必须签字才能保存
 * - LLM 差异分析按钮：POST /ai/stocktake-summary 摘要写入结论框
 *
 * 复用 InventoryStocktakeDialog 模式，适配固定资产业务字段。
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules, UploadFile, UploadUserFile } from 'element-plus'
import { api } from '@/services/apiProxy'
import AuditContextHeader from './dialogs/AuditContextHeader.vue'
import { confirmLeave } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'

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
const gpsLoading = ref(false)
const attachmentFileList = ref<UploadUserFile[]>([])

const form = ref({
  location: '',
  date: '',
  counter: '',
  reviewer: '',
  counter_signed_at: '' as string,
  reviewer_signed_at: '' as string,
  asset_list: '',
  status: '' as '' | 'in_use' | 'idle' | 'scrapped' | 'shortage',
  shortage_reason: '',
  shortage_responsibility: '',
  attachments: [] as AttachmentRef[],
  conclusion: '',
})

const shortageReasonValidator = (_rule: any, value: string, callback: any) => {
  if (form.value.status === 'shortage' && !value?.trim()) {
    callback(new Error('盘亏时必须填写盘亏原因'))
  } else {
    callback()
  }
}

const shortageResponsibilityValidator = (_rule: any, value: string, callback: any) => {
  if (form.value.status === 'shortage' && !value?.trim()) {
    callback(new Error('盘亏时必须填写责任认定'))
  } else {
    callback()
  }
}

const formRules: FormRules = {
  location: [{ required: true, message: '请输入盘点地点', trigger: 'blur' }],
  date: [{ required: true, message: '请选择盘点日期', trigger: 'change' }],
  counter: [{ required: true, message: '请填写盘点人', trigger: 'blur' }],
  reviewer: [{ required: true, message: '请填写复核人', trigger: 'blur' }],
  asset_list: [{ required: true, message: '请输入资产编号清单', trigger: 'blur' }],
  status: [{ required: true, message: '请选择盘点状态', trigger: 'change' }],
  conclusion: [{ required: true, message: '请填写监盘结论', trigger: 'blur' }],
  shortage_reason: [{ validator: shortageReasonValidator, trigger: 'blur' }],
  shortage_responsibility: [{ validator: shortageResponsibilityValidator, trigger: 'blur' }],
}

const sheetKey = computed(() => `h_stocktake_${props.stocktakeId || props.wpCode}`)
const draftKey = computed(
  () => `gt:h-stocktake-draft:${props.projectId}:${props.wpId}:${sheetKey.value}`
)

const uploadAction = computed(
  () => `/api/projects/${props.projectId}/attachments/upload`
)
const uploadHeaders = computed(() => {
  const token = localStorage.getItem('token') || ''
  return { Authorization: `Bearer ${token}` }
})

const doubleSigned = computed(
  () => !!form.value.counter?.trim() && !!form.value.reviewer?.trim()
)

const canSummarize = computed(
  () => !!form.value.asset_list?.trim() || !!form.value.conclusion?.trim()
)

function captureGPS() {
  if (!navigator.geolocation) {
    ElMessage.warning('当前浏览器不支持 GPS 定位')
    return
  }
  gpsLoading.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude } = pos.coords
      form.value.location = `${form.value.location} (GPS: ${latitude.toFixed(6)}, ${longitude.toFixed(6)})`.trim()
      gpsLoading.value = false
    },
    () => {
      ElMessage.warning('GPS 定位失败，请手动输入')
      gpsLoading.value = false
    },
    { timeout: 10000 }
  )
}

function onAttachmentUploadSuccess(response: any, file: UploadFile) {
  if (response?.id) {
    const isVideo = file.name?.match(/\.(mp4|mov|avi|wmv|flv|mkv)$/i)
    form.value.attachments.push({
      uuid: response.id,
      type: isVideo ? 'video' : 'image',
      name: response.filename || file.name,
    })
  }
}
function onAttachmentUploadRemove(file: UploadFile) {
  form.value.attachments = form.value.attachments.filter(
    (a) => a.uuid !== (file as any)?.response?.id
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
      detail?.parsed_data?.h_stocktake_records?.[props.stocktakeId || props.wpCode] ||
      {}
    form.value = {
      location: sheet.location || '',
      date: sheet.date || new Date().toISOString().slice(0, 10),
      counter: sheet.counter || '',
      reviewer: sheet.reviewer || '',
      counter_signed_at: sheet.counter_signed_at || '',
      reviewer_signed_at: sheet.reviewer_signed_at || '',
      asset_list: sheet.asset_list || '',
      status: sheet.status || '',
      shortage_reason: sheet.shortage_reason || '',
      shortage_responsibility: sheet.shortage_responsibility || '',
      attachments: Array.isArray(sheet.attachments) ? sheet.attachments : [],
      conclusion: sheet.conclusion || '',
    }
    attachmentFileList.value = (form.value.attachments || []).map((a) => ({
      name: a.name || a.uuid,
      url: '',
      uid: a.uuid as any,
    }))
    riskLevel.value = detail?.risk_level || ''
  } catch {
    /* 静默 */
  }
}

watch(visible, (v) => {
  if (v) loadData()
})

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
        differences: form.value.asset_list
          .split(/[\n,，]/)
          .filter((s: string) => s.trim())
          .map((assetId: string) => ({
            itemName: assetId.trim(),
            bookQty: 1,
            actualQty: form.value.status === 'shortage' ? 0 : 1,
            reason: form.value.shortage_reason || form.value.status,
          })),
        conclusion: form.value.conclusion,
        wp_code: props.wpCode,
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
        counter: form.value.counter,
        reviewer: form.value.reviewer,
        counter_signed_at: form.value.counter_signed_at || now,
        reviewer_signed_at: form.value.reviewer_signed_at || now,
        asset_list: form.value.asset_list,
        status: form.value.status,
        shortage_reason: form.value.shortage_reason,
        shortage_responsibility: form.value.shortage_responsibility,
        attachments: form.value.attachments,
        conclusion: form.value.conclusion,
      },
    }
    await api.patch(
      `/api/projects/${props.projectId}/working-papers/${props.wpId}/parsed-data`,
      payload
    )
    ElMessage.success('固定资产监盘记录已保存')
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
    await confirmLeave('固定资产监盘')
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
.gt-stocktake-status {
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
