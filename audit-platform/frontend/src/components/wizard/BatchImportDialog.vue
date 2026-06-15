<template>
  <el-dialog
    :model-value="modelValue"
    title="批量建项"
    width="720px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <div class="batch-import-content">
      <!-- 步骤 1：下载模板 -->
      <div class="batch-import-section">
        <h4 class="batch-import-section__title">1. 下载建项模板</h4>
        <p class="batch-import-section__desc">
          请先下载标准建项模板，按照模板中「说明事项」sheet 的要求填写数据（含上级企业代码、最终控制方代码）后上传。
        </p>
        <el-button type="primary" plain @click="downloadTemplate" :loading="downloading">
          <el-icon><Download /></el-icon>
          下载模板
        </el-button>
      </div>

      <!-- 步骤 2：上传文件 -->
      <div class="batch-import-section">
        <h4 class="batch-import-section__title">2. 上传填写好的文件</h4>
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          accept=".xlsx"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          drag
          class="batch-import-upload"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">将 .xlsx 文件拖到此处，或<em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">仅支持 .xlsx 格式，最多 500 行数据。上传后将先预校验、确认无误再正式导入。</div>
          </template>
        </el-upload>
        <el-button
          type="primary"
          :loading="validating"
          :disabled="!selectedFile"
          style="margin-top: 12px"
          @click="doValidate"
        >
          预校验
        </el-button>
      </div>

      <!-- 步骤 2.5：预校验结果 -->
      <div v-if="validateResult" class="batch-import-section">
        <h4 class="batch-import-section__title">3. 预校验结果</h4>

        <el-alert
          v-if="validateResult.valid"
          :title="`预校验通过：共 ${validateResult.total_rows} 行数据，可确认导入`"
          type="success"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <el-alert
          v-else
          :title="`预校验未通过：共 ${validateResult.total_rows} 行数据，发现 ${validateResult.errors.length} 行错误，请修正后重新上传校验`"
          type="error"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />

        <!-- 树形预览 -->
        <div v-if="validateResult.tree_preview.length > 0" class="batch-import-preview">
          <div class="batch-import-preview__label">集团架构预览</div>
          <div
            v-for="(group, gi) in validateResult.tree_preview"
            :key="gi"
            class="batch-import-tree-group"
          >
            <div class="batch-import-tree-group__header">
              <span class="batch-import-tree-group__name">{{ group.ultimateName || '未命名集团' }}</span>
              <span v-if="group.ultimateCode" class="batch-import-tree-group__code">{{ group.ultimateCode }}</span>
            </div>
            <el-tree
              :data="group.children || []"
              :props="treeProps"
              node-key="id"
              default-expand-all
              class="batch-import-tree"
            >
              <template #default="{ data }">
                <span class="batch-import-node">
                  <span class="batch-import-node__name">{{ data.companyName || data.label || '—' }}</span>
                  <span class="batch-import-node__code">{{ data.companyCode || '—' }}</span>
                  <el-tag v-if="data.isDetached" type="warning" size="small" effect="plain" round>脱挂</el-tag>
                  <el-tag v-if="data.isCycleBreak" type="danger" size="small" effect="plain" round>循环引用</el-tag>
                  <el-tag v-if="data.hasNoCompanyCode" type="info" size="small" effect="plain" round>缺代码</el-tag>
                </span>
              </template>
            </el-tree>
          </div>
        </div>

        <!-- 错误明细表 -->
        <div v-if="validateResult.errors.length > 0" class="batch-import-preview">
          <div class="batch-import-preview__label batch-import-preview__label--error">错误明细</div>
          <el-table
            :data="validateResult.errors"
            size="small"
            border
            max-height="240"
            row-class-name="batch-import-error-row"
            style="width: 100%"
          >
            <el-table-column prop="row_number" label="行号" width="80" align="center" />
            <el-table-column label="错误原因" min-width="320">
              <template #default="{ row }">
                <span class="batch-import-error-text">{{ row.errors.join('；') }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <el-button
          type="primary"
          :loading="importing"
          :disabled="!canImport"
          style="margin-top: 12px"
          @click="doImport"
        >
          确认导入
        </el-button>
        <span v-if="!canImport" class="batch-import-hint">请先修正错误并重新上传校验后再导入</span>
      </div>

      <!-- 步骤 3：导入结果 -->
      <div v-if="importResult" class="batch-import-section">
        <h4 class="batch-import-section__title">4. 导入结果</h4>
        <el-alert
          v-if="importResult.success_count > 0"
          :title="`成功创建 ${importResult.success_count} 个项目`"
          type="success"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <el-alert
          v-if="importResult.fail_count > 0"
          :title="`${importResult.fail_count} 行导入失败`"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        />
        <!-- 失败明细表 -->
        <el-table
          v-if="importResult.failures && importResult.failures.length > 0"
          :data="importResult.failures"
          size="small"
          border
          max-height="240"
          style="width: 100%"
        >
          <el-table-column prop="row_number" label="行号" width="80" align="center" />
          <el-table-column label="错误原因" min-width="300">
            <template #default="{ row }">
              <span class="batch-import-error-text">{{ row.errors.join('；') }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { downloadFile } from '@/utils/http'
import type { UploadFile, UploadInstance } from 'element-plus'

interface BatchImportFailure {
  row_number: number
  errors: string[]
}

interface BatchImportResult {
  success_count: number
  fail_count: number
  failures: BatchImportFailure[]
}

/** 预校验树形预览节点（与后端 consol_tree_service.to_dict_v2 camelCase 对齐） */
interface PreviewTreeNode {
  id: string
  label: string
  companyCode: string | null
  companyName: string | null
  isDetached?: boolean
  isCycleBreak?: boolean
  hasNoCompanyCode?: boolean
  children?: PreviewTreeNode[]
}

/** 预校验树形分组（一棵集团树） */
interface PreviewGroupTree {
  ultimateCode: string | null
  ultimateName: string | null
  rootProjectId: string | null
  children: PreviewTreeNode[]
}

interface BatchValidateResponse {
  valid: boolean
  total_rows: number
  tree_preview: PreviewGroupTree[]
  errors: BatchImportFailure[]
}

defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  success: []
}>()

const downloading = ref(false)
const validating = ref(false)
const importing = ref(false)
const selectedFile = ref<File | null>(null)
const uploadRef = ref<UploadInstance>()
const validateResult = ref<BatchValidateResponse | null>(null)
const importResult = ref<BatchImportResult | null>(null)

const treeProps = { label: 'label', children: 'children' }

/** 仅当预校验已执行且通过（无错误）时才可确认导入 */
const canImport = computed(() => validateResult.value?.valid === true)

function handleOpen() {
  // 重置全部状态
  selectedFile.value = null
  validateResult.value = null
  importResult.value = null
  uploadRef.value?.clearFiles()
}

async function downloadTemplate() {
  downloading.value = true
  try {
    await downloadFile('/api/projects/batch-template', { fileName: '建项模板.xlsx' })
  } catch {
    ElMessage.error('模板下载失败，请稍后重试')
  } finally {
    downloading.value = false
  }
}

function handleFileChange(file: UploadFile) {
  if (file.raw) {
    selectedFile.value = file.raw
    // 重新选择文件后清除旧的校验/导入结果，避免误导入
    validateResult.value = null
    importResult.value = null
  }
}

function handleExceed() {
  ElMessage.warning('仅支持上传一个文件，请先移除已选文件')
}

async function doValidate() {
  if (!selectedFile.value) return
  validating.value = true
  validateResult.value = null
  importResult.value = null
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const { data } = await http.post('/api/projects/batch-validate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    validateResult.value = data as BatchValidateResponse
    if (validateResult.value?.valid) {
      ElMessage.success('预校验通过，可确认导入')
    } else {
      ElMessage.warning('预校验发现错误，请修正后重新上传')
    }
  } catch {
    ElMessage.error('预校验失败，请检查文件格式')
  } finally {
    validating.value = false
  }
}

async function doImport() {
  if (!selectedFile.value || !canImport.value) return
  importing.value = true
  importResult.value = null
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const { data } = await http.post('/api/projects/batch-import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importResult.value = data as BatchImportResult
    if (importResult.value && importResult.value.success_count > 0) {
      ElMessage.success(`成功导入 ${importResult.value.success_count} 个项目`)
      emit('success')
    }
    // 导入完成后清除文件与校验结果，允许用户修正后重新上传
    selectedFile.value = null
    validateResult.value = null
    uploadRef.value?.clearFiles()
  } catch {
    ElMessage.error('批量导入失败，请检查文件格式')
  } finally {
    importing.value = false
  }
}
</script>

<style scoped>
.batch-import-content {
  padding: 0 4px;
}

.batch-import-section {
  margin-bottom: 24px;
}

.batch-import-section__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary);
  margin: 0 0 8px;
}

