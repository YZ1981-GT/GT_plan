<script setup lang="ts">
/**
 * D1TabSamplingVouching.vue — D1-13 应收票据抽样凭证核对 HTML渲染
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 12.1
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换（结构化视图 | 在线编辑）
 * - 审计目标区域（只读静态文本）
 * - 抽样总体定义区（textarea + 笔数 + 金额 + 样本量 + 抽取笔数 + GtIndexChip）
 * - 特定样本区域（动态行: 描述|金额|原因）
 * - 分隔线 + "凭证核对明细"标题
 * - 凭证核对明细 el-table 12列：
 *   序号|票据类型|号码|出票人|承兑人|金额|到期日|存在性验证|准确性验证|记录恰当性|备注|索引号
 * - 验证结果颜色编码：已核实/金额一致/恰当=绿色；未核实/金额不一致/不恰当=红色
 * - 例外项行浅红色背景
 * - "添加核查项"按钮
 * - 核对结果区（G32核查笔数 | H32核查金额合计）
 * - 例外汇总区 E48-G50（3行×3列: 类别|笔数|金额|占比）
 * - 例外占比超标：红色高亮 + "例外率超标，请考虑扩大样本量"
 * - 测试结论（el-select）
 * - 审计说明/结论 + 编制提示（CAS 1314/抽样方法/例外追查/推断方法）
 * - GtOnlyOfficeSheet v-if isOOMode
 *
 * Requirements: 10.1-10.4, 11.1-11.4, 12.1-12.6, 13.1-13.5, 14.1-14.5, 18.1-18.4, 18.7
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1SamplingVouching } from '../composables/useD1SamplingVouching'
import {
  NOTE_TYPE_OPTIONS,
  EXISTENCE_OPTIONS,
  ACCURACY_OPTIONS,
  APPROPRIATENESS_OPTIONS,
  TEST_CONCLUSION_OPTIONS,
  formatNegativeAmount,
  type VouchingRow,
} from '../composables/d1InspectionFormulas'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  displayPrefs: any
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const injectedDisplayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Dual Mode (HTML ↔ OnlyOffice) ──────────────────────────────────────────

const editorMode = ref<'html' | 'oo'>('html')
const ooHealthy = ref(true)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
])

const isOOMode = computed(() => editorMode.value === 'oo')
const ooSheetName = computed(() => props.sheetName || '应收票据检查表D1-13')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  population,
  updatePopulation,
  specificSamples,
  addSpecificSample,
  removeSpecificSample,
  updateSpecificSample,
  vouchingRows,
  addVouchingRow,
  removeVouchingRow,
  updateVouchingRow,
  checkedCount,
  checkedAmountTotal,
  vouchingAmountTotal,
  exceptionSummary,
  hasExceedingException,
  tolerableErrorRate,
  updateTolerableErrorRate,
  testConclusion,
  updateTestConclusion,
  auditNote,
  auditConclusion,
  saveAuditNote,
  saveAuditConclusion,
} = useD1SamplingVouching({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  saveDebouncedText: (item: ChecklistItem) => {
    http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items: [item] })
      .catch(() => { /* silent */ })
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) {
    const formatted = formatNegativeAmount(val)
    return `<span class="negative-amount">${formatted}</span>`
  }
  return injectedDisplayPrefs.fmtAmount(val)
}

function fmtPercent(val: number): string {
  return (val * 100).toFixed(2) + '%'
}

// ─── Row Class for Exception ──────────────────────────────────────────────────

function getVouchingRowClass({ row }: { row: VouchingRow }): string {
  const isException = row.existenceCheck === '未核实'
    || row.accuracyCheck === '金额不一致'
    || row.appropriatenessCheck === '不恰当'
  return isException ? 'exception-row' : ''
}

// ─── Validation color helper ─────────────────────────────────────────────────

function getCheckClass(val: string): string {
  if (val === '已核实' || val === '金额一致' || val === '恰当') return 'check-positive'
  if (val === '未核实' || val === '金额不一致' || val === '不恰当') return 'check-negative'
  return ''
}

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  'CAS 1314审计抽样准则关于实质性细节测试的要求：设计样本时应考虑测试目标、总体特征、容忍和预期错报。',
  '抽样方法选择说明：根据总体特征选择随机抽样、系统抽样或货币单位抽样方法，并记录选择依据。',
  '例外项追查和评价程序：对每一例外项逐笔追查原因，区分异常偏差和总体偏差，评估是否反映系统性错误。',
  '样本结果推断总体的方法：根据样本中发现的错报推断总体错报，评估总体错报是否超过重要性水平。',
]
</script>

