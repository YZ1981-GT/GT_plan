<!--
  G4TabImpairmentCalc.vue — G4-10 减值准备测算表

  2区段Tab：
  - Tab1: 未审数+审计调整 — Stage / ①余额 / PV / ②率 / ③减值 / ④价值 / ⑤余额调整 / ②A或审定PV / ⑥调整
  - Tab2: 审定数+差异 — ⑦⑧⑨ / 上年减值 / 本年计提转回 / 差异说明

  Stage1/2：损失率法；Stage3：现值法（⑥ = 目标审定减值 − ③ 恒等倒挤）
-->
<template>
  <div class="g4-impairment-calc">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确定债权投资减值准备计提是否充分、准确；按 Stage 分组重算并核对审定减值、账面价值及本年计提/转回。"
      style="margin-bottom: 12px"
    />

    <!-- 审计程序（对齐源底稿） -->
    <el-card class="proc-card no-print-optional" shadow="never">
      <template #header>
        <div class="card-header">
          <span>二、审计程序</span>
          <el-tag size="small" type="info">勾选后自动保存</el-tag>
        </div>
      </template>
      <el-checkbox-group v-model="procedureChecks" :disabled="isReadonly" @change="saveProcedures">
        <div class="proc-item">
          <el-checkbox label="p1">
            1. 将减值准备账面金额、审计调整金额及审定金额与明细账、试算平衡表核对是否相符
          </el-checkbox>
        </div>
        <div class="proc-item">
          <el-checkbox label="p2">
            2. 评估减值准备计提是否充分（关注内控薄弱或存在减值迹象的情形）
          </el-checkbox>
        </div>
        <div class="proc-item proc-sub">
          <el-checkbox label="p21">
            2.1 分析组合划分是否合理（会计政策、共同信用风险特征，参见 G4-9 / G4-11）
          </el-checkbox>
        </div>
        <div class="proc-item proc-sub">
          <el-checkbox label="p22">2.2 验算加计是否正确，并与总账、明细账核对</el-checkbox>
        </div>
        <div class="proc-item proc-sub">
          <el-checkbox label="p23">2.3 重新测算应计提减值，与账面比较并记录调整</el-checkbox>
        </div>
      </el-checkbox-group>
    </el-card>

    <div class="tab-toolbar no-print">
      <div class="toolbar-left">
        <G4EclImportExportDropdown
          :wp-id="wpId"
          sheet="G4-10"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G4-9" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-11" :context-project-id="projectId" /></span>
      </div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G4-10 减值准备测算表</h3>
      <div class="head-actions no-print">
        <el-segmented v-model="activeTab" :options="segmentOptions" size="small" />
        <el-select
          v-if="!isReadonly"
          v-model="newRowStage"
          size="small"
          style="width: 110px"
          placeholder="Stage"
        >
          <el-option label="Stage1" value="Stage1" />
          <el-option label="Stage2" value="Stage2" />
          <el-option label="Stage3" value="Stage3" />
        </el-select>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 投资项目
        </el-button>
        <el-button size="small" :disabled="isReadonly" :loading="pullingG49" @click="pullFromG49">
          从 G4-9 拉取阶段
        </el-button>
        <el-button size="small" :disabled="isReadonly" :loading="pullingG411" @click="pullFromG411">
          从 G4-11 拉取损失率
        </el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pushImpairmentDrafts">
          推送差异至 G4-3
        </el-button>
        <el-button size="small" @click="openReviewDialog('G4-10-impairment-calc')">💬复核</el-button>
      </div>
    </div>

    <!-- 勾稽摘要 -->
    <div class="recon-bar">
      <span>审定减值 Σ⑧ <b>{{ fmtNum(calc.grandTotal.value.adjImpairment) }}</b></span>
      <span>
        试算减值准备
        <b v-if="tbHit">{{ fmtNum(tbHit.amount) }}</b>
        <b v-else-if="reconLoading">…</b>
        <b v-else class="muted">未取到</b>
        <el-tag v-if="tbHit" size="small" type="info" class="tb-tag">{{ tbHit.code }}</el-tag>
      </span>
      <span :class="['tb-diff', { ok: tbMatched, bad: tbHasDiff }]">
        vs试算
        <b>{{ tbDiffText }}</b>
      </span>
      <span>
        G4-1减值小计
        <b v-if="g41Impairment != null">{{ fmtNum(g41Impairment) }}</b>
        <b v-else-if="reconLoading">…</b>
        <b v-else class="muted">未取到</b>
      </span>
      <span :class="['tb-diff', { ok: g41Matched, bad: g41HasDiff }]">
        vsG4-1
        <b>{{ g41DiffText }}</b>
      </span>
      <span>本年计提合计 <b>{{ fmtNum(sumCurrentProvision) }}</b></span>
      <span>本年转回合计 <b>{{ fmtNum(sumCurrentReversal) }}</b></span>
      <el-button size="small" link :loading="reconLoading" @click="refreshRecon">刷新勾稽</el-button>
    </div>

    <details class="pd-source-hint no-print">
      <summary>②信用损失率取值提示（G4-11 / 中证协参考资料）</summary>
      <ul>
        <li>Stage1：使用前瞻性调整后的未来12个月PD；剩余期限不足一年按实际期限折算。</li>
        <li>Stage2：使用前瞻性调整后的整个剩余存续期PD，不得仍按一年期PD计量。</li>
        <li>Stage3：参考PD=100%，并结合LGD、预计回收现金流和折现确定损失。</li>
        <li>PD须说明评级映射、数据版本、前瞻性调整及期限折算；资本监管风险权重不得直接替代PD。</li>
      </ul>
    </details>

    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="impairment-table"
      @current-change="onCurrentChange"
    >
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal">
            <span class="subtotal-label">{{ row._groupLabel }}小计</span>
          </template>
          <template v-else-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <el-table-column label="投资项目" width="140" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal" />
          <span v-else>{{ row.investProject }}</span>
        </template>
      </el-table-column>

      <el-table-column label="Stage" width="100" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal" />
          <template v-else>
            <el-select
              v-if="!isReadonly"
              :model-value="row.stageGroup"
              size="small"
              @change="(v: StageGroup) => updateField(row.id, 'stageGroup', v)"
            >
              <el-option label="Stage1" value="Stage1" />
              <el-option label="Stage2" value="Stage2" />
              <el-option label="Stage3" value="Stage3" />
            </el-select>
            <el-tag v-else size="small" :type="stageTagType(row.stageGroup)">{{ row.stageGroup }}</el-tag>
          </template>
        </template>
      </el-table-column>

      <!-- Tab1 -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="①账面余额" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.bookBalance) }}</span>
            </template>
            <template v-else>
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.bookBalance"
                size="small"
                class="compact-num"
                @change="(v: number) => updateField(row.id, 'bookBalance', v)"
              />
              <span v-else>{{ fmtNum(row.bookBalance) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column min-width="130" align="right">
          <template #header>
            <span :class="{ 'col-emphasis': true }">现金流量现值</span>
            <el-tooltip content="Stage3 必填：③=max(0,①−PV)。Stage1/2 可留空。" placement="top">
              <span class="header-hint">Stage3</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.pvFutureCashFlow"
                size="small"
                :controls="false"
                :class="['compact-num', { 'stage3-input': row.stageGroup === 'Stage3' }]"
                @change="(v: number) => updateField(row.id, 'pvFutureCashFlow', v)"
              />
              <span v-else>{{ fmtNum(row.pvFutureCashFlow) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="②信用损失率" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else-if="row.stageGroup === 'Stage3'">
              <span class="muted">—</span>
            </template>
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.creditLossRate"
                size="small"
                :controls="false"
                :precision="4"
                :step="0.01"
                class="compact-num"
                @change="(v: number) => updateField(row.id, 'creditLossRate', v)"
              />
              <span v-else>{{ pct(row.creditLossRate) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="③减值准备" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.impairmentProvision) }}</span>
            </template>
            <template v-else>
              <el-tooltip :content="impairmentFormulaHint(row)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.impairmentProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="④账面价值" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.bookValue) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="④ = ① − ③" placement="top">
                <span class="formula-cell">{{ fmtNum(row.bookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑤余额调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
            <template v-else>
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.balanceAdjustment"
                size="small"
                class="compact-num"
                @change="(v: number) => updateField(row.id, 'balanceAdjustment', v)"
              />
              <span v-else>{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column min-width="140" align="right">
          <template #header>
            <span>{{ activeAdjHeader }}</span>
          </template>
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else-if="row.stageGroup === 'Stage3'">
              <el-input-number
                v-if="!isReadonly"
                :model-value="displayAdjPv(row)"
                size="small"
                :controls="false"
                class="compact-num stage3-input"
                @change="(v: number) => updateField(row.id, 'adjustedPvFutureCashFlow', v)"
              />
              <span v-else>{{ fmtNum(displayAdjPv(row)) }}</span>
            </template>
            <template v-else>
              <el-input-number
                v-if="!isReadonly"
                :model-value="displayAdjRate(row)"
                size="small"
                :controls="false"
                :precision="4"
                :step="0.01"
                class="compact-num"
                @change="(v: number) => updateField(row.id, 'adjustedCreditLossRate', v)"
              />
              <span v-else>{{ pct(displayAdjRate(row)) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑥减值调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.impairmentAdjustment) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑥ = 目标审定减值 − ③（恒等倒挤，可负）" placement="top">
                <span class="formula-cell">{{ fmtNum(row.impairmentAdjustment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- Tab2 -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="⑦审定账面余额" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjBookBalance) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑦ = ① + ⑤" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjBookBalance) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑧审定减值准备" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjImpairment) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑧ = ③ + ⑥" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjImpairment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑨审定账面价值" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjBookValue) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑨ = ⑦ − ⑧" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjBookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="上年减值准备" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <WpAmountInput
                v-if="!isReadonly"
                :model-value="row.priorImpairment"
                size="small"
                class="compact-num"
                @change="(v: number) => updateField(row.id, 'priorImpairment', v)"
              />
              <span v-else>{{ fmtNum(row.priorImpairment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年计提" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-tooltip content="本年计提 = max(0, ⑧ − 上年减值)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.currentProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年转回" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-tooltip content="本年转回 = max(0, 上年减值 − ⑧)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.currentReversal) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="差异说明" min-width="150">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input
                v-if="!isReadonly"
                :model-value="row.differenceNote"
                size="small"
                @change="(v: string) => updateField(row.id, 'differenceNote', v)"
              />
              <span v-else>{{ row.differenceNote }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm
            v-if="!row._isSubtotal && !row._isTotal"
            title="确认删除？"
            @confirm="calc.removeRow(row.id)"
          >
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="!isReadonly" class="audit-ai-row no-print">
      <el-button
        size="small"
        type="primary"
        link
        :disabled="!aiAvailable"
        :loading="aiLoading"
        @click="handleAiConclusion"
      >
        🤖 AI生成
      </el-button>
    </div>
    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusion"
      note-title="三、审计说明"
      conclusion-title="四、审计结论"
      note-placeholder="填写审计说明：程序执行情况、测试结果、拟调整/未调整事项及其影响、审计范围受限情况等。"
      conclusion-placeholder="请输入减值准备测算的审计结论..."
      @update:note="saveAuditNote"
    />

    <details class="prep-hint no-print">
      <summary>编制提示【非打印】</summary>
      <ul>
        <li><b>损失率法（Stage1/2）</b>：③ = ① × ②；目标审定减值 = (①+⑤)×②A；⑥ = 目标 − ③；⑦=①+⑤；⑧=③+⑥；⑨=⑦−⑧</li>
        <li><b>现值法（Stage3 已减值）</b>：③ = max(0, ① − 未审PV)；目标审定减值 = max(0, ⑦ − 审定PV)；⑥ = 目标 − ③</li>
        <li>②A / 审定PV 未单独修改时，分别回落为② / 未审PV，避免空输入导致假冲回</li>
        <li>当企业账面③恰好等于①×②时，损失率路径⑥等价于旧展开式 ⑤×②A + ①×(②A−②)</li>
        <li>本年计提 = max(0, ⑧ − 上年减值)；本年转回 = max(0, 上年减值 − ⑧)</li>
        <li>跨表：G4-9 拉取阶段 → G4-11 回写/拉取损失率 → 本表勾稽试算与 G4-1 减值小计</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * G4TabImpairmentCalc.vue — G4-10 减值准备测算表
 */
import { ref, computed, inject, watch, onMounted, onBeforeUnmount } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG4EclImpairmentCalc, collectEclRateUpdates } from '../../composables/useG4EclImpairmentCalc'
import { useG4EclFormData } from '../../composables/useG4EclFormData'
import type { ImpairmentCalcRow } from '../../composables/useG4EclFormData'
import {
  parseChecklistRows,
  fetchG4ImpairmentTbAmount,
  fetchG41ImpairmentSubtotal,
  fetchG411MeasurementRows,
  G4_9_ROWS_KEY,
  G4_10_ROWS_KEY,
  G4_STAGE_UPDATED_EVENT,
  G4_ECL_RATE_UPDATED_EVENT,
  type G4ImpairmentTbHit,
} from '../../composables/g4CrossHelpers'
import { useWorkpaperAuditYear } from '../../composables/workpaperAuditYear'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import G4EclImportExportDropdown from '../G4EclImportExportDropdown.vue'
import { useG4EclAiGenerate } from '../../composables/useG4EclAiGenerate'
import { calcSumColumn, round2 } from '@/composables/useG4EclFormulaEngine'
import {
  buildG410ImpairmentDrafts,
  dispatchG4ExceptionDrafts,
} from '../../composables/g4ExceptionRouting'
import { buildCanonicalPayload } from '../../composables/g4StorageContract'

type StageGroup = 'Stage1' | 'Stage2' | 'Stage3'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4EclAiGenerate(wpIdRef)

const calc = useG4EclImpairmentCalc()
const conclusion = ref('')
const activeTab = ref<'tab1' | 'tab2'>('tab1')
const newRowStage = ref<StageGroup>('Stage1')
const pullingG49 = ref(false)
const pullingG411 = ref(false)
const reconLoading = ref(false)
const tbHit = ref<G4ImpairmentTbHit | null>(null)
const g41Impairment = ref<number | null>(null)
const auditYear = useWorkpaperAuditYear()

const formData = useG4EclFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const NOTE_KEY = 'G4-10-impairment-calc-audit-note'
const PROC_KEY = 'G4-10-impairment-calc-procedures'
const CONCLUSION_KEY = 'G4-10-impairment-calc-conclusion'
const auditNote = ref('')
const procedureChecks = ref<string[]>([])

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

function saveProcedures(val: string[] | unknown): void {
  if (props.isReadonly) return
  const checks = Array.isArray(val) ? val : procedureChecks.value
  formData.debouncedSave(PROC_KEY, { remark: JSON.stringify(checks) })
}

watch(conclusion, (val) => {
  if (props.isReadonly) return
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
})

const segmentOptions = [
  { label: '未审数+审计调整', value: 'tab1' },
  { label: '审定数+差异', value: 'tab2' },
]

const activeAdjHeader = computed(() => '②A / 审定PV')

interface DisplayRow extends ImpairmentCalcRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
  _groupLabel?: string
}

const displayRows = computed<DisplayRow[]>(() => {
  const grouped = calc.groupedRows.value
  const result: DisplayRow[] = []

  for (const [key, label] of [
    ['stage1', 'Stage1'],
    ['stage2', 'Stage2'],
    ['stage3', 'Stage3'],
  ] as const) {
    const g = grouped[key]
    if (g.rows.length > 0) {
      for (const r of g.rows) result.push(r as DisplayRow)
      result.push({
        ...calc.createBlankRow({
          id: `sub-${key}`,
          seq: 0,
          investProject: '',
          stageGroup: label,
        }),
        _isSubtotal: true,
        _groupLabel: label,
        ...g.subtotal,
      } as DisplayRow)
    }
  }

  result.push({
    ...calc.createBlankRow({
      id: 'grand-total',
      seq: 0,
      investProject: '',
      stageGroup: 'Stage1',
    }),
    _isTotal: true,
    ...grouped.grandTotal,
  } as DisplayRow)

  return result
})

const sumCurrentProvision = computed(() =>
  calcSumColumn(calc.rows.value.map(r => r.currentProvision)),
)
const sumCurrentReversal = computed(() =>
  calcSumColumn(calc.rows.value.map(r => r.currentReversal)),
)

/** 备抵科目取绝对值与 Σ⑧ 比较（方向因 TB 借贷列示可能不同） */
const tbDiff = computed(() => {
  if (tbHit.value == null) return null
  return round2(Math.abs(tbHit.value.amount) - Math.abs(calc.grandTotal.value.adjImpairment))
})
const tbMatched = computed(() => tbDiff.value != null && Math.abs(tbDiff.value) <= 0.01)
const tbHasDiff = computed(() => tbDiff.value != null && Math.abs(tbDiff.value) > 0.01)
const tbDiffText = computed(() => {
  if (reconLoading.value) return '…'
  if (tbDiff.value == null) return '—'
  if (tbMatched.value) return '0.00（相符）'
  return fmtNum(tbDiff.value)
})

const g41Diff = computed(() => {
  if (g41Impairment.value == null) return null
  return round2(Math.abs(g41Impairment.value) - Math.abs(calc.grandTotal.value.adjImpairment))
})
const g41Matched = computed(() => g41Diff.value != null && Math.abs(g41Diff.value) <= 0.01)
const g41HasDiff = computed(() => g41Diff.value != null && Math.abs(g41Diff.value) > 0.01)
const g41DiffText = computed(() => {
  if (reconLoading.value) return '…'
  if (g41Diff.value == null) return '—'
  if (g41Matched.value) return '0.00（相符）'
  return fmtNum(g41Diff.value)
})

async function refreshRecon(): Promise<void> {
  reconLoading.value = true
  try {
    const [tb, g41] = await Promise.all([
      fetchG4ImpairmentTbAmount(props.projectId, auditYear.value),
      fetchG41ImpairmentSubtotal(props.wpId),
    ])
    tbHit.value = tb
    g41Impairment.value = g41
  } finally {
    reconLoading.value = false
  }
}

async function pullFromG49(): Promise<void> {
  if (props.isReadonly) return
  pullingG49.value = true
  try {
    try { await formData.loadAll() } catch { /* ignore */ }
    const g49 = parseChecklistRows(formData.allResponses.value.get(G4_9_ROWS_KEY))
    const updates = g49
      .filter((r: any) => String(r?.investProject || '').trim() && r?.auditStage)
      .map((r: any) => ({
        investProject: String(r.investProject).trim(),
        auditStage: r.auditStage as StageGroup,
        bookBalance: Number(r.bookBalance) || 0,
      }))
    if (!updates.length) {
      ElMessage.warning('G4-9 无可用投资项目/阶段，请先完成三阶段划分')
      return
    }
    const n = calc.applyStageUpdates(updates)
    persistRows()
    ElMessage.success(`已从 G4-9 同步 ${n} 条阶段`)
  } catch {
    ElMessage.error('从 G4-9 拉取失败')
  } finally {
    pullingG49.value = false
  }
}

async function pullFromG411(): Promise<void> {
  if (props.isReadonly) return
  pullingG411.value = true
  try {
    const measurement = await fetchG411MeasurementRows(props.wpId)
    if (!measurement) {
      ElMessage.warning('未找到 G4-11 测算数据，请先在 G4-11 完成损失率测试并保存')
      return
    }
    const updates = collectEclRateUpdates(measurement.pdLgdRows, measurement.lossRateRows, 'lossRate')
    if (!updates.length) {
      ElMessage.warning('G4-11 无有效损失率行（需填写项目名称与 ECL 率）')
      return
    }
    const result = calc.applyEclRateUpdates(updates)
    const payload = buildCanonicalPayload(G4_10_ROWS_KEY, calc.toJSON())
    await formData.saveImmediate(G4_10_ROWS_KEY, payload)
    const report = result.matchReport
    const skipHint = result.skipped.length
      ? `；未匹配 ${report.unmatched.length}，ID匹配 ${report.byId.length}，名称匹配 ${report.byName.length}`
      : `（ID匹配 ${report.byId.length}，名称匹配 ${report.byName.length}）`
    ElMessage.success(`已从 G4-11 回写 ${result.count} 条损失率${skipHint}`)
  } catch {
    ElMessage.error('从 G4-11 拉取损失率失败')
  } finally {
    pullingG411.value = false
  }
}

function onEclRateUpdated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (detail?.written) {
    void formData.loadAll().then(() => {
      const saved = formData.allResponses.value.get(G4_10_ROWS_KEY)
      const list = parseChecklistRows(saved)
      if (list.length) calc.loadRows(list as ImpairmentCalcRow[])
    })
    return
  }
  const updates = detail?.updates
  if (!Array.isArray(updates) || !updates.length) return
  calc.applyEclRateUpdates(updates)
  persistRows()
}

function displayAdjRate(row: ImpairmentCalcRow): number {
  return calc.effectiveAdjRate(row)
}

function displayAdjPv(row: ImpairmentCalcRow): number {
  return calc.effectiveAdjPv(row)
}

function impairmentFormulaHint(row: ImpairmentCalcRow): string {
  return row.stageGroup === 'Stage3'
    ? '③ = max(0, ① − 现金流量现值)'
    : '③ = ① × ②'
}

function stageTagType(stage: string): 'success' | 'warning' | 'danger' | 'info' {
  if (stage === 'Stage1') return 'success'
  if (stage === 'Stage2') return 'warning'
  if (stage === 'Stage3') return 'danger'
  return 'info'
}

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isSubtotal || row._isTotal) return
  const idx = calc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) calc.activeRowIndex.value = idx
}

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isSubtotal) return 'row-subtotal'
  if (row._isTotal) return 'row-total'
  if (row.stageGroup === 'Stage3') return 'row-stage3'
  return ''
}

function updateField(id: string, field: keyof ImpairmentCalcRow, value: any) {
  const row = calc.rows.value.find(r => r.id === id)
  if (!row) return

  if (field === 'creditLossRate') {
    const prev = row.creditLossRate
    const wasSynced = !row.adjRateTouched || row.adjustedCreditLossRate === prev
    row.creditLossRate = value ?? 0
    if (wasSynced && !row.adjRateTouched) {
      row.adjustedCreditLossRate = row.creditLossRate
    }
  } else if (field === 'adjustedCreditLossRate') {
    row.adjustedCreditLossRate = value ?? 0
    row.adjRateTouched = true
  } else if (field === 'pvFutureCashFlow') {
    const prev = row.pvFutureCashFlow
    const wasSynced = !row.adjPvTouched || row.adjustedPvFutureCashFlow === prev
    row.pvFutureCashFlow = value ?? 0
    if (wasSynced && !row.adjPvTouched) {
      row.adjustedPvFutureCashFlow = row.pvFutureCashFlow
    }
  } else if (field === 'adjustedPvFutureCashFlow') {
    row.adjustedPvFutureCashFlow = value ?? 0
    row.adjPvTouched = true
  } else {
    ;(row as any)[field] = value ?? (typeof (row as any)[field] === 'number' ? 0 : value)
  }

  calc.recalcRow(row)
}

async function handleAddRow() {
  await calc.addRow(newRowStage.value)
}

function pushImpairmentDrafts(): void {
  const drafts = buildG410ImpairmentDrafts(calc.rows.value, formData.allResponses.value)
  if (!drafts.length) {
    ElMessage.info('没有可推送的减值差异')
    return
  }
  dispatchG4ExceptionDrafts(drafts, formData.allResponses.value)
  ElMessage.success(`已推送 ${drafts.length} 条 G4-3 草稿行`)
}

async function handleAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'ecl-measurement-conclusion',
    conclusion.value || '',
    {},
    'AI 审计结论',
  )
  if (text) conclusion.value = text
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

function pct(v: number): string {
  return `${((v ?? 0) * 100).toFixed(2)}%`
}

let persistTimer: ReturnType<typeof setTimeout> | null = null

function persistRows(): void {
  if (props.isReadonly) return
  formData.debouncedSave(
    G4_10_ROWS_KEY,
    buildCanonicalPayload(G4_10_ROWS_KEY, calc.toJSON()),
  )
}

function schedulePersistRows(): void {
  if (props.isReadonly) return
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => persistRows(), 800)
}

watch(() => calc.rows.value, () => schedulePersistRows(), { deep: true })

function onStageUpdated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (detail?.written) {
    void formData.loadAll().then(() => {
      const saved = formData.allResponses.value.get(G4_10_ROWS_KEY)
      const list = parseChecklistRows(saved)
      if (list.length) calc.loadRows(list as ImpairmentCalcRow[])
    })
    return
  }
  const updates = detail?.updates
  if (!Array.isArray(updates) || !updates.length) return
  calc.applyStageUpdates(updates)
  persistRows()
}

