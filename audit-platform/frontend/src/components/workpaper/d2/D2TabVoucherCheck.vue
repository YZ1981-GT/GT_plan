<script setup lang="ts">
/**
 * D2TabVoucherCheck — D2-7 凭证检查表（重构后五区段布局）
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 7.1
 *
 * 五区段容器布局：
 *   一、审计目标 el-alert
 *   二、方法学参数区 MethodologyPanel
 *   三、测试区（双区 el-tabs + 视图切换 el-segmented）
 *   四、审计说明 AuditSummaryPanel
 *   五、审计结论 textarea + AI 辅助按钮
 *
 * 集成：
 *   - useD2VoucherCheckEnhanced（双区数据管理）
 *   - useD2VcMethodology（方法学参数 + B15/B50 联动）
 *   - useD2VcAuditSummary（统计自动化）
 *   - useD2VcImportExport（双区分 sheet 导入导出）
 *   - GtVoucherSamplingEngine（dialog-mode + @filled → 双区回填）
 *   - useWorkpaperVersionToolbar（版本工具栏）
 *   - GtIndexChip（value="wp:D2-7"）
 *   - PostFillAiReviewDialog（回填后 AI 复核）
 *
 * Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.5, 10.4
 */
import { ref, toRef, computed, provide, onMounted, type Ref } from 'vue'
import { useD2VoucherCheckEnhanced } from '../composables/useD2VoucherCheckEnhanced'
import { useD2VcMethodology } from '../composables/useD2VcMethodology'
import { useD2VcAuditSummary } from '../composables/useD2VcAuditSummary'
import { useD2VcImportExport } from '../composables/useD2VcImportExport'
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import { D2_SAVE_ITEMS_KEY } from '../composables/d2InjectionKeys'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import http from '@/utils/http'

import MatrixView from './D2VcMatrixView.vue'
import CardView from './D2VcCardView.vue'
import MethodologyPanel from './D2VcMethodologyPanel.vue'
import AuditSummaryPanel from './D2VcAuditSummaryPanel.vue'
import GtIndexChip from '../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import PostFillAiReviewDialog from '../voucher-sampling/PostFillAiReviewDialog.vue'
import GtWpVersionTrail from '../version-trail/GtWpVersionTrail.vue'

import type { SampledVoucher } from '../composables/useD2VoucherCheckEnhanced'
import type { Phase, FillMode } from '../composables/useSamplingAlgorithms'
import type { ChecklistResponse } from '../composables/useD2FormData'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  htmlData: any
  isReadonly: boolean
  bsDate: string
  sheetName: string
}>()

// ─── Ref Wrappers ────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>
const allResponsesRef = toRef(props, 'allResponses') as Ref<Map<string, any>>
const isReadonlyRef = toRef(props, 'isReadonly') as Ref<boolean>
const bsDateRef = toRef(props, 'bsDate') as Ref<string>

// ─── Provide: saveItems ──────────────────────────────────────────────────────

let saveDebounceTimer: ReturnType<typeof setTimeout> | null = null

async function saveItems(items: ChecklistResponse[]): Promise<void> {
  if (!props.wpId) return
  // Update local map immediately
  for (const item of items) {
    allResponsesRef.value.set(item.item_id, item)
  }
  // Debounced persist
  if (saveDebounceTimer) clearTimeout(saveDebounceTimer)
  saveDebounceTimer = setTimeout(async () => {
    saveDebounceTimer = null
    try {
      await http.put(
        `/api/workpapers/${props.wpId}/checklist-responses`,
        { items },
        { _silent: true } as any,
      )
      versionToolbar.scheduleAutoSnapshot()
    } catch (err) {
      console.warn('[D2TabVoucherCheck] saveItems failed:', err)
    }
  }, 2000)
}

provide(D2_SAVE_ITEMS_KEY, saveItems)

// ─── Core Composables ────────────────────────────────────────────────────────