<template>
  <div class="d1-tab-sampling-vouching">
    <!-- Mode Switcher -->
    <div class="mode-switcher">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <el-tooltip v-if="!ooHealthy" content="OnlyOffice服务不可用" placement="top">
        <span class="oo-disabled-hint">⚠️</span>
      </el-tooltip>
    </div>

    <!-- OnlyOffice mode -->
    <GtOnlyOfficeSheet
      v-if="isOOMode"
      :wp-id="wpId"
      :sheet-name="ooSheetName"
      :project-id="projectId"
    />

    <!-- HTML mode -->
    <template v-if="!isOOMode">
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        class="audit-objective"
      >
        <template #default>
          <p>通过审计抽样选取样本，对抽样票据逐笔核查存在性、准确性和记录恰当性，以获取充分适当的审计证据。</p>
        </template>
      </el-alert>

      <!-- ═══════════════════ 抽样总体定义区 ═══════════════════ -->
      <div class="section-title">抽样总体定义</div>
      <div class="population-area">
        <!-- 抽样总体描述 -->
        <div class="population-field full-width">
          <label>抽样总体</label>
          <el-input
            type="textarea"
            :rows="2"
            :model-value="population.populationDesc"
            placeholder="描述抽样总体范围..."
            :disabled="isReadonly"
            @change="(v: string) => updatePopulation('populationDesc', v || '')"
          />
        </div>

        <!-- 数量字段行 -->
        <div class="population-numbers">
          <div class="population-field">
            <label>总体笔数</label>
            <el-input-number
              :model-value="population.totalCount"
              size="small"
              :controls="false"
              :min="0"
              :disabled="isReadonly"
              style="width: 120px"
              @change="(v: number) => updatePopulation('totalCount', v || 0)"
            />
          </div>
          <div class="population-field">
            <label>总体金额</label>
            <el-input-number
              :model-value="population.totalAmount"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 150px"
              @change="(v: number) => updatePopulation('totalAmount', v || 0)"
            />
            <span class="field-hint" v-if="population.totalAmount > 0" v-html="fmtAmount(population.totalAmount)" />
          </div>
          <div class="population-field">
            <label>确定的抽样样本量</label>
            <el-input-number
              :model-value="population.sampleSize"
              size="small"
              :controls="false"
              :min="0"
              :disabled="isReadonly"
              style="width: 120px"
              @change="(v: number) => updatePopulation('sampleSize', v || 0)"
            />
          </div>
          <div class="population-field">
            <label>实际抽取笔数</label>
            <el-input-number
              :model-value="population.actualDrawn"
              size="small"
              :controls="false"
              :min="0"
              :disabled="isReadonly"
              style="width: 120px"
              @change="(v: number) => updatePopulation('actualDrawn', v || 0)"
            />
            <GtIndexChip
              v-if="population.sampleCalcRef"
              :value="population.sampleCalcRef"
              :context-project-id="projectId"
            />
          </div>
        </div>
      </div>

      <!-- ═══════════════════ 特定样本区域 ═══════════════════ -->
      <div class="section-title">特定样本</div>
      <div class="specific-samples-area">
        <div
          v-for="sample in specificSamples"
          :key="sample.id"
          class="specific-sample-row"
        >
          <el-input
            :model-value="sample.description"
            size="small"
            placeholder="项目描述"
            :disabled="isReadonly"
            style="flex: 2"
            @change="(v: string) => updateSpecificSample(sample.id, 'description', v || '')"
          />
          <el-input-number
            :model-value="sample.amount"
            size="small"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            style="width: 130px"
            @change="(v: number) => updateSpecificSample(sample.id, 'amount', v || 0)"
          />
          <el-input
            :model-value="sample.reason"
            size="small"
            placeholder="抽出原因"
            :disabled="isReadonly"
            style="flex: 1"
            @change="(v: string) => updateSpecificSample(sample.id, 'reason', v || '')"
          />
          <el-button
            v-if="!isReadonly"
            type="danger"
            size="small"
            text
            class="delete-btn"
            @click="removeSpecificSample(sample.id)"
          >
            ✕
          </el-button>
        </div>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="addSpecificSample"
        >
          + 添加特定样本
        </el-button>
      </div>

      <!-- ═══════════════════ 分隔线 + 凭证核对明细 ═══════════════════ -->
      <el-divider />
      <div class="section-title">凭证核对明细</div>

      <!-- Toolbar -->
      <div class="table-toolbar">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addVouchingRow">
          + 添加核查项
        </el-button>
      </div>

      <!-- 凭证核对明细 el-table 12列 -->
      <el-table
        :data="vouchingRows"
        border
        size="small"
        :row-class-name="getVouchingRowClass"
        max-height="500"
        class="vouching-table"
        style="width: 100%"
      >
        <!-- 序号（只读自动编号） -->
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }: { row: VouchingRow }">
            <span>{{ row.seq }}</span>
          </template>
        </el-table-column>

        <!-- 票据类型 -->
        <el-table-column label="票据类型" width="130">
          <template #default="{ row }: { row: VouchingRow }">
            <el-select
              :model-value="row.noteType"
              placeholder="选择类型"
              size="small"
              clearable
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => updateVouchingRow(row.id, 'noteType', v || '')"
            >
              <el-option v-for="o in NOTE_TYPE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>

        <!-- 票据号码 -->
        <el-table-column label="票据号码" min-width="140">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.noteNo"
              size="small"
              placeholder="票据号码"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'noteNo', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 出票人 -->
        <el-table-column label="出票人" min-width="100">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.drawer"
              size="small"
              placeholder="出票人"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'drawer', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 承兑人 -->
        <el-table-column label="承兑人" min-width="100">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.acceptor"
              size="small"
              placeholder="承兑人"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'acceptor', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 金额 -->
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input-number
              :model-value="row.amount"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: number) => updateVouchingRow(row.id, 'amount', v || 0)"
            />
          </template>
        </el-table-column>

        <!-- 到期日 -->
        <el-table-column label="到期日" width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-date-picker
              :model-value="row.maturityDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              placeholder="到期日"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => updateVouchingRow(row.id, 'maturityDate', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 存在性验证 -->
        <el-table-column label="存在性验证" width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-tooltip content="验证票据实物是否存在" placement="top">
              <el-select
                :model-value="row.existenceCheck"
                placeholder="—"
                size="small"
                clearable
                :disabled="isReadonly"
                :class="getCheckClass(row.existenceCheck)"
                style="width: 100%"
                @change="(v: string) => updateVouchingRow(row.id, 'existenceCheck', v || '')"
              >
                <el-option v-for="o in EXISTENCE_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 准确性验证 -->
        <el-table-column label="准确性验证" width="130">
          <template #default="{ row }: { row: VouchingRow }">
            <el-tooltip content="验证票据金额与账面记录是否一致" placement="top">
              <el-select
                :model-value="row.accuracyCheck"
                placeholder="—"
                size="small"
                clearable
                :disabled="isReadonly"
                :class="getCheckClass(row.accuracyCheck)"
                style="width: 100%"
                @change="(v: string) => updateVouchingRow(row.id, 'accuracyCheck', v || '')"
              >
                <el-option v-for="o in ACCURACY_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 记录恰当性 -->
        <el-table-column label="记录恰当性" width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-tooltip content="验证票据账务处理是否恰当" placement="top">
              <el-select
                :model-value="row.appropriatenessCheck"
                placeholder="—"
                size="small"
                clearable
                :disabled="isReadonly"
                :class="getCheckClass(row.appropriatenessCheck)"
                style="width: 100%"
                @change="(v: string) => updateVouchingRow(row.id, 'appropriatenessCheck', v || '')"
              >
                <el-option v-for="o in APPROPRIATENESS_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'remark', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 索引号 -->
        <el-table-column label="索引号" width="130">
          <template #default="{ row }: { row: VouchingRow }">
            <div class="index-cell">
              <el-input
                :model-value="row.indexRef"
                size="small"
                placeholder="索引号"
                :disabled="isReadonly"
                @change="(v: string) => updateVouchingRow(row.id, 'indexRef', v || '')"
              />
              <GtIndexChip
                v-if="row.indexRef"
                :value="row.indexRef"
                :context-project-id="projectId"
              />
            </div>
          </template>
        </el-table-column>

        <!-- 操作列：删除 -->
        <el-table-column label="" width="50" fixed="right">
          <template #default="{ row }: { row: VouchingRow }">
            <el-popconfirm
              title="确定删除该行？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="removeVouchingRow(row.id)"
            >
              <template #reference>
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  size="small"
                  text
                  class="delete-btn"
                >
                  ✕
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- ═══════════════════ 核对结果区 ═══════════════════ -->
      <div class="summary-row">
        <span class="summary-label">核查笔数 (G32)：</span>
        <span class="summary-value">{{ checkedCount }}</span>
        <span class="summary-separator">|</span>
        <span class="summary-label">核查金额合计 (H32)：</span>
        <span class="summary-value" v-html="fmtAmount(checkedAmountTotal)" />
      </div>

      <!-- ═══════════════════ 例外汇总区 E48-G50 ═══════════════════ -->
      <div class="section-title">例外汇总</div>
      <table class="recon-table">
        <thead>
          <tr>
            <th>例外类别</th>
            <th>例外笔数</th>
            <th>例外金额</th>
            <th>占比</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in exceptionSummary"
            :key="'exc-' + idx"
            :class="{ 'exception-rate-exceed': row.rate > tolerableErrorRate }"
          >
            <td>{{ row.category }}</td>
            <td class="recon-num">{{ row.count }}</td>
            <td class="recon-num" v-html="fmtAmount(row.amount)" />
            <td
              class="recon-num"
              :class="{ 'rate-exceed': row.rate > tolerableErrorRate }"
            >
              {{ fmtPercent(row.rate) }}
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 例外超标预警 -->
      <el-tag
        v-if="hasExceedingException"
        type="danger"
        size="large"
        effect="light"
        class="exception-warning-tag"
      >
        ⚠️ 例外率超标，请考虑扩大样本量
      </el-tag>

      <!-- 可容忍误差率设置 -->
      <div class="tolerable-rate-area">
        <label>可容忍误差率：</label>
        <el-input-number
          :model-value="tolerableErrorRate * 100"
          size="small"
          :controls="true"
          :min="0"
          :max="100"
          :precision="1"
          :step="1"
          :disabled="isReadonly"
          style="width: 110px"
          @change="(v: number) => updateTolerableErrorRate((v || 5) / 100)"
        />
        <span class="field-hint">%</span>
      </div>

      <!-- ═══════════════════ 测试结论 ═══════════════════ -->
      <div class="section-title">测试结论</div>
      <el-select
        :model-value="testConclusion"
        placeholder="选择测试结论"
        size="default"
        clearable
        :disabled="isReadonly"
        style="width: 300px; margin-bottom: 16px"
        @change="(v: string) => updateTestConclusion(v || '')"
      >
        <el-option v-for="o in TEST_CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
      </el-select>

      <!-- ═══════════════════ 审计说明 ═══════════════════ -->
      <div class="section-title">审计说明</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditNote"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditNote(v || '')"
        />
        <div class="note-actions">
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-sampling-note')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- ═══════════════════ 审计结论 ═══════════════════ -->
      <div class="section-title">审计结论</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditConclusion"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditConclusion(v || '')"
        />
        <div class="note-actions">
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-sampling-conclusion')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- ═══════════════════ 编制提示 ═══════════════════ -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
    </template>
  </div>
