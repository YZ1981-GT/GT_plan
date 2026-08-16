<template>
  <div class="g10-voucher-check" data-testid="g10-voucher-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <div class="section-head">
      <h3 class="sheet-title">G10-7 交易性金融负债凭证检查表</h3>
      <div class="head-actions">
        <GtVoucherSamplingEngine v-if="!isReadonly && wpId && projectId" :project-id="projectId" :workpaper-id="wpId" :account-code="G10_ACCOUNT_CODE" phase="final" :year="auditYear ?? new Date().getFullYear()" @filled="onSampleFilled" />
        <G10ImportExportDropdown :wp-id="wpId" sheet="G10-7" @imported="onImported" />
        <el-button size="small" :disabled="isReadonly" data-testid="g10-export-memo" @click="exportMemo">
          📄 抽样备忘
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :disabled="vc.quantitativeAbnormalCount.value <= 0"
          data-testid="g10-vc-push-adj"
          @click="onPushAbnormal"
        >
          推送异常→G10-3
          <template v-if="vc.quantitativeAbnormalCount.value">（{{ vc.quantitativeAbnormalCount.value }}）</template>
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-3" /></span>
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="success"
          plain
          :loading="vc.procedureMarking.value"
          :disabled="!vc.rows.value.length"
          data-testid="g10-vc-mark-procedure"
          @click="onMarkProcedure"
        >
          {{ vc.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 凭证程序' }}
        </el-button>
        <GtReviewTrigger section-id="G10-7-voucher" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：通过凭证抽查核实交易性金融负债相关业务的真实性、完整性与准确性，验证原始凭证完整、授权恰当、账务处理、初始成本、利息及公允价值计量正确。" />

    <div class="sampling-params-card" data-testid="g10-vc-params">
      <h4 class="card-title">样本选取（{{ activeScopeLabel }}）</h4>
      <div class="params-grid">
        <div class="param-item param-item-wide">
          <span class="param-label">测试总体</span>
          <el-input
            :model-value="vc.activeScopeParams.value.testPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="如：科目2101本期发生额共XX笔、金额XX"
            @change="(v: string) => vc.updateScopeSampling(vc.activeScope.value, 'testPopulation', v)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">特定样本</span>
          <el-input
            :model-value="vc.activeScopeParams.value.specificSamples"
            size="small"
            :disabled="isReadonly"
            placeholder="大额/异常/关联方等必选样本说明"
            @change="(v: string) => vc.updateScopeSampling(vc.activeScope.value, 'specificSamples', v)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">抽样方法</span>
          <el-select
            :model-value="vc.activeScopeParams.value.samplingMethod"
            size="small"
            clearable
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: string) => vc.updateScopeSampling(vc.activeScope.value, 'samplingMethod', v ?? '')"
          >
            <el-option v-for="o in G10_SAMPLING_METHOD_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">目标样本量</span>
          <el-input-number
            :model-value="vc.activeScopeParams.value.targetSampleSize"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateScopeSampling(vc.activeScope.value, 'targetSampleSize', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">总体金额</span>
          <el-input-number
            :model-value="vc.activeScopeParams.value.populationAmount"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateScopeSampling(vc.activeScope.value, 'populationAmount', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">账面价值</span>
          <el-input-number
            :model-value="vc.activeScopeParams.value.bookValue"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateScopeSampling(vc.activeScope.value, 'bookValue', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">可容忍错报</span>
          <el-input-number
            :model-value="vc.activeScopeParams.value.tolerableMisstatement"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateScopeSampling(vc.activeScope.value, 'tolerableMisstatement', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">预计错报</span>
          <el-input-number
            :model-value="vc.activeScopeParams.value.expectedMisstatement"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateScopeSampling(vc.activeScope.value, 'expectedMisstatement', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">误受风险</span>
          <el-select
            :model-value="vc.activeScopeParams.value.riskOfIncorrectAcceptance"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: 1 | 5 | 10) => vc.updateScopeSampling(vc.activeScope.value, 'riskOfIncorrectAcceptance', v)"
          >
            <el-option :value="1" label="1%（扩展 1.9）" />
            <el-option :value="5" label="5%（扩展 1.6）" />
            <el-option :value="10" label="10%（扩展 1.5）" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">风险系数</span>
          <el-input-number
            :model-value="vc.activeScopeParams.value.riskFactor"
            size="small"
            :min="0"
            :step="0.1"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateScopeSampling(vc.activeScope.value, 'riskFactor', v ?? 1)"
          />
        </div>
      </div>
      <div class="sampling-calc-row">
        <span v-if="vc.suggestedSampleSize.value != null">
          公式样本量：<b>{{ vc.suggestedSampleSize.value }}</b>
        </span>
        <span v-else class="muted">填写账面价值与可容忍错报后可计算样本量</span>
        <el-button
          v-if="!isReadonly && vc.suggestedSampleSize.value"
          size="small"
          link
          type="primary"
          @click="onApplySuggested"
        >采用公式样本量</el-button>
        <span class="sep">|</span>
        <span>进度 {{ vc.currentSampleSize.value }} / {{ vc.activeScopeParams.value.targetSampleSize || '—' }}</span>
        <el-progress
          :percentage="vc.progressPct.value"
          :stroke-width="8"
          style="flex:1;max-width:200px;margin-left:8px"
        />
      </div>
      <div class="ratio-row" data-testid="g10-vc-ratio">
        <span>已查金额 {{ fmt(vc.sampleAbsAmount.value) }}</span>
        <span>
          检查比例
          <b>{{ vc.inspectionRatioPct.value == null ? '—' : `${vc.inspectionRatioPct.value.toFixed(1)}%` }}</b>
        </span>
      </div>
      <el-alert
        v-if="vc.lowInspectionRatio.value"
        type="warning"
        :closable="false"
        show-icon
        class="ratio-alert"
        title="检查比例低于 30%，请扩大样本量或在审计说明中解释原因。"
      />
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G10-7" /></span>
        <el-tag size="small" type="info">当前 {{ vc.scopedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <div class="summary-bar" :class="{ 'summary-error': !vc.isBalanced.value }">
      借方 {{ fmt(vc.debitTotal.value) }} · 贷方 {{ fmt(vc.creditTotal.value) }} · 差额 {{ fmt(vc.balanceDiff.value) }}
      · 异常 {{ vc.abnormalCount.value }} 条
      · 金额类异常 {{ vc.quantitativeAbnormalCount.value }}
    </div>
    <div class="scope-tabs">
      <el-segmented
        :model-value="vc.activeScope.value"
        :options="scopeOptions"
        size="small"
        @update:model-value="(v: any) => vc.setPeriodScope(v)"
      />
    </div>
    <div class="segment-tabs">
      <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
    </div>

    <el-table-v2
      v-if="vc.useVirtualScroll.value"
      :columns="virtualColumns"
      :data="vc.scopedRows.value"
      :width="tableWidth"
      :height="440"
      :row-height="36"
      :header-height="40"
      fixed
      class="virtual-table"
      data-testid="g10-voucher-virtual-table"
    />

    <el-table v-else :data="vc.scopedRows.value" border stripe style="width:100%;font-size:13px" max-height="480"
      highlight-current-row :row-class-name="({ row }) => row.isAbnormal ? 'abnormal-row' : ''"
      @current-change="onRowChange">
      <el-table-column prop="seq" label="序号" width="52" align="center" fixed />
      <template v-if="vc.activeTab.value === 'basic'">
        <el-table-column label="日期" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherDate" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { voucherDate: v })" />
            <span v-else>{{ row.voucherDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { voucherNo: v })" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { businessContent: v })" />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterAccount" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { counterAccount: v })" />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方" width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.debitAmount" size="small" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.id, { debitAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.creditAmount" size="small" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.id, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="📎" width="52">
          <template #default="{ row }">
            <el-button size="small" link :disabled="isReadonly" @click="uploadOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDocDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { supportingDocDesc: v })" />
            <span v-else>{{ row.supportingDocDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="(label, idx) in checkLabels" :key="idx" :label="label" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="checkValue(row, idx)"
              @change="(v: boolean) => setCheck(row, idx, v)" />
            <span v-else>{{ checkValue(row, idx) ? '✓' : '✗' }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="索引号" width="88">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.indexNo" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { indexNo: v })" />
            <GtIndexChip v-else-if="row.indexNo" :value="row.indexNo" />
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="88">
          <template #default="{ row }">
            <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">{{ row.isAbnormal ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.abnormalDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { abnormalDesc: v })" />
            <span v-else>{{ row.abnormalDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.riskLevel" size="small"
              @change="(v: string) => vc.updateRow(row.id, { riskLevel: v as any })">
              <el-option v-for="o in G10_RISK_LEVEL_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.riskLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column label="操作" width="64" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="vc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="vc.activeTab.value === 'conclusion'" class="conclusion-panel" data-testid="g10-voucher-conclusion">
      <div class="conclusion-head">
        <span>抽查结论</span>
        <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly" @click="vc.generateAiConclusion()">🤖 AI</el-button>
      </div>
      <el-input :model-value="vc.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="汇总凭证抽查结论、异常事项及后续程序" :disabled="isReadonly" @update:model-value="vc.updateConclusion" />
    </div>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="voucher-note"
      conclusion-ai-section="voucher-conclusion"
      note-placeholder="填写审计说明：可概述凭证抽查的样本范围、抽样方法、逐笔核对结果、发现的异常凭证及其处理。"
      note-hint="覆盖抽样范围、核对程序与异常事项。"
      conclusion-placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
      :related-context="{
        当前分段: activeScopeLabel,
        行数: vc.scopedRows.value.length,
        异常条数: vc.abnormalCount.value,
        检查比例: vc.inspectionRatioPct.value == null ? '—' : `${vc.inspectionRatioPct.value.toFixed(1)}%`,
      }"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>可用抽凭引擎按科目 2101 抽取样本自动填入；「核对内容」逐笔核对 6 项（齐全/授权/账务/成本/利息/公允）。</p>
        <p>本期与期后分表编制；检查比例 = 已查样本金额 ÷ 总体金额，低于 30% 须扩样或说明。</p>
        <p>异常凭证须填写异常说明并评定风险等级；金额类异常（成本/利息/公允未通过）可「推送异常→G10-3」生成 AJE 草稿并回写 G10-1。</p>
        <p>编制完成后可「回填 G10A 凭证程序」（步骤 6/7/8：新增/处置/截止）。</p>
        <p>抽查结论应覆盖样本范围、发现的异常事项及拟采取的后续审计程序。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, toRef, watch, h, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { Column } from 'element-plus'
import http from '@/utils/http'
import { useG10VoucherCheck, type G10VoucherCheckRow } from '../../composables/useG10VoucherCheck'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import { G10A_PROCEDURE_SHEET, G10A_VOUCHER_PROGRAM_NOS } from '../../composables/g10FvCrossHelpers'
import { G10_ACCOUNT_CODE, G10_RISK_LEVEL_OPTIONS } from '../../composables/g10Constants'
import { G10_VOUCHER_CHECK_DEFS, G10_VOUCHER_PERIOD_OPTIONS, G10_SAMPLING_METHOD_OPTIONS } from '../../composables/g10VoucherConstants'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  auditYear?: number | null
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const vc = useG10VoucherCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  year: computed(() => props.auditYear ?? null),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const NOTE_KEY = 'G10-7-voucher-audit-note'
const CONCLUSION_KEY = 'G10-7-voucher-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]
const scopeOptions = G10_VOUCHER_PERIOD_OPTIONS
const activeScopeLabel = computed(() =>
  scopeOptions.find((o) => o.value === vc.activeScope.value)?.label ?? '本期发生额检查',
)
const checkLabels = G10_VOUCHER_CHECK_DEFS.map((d) => d.label)
const checkKeys = G10_VOUCHER_CHECK_DEFS.map((d) => d.key)
const tableWidth = 960

const virtualColumns = computed<Column<any>[]>(() => [
  { key: 'seq', title: '#', dataKey: 'seq', width: 44, align: 'center' },
  { key: 'voucherNo', title: '凭证编号', dataKey: 'voucherNo', width: 100 },
  { key: 'businessContent', title: '业务内容', dataKey: 'businessContent', width: 180 },
  { key: 'creditAmount', title: '贷方', dataKey: 'creditAmount', width: 100, align: 'right',
    cellRenderer: ({ rowData }: { rowData: G10VoucherCheckRow }) => h('span', fmt(rowData.creditAmount)) },
  { key: 'isAbnormal', title: '异常', dataKey: 'isAbnormal', width: 72, align: 'center',
    cellRenderer: ({ rowData }: { rowData: G10VoucherCheckRow }) => h('span', rowData.isAbnormal ? '是' : '否') },
])

function checkValue(row: G10VoucherCheckRow, idx: number): boolean {
  return row[checkKeys[idx] as keyof G10VoucherCheckRow] as boolean
}

function setCheck(row: G10VoucherCheckRow, idx: number, v: boolean) {
  const key = checkKeys[idx]
  vc.updateRow(row.id, { [key]: v })
}

async function onMarkProcedure() {
  const res = await vc.markProcedureComplete()
  if (!res.ok) {
    ElMessage.warning(res.message)
    return
  }
  ElMessage.success(res.message)
  dispatchProcedureFocus({
    programNos: [...G10A_VOUCHER_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `凭证检查程序（步骤 ${[...G10A_VOUCHER_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_VOUCHER_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

function onApplySuggested() {
  const n = vc.applySuggestedSampleSize(vc.activeScope.value)
  if (n) ElMessage.success(`已采用公式样本量 ${n}`)
}

function exportMemo() {
  const md = vc.buildMemo()
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `G10-7-抽样备忘-${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)
  if (!props.isReadonly) {
    auditNote.value = auditNote.value
      ? `${auditNote.value}\n\n---\n${md}`
      : md
  }
  ElMessage.success('抽样备忘已导出')
}

async function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

async function onPushAbnormal() {
  await vc.pushAbnormalToAdjustment()
}

function onRowChange(row: G10VoucherCheckRow | undefined) {
  if (!row) return
  const idx = vc.scopedRows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.setActiveRowIndex(idx)
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'G10',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => props.debouncedSave(itemId, { remark, conclusion: null }),
  isReadonly: computed(() => props.isReadonly === true),
})

function onSampleFilled(payload: { samples: Array<{ summary?: string; amount?: number; voucherDate?: string; voucherNo?: string }> }) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  for (const s of payload.samples ?? []) {
    vc.mergeSample({
      businessContent: s.summary,
      creditAmount: s.amount,
      voucherDate: s.voucherDate,
      voucherNo: s.voucherNo,
      source: '抽凭',
    })
  }
}

async function uploadOcr(row: G10VoucherCheckRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      let res
      try {
        res = await http.post(`/api/workpapers/${props.wpId}/g10/contract-ocr`, formData)
      } catch {
        res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData)
      }
      const data = res.data?.data ?? res.data ?? {}
      const summary = data.summary ?? data.extracted_fields?.businessContent ?? ''
      if (!summary) { ElMessage.warning('OCR 未识别到内容'); return }
      await ElMessageBox.confirm(`识别结果：${summary}，是否填入业务内容？`, 'OCR 确认', { type: 'info' })
      vc.updateRow(row.id, { businessContent: summary, attachment: file.name })
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.warning('OCR 识别失败')
    }
  }
  input.click()
}

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.g10-voucher-check { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.summary-error { background: #fef0f0; color: #f56c6c; }
.segment-tabs { margin-bottom: 8px; }
.scope-tabs { margin-bottom: 8px; }
.sampling-params-card {
  margin-bottom: 10px; padding: 10px 12px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
}
.card-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; }
.params-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 8px 12px;
}
.param-item-wide { grid-column: 1 / -1; }
.param-label { display: block; font-size: 11px; color: #909399; margin-bottom: 4px; }
.sampling-calc-row {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px;
}
.ratio-row { margin-top: 6px; font-size: 12px; display: flex; gap: 16px; }
.ratio-alert { margin-top: 8px; }
.muted { color: #909399; }
.sep { color: #dcdfe6; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.conclusion-panel { margin-top: 12px; padding: 12px; background: #fafafa; border-radius: 4px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
</style>
