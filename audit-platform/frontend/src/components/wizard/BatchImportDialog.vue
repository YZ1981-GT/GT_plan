<template>
  <el-dialog
    :model-value="modelValue"
    :title="mode === 'consolidation' ? '合并批量建项与企业树维护' : '批量建项'"
    width="min(920px, 96vw)"
    append-to-body
    class="batch-project-dialog"
    @update:model-value="onDialogVisibleChange"
    @open="handleOpen"
  >
    <div class="batch-project-body">
      <el-steps :active="activeStep" finish-status="success" simple class="batch-project-steps">
        <el-step title="取得模板" />
        <el-step title="上传校验" />
        <el-step title="确认执行" />
        <el-step title="查看结果" />
      </el-steps>

      <section class="batch-project-section">
        <h4>1. 取得模板</h4>
        <p>
          {{ mode === 'consolidation'
            ? '新建集团请下载空白模板；调整现有企业树请先选择集团并导出当前树。'
            : '下载建项模板填写新项目；示例位于独立 sheet，不会被导入。' }}
        </p>
        <div class="batch-project-actions">
          <el-button type="primary" plain :loading="downloading" @click="onDownloadTemplate">
            <el-icon><Download /></el-icon>下载建项模板
          </el-button>
          <template v-if="mode === 'consolidation'">
            <el-select v-model="selectedRootId" placeholder="选择要导出的合并项目" filterable clearable class="root-select">
              <el-option
                v-for="root in consolidationRoots"
                :key="root.id"
                :label="root.label"
                :value="root.id"
              />
            </el-select>
            <el-button :disabled="!selectedRootId" :loading="exporting" @click="onExportGroup">
              导出当前集团树
            </el-button>
          </template>
          <el-button
            v-else-if="selectedProjectIds.length"
            :loading="exporting"
            @click="onExportSelected"
          >导出所选项目</el-button>
        </div>
      </section>

      <section class="batch-project-section">
        <h4>2. 上传填写好的文件</h4>
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          accept=".xlsx"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          :disabled="validating || importing"
          drag
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">将 .xlsx 文件拖到此处，或<em>点击选择</em></div>
          <template #tip>
            <div class="el-upload__tip">最多 500 行、5MB。文件只上传一次，确认时直接执行已预览的计划。</div>
          </template>
        </el-upload>
        <el-button
          type="primary"
          :loading="validating"
          :disabled="!selectedFile || importing"
          class="validate-button"
          @click="doValidate"
        >预校验并生成计划</el-button>
      </section>

      <section v-if="validateResult" class="batch-project-section">
        <h4>3. 核对执行计划</h4>
        <el-alert
          :title="validateResult.valid
            ? `预校验通过：共 ${validateResult.total_rows} 行，请核对最终企业树`
            : `预校验未通过：发现 ${validateResult.errors.length} 项阻断问题`"
          :type="validateResult.valid ? 'success' : 'error'"
          :closable="false"
          show-icon
        />
        <div class="summary-grid" aria-label="批量建项计划汇总">
          <div class="summary-card summary-card--create"><strong>{{ validateResult.summary.create }}</strong><span>新建</span></div>
          <div class="summary-card summary-card--update"><strong>{{ validateResult.summary.update }}</strong><span>更新关系</span></div>
          <div class="summary-card"><strong>{{ validateResult.summary.unchanged }}</strong><span>无变化</span></div>
          <div class="summary-card"><strong>{{ validateResult.summary.skip }}</strong><span>跳过</span></div>
          <div class="summary-card summary-card--root"><strong>{{ validateResult.summary.auto_root }}</strong><span>自动合并根</span></div>
          <div class="summary-card summary-card--error"><strong>{{ validateResult.summary.error }}</strong><span>错误行</span></div>
        </div>

        <div v-if="validateResult.tree_preview.length" class="preview-block">
          <div class="preview-title">最终企业树预览</div>
          <div v-for="group in validateResult.tree_preview" :key="group.key || `${group.ultimateCode}@${group.year || ''}`" class="tree-group">
            <div class="tree-group__header">
              <strong>{{ group.ultimateName || '独立企业' }}</strong>
              <span v-if="group.ultimateCode">{{ group.ultimateCode }}</span>
              <el-tag v-if="group.year" size="small" effect="plain">{{ group.year }}年度</el-tag>
            </div>
            <el-tree-v2
              :data="group.children || []"
              :props="treeProps"
              :height="previewTreeHeight(group.children || [])"
              :item-size="32"
              :default-expanded-keys="expandedKeys(group.children || [])"
              :expand-on-click-node="false"
              class="preview-tree"
            >
              <template #default="{ data }">
                <span class="tree-node">
                  <span>{{ data.companyName || data.label || '—' }}</span>
                  <small>{{ data.companyCode || '—' }}</small>
                  <el-tag v-if="data.plannedAction === 'create'" type="success" size="small">新增</el-tag>
                  <el-tag v-else-if="data.plannedAction === 'update'" type="primary" size="small">更新</el-tag>
                  <el-tag v-else-if="data.plannedAction === 'auto_root'" type="warning" size="small">自动根</el-tag>
                  <el-tag v-if="data.relation" size="small" effect="plain">{{ data.relation === 'branch' ? '分公司' : '子公司' }}</el-tag>
                  <el-tag v-if="data.consolidatedProjectId" type="primary" size="small" effect="plain">合并</el-tag>
                  <el-tag v-if="data.standaloneProjectId" type="success" size="small" effect="plain">单户</el-tag>
                  <el-tag v-if="data.isDetached" type="warning" size="small">脱挂</el-tag>
                  <el-tag v-if="data.isCycleBreak" type="danger" size="small">循环引用</el-tag>
                </span>
              </template>
            </el-tree-v2>
          </div>
        </div>

        <div v-if="validateResult.warnings?.length" class="preview-block">
          <div class="preview-title preview-title--warning">提示</div>
          <el-table :data="validateResult.warnings" size="small" border max-height="180">
            <el-table-column prop="row_number" label="行号" width="80" align="center">
              <template #default="{ row }">{{ row.row_number || '批次' }}</template>
            </el-table-column>
            <el-table-column label="提示原因" min-width="360">
              <template #default="{ row }">{{ row.messages.join('；') }}</template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="validateResult.errors.length" class="preview-block">
          <div class="preview-title preview-title--error">阻断问题</div>
          <el-table :data="validateResult.errors" size="small" border max-height="240">
            <el-table-column prop="row_number" label="行号" width="80" align="center">
              <template #default="{ row }">{{ row.row_number || '批次' }}</template>
            </el-table-column>
            <el-table-column label="错误原因" min-width="360">
              <template #default="{ row }"><span class="error-text">{{ row.errors.join('；') }}</span></template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <section v-if="importResult" class="batch-project-section result-section">
        <h4>4. 执行结果</h4>
        <el-alert
          :title="resultTitle"
          :type="importResult.fail_count ? 'warning' : 'success'"
          :closable="false"
          show-icon
        />
        <p v-if="importResult.idempotent" class="idempotent-hint">已返回首次执行结果，没有重复创建项目。</p>
        <el-button
          v-if="importResult.root_project_ids.length"
          type="primary"
          plain
          @click="emit('open-root', importResult.root_project_ids[0])"
        >进入新建合并项目</el-button>
      </section>
    </div>

    <template #footer>
      <div class="batch-project-footer">
        <div>
          <el-button
            v-if="validateResult?.validation_id && validateResult.errors.length"
            :loading="downloadingErrors"
            @click="onDownloadErrors"
          >下载错误明细</el-button>
        </div>
        <div class="batch-project-footer__right">
          <span v-if="validateResult?.valid && !importResult" class="confirm-hint">确认后按当前预览执行，不会再次读取文件</span>
          <el-button @click="onDialogVisibleChange(false)">关闭</el-button>
          <el-button
            type="primary"
            :loading="importing"
            :disabled="!canApply"
            @click="doApply"
          >确认执行</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile, UploadInstance } from 'element-plus'
