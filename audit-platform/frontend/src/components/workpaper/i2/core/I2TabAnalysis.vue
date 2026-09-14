<template>
  <div class="i2-analysis">
    <div class="section-header">
      <span class="section-title">I2-5 实质性分析</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <p class="obj-text">{{ I2_ANALYSIS_OBJECTIVES[0] }}</p>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        （一）构成分析（结构比/占收入比/增长）→（二）同行业指标 →（三）人均同期 →（四）人均同行 →
        结构化说明异常原因 → 结论。分母为 0 时显示「—」避免 #DIV/0!。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-5" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">构成 {{ bundle.compositionRows.length }} 项</el-tag>
        <el-tag v-if="anomalySummary.compositionAnomalyCount" size="small" type="danger">
          构成异常 {{ anomalySummary.compositionAnomalyCount }}
        </el-tag>
        <el-tag v-if="anomalySummary.missingRevenue" size="small" type="warning">未填主营收入</el-tag>
        <el-tag v-if="anomalySummary.peerGapCount" size="small" type="warning">
          同行差异 {{ anomalySummary.peerGapCount }}
        </el-tag>
        <el-button size="small" :disabled="isReadonly" @click="handleSeedI6">从 I6-2 带入构成</el-button>
        <el-button size="small" :disabled="isReadonly || !props.projectId" @click="handleFetchRevenue">从 TB 带入收入</el-button>
        <el-button size="small" @click="handleExportExcel">导出 Excel</el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
      </div>
    </div>

    <!-- （一）构成分析 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、审计过程 —（一）研发费用构成分析表</span>
          <div class="title-actions">
            <span class="meta-label">主营业务收入</span>
            <el-input-number
              :model-value="bundle.compositionMeta.revenueCurrent"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              placeholder="本期"
              @change="(v: number | undefined) => updateCompositionMeta('revenueCurrent', v ?? 0)"
            />
            <el-input-number
              :model-value="bundle.compositionMeta.revenuePrior"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              placeholder="上年同期"
              @change="(v: number | undefined) => updateCompositionMeta('revenuePrior', v ?? 0)"
            />
            <el-tooltip content="增长比例/结构比变动超此阈值判定异常，默认30%" placement="top">
              <span class="meta-label">增长阈值%</span>
            </el-tooltip>
            <el-input-number
              :model-value="thresholdPct.growth"
              size="small"
              :controls="false"
              :min="1"
              :max="200"
              style="width:84px"
              :disabled="isReadonly"
              @change="(v: number | undefined) => onThresholdPctChange('growthThreshold', v)"
            />
            <el-tooltip content="占收入比变动超此阈值（百分点）判定异常，默认2个百分点" placement="top">
              <span class="meta-label">占收入比阈值pt</span>
            </el-tooltip>
            <el-input-number
              :model-value="thresholdPct.revRatioDelta"
              size="small"
              :controls="false"
              :min="0.1"
              :max="50"
              :step="0.1"
              style="width:84px"
              :disabled="isReadonly"
              @change="(v: number | undefined) => onThresholdPctChange('revRatioDeltaThreshold', v)"
            />
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addCompositionRow()">+ 项目</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="compositionDisplayRows"
        border
        size="small"
        max-height="420"
        :row-class-name="compositionRowClass"
      >
        <el-table-column prop="itemName" label="项目" min-width="120" fixed>
          <template #default="{ row }">
            <template v-if="row._isTotal || row._isRev">
              <b>{{ row.itemName }}</b>
            </template>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.itemName"
              size="small"
              @update:model-value="(v: string) => onCompField(row, 'itemName', v)"
            />
            <span v-else>{{ row.itemName }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期合计" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row._isTotal && !row._isRev && !isReadonly"
              :model-value="row.currentAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @change="(v: number | undefined) => onCompField(row, 'currentAmount', v ?? 0)"
            />
            <span v-else :class="{ 'total-text': row._isTotal || row._isRev }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结构比" width="80" align="right">
          <template #header>
            <el-tooltip content="=本期金额/本期合计；分母为0显示—" placement="top">
              <span class="formula-header">结构比</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtPct(row.currentStructure) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占主营收入比" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtPct(row.currentRevRatio) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="上年同期" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row._isTotal && !row._isRev && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @change="(v: number | undefined) => onCompField(row, 'priorAmount', v ?? 0)"
            />
            <span v-else :class="{ 'total-text': row._isTotal || row._isRev }">{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结构比" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtPct(row.priorStructure) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占主营收入比" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtPct(row.priorRevRatio) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="增长比例" width="90" align="right">
          <template #header>
            <el-tooltip content="=(本期−上年同期)/|上年同期|；上年为0显示—" placement="top">
              <span class="formula-header">增长比例</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': row.isAnomaly }">{{ fmtPct(row.growthRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占收入比变动" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': row.isAnomaly }">{{ fmtPctPts(row.revRatioChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预算金额" width="110" align="right">
          <template #header>
            <el-tooltip content="本期预算金额；填写后自动计算预算差异/差异率" placement="top">
              <span class="formula-header">预算金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!row._isTotal && !row._isRev && !isReadonly"
              :model-value="row.budgetAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @change="(v: number | undefined) => onCompField(row, 'budgetAmount', v ?? 0)"
            />
            <span v-else :class="{ 'total-text': row._isTotal || row._isRev }">{{ fmtAmt(row.budgetAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预算差异" width="100" align="right">
          <template #header>
            <el-tooltip content="=本期金额−预算金额；预算未填不计算" placement="top">
              <span class="formula-header">预算差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': row.isAnomaly }">{{ fmtAmt(row.budgetVariance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预算差异率" width="90" align="right">
          <template #header>
            <el-tooltip content="=预算差异/预算金额；超增长阈值判定异常" placement="top">
              <span class="formula-header">预算差异率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': row.isAnomaly }">{{ fmtPct(row.budgetVarianceRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动分析" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!row._isTotal && !row._isRev && !isReadonly"
              :model-value="row.varianceAnalysis"
              size="small"
              placeholder="变动原因"
              @update:model-value="(v: string) => onCompField(row, 'varianceAnalysis', v)"
            />
            <span v-else>{{ row.varianceAnalysis || '' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
          <template #default="{ row }">
            <el-button v-if="!row._isTotal && !row._isRev" size="small" type="danger" text @click="onCompRemove(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- （二）同行业 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>（二）费用指标分析表（与同行业数据比较）</span>
          <el-button size="small" plain :disabled="isReadonly" @click="addPeerIndicator()">+ 指标</el-button>
        </div>
      </template>
      <el-table :data="bundle.peerIndicators" border size="small">
        <el-table-column prop="indicator" label="指标" min-width="180">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indicator"
              size="small"
              @update:model-value="(v: string) => updatePeerIndicator($index, 'indicator', v)"
            />
            <span v-else>{{ row.indicator }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtPct(row.current) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同行业公司A" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.peerA ?? undefined"
              size="small"
              :controls="false"
              :step="0.01"
              style="width:100%"
              @change="(v: number | undefined) => updatePeerIndicator($index, 'peerA', v ?? null)"
            />
            <span v-else>{{ fmtPct(row.peerA) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同行业公司B" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.peerB ?? undefined"
              size="small"
              :controls="false"
              :step="0.01"
              style="width:100%"
              @change="(v: number | undefined) => updatePeerIndicator($index, 'peerB', v ?? null)"
            />
            <span v-else>{{ fmtPct(row.peerB) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同行业公司C" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.peerC ?? undefined"
              size="small"
              :controls="false"
              :step="0.01"
              style="width:100%"
              @change="(v: number | undefined) => updatePeerIndicator($index, 'peerC', v ?? null)"
            />
            <span v-else>{{ fmtPct(row.peerC) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="比较分析" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.analysis"
              size="small"
              @update:model-value="(v: string) => updatePeerIndicator($index, 'analysis', v)"
            />
            <span v-else>{{ row.analysis || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint-text">同行公司 A/B/C 请录入比率小数（如 0.08 表示 8%）。本期值由构成合计÷主营收入自动带出。</p>
    </el-card>

    <!-- （三）人均同期 -->
    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title-text">（三）人均费用指标同期对比分析表</span></template>
      <el-form label-width="120px" size="small" class="pcap-form">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="研发人员人数(本期)">
              <el-input-number
                :model-value="bundle.perCapitaYoY.headcountCurrent"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updatePerCapitaYoY('headcountCurrent', v ?? 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="人数(上年)">
              <el-input-number
                :model-value="bundle.perCapitaYoY.headcountPrior"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updatePerCapitaYoY('headcountPrior', v ?? 0)"
              />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="人均薪酬(本期)">
              <span class="formula-cell">{{ fmtAmt(bundle.perCapitaYoY.avgSalaryCurrent) }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="人均薪酬变动">
              <span class="formula-cell">{{ fmtPct(bundle.perCapitaYoY.avgSalaryGrowth) }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="人均研发经费(本期)">
              <span class="formula-cell">{{ fmtAmt(bundle.perCapitaYoY.avgRdCurrent) }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="人均经费变动">
              <span class="formula-cell">{{ fmtPct(bundle.perCapitaYoY.avgRdGrowth) }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="人均材料(本期)">
              <span class="formula-cell">{{ fmtAmt(bundle.perCapitaYoY.avgMaterialCurrent) }}</span>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="人均材料变动">
              <span class="formula-cell">{{ fmtPct(bundle.perCapitaYoY.avgMaterialGrowth) }}</span>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="对比分析">
          <el-input
            type="textarea"
            :model-value="bundle.perCapitaYoY.analysis"
            :disabled="isReadonly"
            :autosize="{ minRows: 2 }"
            @change="(v: string) => updatePerCapitaYoY('analysis', v)"
          />
        </el-form-item>
      </el-form>
      <p class="hint-text">人工费/材料费/研发经费总额由构成表自动同步；请填写研发人员人数以计算人均指标。</p>
    </el-card>

    <!-- （四）人均同行 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>（四）人均费用指标同行业对比分析表</span>
          <el-button size="small" plain :disabled="isReadonly" @click="addPerCapitaPeer()">+ 可比公司</el-button>
        </div>
      </template>
      <el-table :data="bundle.perCapitaPeers" border size="small">
        <el-table-column prop="companyName" label="公司名称" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly && !row.isSelf"
              :model-value="row.companyName"
              size="small"
              @update:model-value="(v: string) => updatePerCapitaPeer($index, 'companyName', v)"
            />
            <b v-else>{{ row.companyName || '本公司' }}</b>
          </template>
        </el-table-column>
        <el-table-column label="研发人员总数" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row.isSelf"
              :model-value="row.headcount"
              size="small"
              :controls="false"
              style="width:100%"
              @change="(v: number | undefined) => updatePerCapitaPeer($index, 'headcount', v ?? 0)"
            />
            <span v-else>{{ row.headcount || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="人均薪酬" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row.isSelf"
              :model-value="row.avgSalary"
              size="small"
              :controls="false"
              style="width:100%"
              @change="(v: number | undefined) => updatePerCapitaPeer($index, 'avgSalary', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.avgSalary) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="人均研发经费" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row.isSelf"
              :model-value="row.avgRdExpense"
              size="small"
              :controls="false"
              style="width:100%"
              @change="(v: number | undefined) => updatePerCapitaPeer($index, 'avgRdExpense', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.avgRdExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="人均材料" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row.isSelf"
              :model-value="row.avgMaterial"
              size="small"
              :controls="false"
              style="width:100%"
              @change="(v: number | undefined) => updatePerCapitaPeer($index, 'avgMaterial', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.avgMaterial) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同行业对比分析" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.analysis"
              size="small"
              @update:model-value="(v: string) => updatePerCapitaPeer($index, 'analysis', v)"
            />
            <span v-else>{{ row.analysis || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、结构化说明 -->
    <el-card shadow="never" class="block-card">
      <template #header><span class="block-title-text">三、审计说明</span></template>
      <div v-for="(p, i) in I2_ANALYSIS_NOTE_PROMPTS" :key="p.key" class="note-block">
        <div class="note-label">{{ i + 1 }}. {{ p.label }}</div>
        <el-input
          type="textarea"
          :model-value="bundle.structuredNotes[p.key]"
          :disabled="isReadonly"
          :autosize="{ minRows: 2 }"
          placeholder="a. …&#10;b. …"
          @change="(v: string) => updateStructuredNote(p.key, v)"
        />
      </div>
    </el-card>

    <!-- 四、结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="conclusion-header">
          <span>四、审计结论</span>
          <el-button v-if="!isReadonly" size="small" text type="primary" @click="fillAutoConclusion">生成草稿</el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="经实质性分析，研发费用…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <!-- （五）开发支出项目波动 — Spec 兼容 -->
    <details class="legacy-block">
      <summary>（五）开发支出项目波动分析（资本化余额，可选）</summary>
      <el-alert
        v-if="hasAnomalies"
        type="error"
        :closable="false"
        show-icon
        class="mb-8"
        :title="`发现 ${anomalyRows.length} 个项目差异超过重要性水平`"
      />
      <el-table :data="projectDisplayRows" border size="small" :row-class-name="projectRowClass" max-height="320">
        <el-table-column prop="projectName" label="项目" min-width="140" />
        <el-table-column prop="endAmount" label="期末" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.endAmount) }}</template>
        </el-table-column>
        <el-table-column label="同比变动率" width="100" align="right">
          <template #default="{ row }">{{ fmtPct(row.changeRate) }}</template>
        </el-table-column>
        <el-table-column prop="variance" label="差异" width="110" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': row.exceedThreshold }">{{ fmtAmt(row.variance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="anomalyReason" label="异常原因" min-width="140" />
      </el-table>
      <div class="table-actions">
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddProject">+ 项目</el-button>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useI2Analysis } from '../../composables/useI2Analysis'
import { exportMultiSheetData } from '@/composables/useExcelIO'
import {
  I2_ANALYSIS_OBJECTIVES,
  I2_ANALYSIS_NOTE_PROMPTS,
  I2_ANALYSIS_GROWTH_THRESHOLD,
  I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
} from '../../composables/i2AnalysisModel'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => Boolean(props.isReadonly))

const allResponsesRef = computed(() => props.allResponses)

const {
  bundle,
  compositionSummary,
  anomalySummary,
  updateCompositionMeta,
  updateCompositionField,
  addCompositionRow,
  removeCompositionRow,
  updateThreshold,
  fetchRevenueFromTb,
  updatePeerIndicator,
  addPeerIndicator,
  updatePerCapitaYoY,
  updatePerCapitaPeer,
  addPerCapitaPeer,
  updateStructuredNote,
  seedFromI6,
  buildConclusionDraft,
  rows,
  totalRow,
  anomalyRows,
  hasAnomalies,
  addRow,
  save,
} = useI2Analysis({
  allResponses: allResponsesRef,
  saveResponses: props.saveResponse,
})

const thresholdPct = computed(() => ({
  growth: Math.round((bundle.value.compositionMeta.growthThreshold ?? I2_ANALYSIS_GROWTH_THRESHOLD) * 100),
  revRatioDelta: Math.round((bundle.value.compositionMeta.revRatioDeltaThreshold ?? I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD) * 1000) / 10,
}))

function onThresholdPctChange(field: 'growthThreshold' | 'revRatioDeltaThreshold', pctValue: number | undefined) {
  const pct = pctValue ?? (field === 'growthThreshold' ? 30 : 2)
  updateThreshold(field, pct / 100)
}

async function handleFetchRevenue() {
  const r = await fetchRevenueFromTb(props.projectId)
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

async function handleExportExcel() {
  const t = compositionSummary.value
  const fmt2 = (v: number | null | undefined) => (v == null ? '' : Number(v.toFixed(2)))
  const fmtPctVal = (v: number | null | undefined) => (v == null ? '' : Number((v * 100).toFixed(2)))

  const compositionData = bundle.value.compositionRows.map((r) => ({
    itemName: r.itemName,
    currentAmount: fmt2(r.currentAmount),
    currentStructure: fmtPctVal(r.currentStructure),
    currentRevRatio: fmtPctVal(r.currentRevRatio),
    priorAmount: fmt2(r.priorAmount),
    priorStructure: fmtPctVal(r.priorStructure),
    priorRevRatio: fmtPctVal(r.priorRevRatio),
    growthRate: fmtPctVal(r.growthRate),
    revRatioChange: fmtPctVal(r.revRatioChange),
    budgetAmount: fmt2(r.budgetAmount),
    budgetVariance: fmt2(r.budgetVariance),
    budgetVarianceRate: fmtPctVal(r.budgetVarianceRate),
    varianceAnalysis: r.varianceAnalysis,
  }))
  compositionData.push({
    itemName: '合计',
    currentAmount: fmt2(t.totalCurrent),
    currentStructure: '' as any,
    currentRevRatio: fmtPctVal(t.currentRevRatio),
    priorAmount: fmt2(t.totalPrior),
    priorStructure: '' as any,
    priorRevRatio: fmtPctVal(t.priorRevRatio),
    growthRate: fmtPctVal(t.growthRate),
    revRatioChange: fmtPctVal(t.revRatioChange),
    budgetAmount: fmt2(t.totalBudget),
    budgetVariance: fmt2(t.budgetVariance),
    budgetVarianceRate: fmtPctVal(t.budgetVarianceRate),
    varianceAnalysis: '',
  })

  const peerData = bundle.value.peerIndicators.map((p) => ({
    indicator: p.indicator,
    current: fmtPctVal(p.current),
    peerA: fmtPctVal(p.peerA),
    peerB: fmtPctVal(p.peerB),
    peerC: fmtPctVal(p.peerC),
    analysis: p.analysis,
  }))

  const py = bundle.value.perCapitaYoY
  const perCapitaYoYData = [{
    headcountCurrent: py.headcountCurrent,
    headcountPrior: py.headcountPrior,
    avgSalaryCurrent: fmt2(py.avgSalaryCurrent),
    avgSalaryPrior: fmt2(py.avgSalaryPrior),
    avgSalaryGrowth: fmtPctVal(py.avgSalaryGrowth),
    avgRdCurrent: fmt2(py.avgRdCurrent),
    avgRdPrior: fmt2(py.avgRdPrior),
    avgRdGrowth: fmtPctVal(py.avgRdGrowth),
    avgMaterialCurrent: fmt2(py.avgMaterialCurrent),
    avgMaterialPrior: fmt2(py.avgMaterialPrior),
    avgMaterialGrowth: fmtPctVal(py.avgMaterialGrowth),
    analysis: py.analysis,
  }]

  const perCapitaPeerData = bundle.value.perCapitaPeers.map((p) => ({
    companyName: p.companyName,
    headcount: p.headcount,
    avgSalary: fmt2(p.avgSalary),
    avgRdExpense: fmt2(p.avgRdExpense),
    avgMaterial: fmt2(p.avgMaterial),
    analysis: p.analysis,
  }))

  const noteData = I2_ANALYSIS_NOTE_PROMPTS.map((p) => ({
    label: p.label,
    content: bundle.value.structuredNotes[p.key],
  }))

  await exportMultiSheetData({
    fileName: `I2-5研发费用实质性分析_${props.projectId || ''}.xlsx`,
    sheets: [
      {
        sheetName: '构成',
        columns: [
          { key: 'itemName', header: '项目' },
          { key: 'currentAmount', header: '本期金额' },
          { key: 'currentStructure', header: '本期结构比%' },
          { key: 'currentRevRatio', header: '本期占收入比%' },
          { key: 'priorAmount', header: '上年同期' },
          { key: 'priorStructure', header: '上年结构比%' },
          { key: 'priorRevRatio', header: '上年占收入比%' },
          { key: 'growthRate', header: '增长比例%' },
          { key: 'revRatioChange', header: '占收入比变动pt' },
          { key: 'budgetAmount', header: '预算金额' },
          { key: 'budgetVariance', header: '预算差异' },
          { key: 'budgetVarianceRate', header: '预算差异率%' },
          { key: 'varianceAnalysis', header: '变动分析' },
        ],
        data: compositionData,
      },
      {
        sheetName: '同行',
        columns: [
          { key: 'indicator', header: '指标' },
          { key: 'current', header: '本期%' },
          { key: 'peerA', header: '同行业公司A%' },
          { key: 'peerB', header: '同行业公司B%' },
          { key: 'peerC', header: '同行业公司C%' },
          { key: 'analysis', header: '比较分析' },
        ],
        data: peerData,
      },
      {
        sheetName: '人均同期',
        columns: [
          { key: 'headcountCurrent', header: '人数(本期)' },
          { key: 'headcountPrior', header: '人数(上年)' },
          { key: 'avgSalaryCurrent', header: '人均薪酬(本期)' },
          { key: 'avgSalaryPrior', header: '人均薪酬(上年)' },
          { key: 'avgSalaryGrowth', header: '人均薪酬变动%' },
          { key: 'avgRdCurrent', header: '人均研发经费(本期)' },
          { key: 'avgRdPrior', header: '人均研发经费(上年)' },
          { key: 'avgRdGrowth', header: '人均经费变动%' },
          { key: 'avgMaterialCurrent', header: '人均材料(本期)' },
          { key: 'avgMaterialPrior', header: '人均材料(上年)' },
          { key: 'avgMaterialGrowth', header: '人均材料变动%' },
          { key: 'analysis', header: '对比分析' },
        ],
        data: perCapitaYoYData,
      },
      {
        sheetName: '人均同行',
        columns: [
          { key: 'companyName', header: '公司名称' },
          { key: 'headcount', header: '研发人员总数' },
          { key: 'avgSalary', header: '人均薪酬' },
          { key: 'avgRdExpense', header: '人均研发经费' },
          { key: 'avgMaterial', header: '人均材料' },
          { key: 'analysis', header: '同行业对比分析' },
        ],
        data: perCapitaPeerData,
      },
      {
        sheetName: '说明',
        columns: [
          { key: 'label', header: '题干' },
          { key: 'content', header: '说明内容' },
        ],
        data: noteData,
      },
    ],
  })
}

const AUDIT_CONCLUSION_KEY = 'I2-5-audit-conclusion'
const auditConclusion = ref('')

function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}
function hydrateAudit() {
  auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY)
}
function saveAuditConclusion(val: string) {
  auditConclusion.value = val
  void props.saveResponse('I2-5', { [AUDIT_CONCLUSION_KEY]: val })
}
watch(() => props.allResponses, hydrateAudit, { immediate: true })
onMounted(hydrateAudit)

const compositionDisplayRows = computed(() => {
  const data = bundle.value.compositionRows.map((r, idx) => ({
    ...r,
    _dataIndex: idx,
    _isTotal: false,
    _isRev: false,
  }))
  const t = compositionSummary.value
  data.push({
    rowId: 'total',
    itemName: '合计',
    currentAmount: t.totalCurrent,
    priorAmount: t.totalPrior,
    budgetAmount: t.totalBudget,
    budgetVariance: t.budgetVariance,
    budgetVarianceRate: t.budgetVarianceRate,
    varianceAnalysis: '',
    currentStructure: t.totalCurrent > 0 ? 1 : null,
    priorStructure: t.totalPrior > 0 ? 1 : null,
    currentRevRatio: t.currentRevRatio,
    priorRevRatio: t.priorRevRatio,
    growthRate: t.growthRate,
    revRatioChange: t.revRatioChange,
    isAnomaly: false,
    _dataIndex: -1,
    _isTotal: true,
    _isRev: false,
  } as any)
  data.push({
    rowId: 'revenue',
    itemName: '主营业务收入',
    currentAmount: bundle.value.compositionMeta.revenueCurrent,
    priorAmount: bundle.value.compositionMeta.revenuePrior,
    varianceAnalysis: '',
    currentStructure: null,
    priorStructure: null,
    currentRevRatio: null,
    priorRevRatio: null,
    growthRate: null,
    revRatioChange: null,
    isAnomaly: false,
    _dataIndex: -1,
    _isTotal: false,
    _isRev: true,
  } as any)
  data.push({
    rowId: 'rd-ratio',
    itemName: '研发费用占主营业务收入比',
    currentAmount: 0,
    priorAmount: 0,
    varianceAnalysis: '',
    currentStructure: null,
    priorStructure: null,
    currentRevRatio: t.rdToRevenueCurrent,
    priorRevRatio: t.rdToRevenuePrior,
    growthRate: null,
    revRatioChange: t.revRatioChange,
    isAnomaly: false,
    _dataIndex: -1,
    _isTotal: false,
    _isRev: true,
  } as any)
  return data
})

function onCompField(row: any, field: string, value: any) {
  if (row._dataIndex == null || row._dataIndex < 0) return
  updateCompositionField(row._dataIndex, field as any, value)
}

function onCompRemove(row: any) {
  if (row._dataIndex == null || row._dataIndex < 0) return
  removeCompositionRow(row._dataIndex)
}

const projectDisplayRows = computed(() => [
  ...rows.value.map((r) => ({ ...r, _isTotal: false })),
  { ...totalRow.value, _isTotal: true },
])

function compositionRowClass({ row }: { row: any }) {
  if (row._isTotal) return 'total-row'
  if (row._isRev) return 'rev-row'
  if (row.isAnomaly) return 'anomaly-row'
  return ''
}

function projectRowClass({ row }: { row: any }) {
  if (row._isTotal) return 'total-row'
  if (row.exceedThreshold) return 'anomaly-row'
  return ''
}

function handleSeedI6() {
  const r = seedFromI6()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

async function handleSave() {
  await save()
  emit('save')
  ElMessage.success('实质性分析已保存')
}

function fillAutoConclusion() {
  const draft = buildConclusionDraft()
  auditConclusion.value = draft
  saveAuditConclusion(draft)
  ElMessage.success('已生成审计结论草稿')
}

async function handleAddProject() {
  try {
    const { value } = await ElMessageBox.prompt('请输入开发支出项目名称', '新增波动分析项目', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (value?.trim()) addRow(value.trim())
  } catch { /* cancel */ }
}

function handleReview() {
  openReviewDialog('I2-5-实质性分析')
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  if (Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(2)}%`
}

function fmtPctPts(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const pts = v * 100
  return `${pts >= 0 ? '+' : ''}${pts.toFixed(2)}pt`
}
</script>

<style scoped>
.i2-analysis { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.objective-alert { margin-bottom: 12px; }
.obj-text { margin: 4px 0 0; font-size: 12px; line-height: 1.6; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6;
}
.tab-toolbar { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.block-card { margin-bottom: 14px; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.block-title-text { font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.meta-label { font-size: 12px; color: #6b7280; font-weight: 400; }
.formula-header { border-bottom: 1px dashed #a5b4fc; cursor: help; }
.formula-cell { color: #6366f1; font-weight: 500; }
.text-danger { color: #dc2626 !important; font-weight: 700; }
.total-text { font-weight: 600; }
.hint-text { margin: 8px 0 0; font-size: 12px; color: #6b7280; }
.note-block { margin-bottom: 12px; }
.note-label { font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 4px; }
.audit-conclusion-card { margin-top: 8px; }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; }
.legacy-block {
  margin-top: 16px; padding: 10px 14px; background: #fafafa; border: 1px solid #ebeef5;
  border-radius: 6px; font-size: 12px;
}
.legacy-block summary { cursor: pointer; font-weight: 600; color: #374151; margin-bottom: 8px; }
.table-actions { margin-top: 8px; }
.mb-8 { margin-bottom: 8px; }
.pcap-form :deep(.el-form-item) { margin-bottom: 8px; }
:deep(.total-row) { background: #f5f7fa !important; font-weight: 600; }
:deep(.rev-row) { background: #f8fafc !important; }
:deep(.anomaly-row) { background: #fef2f2 !important; }
</style>
