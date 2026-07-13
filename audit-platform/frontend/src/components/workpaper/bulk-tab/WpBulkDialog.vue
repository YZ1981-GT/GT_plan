<template>
  <el-dialog
    v-model="visible"
    title="批量 Tab 导入导出（结构化数据包）"
    width="640px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 步骤一：选择操作 -->
    <div v-if="step === 'action'" class="bulk-action-step">
      <p class="bulk-desc">
        本功能将项目中已实例化的底稿 Tab 数据以 ZIP 结构化包形式导入/导出，
        与"批量导出底稿文件"（整份文件）互不替代。
      </p>
      <div class="bulk-action-buttons">
        <el-button
          type="primary"
          size="large"
          @click="selectAction('export-templates')"
        >
          导出全部模板
        </el-button>
        <el-button
          type="success"
          size="large"
          @click="selectAction('import-data')"
        >
          导入全部数据
        </el-button>
        <el-button
          type="warning"
          size="large"
          @click="selectAction('export-data')"
        >
          导出全部数据
        </el-button>
      </div>
    </div>

    <!-- 步骤二：配置选项 -->
    <div v-else-if="step === 'options'" class="bulk-options-step">
      <el-form label-position="top">
        <!-- 循环多选 -->
        <el-form-item label="选择审计循环" required>
          <el-checkbox-group v-model="selectedCycles">
            <el-checkbox
              v-for="cycle in availableCycles"
              :key="cycle.code"
              :label="cycle.code"
              :value="cycle.code"
            >
              {{ cycle.code }} - {{ cycle.name }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <!-- 冲突策略（仅导入时显示） -->
        <el-form-item
          v-if="currentAction === 'import-data'"
          label="冲突策略（库中已有数据时）"
        >
          <el-radio-group v-model="conflictStrategy">
            <el-radio value="overwrite">覆盖（以 ZIP 为准）</el-radio>
            <el-radio value="fill-empty">仅填空（不覆盖已有内容）</el-radio>
            <el-radio value="reject">拒绝（存在数据则跳过该表）</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- DryRun 开关（仅导入时显示） -->
        <el-form-item
          v-if="currentAction === 'import-data'"
          label="预检模式（DryRun）"
        >
          <el-switch
            v-model="dryRun"
            active-text="开启（仅校验不写库）"
            inactive-text="关闭（正式导入）"
          />
        </el-form-item>

        <!-- 仅导出有数据的 Tab（仅导出数据时显示） -->
        <el-form-item
          v-if="currentAction === 'export-data'"
          label="导出范围"
        >
          <el-checkbox v-model="onlyWithData">
            仅导出有数据的 Tab（跳过空表）
          </el-checkbox>
        </el-form-item>

        <!-- 文件上传（仅导入时显示） -->
        <el-form-item
          v-if="currentAction === 'import-data'"
          label="选择 ZIP 文件"
        >
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".zip"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
          >
            <template #trigger>
              <el-button type="primary" plain>选择文件</el-button>
            </template>
            <template #tip>
              <div class="el-upload__tip">
                仅支持 .zip 格式，需包含 manifest.json
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
    </div>

    <!-- 步骤三：执行中 / 报告 -->
    <div v-else-if="step === 'executing'" class="bulk-executing-step">
      <div v-if="loading" class="bulk-loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在{{ actionLabel }}，请稍候...</p>
        <WpBulkProgressBar
          :project-id="projectId"
          :label="actionLabel"
          :task-id="progressTaskId"
          style="width: 100%; margin-top: 8px;"
        />
      </div>
      <div v-else-if="report" class="bulk-report">
        <WpBulkImportReport
          :report="report"
          :dry-run="dryRun"
        />
      </div>
    </div>

    <template #footer>
      <!-- 步骤一无 footer -->
      <template v-if="step === 'options'">
        <el-button @click="step = 'action'">返回</el-button>
        <el-button
          type="primary"
          :disabled="!canExecute"
          :loading="loading"
          @click="handleExecute"
        >
          {{ executeButtonLabel }}
        </el-button>
      </template>
      <template v-else-if="step === 'executing' && !loading">
        <el-button @click="handleClose">关闭</el-button>
        <el-button
          v-if="dryRun && currentAction === 'import-data' && report"
          type="primary"
          @click="handleConfirmImport"
        >
          确认正式导入
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/**
 * WpBulkDialog — 项目级底稿批量 Tab 导入导出弹窗
 *
 * 三按钮（导出全部模板 / 导入全部数据 / 导出全部数据）+ 循环多选 +
 * 冲突策略 radio + only_with_data 勾选 + DryRun 开关。
 * 与 WpBatchExportDialog（整份文件批量导出）并列，互不替代。
 *
 * Requirements: 5.1
 */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import {
  useBulkTabImportExport,
  type ImportReport,
  type ConflictStrategy,
} from '@/composables/useBulkTabImportExport'
import WpBulkImportReport from './WpBulkImportReport.vue'
import WpBulkProgressBar from './WpBulkProgressBar.vue'

export type BulkAction = 'export-templates' | 'import-data' | 'export-data'
export type { ConflictStrategy }
type Step = 'action' | 'options' | 'executing'

const props = defineProps<{
  modelValue: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'imported'): void
  (e: 'exported'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const projectIdRef = computed(() => props.projectId)
const {
  exportTemplates,
  exportData,
  importData,
  loading,
} = useBulkTabImportExport(projectIdRef)

// ─── 步骤状态 ───
const step = ref<Step>('action')
const currentAction = ref<BulkAction>('export-templates')

// ─── 配置选项 ───
const availableCycles = [
  { code: 'D', name: '销售收入' },
  { code: 'K', name: '管理' },
  { code: 'F', name: '采购存货' },
  { code: 'G', name: '投资' },
  { code: 'H', name: '固定资产' },
]

const selectedCycles = ref<string[]>(['D'])
const conflictStrategy = ref<ConflictStrategy>('overwrite')
const dryRun = ref(true)
const onlyWithData = ref(false)
const uploadFile = ref<File | null>(null)
const report = ref<ImportReport | null>(null)
/** 异步任务 ID（同步端点无此值时进度条走不确定态） */
const progressTaskId = ref<string | null>(null)

// ─── 计算属性 ───
const actionLabel = computed(() => {
  switch (currentAction.value) {
    case 'export-templates': return '导出全部模板'
    case 'import-data': return '导入全部数据'
    case 'export-data': return '导出全部数据'
  }
})

const executeButtonLabel = computed(() => {
  if (currentAction.value === 'import-data') {
    return dryRun.value ? '开始预检' : '开始导入'
  }
  return `开始${actionLabel.value}`
})

const canExecute = computed(() => {
  if (selectedCycles.value.length === 0) return false
  if (currentAction.value === 'import-data' && !uploadFile.value) return false
  return true
})

// ─── 方法 ───
function selectAction(action: BulkAction) {
  currentAction.value = action
  step.value = 'options'
  report.value = null
  // 导入默认开启 DryRun
  if (action === 'import-data') {
    dryRun.value = true
  }
}

function handleFileChange(file: UploadFile) {
  uploadFile.value = file.raw || null
}

function handleFileRemove() {
  uploadFile.value = null
}

async function handleExecute() {
  if (!canExecute.value) return
  step.value = 'executing'
  report.value = null

  try {
    switch (currentAction.value) {
      case 'export-templates': {
        await exportTemplates(selectedCycles.value)
        emit('exported')
        break
      }
      case 'export-data': {
        await exportData(selectedCycles.value, onlyWithData.value)
        emit('exported')
        break
      }
      case 'import-data': {
        if (!uploadFile.value) return
        const result = await importData(uploadFile.value, {
          dryRun: dryRun.value,
          strategy: conflictStrategy.value,
          cycles: selectedCycles.value,
        })
        // 组合式函数内部已弹 ElMessage；失败返回 null
        if (result === null) {
          step.value = 'options'
          return
        }
        report.value = result
        if (!dryRun.value) {
          emit('imported')
        }
        break
      }
    }
  } catch (err: unknown) {
    // 组合式函数已弹出错误提示，此处仅回退步骤
    step.value = 'options'
    void err
  }
}

async function handleConfirmImport() {
  // DryRun 预检通过后，用户确认正式导入
  dryRun.value = false
  await handleExecute()
}

function handleClose() {
  visible.value = false
  // 重置状态
  step.value = 'action'
  currentAction.value = 'export-templates'
  report.value = null
  uploadFile.value = null
  progressTaskId.value = null
}
</script>

<style scoped>
.bulk-desc {
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
  line-height: 1.6;
}

.bulk-action-buttons {
  display: flex;
  gap: 12px;
  justify-content: center;
  padding: 24px 0;
}

.bulk-action-buttons .el-button {
  min-width: 140px;
  height: 48px;
  font-size: 15px;
}

.bulk-options-step {
  min-height: 200px;
}

.bulk-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  gap: 12px;
  color: var(--el-text-color-secondary);
}

.bulk-report {
  max-height: 400px;
  overflow-y: auto;
}
</style>