import {
  applyBatchProjectPlan,
  BATCH_PLAN_STATUS,
  batchErrorMessage,
  downloadBatchErrors,
  downloadBatchTemplate,
  downloadGroupImportTemplate,
  downloadSelectedProjectTemplate,
  getBatchProjectPlan,
  newBatchIdempotencyKey,
  validateBatchProjectFile,
  type BatchImportResult,
  type BatchProjectMode,
  type BatchValidateResponse,
  type PreviewTreeNode,
} from '@/services/batchProjectImport'

interface ConsolidationRootOption {
  id: string
  label: string
}

interface StoredBatchPlan {
  validationId: string
  idempotencyKey: string
  mode: BatchProjectMode
  expiresAt: string
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  mode?: BatchProjectMode
  consolidationRoots?: ConsolidationRootOption[]
  selectedProjectIds?: string[]
}>(), {
  mode: 'project',
  consolidationRoots: () => [],
  selectedProjectIds: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  success: [result: BatchImportResult]
  'open-root': [projectId: string]
}>()

const downloading = ref(false)
const exporting = ref(false)
const downloadingErrors = ref(false)
const validating = ref(false)
const importing = ref(false)
const selectedFile = ref<File | null>(null)
const selectedRootId = ref('')
const uploadRef = ref<UploadInstance>()
const validateResult = ref<BatchValidateResponse | null>(null)
const importResult = ref<BatchImportResult | null>(null)
const idempotencyKey = ref('')
let interactionEpoch = 0
const treeProps = { label: 'label', children: 'children', value: 'nodeKey' }