onMounted(async () => {
  if (props.htmlData?.impairmentCalc) {
    const data = props.htmlData.impairmentCalc
    if (data.rows) calc.loadRows(data.rows)
    if (data.conclusion) conclusion.value = data.conclusion
  }
  await formData.loadAll()
  const savedRows = parseChecklistRows(formData.allResponses.value.get(G4_10_ROWS_KEY))
  if (savedRows.length) {
    calc.loadRows(savedRows as ImpairmentCalcRow[])
  }
  const note = formData.allResponses.value.get(NOTE_KEY)
  if (note?.remark) auditNote.value = note.remark
  const conc = formData.allResponses.value.get(CONCLUSION_KEY)
  if (conc?.remark) conclusion.value = conc.remark
  const proc = formData.allResponses.value.get(PROC_KEY)
  if (proc?.remark) {
    try {
      const parsed = JSON.parse(proc.remark)
      if (Array.isArray(parsed)) procedureChecks.value = parsed
    } catch {
      /* ignore */
    }
  }
  window.addEventListener(G4_STAGE_UPDATED_EVENT, onStageUpdated)
  window.addEventListener(G4_ECL_RATE_UPDATED_EVENT, onEclRateUpdated)
  void refreshRecon()
})

onBeforeUnmount(() => {
  if (persistTimer) clearTimeout(persistTimer)
  window.removeEventListener(G4_STAGE_UPDATED_EVENT, onStageUpdated)
  window.removeEventListener(G4_ECL_RATE_UPDATED_EVENT, onEclRateUpdated)
})

