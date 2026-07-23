<template>
  <div class="i3-tab-detail">
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span><span>原值滚动：期初→增加→减少→期末，再未审+调整→审定</span></div>
        <div class="guidance-step"><span class="step-num">②</span><span>减值滚动：同期结构；本期计提对接 I3-6，处置转出走减少</span></div>
        <div class="guidance-step"><span class="step-num">③</span><span>净值=原值审定−减值审定（商誉不摊销、减值不可转回）</span></div>
        <div class="guidance-step"><span class="step-num">④</span><span>合计勾稽 I3-1；新增商誉核对入账测算 / I3-4</span></div>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>I3-2 编制逻辑（对齐 Excel 双表）：</strong>
        左表记录商誉<strong>原值</strong>滚动，右表记录<strong>减值准备</strong>滚动；
        同一被投资单位两表并行。存在性/完整性看增减变动及支持证据，计价看减值测试（I3-6/I3-7）与账项调整。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：存在性、完整性、计价和分摊——逐项核实商誉原值与减值准备的期初、本期增减及期末审定数；明细合计与 I3-1 审定表勾稽一致（CAS8、CAS20）。"
    />

    <el-alert
      v-if="crossValidation.hasAnyWarning"
      type="warning"
      :closable="false"
      class="cross-validation-alert"
    >
      <template #default>
        <div class="cross-validation-content">
          <span>明细合计与 I3-1 审定表不一致：</span>
          <span v-if="crossValidation.hasOriginalWarning" class="warning-item">
            原值审定差异 {{ fmtAmount(crossValidation.goodwillOriginalDiff) }}
          </span>
          <span v-if="crossValidation.hasImpairmentWarning" class="warning-item">
            减值审定差异 {{ fmtAmount(crossValidation.accImpairmentDiff) }}
          </span>
          <span v-if="crossValidation.hasNetValueWarning" class="warning-item">
            净值差异 {{ fmtAmount(crossValidation.netValueDiff) }}
          </span>
        </div>
      </template>
    </el-alert>

    <el-alert
      v-if="hasRollForwardWarning"
      type="error"
      :closable="false"
      class="cross-validation-alert"
      title="滚动勾稽异常：存在期末≠期初+增加−减少，或审定≠未审+调整的行，请检查录入。"
    />

    <el-alert
      v-if="entryVarianceWarnings.length"
      type="warning"
      :closable="false"
      class="cross-validation-alert"
    >
      <template #default>
        <div class="cross-validation-content">
          <span>入账测算与原值滚动差异（I3-4）：</span>
          <span v-for="v in entryVarianceWarnings" :key="v.investee" class="warning-item">
            {{ v.investee }} 测算{{ fmtAmount(v.entryCalc) }} vs 本期增加{{ fmtAmount(v.costIncrease) }}
            （差 {{ fmtAmount(v.diffVsIncrease) }}）
          </span>
        </div>
      </template>
    </el-alert>

    <el-alert
      v-if="ajeVarianceWarnings.length"
      type="warning"
      :closable="false"
      class="cross-validation-alert"
    >
      <template #default>
        <div class="cross-validation-content">
          <span>I3-3 账项调整与明细列不一致（可点「从 I3-3 回写调整」）：</span>
          <span v-for="v in ajeVarianceWarnings" :key="v.investee" class="warning-item">
            <template v-if="v.investee === '未指定'">有分录未填被投资单位</template>
            <template v-else-if="v.missingOnDetail">
              {{ v.investee }} 在 I3-3 有调整但明细无此行
            </template>
            <template v-else>
              {{ v.investee }} 原值AJE差 {{ fmtAmount(v.costDiff) }} / 减值AJE差 {{ fmtAmount(v.impDiff) }}
            </template>
          </span>
        </div>
      </template>
    </el-alert>

    <div class="xref-bar">
      <span class="xref-label">交叉索引：</span>
      <GtIndexChip value="I3-1" label="审定表" @click="navigate('I3-1')" />
      <GtIndexChip value="I3-3" label="调整分录" @click="navigate('I3-3')" />
      <GtIndexChip value="I3-4" label="入账测算" @click="navigate('I3-4')" />
      <GtIndexChip value="I3-6" label="减值测试" @click="navigate('I3-6')" />
      <GtIndexChip value="wp:I3-2" :context-project-id="projectId" />
      <template v-if="!isReadonly">
        <el-button size="small" type="primary" plain @click="handleSyncFromI36">从 I3-6 带入本期计提</el-button>
        <el-button size="small" plain @click="handleSyncFromI33">从 I3-3 回写调整</el-button>
        <el-button size="small" plain @click="handleSyncFromI34">从 I3-4 带入新增</el-button>
      </template>
      <el-button size="small" :type="dualView ? 'success' : 'default'" @click="dualView = !dualView">
        {{ dualView ? '退出并排' : '原值|减值并排' }}
      </el-button>
    </div>

    <div class="toolbar-row tab-toolbar" v-if="!dualView">
      <el-segmented
        v-model="activeSectionKey"
        :options="segmentOptions"
        class="segment-bar"
      />
      <div class="toolbar-right">
        <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddRow">+ 新增</el-button>
        <el-dropdown v-if="!isReadonly" trigger="click">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="() => void exportTemplate('I3-2')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="() => void exportData('I3-2')">导出数据</el-dropdown-item>
              <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onImportFileSelected" />
        <span class="row-count">共 {{ rows.length }} 行</span>
        <span class="net-chip">净值合计 <strong>{{ fmtAmount(summaryRow.goodwillNetValue) }}</strong></span>
        <span class="mov-chip">本期借方 <strong>{{ fmtAmount(summaryRow.periodDebit) }}</strong></span>
        <span class="mov-chip">本期贷方 <strong>{{ fmtAmount(summaryRow.periodCredit) }}</strong></span>
      </div>
    </div>

    <!-- 宽屏并排：原值 | 减值 -->
    <div v-if="dualView" class="dual-view">
      <div class="dual-pane">
        <div class="dual-title">商誉明细表（原值）</div>
        <el-table :data="rows" border size="small" max-height="420" row-key="rowId">
          <el-table-column type="index" width="40" />
          <el-table-column
            v-for="col in costColumns"
            :key="'d-c-' + col.key"
            :prop="col.key"
            :label="col.label"
            :min-width="col.width"
            :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
          >
            <template #default="{ row, $index }">
              <span v-if="col.type === 'formula'" class="formula-value">{{ fmtAmount((row as any)[col.key]) }}</span>
              <el-input-number
                v-else-if="col.type === 'number' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                :controls="false"
                class="cell-input-number"
                @change="(val: number | undefined) => handleCellChange($index, col.key, val ?? 0)"
              />
              <el-input
                v-else-if="col.type === 'text' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                @change="(val: string) => handleCellChange($index, col.key, val)"
              />
              <el-select
                v-else-if="col.type === 'select' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                clearable
                @change="(val: string) => handleCellChange($index, col.key, val ?? '')"
              >
                <el-option v-for="opt in col.options" :key="opt" :label="opt || '（空）'" :value="opt" />
              </el-select>
              <span v-else>{{ col.type === 'number' ? fmtAmount((row as any)[col.key]) : ((row as any)[col.key] || '-') }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="dual-pane">
        <div class="dual-title">商誉明细表（减值准备）</div>
        <el-table :data="rows" border size="small" max-height="420" row-key="rowId">
          <el-table-column type="index" width="40" />
          <el-table-column
            v-for="col in impairmentColumns"
            :key="'d-i-' + col.key"
            :prop="col.key"
            :label="col.label"
            :min-width="col.width"
            :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
          >
            <template #default="{ row, $index }">
              <span v-if="col.type === 'formula'" class="formula-value">{{ fmtAmount((row as any)[col.key]) }}</span>
              <el-input-number
                v-else-if="col.type === 'number' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                :controls="false"
                class="cell-input-number"
                @change="(val: number | undefined) => handleCellChange($index, col.key, val ?? 0)"
              />
              <el-select
                v-else-if="col.key === 'cguName' && !isReadonly"
                :model-value="row.cguName"
                size="small"
                filterable
                allow-create
                clearable
                style="width:100%"
                @change="(v: string) => handleCellChange($index, 'cguName', v ?? '')"
              >
                <el-option v-for="n in cguNameOptions" :key="n" :label="n" :value="n" />
              </el-select>
              <el-select
                v-else-if="col.type === 'select' && col.editable && !isReadonly"
                :model-value="(row as any)[col.key]"
                size="small"
                clearable
                @change="(val: string) => handleCellChange($index, col.key, val ?? '')"
              >
                <el-option v-for="opt in col.options" :key="opt" :label="opt || '（空）'" :value="opt" />
              </el-select>
              <span v-else>{{ col.type === 'number' ? fmtAmount((row as any)[col.key]) : ((row as any)[col.key] || '-') }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 单表区段模式 -->
    <el-table
      v-else
      :data="rows"
      border
      size="small"
      highlight-current-row
      :current-row-key="activeRowKey"
      row-key="rowId"
      class="detail-table"
      :row-class-name="getRowClassName"
      max-height="480"
      @current-change="onCurrentRowChange"
    >
      <el-table-column type="index" label="#" width="45" align="center" fixed="left" />

      <el-table-column
        v-for="col in activeColumns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :min-width="col.width"
        :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
      >
        <template v-if="col.type === 'formula'" #header>
          <el-tooltip :content="col.tooltip" placement="top">
            <span class="formula-col-header">{{ col.label }}</span>
          </el-tooltip>
        </template>

        <template #default="{ row, $index }">
          <span v-if="col.type === 'formula'" class="formula-value">
            <el-tooltip :content="col.tooltip" placement="top">
              <span>{{ fmtAmount((row as any)[col.key]) }}</span>
            </el-tooltip>
          </span>

          <el-input-number
            v-else-if="col.type === 'number' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            size="small"
            :controls="false"
            :precision="2"
            class="cell-input-number"
            @change="(val: number | undefined) => handleCellChange($index, col.key, val ?? 0)"
          />

          <el-select
            v-else-if="col.key === 'cguName' && !isReadonly"
            :model-value="(row as any)[col.key]"
            size="small"
            class="cell-select"
            filterable
            allow-create
            clearable
            @change="(val: string) => handleCellChange($index, col.key, val ?? '')"
          >
            <el-option v-for="n in cguNameOptions" :key="n" :label="n" :value="n" />
          </el-select>

          <el-input
            v-else-if="col.type === 'text' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            size="small"
            class="cell-input-text"
            @change="(val: string) => handleCellChange($index, col.key, val)"
          />

          <el-date-picker
            v-else-if="col.type === 'date' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            class="cell-date-picker"
            @change="(val: string) => handleCellChange($index, col.key, val)"
          />

          <el-select
            v-else-if="col.type === 'select' && col.editable && !isReadonly"
            :model-value="(row as any)[col.key]"
            size="small"
            class="cell-select"
            clearable
            @change="(val: string) => handleCellChange($index, col.key, val ?? '')"
          >
            <el-option v-for="opt in col.options" :key="opt" :label="opt || '（空）'" :value="opt" />
          </el-select>

          <span v-else class="cell-readonly">
            {{ col.type === 'number' ? fmtAmount((row as any)[col.key]) : ((row as any)[col.key] || '-') }}
          </span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="80" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" text @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-section" v-if="!dualView">
      <el-table :data="[summaryDisplayRow]" border size="small" class="summary-table">
        <el-table-column label="#" width="45" align="center">
          <template #default><span class="summary-label">合计</span></template>
        </el-table-column>
        <el-table-column
          v-for="col in activeColumns"
          :key="'sum-' + col.key"
          :prop="col.key"
          :label="col.label"
          :min-width="col.width"
          :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
        >
          <template #default="{ row }">
            <span class="summary-value">{{ getSummaryValue(row, col) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="80" />
      </el-table>
    </div>
    <div v-else class="summary-section dual-summary">
      <span>原值审定合计 <strong>{{ fmtAmount(summaryRow.costAudited) }}</strong></span>
      <span>减值审定合计 <strong>{{ fmtAmount(summaryRow.impAudited) }}</strong></span>
      <span class="net-chip">净值合计 <strong>{{ fmtAmount(summaryRow.goodwillNetValue) }}</strong></span>
      <span>本期借方发生额 <strong>{{ fmtAmount(summaryRow.periodDebit) }}</strong></span>
      <span>本期贷方发生额 <strong>{{ fmtAmount(summaryRow.periodCredit) }}</strong></span>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="记录增减变动核查、同一控制/非同一控制区分、与 I3-4/I3-6 勾稽情况等…"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>四、审计结论</span>
          <el-select
            v-if="!isReadonly"
            size="small"
            placeholder="插入结论模板"
            style="width: 220px"
            @change="applyConclusionTemplate"
          >
            <el-option v-for="t in CONCLUSION_TEMPLATES" :key="t.key" :label="t.label" :value="t.key" />
          </el-select>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="商誉明细的审计结论…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="guidance-details" open>
      <summary>编制说明</summary>
      <div class="guidance-content">
        <ol>
          <li>原值与减值准备分表滚动：期末 = 期初 + 本期增加 − 本期减少；审定 = 未审 + 账项调整。</li>
          <li>商誉不摊销；减值准备一经确认不得转回——本期减少仅用于处置子公司等转出，不得填「转回」。</li>
          <li>非同一控制下企业合并形成的商誉，入账测算（合并成本−可辨认净资产公允份额）应与原值本期增加/审定勾稽，详见 I3-4。</li>
          <li>同一控制下企业合并不确认新商誉；账面商誉来自被合并方原已确认金额，需在备注说明。</li>
          <li>本期减值计提应与 I3-6 合并确认商誉减值勾稽；处置减少应有股权处置底稿索引。</li>
          <li>明细原值审定合计、减值审定合计、净值合计须与 I3-1 审定表一致。</li>
          <li>本期借方发生额＝原值本期增加；本期贷方发生额＝原值本期减少＋减值本期计提——合计供 I3-5 检查比例勾稽（对齐 Excel N/O 列）。</li>
        </ol>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabDetail.vue — I3-2 商誉明细表（原值/减值双表滚动）
 */
import { computed, toRef, watch, ref, inject, type Ref } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fmtAmount } from '@/utils/formatters'
import {
  useI3Detail,
  type I3DetailRow,
  type I3DetailSection,
  I3_DETAIL_SECTION_LABELS,
} from '../../composables/useI3Detail'
import { useI3CrossSheet } from '../../composables/useI3CrossSheet'
import { useI3ImportExport } from '../../composables/useI3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  adjGoodwillOriginalSubtotal?: number
  adjAccImpairmentSubtotal?: number
  adjNetValueSubtotal?: number
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

const {
  rows,
  activeSection,
  activeRowIndex,
  summaryRow,
  crossValidation,
  hasRollForwardWarning,
  activeColumns,
  costColumns,
  impairmentColumns,
  switchSection,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
  syncImpIncreaseFromI3_6,
  syncAjeFromI3_3,
  syncFromI3_4,
} = useI3Detail(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'allResponses') as Ref<Map<string, any>>,
  {
    adjGoodwillOriginalSubtotal: toRef(props, 'adjGoodwillOriginalSubtotal') as Ref<number>,
    adjAccImpairmentSubtotal: toRef(props, 'adjAccImpairmentSubtotal') as Ref<number>,
    adjNetValueSubtotal: toRef(props, 'adjNetValueSubtotal') as Ref<number>,
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

const injectedCross = inject<ReturnType<typeof useI3CrossSheet> | null>('i3CrossSheet', null)
const allResponsesRef = computed(() => props.allResponses)
const localCross = injectedCross || useI3CrossSheet(allResponsesRef as any)
const {
  impairmentByCgu,
  adjustmentSync,
  initialValueRows,
  entryVariances,
  ajeVariances,
  cguNameOptions,
} = localCross

const dualView = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const {
  exportTemplate,
  exportData,
  importData,
} = useI3ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
})

const entryVarianceWarnings = computed(() =>
  entryVariances.value.filter((v) => Math.abs(v.diffVsIncrease) > 0.01 && v.entryCalc > 0),
)

const ajeVarianceWarnings = computed(() => ajeVariances.value)

const segmentOptions = I3_DETAIL_SECTION_LABELS.map((label, idx) => ({
  label,
  value: idx as I3DetailSection,
}))

const activeSectionKey = computed({
  get: () => activeSection.value,
  set: (val: I3DetailSection) => switchSection(val),
})

const activeRowKey = computed(() => {
  if (activeRowIndex.value < 0 || activeRowIndex.value >= rows.value.length) return ''
  return rows.value[activeRowIndex.value]?.rowId ?? ''
})

const CONCLUSION_TEMPLATES = [
  {
    key: 'ok',
    label: '勾稽一致、列示恰当',
    text: '经核查，商誉原值及减值准备明细滚动勾稽正确，增减变动有适当支持，明细合计与 I3-1 审定表一致。商誉明细在所有重大方面列示恰当。',
  },
  {
    key: 'aje',
    label: '已提账项调整',
    text: '商誉明细经审计后已提出账项调整（见 I3-3）。调整后原值/减值准备审定数与 I3-1 勾稽一致，我们认为相关认定在所有重大方面公允反映。',
  },
  {
    key: 'impairment',
    label: '本期计提减值',
    text: '本期商誉减值准备增加已与 I3-6 减值测试结论勾稽。商誉减值一经确认不得转回。除上述事项外，明细滚动及审定数列示恰当。',
  },
]

const summaryDisplayRow = computed(() => {
  const s = summaryRow.value
  const sec = activeSection.value
  if (sec === 0) {
    return {
      investee: '合计',
      costOpening: s.costOpening,
      costIncrease: s.costIncrease,
      costIncreaseMethod: '',
      costDecrease: s.costDecrease,
      costDecreaseReason: '',
      costEnding: s.costEnding,
      costUnadj: s.costUnadj,
      costAje: s.costAje,
      costAudited: s.costAudited,
    }
  }
  if (sec === 1) {
    return {
      investee: '合计',
      impOpening: s.impOpening,
      impIncrease: s.impIncrease,
      impIncreaseMethod: '',
      impDecrease: s.impDecrease,
      impDecreaseReason: '',
      impEnding: s.impEnding,
      impUnadj: s.impUnadj,
      impAje: s.impAje,
      impAudited: s.impAudited,
      goodwillNetValue: s.goodwillNetValue,
      cguName: '',
    }
  }
  if (sec === 2) {
    return {
      investee: '合计',
      mergerCost: s.mergerCost,
      netAssetFairValue: s.netAssetFairValue,
      entryGoodwillCalc: s.entryGoodwillCalc,
      costAudited: s.costAudited,
      minorityInterest: s.minorityInterest,
      costConsideration: s.costConsideration,
      costContingent: s.costContingent,
      costTransactionFee: s.costTransactionFee,
      mergerDate: '',
      valuationMethod: '',
      entryRemark: '',
    }
  }
  return {
    investee: '合计',
    acquisitionDate: '',
    consideration: s.consideration,
    counterpartyNetAsset: s.counterpartyNetAsset,
    shareholding: '',
    controlType: '',
    mergerType: '',
    equityLevel: '',
    industry: '',
    impairmentTestMethod: '',
    impairmentIndicator: '',
    basicRemark: '',
  }
})

function onCurrentRowChange(row: I3DetailRow | null): void {
  if (!row) return
  const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) setActiveRow(idx)
}

function handleCellChange(rowIndex: number, field: string, value: string | number): void {
  updateCell(rowIndex, field as keyof I3DetailRow, value)
}

async function handleAddRow(): Promise<void> {
  await addRow()
}

function handleRemoveRow(index: number): void {
  removeRow(index)
}

function handleSyncFromI36() {
  const n = syncImpIncreaseFromI3_6(impairmentByCgu.value)
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已从 I3-6 更新 ${n} 行本期计提` : '无匹配 CGU 可更新（请先填写所属CGU）')
}

function handleSyncFromI33() {
  const result = syncAjeFromI3_3(adjustmentSync.value.byInvestee)
  const tips: string[] = []
  if (result.updated > 0) tips.push(`已回写 ${result.updated} 行`)
  if (result.unmatched.length) tips.push(`未匹配明细：${result.unmatched.slice(0, 3).join('、')}${result.unmatched.length > 3 ? '…' : ''}`)
  if (result.unspecified) tips.push('部分分录未填被投资单位')
  if (!tips.length) {
    ElMessage.info('无差异可回写（或无可匹配被投资单位）')
    return
  }
  ElMessage[result.updated > 0 ? (result.unmatched.length || result.unspecified ? 'warning' : 'success') : 'warning'](
    tips.join('；'),
  )
}

function handleSyncFromI34() {
  const n = syncFromI3_4(initialValueRows.value)
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已从 I3-4 更新 ${n} 行` : '无匹配入账测算可带入')
}