const mode = computed(() => props.mode)
const pendingPlanStorageKey = computed(() => `gt:batch-project-plan:${mode.value}`)
const canApply = computed(() => Boolean(
  validateResult.value?.valid
  && validateResult.value.validation_id
  && !importResult.value,
))
const activeStep = computed(() => {
  if (importResult.value) return 4
  if (validateResult.value?.valid) return 2
  if (selectedFile.value) return 1
  return 0
})
const resultTitle = computed(() => {
  const result = importResult.value
  if (!result) return ''
  const parts = [
    result.created_count ? `新建 ${result.created_count} 个` : '',
    result.updated_count ? `更新关系 ${result.updated_count} 个` : '',
    result.auto_root_count ? `自动创建合并根 ${result.auto_root_count} 个` : '',
    result.unchanged_count ? `${result.unchanged_count} 个无变化` : '',
    result.skipped_count ? `跳过 ${result.skipped_count} 个` : '',
  ].filter(Boolean)
  return parts.length ? `执行完成：${parts.join('，')}` : '执行完成，没有需要变更的项目'
})

function clearPendingPlan() {
  sessionStorage.removeItem(pendingPlanStorageKey.value)
}

function savePendingPlan(result: BatchValidateResponse) {
  if (!result.validation_id || !result.expires_at || !result.valid) {
    clearPendingPlan()
    return
  }
  const stored: StoredBatchPlan = {
    validationId: result.validation_id,
    idempotencyKey: idempotencyKey.value,
    mode: mode.value,
    expiresAt: result.expires_at,
  }
  sessionStorage.setItem(pendingPlanStorageKey.value, JSON.stringify(stored))
}

function readPendingPlan(): StoredBatchPlan | null {
  const raw = sessionStorage.getItem(pendingPlanStorageKey.value)
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as StoredBatchPlan
    const expiresAt = Date.parse(value.expiresAt)
    if (
      value.mode !== mode.value
      || !value.validationId
      || !value.idempotencyKey
      || !Number.isFinite(expiresAt)
      || expiresAt <= Date.now()
    ) {
      clearPendingPlan()
      return null
    }
    return value
  } catch {
    clearPendingPlan()
    return null
  }
}

function isCurrentPendingRestore(epoch: number, stored: StoredBatchPlan): boolean {
  if (epoch !== interactionEpoch || selectedFile.value || validateResult.value || importResult.value) return false
  const current = readPendingPlan()
  return current?.validationId === stored.validationId
    && current.idempotencyKey === stored.idempotencyKey
    && current.mode === stored.mode
}