defineExpose({
  toJSON: () => ({
    rows: calc.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g4-impairment-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.proc-card {
  margin-bottom: 12px;
}
.proc-item {
  margin-bottom: 4px;
}
.proc-sub {
  padding-left: 20px;
}

.recon-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f4f7fb;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.recon-bar b {
  color: #303133;
  font-variant-numeric: tabular-nums;
}
.tb-tag {
  margin-left: 4px;
}
.tb-diff.ok b {
  color: #67c23a;
}
.tb-diff.bad b {
  color: #f56c6c;
}
.recon-hint {
  color: #909399;
}

.pd-source-hint {
  margin-bottom: 10px;
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  color: #8b6914;
  font-size: 12px;
  line-height: 1.65;
}
.pd-source-hint summary {
  cursor: pointer;
  font-weight: 600;
}
.pd-source-hint ul {
  margin: 8px 0 0;
  padding-left: 20px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.audit-ai-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.proc-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.impairment-table {
  font-size: var(--wp-font-size, 13px);
}

.compact-num {
  width: 100%;
}
.compact-num :deep(.el-input__inner) {
  text-align: right;
}

.stage3-input :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}

.header-hint {
  margin-left: 4px;
  font-size: 10px;
  color: #e6a23c;
  font-weight: 600;
}

.col-emphasis {
  font-weight: 600;
}

.muted {
  color: #c0c4cc;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 50px;
  text-align: right;
}

:deep(.row-subtotal) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
:deep(.row-subtotal td) {
  background-color: #f5f7fa !important;
}
:deep(.row-stage3) {
  background-color: #fdf6ec !important;
}
:deep(.row-stage3 td) {
  background-color: #fdf6ec !important;
}

.subtotal-label {
  color: #606266;
  font-weight: 600;
  font-size: 12px;
}
.subtotal-num {
  font-weight: 600;
  color: #303133;
}

:deep(.row-total) {
  background-color: #ecf5ff !important;
  font-weight: 700;
}
:deep(.row-total td) {
  background-color: #ecf5ff !important;
}
.total-label {
  color: #409eff;
  font-weight: 700;
}

.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}

@media print {
  .no-print {
    display: none !important;
  }
  .recon-bar {
    break-inside: avoid;
  }
  .g4-impairment-calc {
    padding: 0;
  }
  :deep(.el-card) {
    border: none;
    box-shadow: none !important;
  }
}
</style>
