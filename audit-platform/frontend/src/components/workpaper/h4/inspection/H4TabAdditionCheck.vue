<template>
  <div class="h4-tab-addition-check">
    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>资产负债表中记录的工程物资是存在的，且已记录于恰当的账户（存在/发生）</li>
        <li>所有应记录的工程物资均已记录，相关披露完整（完整性）</li>
        <li>记录的工程物资由被审计单位拥有或控制（权利与义务）</li>
        <li>工程物资以恰当的金额列报，计价或分摊调整及披露恰当（准确性/计价与分摊）</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H4-4" :context-project-id="projectId" /></span>
      <GtIndexChip value="wp:H4-2" :context-project-id="projectId" context="明细勾稽" />
      <GtIndexChip value="wp:H4-9" :context-project-id="projectId" context="关联方" />
      <el-tag size="small" type="info">样本 {{ rows.length }} 项</el-tag>
      <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">
        异常 {{ summary.anomalyCount }} 项
      </el-tag>
      <el-tag v-if="summary.diffCount > 0" size="small" type="warning">
        三方差异 {{ summary.diffCount }} 项
      </el-tag>
      <el-tag size="small" :type="coverageTagType">
        检查比例 {{ summary.coverageRate.toFixed(2) }}%
      </el-tag>
      <el-button size="small" @click="emit('navigate-sheet', 'H4-2')">← H4-2</el-button>
      <el-button size="small" @click="emit('navigate-sheet', 'H4-5')">H4-5 →</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="warning"
        plain
        :disabled="summary.anomalyCount + summary.diffCount === 0"
        @click="onPushAje"
      >
        推送拟调整→H4-3
      </el-button>
    </div>

    <el-alert
      v-if="summary.incompleteCheckCount > 0"
      type="info"
      :closable="false"
      show-icon
      class="check-alert"
      :title="`有 ${summary.incompleteCheckCount} 笔核对内容 1–4 未全部勾选，请补充测试记录。`"
    />
    <el-alert
      v-if="samplingParams.populationAmount > 0 && summary.coverageRate < 20"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      title="检查比例偏低：请扩大样本量，或在四、审计说明中解释原因。"
    />

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、样本选取标准与规模</span>
          <div class="section-header-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedIncrease.amount > 0)"
              @click="onSyncPopulation"
            >
              从 {{ linkedIncrease.source || 'H4-2' }} 带入本期增加
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="showSampling = true">
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>

      <div class="test-content-hint">
        <p>测试内容说明（核对内容 1–5 列）：</p>
        <ol>
          <li v-for="(item, i) in H4_ADDITION_TEST_CONTENT_ITEMS" :key="i">{{ item }}</li>
        </ol>
        <p class="hint-note">
          特定样本优先：大额、关联方/关联交易、异常款项全部测试；其余按抽样方法抽取。
          总体应对齐 H4-2 审定「本期增加」合计（致同公式勾稽明细表）。
        </p>
      </div>

      <el-descriptions :column="3" border size="small" style="margin-top:8px">
        <el-descriptions-item label="本期新增合计（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="samplingParams.populationAmount"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => updateSamplingParams({ populationAmount: v ?? 0 })"
            />
            <span v-else class="amt-cell">{{ fmtAmt(samplingParams.populationAmount) }}</span>
            <el-tag v-if="linkedIncrease.source" size="small" type="info" class="src-tag">
              源 H4-2: {{ fmtAmt(linkedIncrease.amount) }}
            </el-tag>
            <el-tag v-if="populationManual" size="small" type="warning">手工</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法">
          <el-select
            v-if="!isReadonly"
            :model-value="samplingParams.samplingMethod"
            size="small"
            style="width:140px"
            @change="(v: string) => updateSamplingParams({ samplingMethod: v })"
          >
            <el-option v-for="m in SAMPLING_METHOD_OPTS" :key="m" :label="m" :value="m" />
          </el-select>
          <span v-else>{{ samplingParams.samplingMethod || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="样本量">{{ rows.length }}</el-descriptions-item>
        <el-descriptions-item label="检查借方合计">{{ fmtAmt(summary.checkedAmount) }}</el-descriptions-item>
        <el-descriptions-item label="检查比例">
          <span :class="{ 'warn-coverage': summary.coverageRate < 20 && samplingParams.populationAmount > 0 }">
            {{ summary.coverageRate.toFixed(2) }}%
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="重要性水平">
          <el-input-number
            v-if="!isReadonly"
            :model-value="samplingParams.materialityLevel"
            :controls="false"
            size="small"
            @change="(v: number | undefined) => updateSamplingParams({ materialityLevel: v ?? 0 })"
          />
          <span v-else>{{ fmtAmt(samplingParams.materialityLevel) }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <div class="specific-sample" v-if="!isReadonly || samplingParams.specificSampleNote">
        <span class="param-label">特定样本：</span>
        <el-input
          v-if="!isReadonly"
          :model-value="samplingParams.specificSampleNote"
          size="small"
          placeholder="大额、关联方、异常增加等全部测试说明…"
          @change="(v: string) => updateSamplingParams({ specificSampleNote: v })"
        />
        <span v-else>{{ samplingParams.specificSampleNote }}</span>
      </div>

      <el-alert
        v-if="populationDrift"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`总体与 H4-2（${fmtAmt(linkedIncrease.amount)}）不一致，可重新带入或保留手工数。`"
      />
      <div v-if="linkedIncrease.amount > 0" class="linked-breakdown">
        明细构成：采购 {{ fmtAmt(linkedIncrease.purchase) }}
        ／其他增加 {{ fmtAmt(linkedIncrease.otherIncrease) }}
      </div>
    </el-card>

    <!-- 三、测试 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>三、测试 — 本期增加检查明细（H4-4）</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H4-4')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="rows"
        border
        stripe
        size="small"
        max-height="520"
        class="check-table"
        row-key="rowId"
        :row-class-name="rowClassName"
      >
        <el-table-column prop="seq" label="序号" width="48" fixed align="center" />

        <el-table-column label="工程物资" align="center">
          <el-table-column label="类别" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.category" size="small"
                @change="updateCell(row.rowId, 'category', $event)" />
              <span v-else>{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="名称" min-width="110" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.name" size="small"
                @change="updateCell(row.rowId, 'name', $event)" />
              <span v-else>{{ row.name || '-' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="记账凭证" align="center">
          <el-table-column label="日期" width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherDate" size="small" placeholder="YYYY-MM-DD"
                @change="updateCell(row.rowId, 'voucherDate', $event)" />
              <span v-else>{{ row.voucherDate || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small"
                @change="updateCell(row.rowId, 'voucherNo', $event)" />
              <span v-else>{{ row.voucherNo || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.businessContent" size="small"
                @change="updateCell(row.rowId, 'businessContent', $event)" />
              <span v-else>{{ row.businessContent || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对方科目" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.oppositeAccount" size="small"
                placeholder="如应付账款"
                @change="updateCell(row.rowId, 'oppositeAccount', $event)" />
              <span v-else>{{ row.oppositeAccount || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对方明细" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.oppositeDetail" size="small"
                @change="updateCell(row.rowId, 'oppositeDetail', $event)" />
              <span v-else>{{ row.oppositeDetail || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方金额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'amount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="支持性文件" min-width="150">
          <template #default="{ row }">
            <div class="docs-cell">
              <el-input v-if="!isReadonly" v-model="row.supportingDocs" size="small"
                placeholder="合同/发票/入库单…"
                @change="updateCell(row.rowId, 'supportingDocs', $event)" />
              <span v-else>{{ row.supportingDocs || '-' }}</span>
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                link
                title="上传合同/发票/入库单 OCR 填入"
                @click="handleOcr(row)"
              >OCR</el-button>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="三方核对（增强）" align="center">
          <el-table-column label="供应商" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.supplier" size="small"
                @change="updateCell(row.rowId, 'supplier', $event)" />
              <span v-else>{{ row.supplier || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="发票金额" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.invoiceAmount" :controls="false"
                size="small" class="amt-input"
                @change="updateCell(row.rowId, 'invoiceAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.invoiceAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="90" align="right">
            <template #default="{ row }">
              <span
                class="formula-cell"
                :class="{ 'diff-error': Math.abs(row.diff) > 0.01 && row.invoiceAmount > 0 }"
                title="差异 = 借方金额 − 发票金额"
              >{{ fmtAmt(row.diff) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="核对内容" align="center">
          <el-table-column
            v-for="n in 5"
            :key="n"
            :label="String(n)"
            width="44"
            align="center"
          >
            <template #default="{ row }">
              <el-checkbox
                :model-value="row.checks[`check${n}` as keyof typeof row.checks]"
                :disabled="isReadonly"
                @change="(v: boolean | string | number) => updateCell(row.rowId, `checks.check${n}`, !!v)"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small"
              @change="updateCell(row.rowId, 'indexRef', $event)" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否异常" width="88" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isAbnormal" size="small" style="width:70px"
              @change="updateCell(row.rowId, 'isAbnormal', $event)">
              <el-option label="-" value="" />
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isAbnormal || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="是否关联方" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isRelatedParty" size="small" style="width:88px"
              @change="updateCell(row.rowId, 'isRelatedParty', $event)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isRelatedParty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方名称" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && row.isRelatedParty === '是'"
              v-model="row.relatedPartyName" size="small"
              @change="updateCell(row.rowId, 'relatedPartyName', $event)"
            />
            <span v-else>{{ row.isRelatedParty === '是' ? (row.relatedPartyName || '-') : '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="备注说明" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="updateCell(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="抽凭" width="55" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="onRowSample(row)">抽凭</el-button>
          </template>
        </el-table-column>

        <el-table-column label="" width="40" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="deleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-block">
        <div class="summary-line">
          合计：借方金额 <strong>{{ fmtAmt(summary.checkedAmount) }}</strong>
          <span class="sep">检查比例
            <strong :class="{ 'warn-coverage': summary.coverageRate < 20 && samplingParams.populationAmount > 0 }">
              {{ summary.coverageRate.toFixed(2) }}%
            </strong>
          </span>
        </div>
        <div class="summary-line muted">
          本期新增工程物资合计（总体）：{{ fmtAmt(samplingParams.populationAmount) }}
          <span v-if="samplingParams.populationAmount <= 0">（未填总体时检查比例显示 0%，避免除零）</span>
        </div>
      </div>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" type="primary" @click="handleAddRow">+ 添加检查行</el-button>
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small" :loading="importExport.isExporting.value || importExport.isImporting.value">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计说明</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="onDraftNote">起草说明</el-button>
            <el-button size="small" circle @click="openReview('H4-4-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="若检查比例偏低，扩大样本量或说明原因；概述三方核对差异、关联方采购及截止异常。"
        :disabled="isReadonly"
        @blur="saveNote(auditNote)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>五、审计结论</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" @click="onDraftConclusion">起草结论</el-button>
            <el-button size="small" circle @click="openReview('H4-4-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="基于上述检查，就是否实现一、审计目标发表结论；列明拟调整事项（→ H4-3）及范围受限影响。"
        :disabled="isReadonly"
        @blur="saveConclusion(auditConclusion)"
      />
    </el-card>

    <details class="edit-tips" open>
      <summary>提示（编制要点）</summary>
      <ol>
        <li>本表用于汇总本年度工程物资增加（采购入库等）的测试情况。</li>
        <li>检查比例 = 样本借方合计 ÷ 本期新增总体（覆盖率，非与 H4-1 全量平衡）。总体未填时显示 0%（避免 #DIV/0!）。</li>
        <li>总体宜从 H4-2 审定「本期增加」带入；H4-1 借/贷发生额亦由 H4-2 汇总供给交叉检查。</li>
        <li>抽凭回填：业务内容←凭证摘要；对方科目/明细←counterpartAccount（支持「科目/明细」拆分）；借方金额优先取 debitAmount。</li>
        <li>支持性文件列 OCR：上传合同/发票/入库单扫描件，确认后自动拼接单据号并填入供应商、发票金额等空字段。</li>
        <li>差异 = 借方金额 − 发票金额（平台增强）；有发票金额且差异≠0 时高亮。</li>
        <li>关联方采购可在「是否关联方」标记后，于 H4-9 一键带入。</li>
        <li>核对内容第 5 项：入库单/发票/合同三方一致。</li>
      </ol>
    </details>

    <el-dialog
      v-model="showSampling"
      title="抽凭引擎（科目 1605 工程物资-增加）"
      width="720px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        v-if="showSampling && wpId && projectId"
        :project-id="projectId"
        :workpaper-id="wpId"
        account-code="1605"
        phase="final"
        :year="year ?? new Date().getFullYear()"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabAdditionCheck.vue — H4-4 增加检查表
 * 对齐致同：目标 → 样本选取 → 测试（记账凭证 + 核对1–5）
 * → 检查比例 → 说明/结论；平台增强三方差异 + 关联方预埋
 */
import { computed, inject, toRef, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useH4AdditionCheck,
  SAMPLING_METHOD_OPTS,
  H4_ADDITION_TEST_CONTENT_ITEMS,
  extractOcrFields,
  mapOcrToAdditionPatch,
  type H4AdditionCheckRow,
} from '../../composables/useH4AdditionCheck'
import { useH4ImportExport } from '../../composables/useH4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  year?: number
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)
const isReadonly = toRef(props, 'isReadonly')
const projectId = toRef(props, 'projectId')
const wpId = toRef(props, 'wpId')

const {
  rows,
  samplingParams,
  populationManual,
  auditNote,
  auditConclusion,
  linkedIncrease,
  summary,
  populationDrift,
  addRow,
  deleteRow,
  updateCell,
  updateSamplingParams,
  syncPopulationFromH42,
  saveNote,
  saveConclusion,
  draftNote,
  draftConclusion,
  pushAjeDraftToH43,
  applyVoucherSamples,
  mergeOcrResult,
  rowClassName,
  load,
} = useH4AdditionCheck({
  wpId,
  projectId,
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
    saveResponse(itemId, value)
  },
})

const importExport = useH4ImportExport({
  wpId,
  projectId,
  onImported: () => load(),
})

const showSampling = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const samplingRowId = ref<string | null>(null)

const coverageTagType = computed(() => {
  if (samplingParams.value.populationAmount <= 0) return 'info'
  if (summary.value.coverageRate < 20) return 'danger'
  if (summary.value.coverageRate < 50) return 'warning'
  return 'success'
})

function onSyncPopulation() {
  if (syncPopulationFromH42()) ElMessage.success('已从 H4-2 带入本期增加合计')
  else ElMessage.warning('H4-2 尚无增加发生额，请先完善明细表')
}

function onDraftNote() {
  draftNote()
  ElMessage.success('已起草审计说明，可继续编辑')
}

function onDraftConclusion() {
  draftConclusion()
  ElMessage.success('已起草审计结论，可继续编辑')
}

function onPushAje() {
  const res = pushAjeDraftToH43()
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加检查行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function onRowSample(row: H4AdditionCheckRow) {
  samplingRowId.value = row.rowId
  showSampling.value = true
}

function onSampleFilled(payload: unknown) {
  const n = applyVoucherSamples(payload, samplingRowId.value)
  samplingRowId.value = null
  showSampling.value = false
  if (n > 0) ElMessage.success(`已回填 ${n} 笔抽凭（业务内容/对方科目已映射）`)
  else ElMessage.info('未获取到抽凭样本')
}

async function handleOcr(row: H4AdditionCheckRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const { fields, confidence } = extractOcrFields(res.data)
      const { patch, previewLines } = mapOcrToAdditionPatch(fields)
      if (!previewLines.length && !Object.keys(patch).length) {
        await ElMessageBox.alert('OCR 完成，未识别到可填充字段', '提示')
        return
      }
      const confPct = confidence > 0 ? `\n置信度：${(confidence * 100).toFixed(0)}%` : ''
      await ElMessageBox.confirm(
        `识别结果：\n${previewLines.join('\n')}${confPct}\n\n确认填入本行（支持性文件合并，其余空字段写入）？`,
        'OCR 识别结果',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
      )
      mergeOcrResult(row.rowId, fields)
      ElMessage.success('OCR 结果已填入支持性文件及相关字段')
    } catch (err: any) {
      if (err === 'cancel' || err?.toString?.().includes('cancel')) return
      ElMessage.warning(err?.response?.data?.detail || err?.message || 'OCR 识别失败')
    }
  }
  input.click()
}

async function handleImportExport(command: string) {
  if (command === 'export-template') await importExport.exportTemplate('H4-4')
  else if (command === 'export-data') await importExport.exportData('H4-4')
  else if (command === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  await importExport.importData('H4-4', file)
  load()
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '0.00'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h4-tab-addition-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; margin-bottom: 4px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.6; font-size: 12px; }

.tab-toolbar {
  display: flex; justify-content: flex-end; align-items: center;
  gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.check-alert { margin-bottom: 8px; }

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.block-card { margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }

.test-content-hint {
  font-size: 12px; color: var(--el-text-color-regular); line-height: 1.55;
  background: var(--el-fill-color-lighter); border-radius: 6px; padding: 10px 12px;
}
.test-content-hint ol { margin: 4px 0 0; padding-left: 18px; }
.hint-note { margin: 8px 0 0; color: var(--el-text-color-secondary); }

.pop-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.src-tag { margin-left: 2px; }
.specific-sample {
  display: flex; align-items: center; gap: 8px; margin-top: 10px;
}
.param-label { font-size: 12px; color: var(--el-text-color-secondary); white-space: nowrap; }
.linked-breakdown {
  margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary);
}

.check-table { font-size: var(--wp-font-size, 13px); }
.docs-cell { display: flex; align-items: center; gap: 4px; }
.docs-cell .el-input { flex: 1; min-width: 0; }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  display: block; text-align: right; font-variant-numeric: tabular-nums;
  color: var(--el-color-primary); font-weight: 500;
  border-bottom: 1px dashed #67c23a; cursor: help;
}
.diff-error { color: #f56c6c; font-weight: 600; border-bottom-color: #f56c6c; }
.warn-coverage { color: var(--el-color-danger); font-weight: 600; }

.summary-block {
  margin-top: 10px; padding: 10px 12px;
  background: var(--el-fill-color-lighter); border-radius: 6px;
  font-size: 12px; line-height: 1.7;
}
.summary-line .sep { margin-left: 12px; }
.muted { color: var(--el-text-color-secondary); }

.action-bar { display: flex; align-items: center; gap: 8px; margin-top: 10px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 20px; margin-top: 8px; line-height: 1.6; }

:deep(.row-anomaly) { background: #fef0f0 !important; }
:deep(.row-warn) { background: #fdf6ec !important; }
</style>
