<template>
  <el-dialog
    v-model="visible"
    :title="`${typeLabel}导入`"
    width="700px"
    append-to-body
    destroy-on-close
    @close="onClose"
  >
    <!-- 步骤条 -->
    <el-steps :active="step" simple style="margin-bottom: 20px">
      <el-step title="上传文件" />
      <el-step title="校验预览" />
      <el-step title="导入结果" />
    </el-steps>

    <!-- Step 0: 上传 -->
    <div v-if="step === 0" class="gt-import-step">
      <div class="gt-import-tip">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>导入说明</template>
          <div style="font-size: 12px; line-height: 1.8">
            <p>请先下载标准模板，按模板格式填写数据后上传。</p>
            <p>带 <span style="color: #e6a23c; font-weight: 600">*</span> 的列为必填项，黄色底色标记。</p>
            <p>第 2 行为示例数据，导入时会自动跳过。</p>
          </div>
        </el-alert>
      </div>

      <div class="gt-import-actions">
        <el-button type="primary" plain @click="downloadTemplate" :loading="downloading">
          <el-icon><Download /></el-icon> 下载导入模板
        </el-button>
        <el-radio-group v-model="importMode" size="small" style="margin-left: 12px">
          <el-radio-button value="append">追加</el-radio-button>
          <el-radio-button value="overwrite">覆盖</el-radio-button>
        </el-radio-group>
      </div>

      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        accept=".xlsx,.xls"
        :limit="1"
        :on-change="onFileChange"
        :on-remove="onFileRemove"
        class="gt-import-upload"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">将文件拖到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .xlsx 格式，最大 50MB</div>
        </template>
      </el-upload>
    </div>

    <!-- Step 1: 校验预览 -->
    <div v-if="step === 1" class="gt-import-step">
      <div v-if="validating" style="text-align: center; padding: 40px">
        <el-icon class="is-loading" :size="32" color="var(--gt-color-primary)"><Loading /></el-icon>
        <p style="margin-top: 12px; color: #999">正在校验文件格式...</p>
      </div>

      <template v-else-if="validationResult">
        <el-result
          v-if="validationResult.valid"
          icon="success"
          title="格式校验通过"
          :sub-title="`共 ${validationResult.row_count} 行有效数据`"
          style="padding: 10px 0"
        />
        <el-result
          v-else
          icon="error"
          title="格式校验未通过"
          :sub-title="`发现 ${validationResult.errors?.length || 0} 个错误`"
          style="padding: 10px 0"
        />

        <div v-if="validationResult.errors?.length" class="gt-import-errors">
          <div v-for="(err, i) in validationResult.errors.slice(0, 20)" :key="i" class="gt-import-error-item">
            <el-icon color="#f56c6c"><CircleClose /></el-icon>
            <span>{{ err.message }}</span>
          </div>
          <div v-if="validationResult.errors.length > 20" style="color: #999; font-size: 12px; padding: 4px 0">
            ... 还有 {{ validationResult.errors.length - 20 }} 个错误
          </div>
        </div>

        <div v-if="validationResult.warnings?.length" class="gt-import-warnings">
          <div v-for="(w, i) in validationResult.warnings" :key="i" class="gt-import-warning-item">
            <el-icon color="#e6a23c"><Warning /></el-icon>
            <span>{{ w.message }}</span>
          </div>
        </div>

        <div v-if="validationResult.preview_rows?.length" style="margin-top: 12px">
          <h4 style="font-size: 13px; color: #666; margin-bottom: 8px">数据预览（前 10 行）</h4>
          <el-table :data="validationResult.preview_rows" size="small" stripe max-height="250" border>
            <el-table-column
              v-for="col in previewColumns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="100"
              show-overflow-tooltip
            />
          </el-table>
        </div>
      </template>
    </div>

    <!-- Step 2: 导入结果 -->
    <div v-if="step === 2" class="gt-import-step">
      <div v-if="importing" style="text-align: center; padding: 40px">
        <el-icon class="is-loading" :size="32" color="var(--gt-color-primary)"><Loading /></el-icon>
        <p style="margin-top: 12px; color: #999">正在导入数据...</p>
      </div>

      <template v-else-if="importResult">
        <el-result
          v-if="importResult.success"
          icon="success"
          :title="importResult.message"
        >
          <template #sub-title>
            <div style="font-size: 13px; color: #666">
              <span>成功 {{ importResult.imported_count }} 条</span>
              <span v-if="importResult.skipped_count"> · 跳过 {{ importResult.skipped_count }} 条</span>
              <span v-if="importResult.failed_count" style="color: #f56c6c"> · 失败 {{ importResult.failed_count }} 条</span>
            </div>
          </template>
        </el-result>
        <el-result
          v-else
          icon="error"
          :title="importResult.message || '导入失败'"
        />

        <!-- 失败行详情 -->
        <div v-if="importResult.failed_rows?.length" class="gt-import-errors" style="margin-top: 8px">
          <h4 style="font-size: 12px; color: #999; margin-bottom: 6px">失败行详情：</h4>
          <div v-for="(fr, i) in importResult.failed_rows.slice(0, 20)" :key="i" class="gt-import-error-item">
            <el-icon color="#f56c6c"><CircleClose /></el-icon>
            <span>第 {{ fr.row }} 行: {{ fr.error }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- 底部按钮 -->
    <template #footer>
      <div class="gt-import-footer">
        <el-button v-if="step === 1 || (step === 2 && !importing && !importResult?.success)" @click="step = 0">
          {{ step === 2 ? '重新上传' : '上一步' }}
        </el-button>
        <div style="flex: 1" />
        <el-button @click="onClose">{{ step === 2 && importResult?.success ? '关闭' : '取消' }}</el-button>
        <el-button
          v-if="step === 0"
          type="primary"
          :disabled="!selectedFile"
          :loading="validating"
          @click="doValidate"
        >
          上传校验
        </el-button>
        <el-button
          v-if="step === 1 && validationResult?.valid"
          type="primary"
          :loading="importing"
          @click="doImport"
        >
          确认导入
        </el-button>
        <el-button
          v-if="step === 2 && !importing && importResult?.failed_count && importResult?.success"
          type="warning"
          @click="step = 0"
        >
          修改后重新导入
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, UploadFilled, Loading, CircleClose, Warning } from '@element-plus/icons-vue'
import type { UploadInstance } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  modelValue: boolean
  importType: string
  projectId?: string
  year?: number
  subType?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'imported', result: any): void
}>()