.batch-import-section__desc {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary);
  line-height: 1.6;
  margin: 0 0 12px;
}

.batch-import-upload {
  width: 100%;
}

.batch-import-upload :deep(.el-upload-dragger) {
  border-color: var(--gt-color-border);
  border-radius: var(--gt-radius-md, 8px);
}

.batch-import-upload :deep(.el-upload-dragger:hover) {
  border-color: var(--gt-color-primary);
}

.batch-import-upload :deep(.el-icon--upload) {
  color: var(--gt-color-primary);
}

/* ── 预校验预览 ── */
.batch-import-preview {
  margin-bottom: 12px;
}

.batch-import-preview__label {
  font-size: var(--gt-font-size-xs, 12px);
  font-weight: 600;
  color: var(--gt-color-text-secondary);
  margin: 0 0 6px;
}

.batch-import-preview__label--error {
  color: var(--gt-color-coral, #ff5149);
}

.batch-import-tree-group {
  border: 1px solid var(--gt-color-border-purple-light, #e7dcf5);
  border-radius: var(--gt-radius-md, 8px);
  padding: 8px 12px;
  margin-bottom: 8px;
  background-color: var(--gt-color-primary-bg, #f4f0fa);
}

.batch-import-tree-group__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.batch-import-tree-group__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-primary);
}

.batch-import-tree-group__code {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary);
  font-family: var(--gt-font-mono, monospace);
}

.batch-import-tree {
  background-color: transparent;
}

.batch-import-node {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.batch-import-node__name {
  font-size: 13px;
  color: var(--gt-color-text-primary);
}

.batch-import-node__code {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary);
  font-family: var(--gt-font-mono, monospace);
}

.batch-import-error-text {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-coral, #ff5149);
}

.batch-import-hint {
  margin-left: 12px;
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary);
}

/* 错误行红色标注 */
.batch-import-content :deep(.batch-import-error-row) {
  background-color: var(--gt-color-coral-bg, #fff1f0);
}

/* el-tag primary 紫色覆盖（禁用 Element 默认蓝 #409eff） */
:deep(.el-tag--primary) {
  --el-tag-text-color: var(--gt-color-primary);
  --el-tag-bg-color: var(--gt-color-primary-bg);
  --el-tag-border-color: var(--gt-color-border-purple);
  color: var(--gt-color-primary);
  background-color: var(--gt-color-primary-bg);
}

/* el-tree hover 用紫色而非默认蓝 */
.batch-import-tree :deep(.el-tree-node__content:hover) {
  background-color: var(--gt-color-primary-bg);
}

.batch-import-tree :deep(.el-tree-node__content) {
  background-color: transparent;
}
</style>
