<template>
  <div class="import-screen citar-import">
    <header class="import-header">
      <h1 class="import-header__title">数据导入</h1>
      <span class="citar-import__year">{{ year ? `审核年度 ${year}` : '未设置审核年度' }}</span>
      <button class="import-header__doc" type="button" @click="guideVisible = true">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <path d="M2 2h12v2H2zm0 4h12v8H2zm2 2v4h8V8z" />
        </svg>
        使用文档
      </button>
    </header>

    <!-- 导入记录详情（?job=，账务查询来源卡片点映射项跳来；spec citar-cell-source-hover R9） -->
    <CitarImportJobDetail
      v-if="detailJob"
      :project-id="projectId"
      :job-id="detailJob"
      :locate="detailLocate"
      @back="backToLedger"
      @new-import="goSegment('ledger-import')"
    />

    <!-- 三步提示：选文件 → 智能识别与映射 → 导入 -->
    <!-- 识别是表头别名 / 编辑距离 / 历史映射复用的规则实现，没有大模型，故写「智能」不写「AI」（用户 2026-11-04 方案 A） -->
    <ol v-if="!detailJob" class="citar-import__steps">
      <li v-for="(s, i) in STEPS" :key="s" :class="{ 'is-active': step === i, 'is-done': step > i }">{{ i + 1 }}. {{ s }}</li>
    </ol>

    <!-- 当前账套有人工修改：重新导入生成新数据集，这些修改不会带过去（spec citar-table-manual-edit R5） -->
    <p v-if="!detailJob && manualCount && step === 0" class="citar-import__warn" role="status">
      当前账套有人工修改（科目余额表 {{ manualSummary.balance }} 行、序时账 {{ manualSummary.ledger }} 行）。重新导入后这些修改不会保留。
    </p>

    <section v-if="!detailJob" class="import-card">
      <!-- 第 1 步：选文件（CITAR 拖拽区） -->
      <template v-if="step === 0">
        <div
          class="import-drop"
          :class="{ 'import-drop--over': dragOver }"
          role="button"
          tabindex="0"
          @click="pick"
          @keydown.enter.prevent="pick"
          @keydown.space.prevent="pick"
          @dragover.prevent="dragOver = true"
          @dragleave="dragOver = false"
          @drop.prevent="onDrop"
        >
          <div v-if="files.length" class="citar-import__files" @click.stop>
            <div v-for="(f, i) in files" :key="f.name + f.size" class="import-file">
              <svg class="import-file__icon" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M6 2h8l4 4v16H6zm8 1.5V7h3.5z" />
              </svg>
              <div class="import-file__meta">
                <p class="import-file__name">{{ f.name }}</p>
                <p class="import-file__size">{{ formatSize(f.size) }}</p>
              </div>
              <button class="import-file__clear" type="button" :disabled="detecting" @click="removeFile(i)">移除</button>
            </div>
          </div>
          <template v-else>
            <svg class="import-drop__icon" width="40" height="40" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 4a6 6 0 0 1 5.9 4.9A4.5 4.5 0 0 1 17.5 18H7a5 5 0 0 1-.8-9.94A6 6 0 0 1 12 4zm1 7h2.5L12 7.5 8.5 11H11v4h2z" />
            </svg>
            <p class="import-drop__text">将科目余额表、序时账等文件拖到此处，或<span class="import-drop__link">点击上传</span></p>
          </template>
        </div>

        <input ref="inputRef" class="import-input" type="file" multiple :accept="ACCEPTED_EXTENSIONS" @change="onPicked" />

        <ul class="import-notes">
          <li>支持 .xlsx / .xlsm / .csv / .tsv / .zip，可一次选多个文件（最多 20 个，合计 500MB）</li>
          <li>系统智能识别科目余额表、序时账、辅助余额表与辅助明细账，并自动匹配列；识别后可逐列确认</li>
        </ul>

        <div v-if="detecting" class="citar-import__progress">
          <el-progress :percentage="uploadPercent" :stroke-width="8" />
          <span>{{ uploadPercent < 90 ? '正在上传…' : '正在智能识别表格结构，大文件需要几分钟…' }}</span>
        </div>

        <div class="import-actions">
          <button class="import-pick" type="button" :disabled="detecting" @click="pick">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M1.5 3h4l1.5 1.5h6.5V13H1.5z" />
            </svg>
            选择文件
          </button>
          <span class="import-actions__hint">若上方拖拽区点击无反应，请用此按钮选择文件</span>
          <button class="import-submit" type="button" :disabled="!files.length || detecting || !year" @click="runDetect">
            {{ detecting ? '智能预检中…' : '开始智能预检' }}
          </button>
        </div>
      </template>

      <!-- 第 2 步：识别结果确认 + 列映射（复用平台组件，校验规则与原导入页一致） -->
      <DetectionPreview
        v-else-if="step === 1 && subStep === 'preview'"
        :detection-result="detection"
        @confirm="onPreviewConfirm"
        @back="resetToUpload"
      />
      <ColumnMappingEditor
        v-else-if="step === 1"
        :sheets="confirmedSheets"
        :detection-result="detection"
        :project-id="projectId"
        @confirm="submitJob"
        @back="subStep = 'preview'"
      />

      <!-- 第 3 步：导入进度 -->
      <template v-else>
        <div v-if="!jobId" class="citar-import__submitting">
          <template v-if="!submitError">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
            <p>正在提交导入作业…</p>
          </template>
          <template v-else>
            <p class="citar-import__error">{{ submitError }}</p>
            <div class="citar-import__retry">
              <button class="import-pick" type="button" @click="step = 1">返回列映射</button>
              <button class="import-submit" type="button" @click="lastMappings && submitJob(lastMappings)">重试提交</button>
            </div>
          </template>
        </div>
        <ImportProgress
          v-else
          :project-id="projectId"
          :job-id="jobId"
          @complete="onComplete"
          @failed="onFailed"
          @canceled="resetToUpload"
          @background="goSegment('ledger-query')"
        />
      </template>
    </section>

    <ErrorDialog v-model:visible="errorVisible" :errors="errors" />
    <LedgerImportGuideDialog v-model="guideVisible" />
  </div>