async function restorePendingPlan(epoch: number) {
  const stored = readPendingPlan()
  if (!stored) return
  try {
    const status = await getBatchProjectPlan(stored.validationId)
    if (!isCurrentPendingRestore(epoch, stored)) return
    if (status.mode !== mode.value) {
      clearPendingPlan()
      return
    }
    idempotencyKey.value = stored.idempotencyKey
    if (status.status === BATCH_PLAN_STATUS.applied && status.receipt) {
      acceptResult({ ...status.receipt, idempotent: true }, epoch)
      return
    }
    if (status.status === BATCH_PLAN_STATUS.applying) {
      importing.value = true
      try {
        await recoverResult(stored.validationId, epoch)
      } finally {
        if (epoch === interactionEpoch) importing.value = false
      }
      return
    }
    if (status.status === BATCH_PLAN_STATUS.validated && status.valid) {
      validateResult.value = {
        valid: true,
        total_rows: status.total_rows,
        tree_preview: status.tree_preview,
        errors: status.errors,
        warnings: status.warnings,
        summary: status.summary,
        validation_id: status.validation_id,
        file_sha256: null,
        template_version: status.template_version,
        expires_at: status.expires_at,
      }
      ElMessage.info('已恢复上次未执行的批量建项计划')
      return
    }
    clearPendingPlan()
  } catch (error: any) {
    if (!isCurrentPendingRestore(epoch, stored)) return
    if ([401, 403, 404].includes(Number(error?.response?.status))) clearPendingPlan()
    // 网络暂不可用时保留计划身份，下次打开仍可恢复。
  }
}

function onDialogVisibleChange(value: boolean) {
  if (!value) interactionEpoch += 1
  emit('update:modelValue', value)
}

function handleOpen() {
  const epoch = ++interactionEpoch
  selectedFile.value = null
  validateResult.value = null
  importResult.value = null
  validating.value = false
  importing.value = false
  idempotencyKey.value = ''
  selectedRootId.value = ''
  uploadRef.value?.clearFiles()
  void restorePendingPlan(epoch)
}

function handleFileChange(file: UploadFile) {
  if (!file.raw || validating.value || importing.value) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    ElMessage.error('仅支持 .xlsx 格式文件')
    uploadRef.value?.clearFiles()
    return
  }
  interactionEpoch += 1
  selectedFile.value = file.raw
  clearPendingPlan()
  validateResult.value = null
  importResult.value = null
  idempotencyKey.value = newBatchIdempotencyKey()
}

function handleExceed() {
  ElMessage.warning('仅支持上传一个文件，请先移除已选文件')
}

function previewTreeHeight(nodes: PreviewTreeNode[]): number {
  let count = 0
  const stack = [...nodes]
  while (stack.length) {
    const node = stack.pop()!
    count += 1
    stack.push(...(node.children || []))
  }
  return Math.min(260, Math.max(64, count * 32 + 8))
}

function expandedKeys(nodes: PreviewTreeNode[]): string[] {
  if (!validateResult.value?.summary.update) {
    return nodes.map((node) => node.nodeKey || node.id).filter(Boolean)
  }
  const keys: string[] = []
  function visit(node: PreviewTreeNode): boolean {
    const childChanged = (node.children || []).map(visit).some(Boolean)
    const changed = node.plannedAction === 'update' || childChanged
    if (changed && node.children?.length) keys.push(node.nodeKey || node.id)
    return changed
  }
  nodes.forEach(visit)
  return keys
}

async function onDownloadTemplate() {
  downloading.value = true
  try {
    await downloadBatchTemplate(mode.value)
  } catch (error) {
    ElMessage.error(batchErrorMessage(error, '模板下载失败，请稍后重试'))
  } finally {
    downloading.value = false
  }
}

async function onExportGroup() {
  if (!selectedRootId.value) return
  exporting.value = true
  try {
    await downloadGroupImportTemplate(selectedRootId.value)
  } catch (error) {
    ElMessage.error(batchErrorMessage(error, '当前集团树导出失败'))
  } finally {
    exporting.value = false
  }
}

