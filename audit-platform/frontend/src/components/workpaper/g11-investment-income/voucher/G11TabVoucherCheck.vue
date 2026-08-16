<template>
  <div class="g11-voucher-check" data-testid="g11-voucher-check">
    <div class="section-head">
      <h3 class="sheet-title">G11-5 投资收益凭证检查表</h3>
      <div class="head-actions">
        <GtVoucherSamplingEngine v-if="!isReadonly && wpId && projectId" :project-id="projectId" :workpaper-id="wpId" :account-code="G11_ACCOUNT_CODE" phase="final" :year="auditYear ?? new Date().getFullYear()" @filled="onSampleFilled" />
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-5" @imported="onImported" />
        <el-button size="small" :disabled="isReadonly" data-testid="g11-export-memo" @click="exportMemo">
          📄 抽样备忘
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :disabled="vc.quantitativeAbnormalCount.value <= 0"
          data-testid="g11-vc-push-adj"
          @click="onPushAbnormal"
        >
          推送异常→G11-3
          <template v-if="vc.quantitativeAbnormalCount.value">（{{ vc.quantitativeAbnormalCount.value }}）</template>
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G11-3" /></span>
        <el-button
          v-if="!isReadonly && projectId"
          size="small"
          type="success"
          plain
          :loading="vc.procedureMarking.value"
          :disabled="!vc.rows.value.length"
          data-testid="g11-vc-mark-procedure"
          @click="onMarkProcedure"
        >
          {{ vc.procedureMarked.value ? '已回填 G11A（可重写）' : '回填 G11A 凭证程序' }}
        </el-button>
        <GtReviewTrigger section-id="G11-5-voucher" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="vc.addRow()">+ 新增</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="ao-wrap">
          <div class="ao-title">审计目标</div>
          <ol class="ao-list">
            <li>确定记录的投资收益是否已发生，且与被审计单位有关（发生）；</li>
            <li>确定所有应当记录的投资收益是否均已记录（完整性）；</li>
            <li>确定与投资收益有关的金额及其他数据是否已恰当记录，是否已记录于正确的会计期间，是否已记录于恰当的账户（准确性、截止、分类）。</li>
          </ol>
        </div>
      </template>
    </el-alert>

    <div class="sampling-params-card" data-testid="g11-vc-params">
      <h4 class="card-title">二、样本选取方法与规模</h4>
      <div class="params-grid">
        <div class="param-item param-item-wide">
          <span class="param-label">测试总体</span>
          <el-input
            :model-value="vc.samplingParams.value.testPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="如：科目6111本期贷方发生额共XX笔、金额XX"
            @change="(v: string) => vc.updateSampling('testPopulation', v)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">特定样本</span>
          <el-input
            :model-value="vc.samplingParams.value.specificSamples"
            size="small"
            :disabled="isReadonly"
            placeholder="大额、关联方/关联交易、异常投资收益等必选样本"
            @change="(v: string) => vc.updateSampling('specificSamples', v)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">抽样总体</span>
          <el-input
            :model-value="vc.samplingParams.value.samplingPopulation"
            size="small"
            :disabled="isReadonly"
            placeholder="测试总体扣除特定样本后的剩余总体"
            @change="(v: string) => vc.updateSampling('samplingPopulation', v)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">抽样方法</span>
          <el-select
            :model-value="vc.samplingParams.value.samplingMethod"
            size="small"
            clearable
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: string) => vc.updateSampling('samplingMethod', v ?? '')"
          >
            <el-option v-for="o in G11_SAMPLING_METHOD_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">目标样本量</span>
          <el-input-number
            :model-value="vc.samplingParams.value.targetSampleSize"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateSampling('targetSampleSize', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">本期发生额</span>
          <div class="param-with-action">
            <el-input-number
              :model-value="vc.samplingParams.value.populationAmount"
              size="small"
              :min="0"
              :controls="false"
              :disabled="isReadonly"
              style="flex:1"
              @change="(v: number | undefined) => vc.updateSampling('populationAmount', v ?? 0)"
            />
            <el-button
              v-if="!isReadonly"
              size="small"
              link
              type="primary"
              data-testid="g11-vc-pull-population"
              :disabled="vc.g11AdjPopulationHint.value <= 0"
              @click="vc.pullPopulationFromAdjudication()"
            >从G11-1带入</el-button>
          </div>
          <span v-if="vc.g11AdjPopulationHint.value > 0" class="hint-text">
            G11-1 未审合计 {{ fmt(vc.g11AdjPopulationHint.value) }}
          </span>
        </div>
        <div class="param-item">
          <span class="param-label">账面价值</span>
          <el-input-number
            :model-value="vc.samplingParams.value.bookValue"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateSampling('bookValue', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">可容忍错报</span>
          <el-input-number
            :model-value="vc.samplingParams.value.tolerableMisstatement"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateSampling('tolerableMisstatement', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">预计错报</span>
          <el-input-number
            :model-value="vc.samplingParams.value.expectedMisstatement"
            size="small"
            :min="0"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateSampling('expectedMisstatement', v ?? 0)"
          />
        </div>
        <div class="param-item">
          <span class="param-label">误受风险</span>
          <el-select
            :model-value="vc.samplingParams.value.riskOfIncorrectAcceptance"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: 1 | 5 | 10) => vc.updateSampling('riskOfIncorrectAcceptance', v)"
          >
            <el-option :value="1" label="1%（扩展 1.9）" />
            <el-option :value="5" label="5%（扩展 1.6）" />
            <el-option :value="10" label="10%（扩展 1.5）" />
          </el-select>
        </div>
        <div class="param-item">
          <span class="param-label">风险系数</span>
          <el-input-number
            :model-value="vc.samplingParams.value.riskFactor"
            size="small"
            :min="0"
            :step="0.1"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @change="(v: number | undefined) => vc.updateSampling('riskFactor', v ?? 1)"
          />
        </div>
        <div class="param-item param-item-wide">
          <span class="param-label">抽样过程</span>
          <el-input
            :model-value="vc.samplingParams.value.samplingProcess"
            size="small"
            :disabled="isReadonly"
            placeholder="如：使用 IDEA/抽凭引擎按金额或笔数抽取…"
            @change="(v: string) => vc.updateSampling('samplingProcess', v)"
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
        <span>进度 {{ vc.currentSampleSize.value }} / {{ vc.samplingParams.value.targetSampleSize || '—' }}</span>
        <el-progress
          :percentage="vc.progressPct.value"
          :stroke-width="8"
          style="flex:1;max-width:200px;margin-left:8px"
        />
      </div>
      <div class="ratio-row" data-testid="g11-vc-ratio">
        <span>已查金额（合计）{{ fmt(vc.sampleAbsAmount.value) }}</span>
        <span>本期发生额 {{ fmt(vc.samplingParams.value.populationAmount) }}</span>
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

    <div class="check-legend methodology-block">
      <div class="legend-title">三、测试 — 核对内容说明</div>
      <ol class="legend-list">
        <li v-for="d in G11_VOUCHER_CHECK_DEFS" :key="d.key">{{ d.title }}</li>
      </ol>
      <p class="legend-note">核对项为三态：未测 / 通过 / 不通过；任一「不通过」或强制异常 → 标异常；「未测」不计入异常。</p>
    </div>

    <GCycleProcedureCutoffPanel
      v-if="!isReadonly && wpId && projectId"
      :wp-id="wpId"
      :project-id="projectId"
      :account-code="G11_ACCOUNT_CODE"
      cycle="g11"
      :year="auditYear ?? undefined"
      fill-target-hint="样本将回填至本表 G11-5；跨期疑点自动强制异常"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G11-5" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ vc.rows.value.length }} 行</el-tag>
        <el-tag size="small" type="warning">未测 {{ vc.untestedCount.value }}</el-tag>
        <el-tag size="small" :type="vc.cutoffAbnormalCount.value > 0 ? 'warning' : 'info'">
          截止跨期 {{ vc.cutoffAbnormalCount.value }}
        </el-tag>
      </div>
    </div>

    <div class="summary-bar">
      贷方合计 {{ fmt(vc.creditTotal.value) }}
      · 异常 {{ vc.abnormalCount.value }} 条
      · 金额类异常 {{ vc.quantitativeAbnormalCount.value }}
      · 检查比例 {{ vc.inspectionRatioPct.value == null ? '—' : `${vc.inspectionRatioPct.value.toFixed(1)}%` }}
    </div>

    <div class="segment-tabs">
      <el-segmented v-model="vc.activeTab.value" :options="tabOptions" size="small" />
    </div>

    <el-table
      :data="vc.rows.value"
      border
      stripe
      style="width:100%;font-size:13px"
      max-height="480"
      highlight-current-row
      :row-class-name="({ row }) => row.isAbnormal ? 'abnormal-row' : ''"
      @current-change="onRowChange"
    >
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
        <el-table-column label="对方明细科目" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.counterDetail" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { counterDetail: v })" />
            <span v-else>{{ row.counterDetail }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.creditAmount" size="small" style="width:100%"
              @update:model-value="(v: number) => vc.updateRow(row.id, { creditAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="附件" width="72">
          <template #default="{ row }">
            <el-button size="small" link :disabled="isReadonly" @click="uploadOcr(row)">📎</el-button>
          </template>
        </el-table-column>
      </template>
      <template v-else-if="vc.activeTab.value === 'check'">
        <el-table-column label="支持性文件" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supportingDocDesc" size="small"
              @update:model-value="(v: string) => vc.updateRow(row.id, { supportingDocDesc: v })" />
            <span v-else>{{ row.supportingDocDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="def in G11_VOUCHER_CHECK_DEFS"
          :key="def.key"
          :label="def.label"
          :title="def.title"
          width="88"
          align="center"
        >
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="g11CheckSelectValue((row as any)[def.key])"
              size="small"
              @change="(v: string) => vc.updateRow(row.id, { [def.key]: parseG11CheckSelect(v) } as any)"
            >
              <el-option v-for="o in G11_CHECK_STATE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ formatG11CheckState((row as any)[def.key]) }}</span>
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
        <el-table-column label="强制异常" width="88" align="center">
          <template #default="{ row }">
            <el-switch
              v-if="!isReadonly"
              :model-value="row.forceAbnormal"
              size="small"
              @update:model-value="(v: boolean) => vc.updateRow(row.id, { forceAbnormal: !!v })"
            />
            <span v-else>{{ row.forceAbnormal ? '是' : '否' }}</span>
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
              <el-option v-for="o in G11_RISK_LEVEL_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
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

    <div v-if="vc.activeTab.value === 'conclusion'" class="conclusion-panel" data-testid="g11-voucher-conclusion">
      <div class="conclusion-head">
        <span>抽查结论</span>
        <el-button size="small" :loading="vc.aiLoading.value" :disabled="isReadonly" @click="vc.generateAiConclusion()">🤖 AI</el-button>
      </div>
      <el-input
        :model-value="vc.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="汇总凭证抽查结论、异常事项及后续程序"
        :disabled="isReadonly"
        @update:model-value="vc.updateConclusion"
      />
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>四、审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述样本选取方法、样本量、逐笔核对结果、异常事项及处理。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>五、审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表对投资收益（6111，损益类）贷方发生额抽取凭证检查，验证发生、完整、准确、期间归属及账务处理。</p>
        <p>2. 先填写「样本选取」；可用「从G11-1带入」填充本期发生额。检查比例 = 已查贷方合计 ÷ 本期发生额。</p>
        <p>3. 核对五项为三态（未测/通过/不通过）；截止跨期可强制异常。金额/账务「不通过」可推送→G11-3。</p>
        <p>4. 编制完成后可「回填 G11A」步骤 3；检查比例低于 30% 须扩样或在审计说明中解释。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, onMounted, onBeforeUnmount, inject, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useG11VoucherCheck, type G11VoucherCheckRow } from '../../composables/useG11VoucherCheck'
import { G11_ACCOUNT_CODE } from '../../composables/g11Constants'
import {
  G11_VOUCHER_CHECK_DEFS,
  G11_SAMPLING_METHOD_OPTIONS,
  G11_RISK_LEVEL_OPTIONS,
  G11_CHECK_STATE_OPTIONS,
  formatG11CheckState,
  g11CheckSelectValue,
  parseG11CheckSelect,
} from '../../composables/g11VoucherConstants'
import { G11A_VOUCHER_PROGRAM_NOS, G11A_PROCEDURE_SHEET } from '../../composables/g11VoucherCross'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import {
  GCYCLE_CUTOFF_EVENT,
  type GCycleCutoffFilledDetail,
} from '../../composables/gCycleCutoffFill'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GCycleProcedureCutoffPanel from '../../shared/GCycleProcedureCutoffPanel.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

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

const vc = useG11VoucherCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  year: computed(() => props.auditYear ?? null),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const NOTE_KEY = 'G11-voucher-audit-note'
const CONCLUSION_KEY = 'G11-voucher-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: val, remark: null })
  props.debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.conclusion || c?.remark) auditConclusion.value = String(c.conclusion ?? c.remark ?? '')
  window.addEventListener(GCYCLE_CUTOFF_EVENT.g11, onCutoffFilled as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener(GCYCLE_CUTOFF_EVENT.g11, onCutoffFilled as EventListener)
})

function onCutoffFilled(e: Event) {
  const detail = (e as CustomEvent<GCycleCutoffFilledDetail>).detail
  if (!detail?.samples?.length) return
  vc.applyCutoffResults(detail.samples, detail.fillMode ?? 'append')
}

const tabOptions = [
  { label: '凭证基础', value: 'basic' },
  { label: '核对内容', value: 'check' },
  { label: '结论', value: 'conclusion' },
]

async function onImported() {
  emit('imported')
  vc.reloadFromStore()
}

function onRowChange(row: G11VoucherCheckRow | undefined) {
  if (!row) return
  const idx = vc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.activeRowIndex.value = idx
}

function onSampleFilled(payload: { samples: Array<{ summary?: string; amount?: number; voucherDate?: string; voucherNo?: string; counterpartAccount?: string }> }) {
  for (const s of payload.samples ?? []) {
    vc.mergeSample({
      businessContent: s.summary,
      creditAmount: s.amount,
      voucherDate: s.voucherDate,
      voucherNo: s.voucherNo,
      counterAccount: s.counterpartAccount,
      source: '抽凭',
    })
  }
}

function onApplySuggested() {
  const n = vc.applySuggestedSampleSize()
  if (n) ElMessage.success(`已采用公式样本量 ${n}`)
}

async function onPushAbnormal() {
  const n = await vc.pushAbnormalToAdjustment()
  if (n > 0 && jumpToSection) {
    const go = await confirmNavigateToSheet({
      title: '已推送至 G11-3',
      message: `已追加 ${n} 笔调整草稿，是否前往 G11-3 查看？`,
      confirmText: '前往 G11-3',
    })
    if (go) jumpToSection('调整分录汇总G11-3')
  }
}

async function onMarkProcedure() {
  const res = await vc.markProcedureComplete()
  if (!res.ok) {
    ElMessage.warning(res.message)
    return
  }
  ElMessage.success(res.message)
  dispatchProcedureFocus({
    programNos: [...G11A_VOUCHER_PROGRAM_NOS],
    sheetCode: 'G11A',
    sheetName: G11A_PROCEDURE_SHEET,
  })
  if (jumpToSection) {
    const go = await confirmNavigateToSheet({
      title: '已回填 G11A',
      message: res.message + '，是否前往程序表查看？',
      confirmText: '前往 G11A',
    })
    if (go) jumpToSection(G11A_PROCEDURE_SHEET)
  }
}

function exportMemo() {
  const md = vc.buildMemo()
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `G11-5_抽样备忘_${new Date().toISOString().slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出抽样备忘')
}

async function uploadOcr(row: G11VoucherCheckRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(`/api/workpapers/${props.wpId}/g11/contract-ocr`, formData)
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
.g11-voucher-check { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-top: 16px; margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.ao-wrap { font-size: 12px; }
.ao-title { font-weight: 600; margin-bottom: 4px; }
.ao-list { margin: 0; padding-left: 18px; line-height: 1.55; }
.sampling-params-card {
  margin-bottom: 12px;
  padding: 12px;
  background: #fafbfc;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.card-title { margin: 0 0 10px; font-size: 13px; font-weight: 600; color: #303133; }
.params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px 12px;
}
.param-item { display: flex; flex-direction: column; gap: 4px; }
.param-item-wide { grid-column: 1 / -1; }
.param-label { font-size: 12px; color: #606266; }
.param-with-action { display: flex; align-items: center; gap: 4px; }
.hint-text { font-size: 11px; color: #909399; }
.legend-note { margin: 6px 0 0; font-size: 12px; color: #909399; }
.sampling-calc-row {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  margin-top: 10px; font-size: 12px; color: #606266;
}
.sampling-calc-row .muted { color: #909399; }
.sampling-calc-row .sep { color: #dcdfe6; }
.ratio-row {
  display: flex; flex-wrap: wrap; gap: 16px;
  margin-top: 8px; font-size: 12px; color: #303133;
}
.ratio-alert { margin-top: 8px; }
.methodology-block {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
}
.legend-title { font-weight: 600; font-size: 12px; color: #b88230; margin-bottom: 4px; }
.legend-list { margin: 0; padding-left: 18px; font-size: 12px; color: #606266; line-height: 1.55; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.summary-bar { padding: 8px 12px; background: #f5f7fa; font-size: 12px; margin-bottom: 8px; border-radius: 4px; }
.segment-tabs { margin-bottom: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
.conclusion-panel { margin-top: 12px; padding: 12px; background: #fafafa; border-radius: 4px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; }
</style>