// 双区数据管理
const {
  currentRows,
  postRows,
  activeZone,
  viewMode,
  activeRows,
  switchZone,
  switchViewMode,
  addRow,
  removeRow,
  updateRow,
  fillFromSampledVouchers,
  saveToResponses,
} = useD2VoucherCheckEnhanced({
  allResponses: allResponsesRef,
  isReadonly: isReadonlyRef,
  bsDate: bsDateRef,
})

// 方法学参数
const methodology = useD2VcMethodology({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: allResponsesRef,
  isReadonly: isReadonlyRef,
})

// 审计说明统计
const auditSummary = useD2VcAuditSummary({
  wpId: wpIdRef,
  projectId: projectIdRef,
  currentRows,
  postRows,
  allResponses: allResponsesRef,
  isReadonly: isReadonlyRef,
})

// 导入导出
const importExport = useD2VcImportExport({
  wpId: wpIdRef,
  currentRows,
  postRows,
  saveToResponses,
})

// 版本工具栏
const versionToolbar = useWorkpaperVersionToolbar({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// AI 生成
const { aiAvailable, generateAndConfirm } = useD2AiGenerate(wpIdRef)

// ─── 审计结论（区段五）──────────────────────────────────────────────────────

const CONCLUSION_KEY = 'D2-vc-conclusion'
const conclusion = ref('')
const aiLoadingConclusion = ref(false)

function loadConclusion(): void {
  const resp = allResponsesRef.value.get(CONCLUSION_KEY)
  if (resp?.remark) {
    conclusion.value = resp.remark
  }
}

function saveConclusion(v: string): void {
  if (props.isReadonly) return
  conclusion.value = v
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: v }
  allResponsesRef.value.set(CONCLUSION_KEY, item)
  void saveItems([item] as any)
}

async function generateConclusionAI(): Promise<void> {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm('vc-conclusion', conclusion.value, {
      sheet: 'D2-7',
      stats: auditSummary.stats.value,
      checked: currentRows.value.length + postRows.value.length,
    }, 'AI · 审计结论')
    if (text) saveConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

// ─── 视图切换选项 ────────────────────────────────────────────────────────────

const viewOptions = [
  { label: '矩阵视图', value: 'matrix' },
  { label: '卡片视图', value: 'card' },
]

// ─── 抽凭引擎集成 ────────────────────────────────────────────────────────────

const showPostFillReview = ref(false)
const lastFilledRows = ref<any[]>([])

const year = computed(() => {
  if (props.bsDate && props.bsDate.length >= 4) {
    return parseInt(props.bsDate.slice(0, 4), 10)
  }
  return new Date().getFullYear() - 1
})

const currentPhase = computed<Phase>(() => 'final')

function onSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: string }): void {
  const { samples, fillMode } = payload
  fillFromSampledVouchers(samples, fillMode === 'merge' ? 'merge' : 'replace')
  // Keep refs for PostFill review
  lastFilledRows.value = samples.map(s => ({
    voucherNo: s.voucherNo,
    voucherDate: s.voucherDate,
    debitAmount: s.debitAmount,
    creditAmount: s.creditAmount,
  }))
  // Trigger PostFillAiReviewDialog
  showPostFillReview.value = true
}

/** PostFill AI 复核意见应用到审计说明 */
function handlePostFillApplied(text: string): void {
  if (text && auditSummary.summaryText) {
    const current = auditSummary.summaryText.value || ''
    auditSummary.summaryText.value = current
      ? `${current}\n\n【AI 复核意见】${text}`
      : `【AI 复核意见】${text}`
    auditSummary.saveToResponses()
  }
}

// ─── 行数统计 ────────────────────────────────────────────────────────────────

const currentRowCount = computed(() => currentRows.value.length)
const postRowCount = computed(() => postRows.value.length)
const totalRowCount = computed(() => currentRowCount.value + postRowCount.value)

// ─── 导入导出下拉菜单 ────────────────────────────────────────────────────────

