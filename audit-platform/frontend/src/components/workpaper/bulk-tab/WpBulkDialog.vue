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
          <el-checkbox
            :model-value="selectedCycles.length === availableCycles.length"
            :indeterminate="selectedCycles.length > 0 && selectedCycles.length < availableCycles.length"
            @change="toggleSelectAll"
            style="margin-bottom: 8px;"
          >
            全选/取消全选
          </el-checkbox>
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

        <!-- 增量导出（仅导出数据时显示） -->
        <el-form-item v-if="currentAction === 'export-data'" label="增量导出">
          <el-checkbox v-model="incrementalExport">
            仅导出自上次导出后有变更的 Tab（跳过未修改的底稿）
          </el-checkbox>
        </el-form-item>

        <!-- 密码保护（导出时显示） -->
        <el-form-item v-if="currentAction !== 'import-data'" label="密码保护（可选）">
          <el-input
            v-model="exportPassword"
            type="password"
            placeholder="留空则不加密"
            show-password
            clearable
            style="max-width: 300px;"
          />
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
        <el-progress
          v-if="downloadProgress > 0"
          :percentage="downloadProgress"
          :stroke-width="10"
          style="width: 80%; margin-top: 12px;"
        />
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
import http from '@/utils/http'
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
  downloadProgress,
} = useBulkTabImportExport(projectIdRef)

// ─── 步骤状态 ───
const step = ref<Step>('action')
const currentAction = ref<BulkAction>('export-templates')

// ─── 配置选项 ───
const availableCycles = [
  { code: 'D', name: 'D 销售循环' },
  { code: 'E', name: 'E 货币资金' },
  { code: 'F', name: 'F 采购存货' },
  { code: 'G', name: 'G 投资循环' },
  { code: 'H', name: 'H 固定资产' },
  { code: 'I', name: 'I 无形资产' },
  { code: 'J', name: 'J 职工薪酬' },
  { code: 'K', name: 'K 其他循环' },
  { code: 'L', name: 'L 债务循环' },
  { code: 'M', name: 'M 权益循环' },
  { code: 'N', name: 'N 税项循环' },
]

const selectedCycles = ref<string[]>(availableCycles.map(c => c.code))
const conflictStrategy = ref<ConflictStrategy>('overwrite')
const dryRun = ref(true)
const onlyWithData = ref(true)
const incrementalExport = ref(false)
const exportPassword = ref('')
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
function toggleSelectAll(checked: boolean | string | number) {
  if (checked) {
    selectedCycles.value = availableCycles.map(c => c.code)
  } else {
    selectedCycles.value = []
  }
}

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
  if (file.raw && currentAction.value === 'import-data') {
    // Auto-detect cycles from ZIP manifest (#16)
    const formData = new FormData()
    formData.append('file', file.raw)
    http.post(
      `/api/projects/${props.projectId}/bulk-tab/preview-manifest`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    ).then((res: any) => {
      const data = res?.data ?? res
      if (data?.cycles?.length) {
        selectedCycles.value = data.cycles.filter(
          (c: string) => availableCycles.some(ac => ac.code === c)
        )
        ElMessage.success(`已从 ZIP 识别 ${data.file_count} 张底稿，循环: ${selectedCycles.value.join(', ')}`)
      }
    }).catch(() => {
      // Silent — manual selection still works
    })
  }
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
        // #29: Large export warning — auto-suggest async for >5 cycles
        if (selectedCycles.value.length > 5) {
          ElMessage.info({
            message: `正在导出 ${selectedCycles.value.length} 个循环的全部数据，文件可能较大，请耐心等待...`,
            duration: 5000,
          })
        }
        await exportData(selectedCycles.value, onlyWithData.value, incrementalExport.value, exportPassword.value || undefined)
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