</template>

<script setup lang="ts">
/**
 * 数据导入（CITAR 版式 + 平台真实导入流程）。
 *
 * 流程与 views/LedgerImportPage.vue 相同：detect → 识别预览 → 列映射 → submit → SSE 进度。
 * 中间两步与进度直接复用 components/ledger-import 下的组件（致命错误拦截、年度置信度确认、
 * 规模警告强制继续、关键列必须映射都在组件里），本页只换外观与编排。
 * 差异：按项目审核年度导入（detect 带 year_override、submit 用项目年度），完成后进「账务查询」。
 */
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import DetectionPreview from '@/components/ledger-import/DetectionPreview.vue'
import ColumnMappingEditor from '@/components/ledger-import/ColumnMappingEditor.vue'
import ImportProgress from '@/components/ledger-import/ImportProgress.vue'
import ErrorDialog from '@/components/ledger-import/ErrorDialog.vue'
import type {
  ImportError,
  LedgerDetectionResult,
  SheetDetection,
} from '@/components/ledger-import/LedgerImportDialog.vue'
// 列映射组件 emit 的是新版类型（LedgerImportDialog 里的同名类型已标 deprecated）
import type { ConfirmedMapping } from '@/types/ledger-import'
import { ledger as P_ledger } from '@/services/apiPaths'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { fetchManualEditsSummary } from '../citarLedgerEdits'
import CitarImportJobDetail from '../components/CitarImportJobDetail.vue'
import { useCitarProject } from '../useCitarProject'

const LedgerImportGuideDialog = defineAsyncComponent(
  () => import('@/components/ledger-import/LedgerImportGuideDialog.vue'),
)

defineOptions({ name: 'CitarDataImport' })

const STEPS = ['选择文件', '智能识别与映射', '导入']
const ACCEPTED_EXTENSIONS = '.xlsx,.xlsm,.csv,.tsv,.zip'
const MAX_FILES = 20

const { projectId, year, goSegment } = useCitarProject()
const route = useRoute()
const router = useRouter()

/** ?job= 打开某次导入的记录详情（只读），?locate= 高亮其中一列的映射 */
const detailJob = computed(() => (typeof route.query.job === 'string' ? route.query.job : ''))
const detailLocate = computed(() => (typeof route.query.locate === 'string' ? route.query.locate : ''))

/** 从账务查询卡片跳来 ⇒ 回到原页签与定位；直接打开的链接没有上一页 ⇒ 进账务查询 */
function backToLedger() {
  if (window.history.state?.back) router.back()
  else goSegment('ledger-query')
}

const step = ref(0)
const subStep = ref<'preview' | 'mapping'>('preview')
const files = ref<File[]>([])
const dragOver = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)
const detecting = ref(false)
const uploadPercent = ref(0)
const detection = ref<LedgerDetectionResult | null>(null)
const confirmedSheets = ref<SheetDetection[]>([])
const forceSubmit = ref(false)
const jobId = ref('')
const submitError = ref('')
const lastMappings = ref<ConfirmedMapping[] | null>(null)
const errors = ref<ImportError[]>([])
const errorVisible = ref(false)
const guideVisible = ref(false)

/** 当前账套人工修改行数（重新导入前提示） */
const manualSummary = ref({ balance: 0, ledger: 0 })
const manualCount = computed(() => manualSummary.value.balance + manualSummary.value.ledger)
watch([projectId, year], async ([pid, y]) => {
  manualSummary.value = { balance: 0, ledger: 0 }
  if (!pid || !y) return
  try {
    manualSummary.value = await fetchManualEditsSummary(pid, y)
  } catch {
    // 只是提示，读不到不影响导入
  }
}, { immediate: true })