function handleImportExportCommand(command: string): void {
  if (command === 'export-template') {
    importExport.exportTemplate()
  } else if (command === 'export-data') {
    importExport.exportData()
  } else if (command === 'import-data') {
    // Trigger file input
    importFileInput.value?.click()
  }
}

const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    importExport.importData(file)
    input.value = '' // Reset for next selection
  }
}

// ─── selfLoad 逻辑 ──────────────────────────────────────────────────────────

onMounted(() => {
  methodology.initialize()
  auditSummary.loadOccurrenceAmount()
  loadConclusion()
})
</script>

<template>
  <div class="d2-voucher-check">
    <!-- ═══════════════════════════════════════════════════════════════════════
         一、审计目标
         ═══════════════════════════════════════════════════════════════════════ -->
    <el-alert
      title="审计目标"
      type="info"
      :closable="false"
      show-icon
      class="section-audit-objective"
    >
      <template #default>
        <p class="objective-text">
          通过对应收账款本期增减变动的凭证抽查及期后收款调整的检查，确认应收账款发生额的真实性、准确性、截止性与计价分摊，
          识别异常交易并评估错报风险。
        </p>
      </template>
    </el-alert>

    <!-- 操作引导区 -->
    <div class="vc-guide-area">
      <div class="guide-title">📋 编制步骤</div>
      <div class="guide-steps">
        <div class="guide-step"><span class="step-num">1</span> 配置方法学参数</div>
        <div class="guide-step"><span class="step-num">2</span> 运行抽凭引擎</div>
        <div class="guide-step"><span class="step-num">3</span> 上传附件OCR核对</div>
        <div class="guide-step"><span class="step-num">4</span> 确认核对结果</div>
        <div class="guide-step"><span class="step-num">5</span> 查看统计说明</div>
      </div>
    </div>

    <!-- 方法论上下文（CAS 1314） -->
    <div class="vc-methodology-context">
      <div class="context-title">审计准则要点 · CAS 1314</div>
      <ul class="context-list">
        <li>审计抽样应获取关于测试总体的充分适当审计证据，从而合理推断总体特征</li>
        <li>样本量应足以将抽样风险降至可接受水平，并与可容忍错报/偏差率相适应</li>
        <li>对于货币单元抽样（MUS），抽样间隔 = 可容忍错报 ÷ 可靠性系数（泊松分布表）</li>
        <li>异常情况应进一步调查其性质和原因，评估对总体的影响</li>
      </ul>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════════════
         二、方法学参数区
         ═══════════════════════════════════════════════════════════════════════ -->
    <section class="section-methodology">
      <MethodologyPanel
        :is-readonly="isReadonly"
        :methodology="methodology"
      />
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════════
         三、测试区（双区 el-tabs + 视图切换 el-segmented）
         ═══════════════════════════════════════════════════════════════════════ -->
    <section class="section-test-zone">
      <!-- 工具栏 -->
      <div class="zone-toolbar">
        <div class="toolbar-left">
          <el-segmented
            :model-value="viewMode"
            :options="viewOptions"
            size="small"
            @change="(v: any) => switchViewMode(v.value ?? v)"
          />
          <el-tag type="info" size="small" effect="plain" class="row-count-tag">
            共 {{ totalRowCount }} 行
          </el-tag>
        </div>
        <div class="toolbar-right">
          <!-- 抽凭引擎 -->
          <GtVoucherSamplingEngine
            v-if="wpId && projectId && !isReadonly"
            account-code="1122"
            :phase="currentPhase"
            default-method="random"
            :workpaper-id="wpId"
            :project-id="projectId"
            :year="year"
            dialog-mode
            @filled="onSamplingFilled"
          />
          <!-- 导入导出 -->
          <el-dropdown
            trigger="click"
            :disabled="isReadonly"
            @command="handleImportExportCommand"
          >
            <el-button size="small" :disabled="isReadonly">
              导入导出 <el-icon class="el-icon--right"><i class="el-icon-arrow-down" /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                <el-dropdown-item command="import-data" :disabled="isReadonly">导入数据</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <input
            ref="importFileInput"
            type="file"
            accept=".xlsx,.xls"
            style="display:none"
            @change="handleImportFileChange"
          />
          <!-- GtIndexChip -->
          <GtIndexChip value="wp:D2-7" :context-project-id="projectId" />
          <!-- 版本历史 -->
          <el-button size="small" text @click="versionToolbar.openVersionHistory()">📋 版本</el-button>
        </div>
      </div>

      <!-- 双区 Tabs -->
      <el-tabs
        :model-value="activeZone"
        type="border-card"
        class="zone-tabs"
        @tab-change="(name: any) => switchZone(name as 'current' | 'post')"
      >
        <el-tab-pane name="current">
          <template #label>
            <span>(1) 本期增减变动检查</span>
            <el-badge :value="currentRowCount" :max="999" type="info" class="tab-badge" />
          </template>
          <MatrixView
            v-if="viewMode === 'matrix'"
            :rows="currentRows"
            :is-readonly="isReadonly"
            :wp-id="wpId"
            :project-id="projectId"
            @update-row="updateRow"
            @add-row="addRow"
            @remove-row="removeRow"
          />
          <CardView
            v-else
            :rows="currentRows"
            :is-readonly="isReadonly"
            :wp-id="wpId"
            :project-id="projectId"
            @update-row="updateRow"
          />
        </el-tab-pane>

        <el-tab-pane name="post">
          <template #label>
            <span>(2) 期后收款调整检查</span>
            <el-badge :value="postRowCount" :max="999" type="info" class="tab-badge" />
          </template>
          <MatrixView
            v-if="viewMode === 'matrix'"
            :rows="postRows"
            :is-readonly="isReadonly"
            :wp-id="wpId"
            :project-id="projectId"
            @update-row="updateRow"
            @add-row="addRow"
            @remove-row="removeRow"
          />
          <CardView
            v-else
            :rows="postRows"
            :is-readonly="isReadonly"
            :wp-id="wpId"
            :project-id="projectId"
            @update-row="updateRow"
          />
        </el-tab-pane>
      </el-tabs>
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════════
         四、审计说明
         ═══════════════════════════════════════════════════════════════════════ -->
    <section class="section-audit-summary">
      <AuditSummaryPanel
        :is-readonly="isReadonly"
        :audit-summary="auditSummary"
      />
    </section>

    <!-- ═══════════════════════════════════════════════════════════════════════
         五、审计结论
         ═══════════════════════════════════════════════════════════════════════ -->
    <section class="section-conclusion">
      <el-card shadow="never" class="conclusion-card">
        <template #header>
          <div class="conclusion-header">
            <span class="conclusion-title">审计结论</span>
            <el-tooltip :content="aiAvailable ? 'AI 辅助生成审计结论' : 'AI 服务暂不可用'" placement="top">
              <el-button
                size="small"
                text
                type="primary"
                :loading="aiLoadingConclusion"
                :disabled="isReadonly || !aiAvailable"
                @click="generateConclusionAI"
              >
                🤖 AI 辅助
              </el-button>
            </el-tooltip>
          </div>
        </template>
        <el-input
          type="textarea"
          :autosize="{ minRows: 5 }"
          :model-value="conclusion"
          placeholder="根据凭证抽查结果，对应收账款本期增减变动及期后收款调整的真实性、准确性和截止性作出审计结论..."
          :disabled="isReadonly"
          @change="saveConclusion"
        />
      </el-card>
    </section>

    <!-- 编制提示 -->
    <details class="vc-compile-hints">
      <summary>编制提示</summary>
      <div class="hints-content">
        <p><strong>操作说明：</strong></p>
        <ul>
          <li><strong>方法学参数配置</strong>：系统将自动联动 B15（重要性水平）和 B50（风险评估）数据，推荐抽样方法和样本量。用户可覆盖 AI 推荐值。</li>
          <li><strong>抽凭引擎</strong>：点击工具栏"抽凭"按钮，配置科目和抽样参数后执行抽样。抽样结果自动按凭证日期分配到本期/期后区块。</li>
          <li><strong>OCR 核对</strong>：在矩阵视图中点击📎按钮上传发票/合同等证据文件，系统自动 OCR 识别并与凭证数据比对，确认后回填核对内容1~5。</li>
          <li><strong>异常标记</strong>：在"是否异常"列可选择或自定义异常类型。异常标记会自动纳入审计说明统计。</li>
          <li><strong>审计说明</strong>：统计指标（覆盖比例、异常率等）自动计算，2 秒内刷新。可点击 AI 按钮生成审计说明文字。</li>
          <li><strong>导入导出</strong>：支持双区分 sheet 导入导出，按凭证编号合并（已有行保留核对结果不覆盖）。</li>
        </ul>
        <p><strong>审计准则依据：</strong> CAS 1314《审计抽样》、CAS 1231《针对评估的重大错报风险采取的应对措施》</p>
      </div>
    </details>

    <!-- ═══════════════════════════════════════════════════════════════════════
         PostFillAiReviewDialog — 回填后 AI 复核
         ═══════════════════════════════════════════════════════════════════════ -->
    <PostFillAiReviewDialog
      v-model="showPostFillReview"
      :wp-id="wpId"
      :rows="lastFilledRows"
      section="voucher-review"
      :ai-available="aiAvailable"
      @applied="handlePostFillApplied"
    />

    <!-- GtWpVersionTrail Drawer -->
    <GtWpVersionTrail
      :ref="(el: any) => { versionToolbar.versionTrailRef.value = el }"
      :workpaper-id="wpId"
      :project-id="projectId"
    />
  </div>
