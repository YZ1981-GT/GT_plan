<template>
  <el-dialog
    v-model="visible"
    title="批量 Tab 导入导出（结构化数据包）"
    width="640px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 步骤一：选择场景（文案全部来自后端 scenario_registry 单一真源） -->
    <div v-if="step === 'action'" class="bulk-action-step">
      <p class="bulk-desc">
        本功能将项目中已实例化的底稿 Tab 数据以 ZIP 结构化包形式导入/导出，
        与"批量导出底稿文件"（整份文件）互不替代。
      </p>

      <!--
        错误文案走**默认插槽**而不是 `:title` prop：测试里 el-alert 会被 stub，
        stub 不渲染 prop ⇒ 断言"错误已呈现"会假绿。插槽内容在 stub 下仍会渲染。
      -->
      <el-alert
        v-if="scenarioLoadError"
        type="error"
        :closable="false"
        show-icon
        style="margin-bottom:12px"
      >
        {{ scenarioLoadError }}
      </el-alert>

      <div v-if="scenariosLoading" class="scenario-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在读取场景说明…</span>
      </div>

      <el-tag
        v-else-if="isArchived"
        type="warning"
        size="small"
        effect="plain"
        style="margin-bottom:10px"
      >
        项目已归档 · 仅可导出
      </el-tag>

      <div v-if="!scenariosLoading" class="scenario-cards">
        <el-tooltip
          v-for="sc in scenarios"
          :key="sc.key"
          :disabled="!sc.disabled"
          :content="sc.disabledReason || ''"
          placement="top"
        >
          <div
            class="scenario-card"
            :class="{ 'is-disabled': sc.disabled }"
            :data-testid="`bulk-scenario-${sc.key}`"
            role="button"
            tabindex="0"
            :aria-disabled="sc.disabled"
            @click="selectScenario(sc)"
            @keydown.enter.prevent="selectScenario(sc)"
            @keydown.space.prevent="selectScenario(sc)"
          >
            <div class="scenario-card-head">
              <span class="scenario-title">{{ sc.label }}</span>
              <el-tag size="small" :type="directionTagType(sc.direction)" effect="plain">
                {{ directionLabel(sc.direction) }}
              </el-tag>
            </div>
            <dl class="scenario-meta">
              <dt>产物内容</dt>
              <dd>{{ sc.artifactNote }}</dd>
              <dt>适用时点</dt>
              <dd>{{ sc.timingNote }}</dd>
            </dl>
          </div>
        </el-tooltip>
      </div>
    </div>

    <!-- 步骤二：配置选项 -->
    <div v-else-if="step === 'options'" class="bulk-options-step">
      <!-- 场景说明回显（同一真源，不重写文案） -->
      <div v-if="currentScenario" class="scenario-recap" data-testid="bulk-scenario-recap">
        <div class="scenario-recap-title">{{ currentScenario.label }}</div>
        <div class="scenario-recap-line">{{ currentScenario.artifactNote }}</div>
        <div class="scenario-recap-line muted">{{ currentScenario.timingNote }}</div>
      </div>

      <el-form label-position="top">
        <!-- round_trip 场景：本次做哪一腿 -->
        <el-form-item
          v-if="currentScenario?.direction === 'round_trip'"
          label="本次操作"
          required
        >
          <el-radio-group
            :model-value="roundTripLeg"
            data-testid="bulk-roundtrip-leg"
            @update:model-value="(v: any) => switchRoundTripLeg(v)"
          >
            <el-radio value="export">先导出（拿到含取数的数据包）</el-radio>
            <el-radio value="import">导回（上传改好的数据包）</el-radio>
          </el-radio-group>
        </el-form-item>

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
import { ref, computed, watch } from 'vue'
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

/**
 * 四场景描述 —— **全部字段来自后端** `GET .../bulk-tab/scenarios`
 * （真源 `app/services/bulk_tab/scenario_registry.py`）。
 *
 * 🔴 本组件不得自行拼写 `label` / `artifactNote` / `timingNote`（R3.7）。
 * 守卫 `__tests__/bulkScenarioSingleSource.spec.ts` 扫本文件源码钉死：
 * 一旦把这些中文说明抄进前端，两处文案就会各改一半，用户看到的说明与后端
 * 实际行为脱节 —— 而这类不一致没有任何编译期信号。
 *
 * `disabled` / `disabledReason` 同样由后端算：门控真源是
 * `workflow_gate._BLOCKED_STATUSES`，前端再判一次归档就是抄第二份规则。
 */
interface BulkScenario {
  key: string
  label: string
  artifactNote: string
  timingNote: string
  exportEndpoint: string | null
  importEndpoint: string | null
  mode: 'template' | 'data'
  direction: 'export' | 'import' | 'round_trip'
  archivedAllowed: boolean
  disabled: boolean
  disabledReason: string | null
}

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

// ─── 四场景（后端单一真源） ───
const scenarios = ref<BulkScenario[]>([])
const scenariosLoading = ref(false)
const scenarioLoadError = ref<string | null>(null)
const isArchived = ref(false)
const currentScenario = ref<BulkScenario | null>(null)
/** round_trip 场景本次要做的方向（导出 / 导回） */
const roundTripLeg = ref<'export' | 'import'>('export')

/**
 * 拉取四场景。
 *
 * 🔴 失败时**不静默降级到硬写默认值**：那会让"后端改了文案、前端还显示旧的"
 * 变成看不见的偏差（memory 记的 fail-open 掩盖接线错误）。这里把错误显式呈现，
 * 场景列表保持为空 ⇒ 用户点不到入口，但知道为什么。
 */