async function onExportSelected() {
  if (!props.selectedProjectIds.length) return
  exporting.value = true
  try {
    await downloadSelectedProjectTemplate(props.selectedProjectIds)
  } catch (error) {
    ElMessage.error(batchErrorMessage(error, '所选项目导出失败'))
  } finally {
    exporting.value = false
  }
}

async function doValidate() {
  const file = selectedFile.value
  if (!file || validating.value || importing.value) return
  const expectedEpoch = interactionEpoch
  validating.value = true
  validateResult.value = null
  importResult.value = null
  if (!idempotencyKey.value) idempotencyKey.value = newBatchIdempotencyKey()
  const key = idempotencyKey.value
  try {
    const result = await validateBatchProjectFile(file, mode.value, key)
    if (expectedEpoch !== interactionEpoch || selectedFile.value !== file) return
    validateResult.value = result
    savePendingPlan(result)
    if (result.valid) {
      ElMessage.success('预校验通过，请核对最终企业树后确认执行')
    } else {
      ElMessage.warning('预校验存在阻断问题，请下载错误明细并修正')
    }
  } catch (error) {
    if (expectedEpoch === interactionEpoch && selectedFile.value === file) {
      ElMessage.error(batchErrorMessage(error, '预校验失败，请稍后重试'))
    }
  } finally {
    if (expectedEpoch === interactionEpoch) validating.value = false
  }
}

function acceptResult(result: BatchImportResult, expectedEpoch = interactionEpoch): boolean {
  if (expectedEpoch !== interactionEpoch) return false
  importResult.value = result
  clearPendingPlan()
  ElMessage.success(result.idempotent ? '已恢复首次执行结果，没有重复建项' : '批量建项执行完成')
  emit('success', result)
  return true
}

function isAmbiguousApplyOutcome(error: any): boolean {
  const status = Number(error?.response?.status)
  return !Number.isFinite(status) || status >= 500 || status === 408 || status === 504
}

function recoveryErrorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : batchErrorMessage(error, '批量建项结果查询失败')
}

async function recoverResult(validationId: string, expectedEpoch = interactionEpoch): Promise<boolean> {
  const delays = [0, 400, 800, 1200]
  for (const delay of delays) {
    if (expectedEpoch !== interactionEpoch) return false
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay))
    if (expectedEpoch !== interactionEpoch) return false
    const status = await getBatchProjectPlan(validationId)
    if (expectedEpoch !== interactionEpoch) return false
    if (status.status === BATCH_PLAN_STATUS.applied && status.receipt) {
      return acceptResult({ ...status.receipt, idempotent: true }, expectedEpoch)
    }
    if (status.status === BATCH_PLAN_STATUS.failed) {
      throw new Error(status.public_error || '批量建项执行失败')
    }
    // apply 与业务写同一事务时，GET 可能短暂读到旧的 validated；它和 applying 都不能
    // 证明“没有写入”，继续有限轮询直到得到终态或明确未知。
    if (
      status.status !== BATCH_PLAN_STATUS.applying
      && status.status !== BATCH_PLAN_STATUS.validated
    ) return false
  }
  throw new Error('批量建项状态尚未确认，请稍后重新打开本窗口查看结果；系统会按同一计划幂等处理，不会重复建项')
}

async function doApply() {
  const validationId = validateResult.value?.validation_id
  if (!validationId || !canApply.value) return
  const expectedEpoch = interactionEpoch
  importing.value = true
  try {
    acceptResult(await applyBatchProjectPlan(validationId, idempotencyKey.value), expectedEpoch)
  } catch (error: any) {
    if (expectedEpoch !== interactionEpoch) return
    if (!isAmbiguousApplyOutcome(error)) {
      ElMessage.error(batchErrorMessage(error, '批量建项失败，请重新预校验后重试'))
      return
    }
    try {
      if (await recoverResult(validationId, expectedEpoch)) return
    } catch (recoverError) {
      if (expectedEpoch === interactionEpoch) ElMessage.error(recoveryErrorMessage(recoverError))
      return
    }
    if (expectedEpoch === interactionEpoch) {
      ElMessage.error('批量建项状态尚未确认，请稍后重新打开本窗口查看结果')
    }
  } finally {
    if (expectedEpoch === interactionEpoch) importing.value = false
  }
}