function triggerImport() {
  fileInputRef.value?.click()
}

async function onImportFileSelected(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await importData('I3-2', file)
}

function navigate(code: string): void {
  emit('navigate-sheet', code)
}

function getRowClassName({ row, rowIndex }: { row: I3DetailRow; rowIndex: number }): string {
  const classes: string[] = []
  if (rowIndex === activeRowIndex.value) classes.push('active-synced-row')
  if (row.impIncrease > 0) classes.push('row-impaired')
  return classes.join(' ')
}

function getSummaryValue(row: Record<string, any>, col: { key: string; type: string }): string {
  const val = row[col.key]
  if (val == null || val === '') return '-'
  if (col.type === 'number' || col.type === 'formula') return fmtAmount(val as number)
  return String(val)
}

const NOTE_KEY = 'I3-2-audit-note'
const CONCLUSION_KEY = 'I3-2-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', CONCLUSION_KEY, val)
}

function applyConclusionTemplate(key: string): void {
  const t = CONCLUSION_TEMPLATES.find((x) => x.key === key)
  if (!t) return
  auditConclusion.value = t.text
  saveAuditConclusion(t.text)
}

watch(
  () => props.allResponses,
  () => {
    const n = props.allResponses.get(NOTE_KEY)
    if (n?.remark != null) auditNote.value = n.remark
    const c = props.allResponses.get(CONCLUSION_KEY)
    if (c?.remark != null) auditConclusion.value = c.remark
  },
  { immediate: true },
)
</script>