</template>

<style scoped>
.d2-voucher-check {
  padding: 16px;
  font-size: 13px;
}

/* ─── 一、审计目标 ──────────────────────────────────────────────────────── */
.section-audit-objective {
  margin-bottom: 16px;
}
.objective-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #606266;
}

/* ─── 二、方法学参数区 ──────────────────────────────────────────────────── */
.section-methodology {
  margin-bottom: 16px;
}

/* ─── 操作引导区 ──────────────────────────────────────────────────────── */
.vc-guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
}
.guide-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a73e8;
  margin-bottom: 10px;
}
.guide-steps {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}
.guide-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #303133;
}
.step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

/* ─── 方法论上下文（CAS 1314）──────────────────────────────────────────── */
.vc-methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.context-title {
  font-size: 13px;
  font-weight: 600;
  color: #e6a23c;
  margin-bottom: 8px;
}
.context-list {
  margin: 0;
  padding-left: 18px;
  list-style: disc;
}
.context-list li {
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}

/* ─── 编制提示 ────────────────────────────────────────────────────────── */
.vc-compile-hints {
  margin-top: 16px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  overflow: hidden;
}
.vc-compile-hints summary {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  cursor: pointer;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.vc-compile-hints summary:hover {
  background: #f5f7fa;
}
.hints-content {
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}
.hints-content ul {
  margin: 6px 0;
  padding-left: 20px;
}
.hints-content li {
  margin-bottom: 6px;
}
.hints-content p {
  margin: 8px 0;
}

/* ─── 三、测试区 ────────────────────────────────────────────────────────── */
.section-test-zone {
  margin-bottom: 16px;
}

.zone-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.row-count-tag {
  font-size: 12px;
}

.zone-tabs {
  --el-tabs-header-height: 40px;
}
.zone-tabs :deep(.el-tabs__content) {
  padding: 12px;
}

.tab-badge {
  margin-left: 6px;
}

/* ─── 四、审计说明 ──────────────────────────────────────────────────────── */
.section-audit-summary {
  margin-bottom: 16px;
}

/* ─── 五、审计结论 ──────────────────────────────────────────────────────── */
.section-conclusion {
  margin-bottom: 16px;
}
.conclusion-card {
  border: 1px solid #ebeef5;
}
.conclusion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.conclusion-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}
</style>