async function onDownloadErrors() {
  const validationId = validateResult.value?.validation_id
  if (!validationId) return
  downloadingErrors.value = true
  try {
    await downloadBatchErrors(validationId)
  } catch (error) {
    ElMessage.error(batchErrorMessage(error, '错误明细下载失败'))
  } finally {
    downloadingErrors.value = false
  }
}
</script>

<style scoped>
:global(.batch-project-dialog) {
  display: flex;
  flex-direction: column;
  max-height: 80vh;
  margin-top: 8vh;
  overflow: hidden;
}

:global(.batch-project-dialog .el-dialog__header),
:global(.batch-project-dialog .el-dialog__footer) {
  flex: 0 0 auto;
}

:global(.batch-project-dialog .el-dialog__body) {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-top: 8px;
}

.batch-project-body { padding: 0 2px; }
.batch-project-steps { margin-bottom: 18px; }
.batch-project-section { margin-bottom: 22px; }
.batch-project-section h4 { margin: 0 0 8px; color: var(--gt-color-primary); font-size: 14px; }
.batch-project-section p { margin: 0 0 12px; color: var(--gt-color-text-secondary); line-height: 1.6; font-size: 12px; }
.batch-project-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.root-select { width: min(320px, 100%); }
.validate-button { margin-top: 12px; }
.summary-grid { display: grid; grid-template-columns: repeat(6, minmax(88px, 1fr)); gap: 8px; margin: 12px 0; }
.summary-card { display: flex; flex-direction: column; align-items: center; padding: 10px 6px; border: 1px solid var(--gt-color-border); border-radius: 8px; background: var(--gt-color-fill-lighter); }
.summary-card strong { font-size: 20px; color: var(--gt-color-text-primary); }
.summary-card span { margin-top: 3px; color: var(--gt-color-text-secondary); font-size: 11px; }
.summary-card--create strong { color: var(--el-color-success); }
.summary-card--update strong { color: var(--el-color-primary); }
.summary-card--root strong { color: var(--el-color-warning); }
.summary-card--error strong { color: var(--el-color-danger); }
.preview-block { margin-top: 12px; }
.preview-title { margin-bottom: 7px; color: var(--gt-color-text-secondary); font-size: 12px; font-weight: 600; }
.preview-title--warning { color: var(--el-color-warning); }
.preview-title--error, .error-text { color: var(--el-color-danger); }
.tree-group { margin-bottom: 10px; padding: 10px; border: 1px solid var(--gt-color-border); border-radius: 8px; }
.tree-group__header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 6px; }
.tree-group__header span { color: var(--gt-color-text-secondary); font-family: monospace; font-size: 11px; }
.preview-tree { max-height: 260px; overflow: auto; }
.tree-node { display: inline-flex; min-width: 0; align-items: center; gap: 6px; }
.tree-node small { color: var(--gt-color-text-tertiary); font-family: monospace; }
.result-section { margin-bottom: 0; }
.idempotent-hint { margin-top: 8px !important; color: var(--el-color-success) !important; }
.batch-project-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.batch-project-footer__right { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.confirm-hint { color: var(--gt-color-text-tertiary); font-size: 11px; }

@media (max-width: 680px) {
  :global(.batch-project-dialog) { width: 96vw !important; max-height: 88vh; margin-top: 4vh; }
  .batch-project-steps { display: none; }
  .summary-grid { grid-template-columns: repeat(3, 1fr); }
  .batch-project-footer { align-items: stretch; flex-direction: column; }
  .batch-project-footer__right { flex-wrap: wrap; }
  .confirm-hint { flex-basis: 100%; text-align: right; }
  .root-select { width: 100%; }
}
</style>