function pick() {
  if (!detecting.value) inputRef.value?.click()
}

function addFiles(list: FileList | null | undefined) {
  if (!list) return
  const next = [...files.value]
  for (const f of Array.from(list)) {
    // 同名同大小视为同一文件
    if (!next.some(x => x.name === f.name && x.size === f.size)) next.push(f)
  }
  if (next.length > MAX_FILES) {
    ElMessage.warning(`最多上传 ${MAX_FILES} 个文件`)
    next.length = MAX_FILES
  }
  files.value = next
}

function onDrop(event: DragEvent) {
  dragOver.value = false
  addFiles(event.dataTransfer?.files)
}

function onPicked(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(input.files)
  // 清空，否则再选同一个文件不会触发 change
  input.value = ''
}

function removeFile(index: number) {
  files.value = files.value.filter((_, i) => i !== index)
}

async function runDetect() {
  if (!year.value) return
  detecting.value = true
  uploadPercent.value = 0
  ;(globalThis as any).__suppressTimeoutToast = true
  try {
    const form = new FormData()
    for (const f of files.value) form.append('files', f, f.name)
    // 按项目审核年度识别（原导入页不传，靠文件里的年份猜）
    form.append('year_override', String(year.value))
    const result = (await api.post(P_ledger.import.v2Detect(projectId.value), form, {
      timeout: 600000,
      _silent: true,
      onUploadProgress: (evt: any) => {
        // 上传字节进度，非金额
        // eslint-disable-next-line gt-audit/no-amount-arithmetic
        if (evt.total) uploadPercent.value = Math.min(90, Math.round((evt.loaded / evt.total) * 90))
      },
    } as any)) as LedgerDetectionResult
    uploadPercent.value = 100
    const fatal = (result.errors || []).filter(e => e.severity === 'fatal')
    if (fatal.length) {
      errors.value = fatal
      errorVisible.value = true
      return
    }
    detection.value = result
    subStep.value = 'preview'
    step.value = 1
  } catch (err) {
    handleApiError(err, '预检')
  } finally {
    detecting.value = false
    ;(globalThis as any).__suppressTimeoutToast = false
  }
}

function onPreviewConfirm(sheets: SheetDetection[], force?: boolean) {
  confirmedSheets.value = sheets
  forceSubmit.value = !!force
  subStep.value = 'mapping'
}

async function submitJob(mappings: ConfirmedMapping[]) {
  if (!detection.value || !year.value) return
  lastMappings.value = mappings
  submitError.value = ''
  jobId.value = ''
  step.value = 2
  try {
    const res = (await api.post(
      P_ledger.import.v2Submit(projectId.value),
      {
        upload_token: detection.value.upload_token,
        year: year.value,
        confirmed_mappings: mappings,
        force_activate: false,
        force_submit: forceSubmit.value,
      },
      { timeout: 600000, _silent: true } as any,
    )) as { job_id: string }
    jobId.value = res.job_id
  } catch (err: any) {
    const detail = err?.response?.data?.detail
    submitError.value =
      (typeof detail === 'string' && detail) || detail?.message || err?.message || '提交导入作业失败，请稍后重试'
  }
}

function onComplete() {
  ElMessage.success('导入完成，试算表已按新数据重算')
  goSegment('ledger-query')
}

function onFailed() {
  errors.value = [{ code: 'IMPORT_FAILED', severity: 'fatal', message: '导入过程中发生错误，请查看详情' }]
  errorVisible.value = true
}

function resetToUpload() {
  step.value = 0
  subStep.value = 'preview'
  detection.value = null
  jobId.value = ''
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  // 文件大小，非金额
  // eslint-disable-next-line gt-audit/no-amount-toFixed
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[i]}`
}
</script>

<style scoped src="../styles/data-import.css"></style>

<style scoped>

.citar-import__warn {
  margin: 0 0 12px;
  padding: 8px 12px;
  border: 1px solid #f0d9a8;
  border-radius: 6px;
  background: #fff8e8;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-8a5300);
}

.citar-import__year {
  margin-left: 16px;
  font-size: var(--citar-fs-13);
  color: rgba(255, 255, 255, 0.85);
}

.citar-import__steps {
  display: flex;
  gap: 24px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
  font-size: var(--citar-fs-13);
  color: var(--citar-c-9a9aa4);
}

.citar-import__steps .is-active {
  color: var(--citar-c-6e0ba6);
  font-weight: 700;
}

.citar-import__steps .is-done {
  color: var(--citar-c-4c1273);
}

.citar-import__files {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  max-width: 520px;
}

.citar-import__progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 14px;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-8c8c96);
}

.citar-import__submitting {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 0;
  font-size: var(--citar-fs-14);
  color: var(--citar-c-6e0ba6);
}

.citar-import__error {
  margin: 0;
  color: var(--citar-c-a3262a);
}

.citar-import__retry {
  display: flex;
  gap: 12px;
}

.citar-import__retry .import-submit {
  margin-left: 0;
}
</style>