<style scoped>
.i3-tab-detail {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border: 1px solid #b3d8f0;
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 12px;
}
.guidance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 20px;
}
.guidance-step {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 12px;
  color: #1a5276;
  line-height: 1.5;
}
.step-num {
  display: inline-flex;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2980b9;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-context p { margin: 0; }

.objective-alert { margin-bottom: 12px; }
.cross-validation-alert { margin-bottom: 10px; }
.cross-validation-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.warning-item {
  padding: 2px 8px;
  background: #fef9c3;
  border-radius: 4px;
  font-weight: 500;
}

.xref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  font-size: 12px;
}
.xref-label { color: var(--el-text-color-secondary); }

.dual-view {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
@media (max-width: 1100px) {
  .dual-view { grid-template-columns: 1fr; }
}
.dual-pane {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px;
  background: #fff;
  overflow: auto;
}
.dual-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
  color: #1a5276;
}

.toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 16px;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.row-count { color: var(--el-text-color-secondary); font-size: 12px; }
.net-chip {
  font-size: 12px;
  padding: 2px 10px;
  background: #f0fdf4;
  border-radius: 4px;
  color: #166534;
}
.mov-chip {
  font-size: 12px;
  padding: 2px 10px;
  background: #eff6ff;
  border-radius: 4px;
  color: #1e40af;
}