const TYPE_LABELS: Record<string, string> = {
  adjustments: '调整分录',
  report: '报表数据',
  disclosure_note: '附注数据',
  workpaper: '底稿数据',
  formula: '公式',
  staff: '人员库',
  trial_balance: '试算表',
}

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const typeLabel = computed(() => TYPE_LABELS[props.importType] || props.importType)

const step = ref(0)
const uploadRef = ref<UploadInstance>()
const selectedFile = ref<File | null>(null)
const importMode = ref<'append' | 'overwrite'>('append')
const downloading = ref(false)
const validating = ref(false)
const importing = ref(false)
const validationResult = ref<any>(null)
const importResult = ref<any>(null)

const previewColumns = computed(() => {
  if (!validationResult.value?.preview_rows?.length) return []
  return Object.keys(validationResult.value.preview_rows[0])
})

watch(visible, (v) => {
  if (v) {
    step.value = 0
    selectedFile.value = null
    importMode.value = 'append'
    validationResult.value = null
    importResult.value = null
  }
})

function onClose() {
  visible.value = false
}

function onFileChange(file: any) {
  selectedFile.value = file?.raw || null
}

function onFileRemove() {
  selectedFile.value = null
}

async function downloadTemplate() {
  downloading.value = true
  try {
    const resp = await http.get(`/api/import-templates/${props.importType}/download`, {
      responseType: 'blob',
    })
    const blob = new Blob([resp.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${typeLabel.value}导入模板.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('模板下载失败')
  } finally {
    downloading.value = false
  }
}

async function doValidate() {
  if (!selectedFile.value) return
  validating.value = true
  step.value = 1
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const { data } = await http.post(
      `/api/import-templates/${props.importType}/validate`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    validationResult.value = data?.data ?? data
  } catch (err: any) {
    validationResult.value = {
      valid: false,
      errors: [{ message: err?.response?.data?.detail || err?.message || '校验失败' }],
      warnings: [],
      preview_rows: [],
      row_count: 0,
    }
  } finally {
    validating.value = false
  }
}

async function doImport() {
  if (!selectedFile.value) return
  importing.value = true
  step.value = 2
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const params = new URLSearchParams()
    if (props.projectId) params.set('project_id', props.projectId)
    if (props.year) params.set('year', String(props.year))
    if (props.subType) params.set('sub_type', props.subType)
    params.set('mode', importMode.value)

    const qs = params.toString()
    const url = `/api/import-templates/${props.importType}/import${qs ? '?' + qs : ''}`
    const { data } = await http.post(url, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importResult.value = data?.data ?? data
    if (importResult.value?.success) {
      ElMessage.success(importResult.value.message)
      emit('imported', importResult.value)
    }
  } catch (err: any) {
    importResult.value = {
      success: false,
      message: err?.response?.data?.detail || err?.message || '导入失败',
    }
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.gt-import-step { min-height: 200px; }
.gt-import-tip { margin-bottom: 16px; }
.gt-import-actions { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.gt-import-upload { width: 100%; }
.gt-import-upload :deep(.el-upload-dragger) { padding: 30px 20px; }
.gt-import-errors, .gt-import-warnings { margin-top: 8px; max-height: 150px; overflow-y: auto; }
.gt-import-error-item, .gt-import-warning-item {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px; font-size: 12px; line-height: 1.6;
}
.gt-import-error-item { color: #f56c6c; }
.gt-import-warning-item { color: #e6a23c; }
.gt-import-footer { display: flex; align-items: center; width: 100%; }
</style>