</template>

<style scoped>
.d1-tab-sampling-vouching {
  padding: 12px;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective p {
  margin: 0 0 4px;
  font-size: 13px;
  line-height: 1.6;
}

/* ─── 抽样总体定义区 ─── */
.population-area {
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 16px;
}

.population-field {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.population-field.full-width {
  flex-direction: column;
  align-items: flex-start;
}

.population-field label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
  min-width: 110px;
}

.population-field.full-width label {
  min-width: auto;
  margin-bottom: 4px;
}

.population-field.full-width .el-textarea {
  width: 100%;
}

.population-numbers {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
}

.field-hint {
  font-size: 12px;
  color: #909399;
}

/* ─── 特定样本区域 ─── */
.specific-samples-area {
  margin-bottom: 16px;
}

.specific-sample-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

/* ─── 工具栏 ─── */
.table-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

/* ─── 凭证核对明细表 ─── */
.vouching-table {
  margin-bottom: 12px;
}

/* 例外项行浅红色背景 */
:deep(.el-table .exception-row td) {
  background-color: #fef0f0 !important;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 验证结果颜色编码 */
:deep(.check-positive .el-input__inner),
:deep(.check-positive .el-select__placeholder) {
  color: #67c23a !important;
}

:deep(.check-negative .el-input__inner),
:deep(.check-negative .el-select__placeholder) {
  color: #f56c6c !important;
}

/* ─── 合计行/核对结果区 ─── */
.summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 16px;
}

.summary-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.summary-value {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
}

.summary-separator {
  color: #c0c4cc;
  margin: 0 8px;
}

/* ─── 段落标题 ─── */
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 18px 0 10px;
}

/* ─── 例外汇总表格 ─── */
.recon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 16px;
}

.recon-table th,
.recon-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  vertical-align: middle;
}

.recon-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.recon-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 例外率超标行 */
.exception-rate-exceed {
  background-color: #fef0f0;
}

.rate-exceed {
  color: #f56c6c !important;
  font-weight: 600;
}

/* 例外超标预警标签 */
.exception-warning-tag {
  margin-bottom: 16px;
  font-size: 13px;
}

/* ─── 可容忍误差率 ─── */
.tolerable-rate-area {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #606266;
}

.tolerable-rate-area label {
  font-weight: 500;
}

/* ─── 索引号单元格 ─── */
.index-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.index-cell .el-input {
  flex: 1;
}

/* ─── 删除按钮 ─── */
.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

/* ─── 审计说明/结论 ─── */
.note-section {
  margin-bottom: 8px;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

/* ─── 编制提示折叠区 ─── */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