.detail-table { font-size: var(--wp-font-size, 13px); }
.detail-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f8fafc;
}
.detail-table :deep(.active-synced-row) { background: #eff6ff !important; }
.detail-table :deep(.row-impaired) { background: #fef0f0 !important; }

.formula-col-header {
  border-bottom: 1px dashed #6b7280;
  cursor: help;
}
.formula-value {
  border-bottom: 1px dashed #9ca3af;
  cursor: help;
  font-weight: 500;
}

.cell-input-number { width: 100%; }
.cell-input-number :deep(.el-input__inner) { text-align: right; }
.cell-input-text, .cell-date-picker, .cell-select { width: 100%; }
.cell-readonly { color: var(--el-text-color-regular); }

.summary-section {
  margin-top: 8px;
  position: sticky;
  bottom: 0;
  z-index: 5;
}
.dual-summary {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #f0fdf4;
  border-radius: 6px;
  font-size: 13px;
  color: #166534;
}
.summary-table :deep(.el-table__header) { display: none; }
.summary-table :deep(tr td) {
  background: #f0fdf4 !important;
  font-weight: 600;
}
.summary-label, .summary-value { color: #166534; font-weight: 700; }

.audit-note-card { margin-top: 12px; }
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.guidance-details {
  margin-top: 14px;
  font-size: 12px;
  color: #1a5276;
  background: #f5f8fb;
  border: 1px solid #d6e4f0;
  border-radius: 6px;
  padding: 10px 14px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; }
.guidance-content ol {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.85;
  color: #2c5282;
}
</style>