async function loadScenarios(): Promise<void> {
  scenariosLoading.value = true
  scenarioLoadError.value = null
  try {
    const resp = await http.get(`/api/projects/${props.projectId}/bulk-tab/scenarios`)
    const payload = resp.data?.data ?? resp.data
    const list = payload?.scenarios
    if (!Array.isArray(list) || list.length === 0) {
      throw new Error('后端未返回场景列表')
    }
    scenarios.value = list as BulkScenario[]
    isArchived.value = !!payload?.isArchived
  } catch (err: any) {
    scenarios.value = []
    scenarioLoadError.value =
      `无法读取导入导出场景说明：${err?.message ?? err}。` +
      '请稍后重试；若持续失败请联系管理员（场景说明由后端统一维护）。'
  } finally {
    scenariosLoading.value = false
  }
}

/** 方向标签 —— 这是 UI 词汇（非场景说明），可在前端定义 */
function directionLabel(direction: BulkScenario['direction']): string {
  if (direction === 'export') return '导出'
  if (direction === 'import') return '导入'
  return '导出后可导回'
}

function directionTagType(direction: BulkScenario['direction']): 'success' | 'warning' | 'info' {
  if (direction === 'export') return 'success'
  if (direction === 'import') return 'warning'
  return 'info'
}

/** 场景 → 底层动作。round_trip 由 `roundTripLeg` 决定本次走哪一腿。 */
function resolveAction(sc: BulkScenario, leg: 'export' | 'import'): BulkAction {
  if (sc.direction === 'import' || (sc.direction === 'round_trip' && leg === 'import')) {
    return 'import-data'
  }
  return sc.mode === 'template' ? 'export-templates' : 'export-data'
}

function selectScenario(sc: BulkScenario): void {
  if (sc.disabled) {
    ElMessage.warning(sc.disabledReason || '当前项目状态下该操作不可用')
    return
  }
  currentScenario.value = sc
  roundTripLeg.value = 'export'
  currentAction.value = resolveAction(sc, 'export')
  step.value = 'options'
}

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
/**
 * 当前操作标题 —— 取所选场景的 `label`（后端真源），不再按 action 硬写中文。
 *
 * 兜底 '批量导入导出' 只在「无所选场景」这种不该出现的状态下用到，
 * 它是通用词、不是四场景说明，不构成 R3.7 的第二份文案源。
 */
const actionLabel = computed(() => currentScenario.value?.label ?? '批量导入导出')

/** round_trip 切腿时同步底层动作（否则会拿导出的配置去跑导入） */
function switchRoundTripLeg(leg: 'export' | 'import'): void {
  roundTripLeg.value = leg
  if (currentScenario.value) {
    currentAction.value = resolveAction(currentScenario.value, leg)
  }
}

/**
 * 执行按钮文案。
 *
 * round_trip 场景不拼场景 label —— 那会得到「开始导出已取数数据 → 编辑 → 导回」
 * 这种把三步流程塞进一个按钮的拗口文案（2026-08-12 浏览器实测发现）。
 * 该场景的按钮只描述**本次这一腿**在做什么，完整语义已由上方场景回显承担。
 */
const executeButtonLabel = computed(() => {
  if (currentAction.value === 'import-data') {
    return dryRun.value ? '开始预检' : '开始导入'
  }
  if (currentScenario.value?.direction === 'round_trip') {
    return '开始导出数据包'
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
  currentScenario.value = null
  roundTripLeg.value = 'export'
  report.value = null
  uploadFile.value = null
  progressTaskId.value = null
}

/**
 * 每次打开弹窗都重新拉场景 —— 不做首次缓存。
 *
 * 理由：`disabled` 取决于**项目当前状态**（归档与否）。缓存会让用户在别处归档项目后
 * 回到这里仍看到导入入口可点，点下去被后端 `workflow_gate` 静默跳过 ⇒
 * 「按钮亮着但什么都没发生」，比直接置灰更难排查。
 */
watch(
  () => props.modelValue,
  (open) => {
    if (open) void loadScenarios()
  },
  { immediate: true },
)
</script>

<style scoped>
.bulk-desc {
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
  line-height: 1.6;
}

/* ── 四场景卡片（替代原来三个裸按钮） ─────────────────────────────────── */

.scenario-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.scenario-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.scenario-card {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
  background: var(--el-fill-color-blank);
}

.scenario-card:hover:not(.is-disabled),
.scenario-card:focus-visible:not(.is-disabled) {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
  outline: none;
}

.scenario-card.is-disabled {
  cursor: not-allowed;
  opacity: 0.55;
  background: var(--el-fill-color-light);
}

.scenario-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.scenario-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.scenario-meta {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
}

.scenario-meta dt {
  color: var(--el-text-color-secondary);
  font-weight: 600;
  margin-top: 4px;
}

.scenario-meta dd {
  margin: 0;
  color: var(--el-text-color-regular);
}

/* ── 场景说明回显（options 步骤） ───────────────────────────────────── */

.scenario-recap {
  border-left: 3px solid var(--el-color-primary);
  background: var(--el-fill-color-light);
  padding: 8px 10px;
  border-radius: 0 4px 4px 0;
  margin-bottom: 14px;
  font-size: 12px;
  line-height: 1.55;
}

.scenario-recap-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
}

.scenario-recap-line.muted {
  color: var(--el-text-color-secondary);
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
