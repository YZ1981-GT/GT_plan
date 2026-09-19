<template>
  <div class="h2-tab-analysis">
    <!-- 一、审计目标（对齐致同模板） -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>资产负债表中记录的在建工程是存在的，且已记录于恰当的账户；</li>
        <li>所有应记录的在建工程均已记录，所有应当包括在财务报表中的相关披露均已包括。</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-4" :context-project-id="projectId" /></span>
        <GtIndexChip value="H2-2" label="← H2-2明细" />
        <GtIndexChip value="H2-10" label="→ H2-10利息" />
        <GtIndexChip value="H2-15" label="→ H2-15减值" />
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">指标 {{ state.indicatorRows.value.length }}</el-tag>
        <el-tag v-if="state.abnormalIndicators.value.length" size="small" type="danger">
          异常 {{ state.abnormalIndicators.value.length }}
        </el-tag>
        <el-tag size="small" type="info">工程 {{ state.progressRows.value.length }}</el-tag>
        <el-button size="small" type="default" link @click="openReview('H2-4')">💬 复核</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        编制逻辑：先做<strong>指标分析性程序</strong>（本期 vs 上期，识别需追加程序的领域）→
        再按工程做<strong>完工进度 / 资本化率 / 工期</strong>深挖 →
        异常项跳转 H2-7/H2-10/H2-15 做细节测试。
        变动率绝对值超 {{ state.CHANGE_THRESHOLD_PCT }}% 须填写变动原因；可按行业与风险<strong>动态插行</strong>补充指标。
      </p>
    </div>

    <!-- 二、审计过程 — 指标分析（Excel 核心表） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、审计过程 — 指标分析</span>
          <div class="section-header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              :loading="aiSuggestLoading"
              @click="handleAiSuggest"
            >
              <el-icon><MagicStick /></el-icon> AI 建议新增指标
            </el-button>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              :loading="aiReasonLoading"
              @click="handleAiFillReasons"
            >
              <el-icon><MagicStick /></el-icon> AI 填充变动原因
            </el-button>
            <el-button size="small" circle @click="openReview('H2-4-indicators')">💬</el-button>
          </div>
        </div>
      </template>

      <!-- 外部取数输入 -->
      <div class="ratio-inputs">
        <div class="year-row">
          <label>本期年度
            <el-input v-model="localYearCurrent" size="small" placeholder="如 2025"
              :disabled="isReadonly" @change="onYear('yearCurrent', localYearCurrent)" />
          </label>
          <label>上期年度
            <el-input v-model="localYearPrior" size="small" placeholder="如 2024"
              :disabled="isReadonly" @change="onYear('yearPrior', localYearPrior)" />
          </label>
        </div>
        <div class="input-grid">
          <label>资产总额（本期）
            <el-input-number v-model="localInputs.totalAssetsCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('totalAssetsCurrent', $event)" />
          </label>
          <label>资产总额（上期）
            <el-input-number v-model="localInputs.totalAssetsPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('totalAssetsPrior', $event)" />
          </label>
          <label>在建工程期末（上期）
            <el-input-number v-model="localInputs.cipEndPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('cipEndPrior', $event)" />
          </label>
          <label>减值准备（本期）
            <el-input-number v-model="localInputs.impairmentCurrent" :controls="false" size="small"
              :placeholder="aggImpairmentHint" :disabled="isReadonly"
              @change="onInput('impairmentCurrent', $event)" />
          </label>
          <label>减值准备（上期）
            <el-input-number v-model="localInputs.impairmentPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('impairmentPrior', $event)" />
          </label>
          <label>在建原值（本期，可选）
            <el-input-number v-model="localInputs.cipGrossCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('cipGrossCurrent', $event)" />
          </label>
          <label>在建原值（上期，可选）
            <el-input-number v-model="localInputs.cipGrossPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('cipGrossPrior', $event)" />
          </label>
          <label>利息资本化率%（本期）
            <el-input-number v-model="localInputs.interestCapRateCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('interestCapRateCurrent', $event)" />
          </label>
          <label>利息资本化率%（上期）
            <el-input-number v-model="localInputs.interestCapRatePrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('interestCapRatePrior', $event)" />
          </label>
          <label>实际产出（本期）
            <el-input-number v-model="localInputs.capacityOutputCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('capacityOutputCurrent', $event)" />
          </label>
          <label>设计产能（本期）
            <el-input-number v-model="localInputs.designCapacityCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('designCapacityCurrent', $event)" />
          </label>
          <label>实际产出（上期）
            <el-input-number v-model="localInputs.capacityOutputPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('capacityOutputPrior', $event)" />
          </label>
          <label>设计产能（上期）
            <el-input-number v-model="localInputs.designCapacityPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('designCapacityPrior', $event)" />
          </label>
        </div>
        <div class="fa-summary">
          <span>期末在建 <b class="auto-src">{{ fmtAmt(state.autoAggregates.value.cipEnd) }}</b>（H2-2）</span>
          <span>预算合计 <b>{{ fmtAmt(state.autoAggregates.value.budget) }}</b></span>
          <span>累计投入 <b>{{ fmtAmt(state.autoAggregates.value.accumulated) }}</b></span>
          <span>本期转固 <b>{{ fmtAmt(state.autoAggregates.value.transfer) }}</b></span>
          <span>项目数 <b>{{ state.autoAggregates.value.projectCount }}</b></span>
          <span>超期 <b :class="{ 'error-amount': state.autoAggregates.value.overdueCount > 0 }">{{ state.autoAggregates.value.overdueCount }}</b></span>
        </div>
      </div>

      <el-table :data="state.indicatorRows.value" border stripe size="small" class="analysis-table">
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column label="项目" min-width="220">
          <template #default="{ row }">
            <div class="ratio-name">
              <el-input
                v-if="!row.builtin && !isReadonly"
                :model-value="row.name"
                size="small"
                @change="(v: string) => state.updateCustomManual(row.id, 'name', v)"
              />
              <span v-else>{{ row.name }}</span>
              <el-tooltip :content="row.riskHint" placement="top">
                <span class="hint-dot" :title="row.formulaHint">?</span>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="yearLabelCurrent" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.builtin && !row.autoCurrent && !isReadonly"
              :model-value="row.manualCurrent"
              :controls="false"
              size="small"
              class="cell-num"
              @change="(v: number | null) => state.updateCustomManual(row.id, 'manualCurrent', v)"
            />
            <span v-else :class="['formula-cell', { 'auto-src': row.autoCurrent }]" :title="row.formulaHint">
              {{ fmtIndicator(row.current, row.unit) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="yearLabelPrior" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.builtin && !row.autoPrior && !isReadonly"
              :model-value="row.manualPrior"
              :controls="false"
              size="small"
              class="cell-num"
              @change="(v: number | null) => state.updateCustomManual(row.id, 'manualPrior', v)"
            />
            <span v-else :class="['formula-cell', { 'auto-src': row.autoPrior }]" :title="row.formulaHint">
              {{ fmtIndicator(row.prior, row.unit) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': isAbnormal(row) }]">
              {{ fmtChange(row.changePct) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动原因及合理性解释" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.explanation"
              size="small"
              :placeholder="isAbnormal(row) ? '变动超阈值，须说明…' : '变动原因…'"
              @change="(v: string) => state.setExplanation(row.id, v)"
            />
            <span v-else>{{ row.explanation || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.builtin"
              size="small"
              type="danger"
              link
              @click="state.removeCustomIndicator(row.id)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 动态插行 -->
      <div v-if="!isReadonly" class="insert-bar">
        <el-dropdown trigger="click" @command="onAddFromCatalog">
          <el-button size="small" type="primary" plain>+ 从推荐添加指标</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="s in state.availableSuggestions.value"
                :key="s.id"
                :command="s.id"
              >
                <div class="sug-item">
                  <div class="sug-name">{{ s.name }}</div>
                  <div class="sug-desc">{{ s.scenario }}</div>
                </div>
              </el-dropdown-item>
              <el-dropdown-item v-if="!state.availableSuggestions.value.length" disabled>
                推荐指标已全部添加
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="state.addCustomIndicator()">+ 自定义空白行</el-button>
        <span class="insert-hint">对应 Excel「……」可插行；建议结合行业与风险选用 AI 推荐指标</span>
      </div>

      <!-- AI 建议结果 -->
      <el-alert
        v-if="aiSuggestText"
        type="success"
        :closable="true"
        class="ai-suggest-alert"
        @close="aiSuggestText = ''"
      >
        <template #title>AI 指标建议</template>
        <div class="ai-suggest-body">{{ aiSuggestText }}</div>
        <div v-if="aiSuggestedIds.length" class="ai-suggest-actions">
          <el-button
            v-for="id in aiSuggestedIds"
            :key="id"
            size="small"
            type="primary"
            plain
            :disabled="!state.availableSuggestions.value.some((s) => s.id === id)"
            @click="quickAddSuggested(id)"
          >
            添加：{{ catalogName(id) }}
          </el-button>
        </div>
      </el-alert>

      <el-alert
        v-if="state.abnormalIndicators.value.length"
        type="warning"
        :closable="false"
        show-icon
        class="alert-abnormal"
      >
        <template #title>
          {{ state.abnormalIndicators.value.length }} 项指标变动超 {{ state.CHANGE_THRESHOLD_PCT }}%，请补充原因并视情况扩大测试
        </template>
        <ul class="anomaly-list">
          <li v-for="a in state.abnormalIndicators.value" :key="a.id">
            {{ a.name }}：变动 {{ fmtChange(a.changePct) }}
          </li>
        </ul>
      </el-alert>
    </el-card>

    <!-- 工程进度深挖（产品增强，数据来自 H2-2） -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二（附）、工程进度分析（按项目）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H2-4-progress')">💬</el-button>
          </div>
        </div>
      </template>
      <el-table :data="state.progressRows.value" border stripe size="small" class="analysis-table"
        empty-text="请先在 H2-2 录入明细（自动取数）">
        <el-table-column prop="name" label="工程项目" min-width="140" />
        <el-table-column prop="budget" label="预算(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.budget) }}</span></template>
        </el-table-column>
        <el-table-column prop="accumulated" label="累计投入(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.accumulated) }}</span></template>
        </el-table-column>
        <el-table-column label="完工率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'warning-value': (row.completionRate ?? 0) > 100 }]"
              :title="`=累计投入/预算×100`">
              {{ row.completionRate != null ? row.completionRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="超预算率(%)" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': (row.overBudgetRate ?? 0) > 10 }]"
              :title="`=(累计-预算)/预算×100`">
              {{ row.overBudgetRate != null ? row.overBudgetRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="预警" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="(row.overBudgetRate ?? 0) > 10" type="danger" size="small">超支</el-tag>
            <el-tag v-else-if="(row.completionRate ?? 0) > 100" type="warning" size="small">超进度</el-tag>
            <el-tag v-else type="success" size="small">正常</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>资本化率分析（按项目）</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-10" label="→ H2-10利息" />
          </div>
        </div>
      </template>
      <el-table :data="state.capRateRows.value" border stripe size="small" class="analysis-table"
        empty-text="请先在 H2-2 录入明细">
        <el-table-column prop="name" label="工程项目" min-width="140" />
        <el-table-column prop="interestAmount" label="资本化利息(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.interestAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="cipBalance" label="在建余额(元)" min-width="110" align="right">
          <template #default="{ row }"><span class="amt-cell">{{ fmtAmt(row.cipBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="实际资本化率(%)" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'warning-value': (row.actualCapRate ?? 0) > 8 }]"
              :title="`=利息/余额×100`">
              {{ row.actualCapRate != null ? row.actualCapRate.toFixed(2) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="benchmarkRate" label="基准利率(%)" min-width="100" align="right">
          <template #default="{ row }"><span>{{ row.benchmarkRate?.toFixed(2) ?? '-' }}%</span></template>
        </el-table-column>
        <el-table-column label="偏差" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="Math.abs((row.actualCapRate ?? 0) - (row.benchmarkRate ?? 0)) > 2" type="warning" size="small">偏高</el-tag>
            <el-tag v-else type="info" size="small">合理</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>工期分析（按项目）</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-5" label="→ H2-5转固" />
          </div>
        </div>
      </template>
      <el-table :data="state.durationRows.value" border stripe size="small" class="analysis-table"
        empty-text="请先在 H2-2 录入计划竣工日期">
        <el-table-column prop="name" label="工程项目" min-width="140" />
        <el-table-column prop="startDate" label="开工日期" min-width="100" />
        <el-table-column prop="plannedEnd" label="预计竣工" min-width="100" />
        <el-table-column prop="actualEnd" label="实际竣工" min-width="100" />
        <el-table-column label="超期天数" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.overdueDays > 180 }]">
              {{ row.overdueDays ?? '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.overdueDays > 180" type="danger" size="small">严重延期</el-tag>
            <el-tag v-else-if="row.overdueDays > 0" type="warning" size="small">延期</el-tag>
            <el-tag v-else-if="row.actualEnd" type="success" size="small">按期</el-tag>
            <el-tag v-else type="info" size="small">在建</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>三、审计说明</span>
          <el-button size="small" type="primary" link :loading="aiNoteLoading" :disabled="isReadonly" @click="handleAiNote">
            <el-icon><MagicStick /></el-icon> AI 生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述指标分析程序、数据来源（H2-1/H2-2）、异常指标及工程深挖发现、跟进程序。"
        :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计结论</span>
          <el-button size="small" type="primary" link :loading="aiConclusionLoading" :disabled="isReadonly" @click="handleAiConclusion">
            <el-icon><MagicStick /></el-icon> AI 生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="state.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="分析性程序总体结论：指标/进度/资本化/工期是否合理，是否需追加细节测试…"
        :disabled="isReadonly"
        @blur="state.saveConclusion(state.conclusion.value)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>对齐致同模板：在建工程/资产总额、期末余额、减值÷原值、实际vs预算、利息资本化率、产能利用率</li>
        <li>蓝色数字为自动取数（H2-2）；资产总额、上期余额、产能、资本化率等需手填或从 TB 引入</li>
        <li>|变动率|&gt;{{ state.CHANGE_THRESHOLD_PCT }}% 标红，须在「变动原因」说明合理性</li>
        <li>可用「从推荐添加」或「AI 建议新增指标」按行业/风险插行（对应 Excel「……」）</li>
        <li>工程深挖：完工率超100%/超预算&gt;10%/工期超180天 → 关注减值（H2-15）与转固时点（H2-5）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabAnalysis.vue — H2-4 分析表
 * 对齐致同 Excel：指标 YoY + 动态插行 + AI 建议指标
 * 附：工程进度/资本化率/工期深挖（H2-2 取数）
 */
import { inject, toRef, computed, reactive, ref, watch } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useH2Analysis,
  SUGGESTED_INDICATOR_CATALOG,
  type IndicatorInputs,
  type IndicatorRow,
} from '../../composables/useH2Analysis'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Analysis({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => {
    const existing = props.allResponses.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    props.allResponses.set(itemId, {
      ...existing,
      remark: typeof value === 'string' ? value : JSON.stringify(value),
    })
    saveResponse(itemId, value)
  },
})

const localInputs = reactive<Partial<IndicatorInputs>>({})
const localYearCurrent = ref('')
const localYearPrior = ref('')

watch(
  () => state.indicatorInputs.value,
  (v) => {
    Object.assign(localInputs, v)
    localYearCurrent.value = v.yearCurrent || ''
    localYearPrior.value = v.yearPrior || ''
  },
  { deep: true, immediate: true },
)

const yearLabelCurrent = computed(() =>
  localYearCurrent.value ? `${localYearCurrent.value}年` : '本期',
)
const yearLabelPrior = computed(() =>
  localYearPrior.value ? `${localYearPrior.value}年` : '上期',
)

const aggImpairmentHint = computed(() => {
  const n = state.autoAggregates.value.impairment
  return n ? String(n) : ''
})

function onInput<K extends keyof IndicatorInputs>(key: K, val: IndicatorInputs[K]) {
  state.updateInput(key, val)
}

function onYear(key: 'yearCurrent' | 'yearPrior', val: string) {
  state.updateInput(key, val)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function isAbnormal(row: IndicatorRow): boolean {
  return row.changePct != null && Math.abs(row.changePct) > state.CHANGE_THRESHOLD_PCT
}

function onAddFromCatalog(id: string) {
  if (state.addIndicatorFromCatalog(id)) {
    ElMessage.success('已添加指标')
  } else {
    ElMessage.warning('该指标已存在或无效')
  }
}

function catalogName(id: string): string {
  return SUGGESTED_INDICATOR_CATALOG.find((s) => s.id === id)?.name ?? id
}

function quickAddSuggested(id: string) {
  onAddFromCatalog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtIndicator(val: number | null, unit: IndicatorRow['unit']): string {
  if (val == null) return '—'
  if (unit === 'amount') {
    return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return `${val.toFixed(2)}%`
}

function fmtChange(pct: number | null): string {
  if (pct == null) return '—'
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(2)}%`
}

// ─── AI ──────────────────────────────────────────────────────────────────────

const aiSuggestLoading = ref(false)
const aiReasonLoading = ref(false)
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
const aiSuggestText = ref('')
const aiSuggestedIds = ref<string[]>([])

async function callH2Ai(section: string, existing = ''): Promise<string> {
  const res = await http.post(
    `/api/workpapers/${props.wpId}/h2/ai-generate`,
    {
      section,
      existingContent: existing,
      relatedContext: state.buildAiContext(),
    },
    { _silent: true } as any,
  )
  return res.data?.content || res.data?.data?.content || ''
}

async function handleAiSuggest() {
  if (!props.wpId || props.isReadonly) return
  aiSuggestLoading.value = true
  aiSuggestText.value = ''
  aiSuggestedIds.value = []
  try {
    const text = await callH2Ai('analysis-indicator-suggest')
    if (!text) {
      ElMessage.warning('AI 未返回建议')
      return
    }
    aiSuggestText.value = text
    // 解析候选 id（形如 id: transfer_ratio 或 【transfer_ratio】）
    const ids: string[] = []
    const avail = new Set(state.availableSuggestions.value.map((s) => s.id))
    for (const s of SUGGESTED_INDICATOR_CATALOG) {
      if (avail.has(s.id) && (text.includes(s.id) || text.includes(s.name))) {
        ids.push(s.id)
      }
    }
    aiSuggestedIds.value = ids.slice(0, 5)
    ElMessage.success('已生成指标建议，可一键添加')
  } catch {
    ElMessage.error('AI 建议失败')
  } finally {
    aiSuggestLoading.value = false
  }
}

async function handleAiFillReasons() {
  if (!props.wpId || props.isReadonly) return
  aiReasonLoading.value = true
  try {
    const text = await callH2Ai('analysis-reason')
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    let parsed: Array<{ id?: string; name?: string; explanation?: string }> = []
    try {
      const match = text.match(/\[[\s\S]*\]/)
      if (match) parsed = JSON.parse(match[0])
    } catch { /* ignore */ }
    if (!parsed.length) {
      ElMessage.warning('AI 返回无法解析为指标原因，请手动填写')
      return
    }
    await ElMessageBox.confirm(
      `AI 已为 ${parsed.length} 项指标生成变动原因，是否填入空缺项？`,
      'AI 填充变动原因',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    const map: Record<string, string> = {}
    const rows = state.indicatorRows.value
    for (const item of parsed) {
      const row =
        rows.find((r) => r.id === item.id) ||
        rows.find((r) => item.name && r.name === item.name)
      if (row && item.explanation && !row.explanation) {
        map[row.id] = item.explanation
      }
    }
    if (Object.keys(map).length) {
      state.setExplanationsBulk(map)
      ElMessage.success(`已填入 ${Object.keys(map).length} 项变动原因`)
    } else {
      ElMessage.info('无空缺项需要填入（已有说明的行未覆盖）')
    }
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.error('AI 填充失败')
  } finally {
    aiReasonLoading.value = false
  }
}

async function handleAiNote() {
  if (!props.wpId || props.isReadonly) return
  aiNoteLoading.value = true
  try {
    const text = await callH2Ai('analysis-progress', state.auditNote.value)
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    await ElMessageBox.confirm(
      text.length > 400 ? text.slice(0, 400) + '…' : text,
      'AI 生成 · 审计说明',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    state.saveNote(text)
    ElMessage.success('已生成审计说明')
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.error('AI 生成失败')
  } finally {
    aiNoteLoading.value = false
  }
}

async function handleAiConclusion() {
  if (!props.wpId || props.isReadonly) return
  aiConclusionLoading.value = true
  try {
    const text = await callH2Ai('analysis-conclusion', state.conclusion.value)
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    await ElMessageBox.confirm(
      text.length > 400 ? text.slice(0, 400) + '…' : text,
      'AI 生成 · 审计结论',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    state.saveConclusion(text)
    ElMessage.success('已生成审计结论')
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.error('AI 生成失败')
  } finally {
    aiConclusionLoading.value = false
  }
}
</script>

<style scoped>
.h2-tab-analysis { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; margin-bottom: 4px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.6; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.methodology-context {
  border-left: 3px solid #f0a020; background: #fdf8e8;
  padding: 12px 16px; margin-bottom: 16px; border-radius: 4px; font-size: 12px;
}
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.section-header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.ratio-inputs { margin-bottom: 12px; }
.year-row {
  display: flex; gap: 16px; margin-bottom: 10px; flex-wrap: wrap;
}
.year-row label {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12px; color: var(--el-text-color-secondary); width: 140px;
}
.input-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px 12px; margin-bottom: 10px;
}
.input-grid label {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12px; color: var(--el-text-color-secondary);
}
.input-grid :deep(.el-input-number), .year-row :deep(.el-input) { width: 100%; }
.fa-summary {
  display: flex; flex-wrap: wrap; gap: 12px 20px;
  font-size: 12px; color: var(--el-text-color-regular);
  padding: 8px 10px; background: var(--el-fill-color-lighter); border-radius: 4px;
}
.analysis-table { font-size: var(--wp-font-size, 13px); }
.ratio-name { display: flex; align-items: center; gap: 6px; }
.hint-dot {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0;
  font-size: 10px; background: var(--el-color-info-light-7); cursor: help;
}
.amt-cell { font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color); cursor: help;
  font-variant-numeric: tabular-nums;
}
.auto-src { color: var(--el-color-primary); }
.warning-value { color: var(--el-color-warning); font-weight: 600; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.cell-num { width: 100%; }
.insert-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-top: 12px;
}
.insert-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.sug-item { max-width: 360px; }
.sug-name { font-size: 13px; }
.sug-desc { font-size: 11px; color: var(--el-text-color-secondary); white-space: normal; }
.ai-suggest-alert { margin-top: 12px; }
.ai-suggest-body { white-space: pre-wrap; font-size: 12px; line-height: 1.6; margin-bottom: 8px; }
.ai-suggest-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.alert-abnormal { margin-top: 12px; }
.anomaly-list { margin: 6px 0 0; padding-left: 18px; font-size: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
