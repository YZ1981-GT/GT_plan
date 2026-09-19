<template>
  <div class="g11-return-rate">
    <div class="guide-strip">
      <div class="guide-step"><span class="step-num">1</span>从 G11-1 带入发生额；从 TB 带入期初/期末</div>
      <div class="guide-step"><span class="step-num">2</span>自动算平均投资与收益率（①/②、④/⑤）</div>
      <div class="guide-step"><span class="step-num">3</span>|变动|&gt;5pp 追查原因并写异常说明</div>
      <div class="guide-step"><span class="step-num">4</span>核对 G11-1 勾稽后填写说明与结论</div>
    </div>

    <div class="methodology-panel">
      <strong>收益率分析方法（源模板二、审计过程）</strong>
      <p>平均投资余额② = (期初投资余额 + 期末投资余额) / 2</p>
      <p>投资收益率③ = 本期发生额① / 平均投资②；上期比率⑥ = 上期审定④ / 平均投资⑤；变动⑦ = ③ − ⑥</p>
      <p>比较各年投资收益率，分析盈利能力；若被审计单位投资金额重大，可与市场平均收益率对标。</p>
      <p>收益率变动超过 5 个百分点视为异常波动，须追查原因。</p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="一、审计目标：确保与投资收益有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。"
    />

    <div class="section-head">
      <h3 class="sheet-title">二、审计过程 —（一）计算变动比率 · G11-4</h3>
      <div class="head-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-4" @imported="onImported" />
        <GtReviewTrigger section-id="G11-4-return-rate" />
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="rr.pullFromAdjudication()">
          从 G11-1 带入
        </el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly"
          :loading="rr.tbLoading.value"
          @click="rr.pullBalancesFromTb()"
        >
          从 TB 带入余额
        </el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="rr.addRow()">+ 新增</el-button>
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G11-4" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G11-1" /></span>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">共 {{ rr.rows.value.length }} 行</el-tag>
        <el-tag v-if="rr.abnormalCount.value > 0" size="small" type="warning">
          异常 {{ rr.abnormalCount.value }} 项
        </el-tag>
      </div>
    </div>

    <el-alert v-if="rr.abnormalCount.value > 0" type="warning" :closable="false" class="warn-alert">
      {{ rr.abnormalCount.value }} 个项目收益率异常波动（|变动⑦|&gt;5pp）
      <template v-if="rr.missingNoteCount.value > 0">
        ；其中 <strong>{{ rr.missingNoteCount.value }}</strong> 项尚未填写异常说明
      </template>
    </el-alert>
    <el-alert
      v-if="rr.adjCrossCheck.value.mismatched"
      type="error"
      :closable="false"
      class="warn-alert"
      :title="`发生额合计与 G11-1 审定合计不一致：G11-4 ${fmt(rr.adjCrossCheck.value.rrTotal)} vs G11-1 ${fmt(rr.adjCrossCheck.value.adjTotal)}（差 ${fmt(rr.adjCrossCheck.value.diff)}），请重新「从 G11-1 带入」或核对手工改数`"
    />

    <el-table
      :data="rr.rows.value"
      border
      size="small"
      style="font-size:13px"
      max-height="520"
      data-testid="g11-return-rate-table"
      show-summary
      :summary-method="summaryMethod"
      :row-class-name="({ row }) => rowClassName(row)"
    >
      <el-table-column label="项目名称" prop="itemName" min-width="180" fixed />
      <el-table-column label="本期数" align="center">
        <el-table-column label="发生额①" width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.currentIncome"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => rr.updateRow(row.id, { currentIncome: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.currentIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.currentOpening"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => rr.updateBalance(row.id, 'currentOpening', v ?? 0)"
            />
            <span v-else>{{ fmt(row.currentOpening) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.currentClosing"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => rr.updateBalance(row.id, 'currentClosing', v ?? 0)"
            />
            <span v-else>{{ fmt(row.currentClosing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均投资②" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="②=(期初+期末)/2">{{ fmt(row.currentAvgBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="比率③=①/②" width="88" align="right">
          <template #default="{ row }">
            <el-tooltip v-if="row.currentReturnRate === null" content="平均余额为零，无法计算收益率（处置/一次性利得常见）">
              <span>N/A</span>
            </el-tooltip>
            <span v-else class="formula-cell" title="③=①/②">{{ fmtPct(row.currentReturnRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="上期数" align="center">
        <el-table-column label="审定数④" width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorAudited"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => rr.updateRow(row.id, { priorAudited: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorOpening"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => rr.updateBalance(row.id, 'priorOpening', v ?? 0)"
            />
            <span v-else>{{ fmt(row.priorOpening) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorClosing"
              size="small"
              style="width:100%"
              @update:model-value="(v: number | undefined) => rr.updateBalance(row.id, 'priorClosing', v ?? 0)"
            />
            <span v-else>{{ fmt(row.priorClosing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均投资⑤" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="⑤=(期初+期末)/2">{{ fmt(row.priorAvgBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="比率⑥=④/⑤" width="88" align="right">
          <template #default="{ row }">
            {{ row.priorReturnRate === null ? 'N/A' : fmtPct(row.priorReturnRate) }}
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="变动⑦=③−⑥" width="96" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.abnormalHighlight" content="收益率异常波动（|变动|&gt;5pp）">
            <span class="rate-warn">{{ row.returnRateChange === null ? 'N/A' : fmtPctPoint(row.returnRateChange) }}</span>
          </el-tooltip>
          <span v-else>{{ row.returnRateChange === null ? 'N/A' : fmtPctPoint(row.returnRateChange) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="市场收益率" width="96" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.marketYield == null ? undefined : row.marketYield * 100"
            size="small"
            :controls="false"
            :precision="2"
            style="width:100%"
            placeholder="%"
            @update:model-value="(v: number | undefined) => rr.updateRow(row.id, { marketYield: v == null ? null : v / 100 })"
          />
          <span v-else>{{ row.marketYield == null ? '—' : fmtPct(row.marketYield) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="较市场" width="80" align="right">
        <template #default="{ row }">
          <span v-if="row.vsMarketDiff == null">—</span>
          <span v-else :class="{ 'rate-warn': Math.abs(row.vsMarketDiff) > 0.05 }" class="formula-cell" title="本期比率③ − 市场收益率">
            {{ fmtPctPoint(row.vsMarketDiff) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="异常说明" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.abnormalNote"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 2 }"
            size="small"
            :class="{ 'note-required': row.noteRequired }"
            placeholder="|变动|&gt;5pp 必填"
            @update:model-value="(v: string) => rr.updateRow(row.id, { abnormalNote: v })"
          />
          <span v-else>{{ row.abnormalNote }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="rr.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <p class="proc-hint">
      （二）比较各年投资收益率，分析盈利能力的稳定性；投资金额重大时，与市场平均收益率比较（见「市场收益率」列）。
    </p>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
        </div>
      </template>
      <el-input
        :model-value="rr.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述收益率分析程序的执行情况、异常波动项目的追查过程与结果。"
        @update:model-value="rr.updateAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <div class="card-actions">
            <el-select
              v-if="!isReadonly"
              placeholder="结论模板"
              size="small"
              style="width:140px"
              clearable
              @change="(k: string) => k && rr.applyConclusionTemplate(k)"
            >
              <el-option
                v-for="t in rr.conclusionTemplates"
                :key="t.key"
                :label="t.label"
                :value="t.key"
              />
            </el-select>
            <el-button
              size="small"
              :loading="rr.aiLoading.value"
              :disabled="isReadonly"
              @click="rr.generateAiConclusion()"
            >
              🤖 AI
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="rr.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="对投资收益收益率分析是否支持相关认定作出结论。"
        @update:model-value="rr.updateConclusion"
      />
    </el-card>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表以收益率分析法复核投资收益合理性，将本期收益率与上期比较，识别异常波动（对齐源模板 G11-4）。</p>
        <p>2. 发生额① / 审定数④ 优先「从 G11-1 带入」；平均投资基数优先「从 TB 带入余额」（持有期间行：1511/1101/1501/1503/1519）。</p>
        <p>3. 处置收益、取得/丧失控制权公允价值利得等一次性项目不自动带入余额，平均余额常为 0 → 比率 N/A。</p>
        <p>4. |变动⑦|&gt;5pp 的项目须填写异常说明；发生额合计应与 G11-1 审定合计勾稽。</p>
        <p>5. 投资金额重大时，在「市场收益率」列填入外部对标，系统自动计算较市场差异。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { toRef, computed } from 'vue'
import type { TableColumnCtx } from 'element-plus'
import { useG11ReturnRateAnalysis, type G11ReturnRateRow } from '../../composables/useG11ReturnRateAnalysis'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const projectIdRef = computed(() => props.projectId ?? '')

const rr = useG11ReturnRateAnalysis({
  wpId: toRef(props, 'wpId'),
  projectId: projectIdRef,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

async function onImported() {
  emit('imported')
  rr.reloadFromStore()
}

function rowClassName(row: G11ReturnRateRow): string {
  if (row.noteRequired) return 'abnormal-row note-missing-row'
  if (row.abnormalHighlight) return 'abnormal-row'
  return ''
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(r: number) {
  return (r * 100).toFixed(2) + '%'
}
function fmtPctPoint(r: number) {
  return (r * 100).toFixed(2) + 'pp'
}

function summaryMethod(param: { columns: TableColumnCtx<G11ReturnRateRow>[]; data: G11ReturnRateRow[] }) {
  const t = rr.totals.value
  const { columns } = param
  const sums: string[] = []
  columns.forEach((col, index) => {
    if (index === 0) {
      sums[index] = '合计'
      return
    }
    const prop = String(col.property ?? col.label ?? '')
    if (prop.includes('发生额') || col.label === '发生额①') sums[index] = fmt(t.currentIncome)
    else if (col.label === '审定数④') sums[index] = fmt(t.priorAudited)
    else if (col.label === '平均投资②') sums[index] = fmt(t.currentAvgBalance)
    else if (col.label === '平均投资⑤') sums[index] = fmt(t.priorAvgBalance)
    else if (col.label === '比率③=①/②') {
      sums[index] = t.currentReturnRate === null ? 'N/A' : fmtPct(t.currentReturnRate)
    } else if (col.label === '比率⑥=④/⑤') {
      sums[index] = t.priorReturnRate === null ? 'N/A' : fmtPct(t.priorReturnRate)
    } else if (String(col.label).includes('变动⑦')) {
      sums[index] = t.returnRateChange === null ? 'N/A' : fmtPctPoint(t.returnRateChange)
    } else if (col.label === '期初余额' || col.label === '期末余额') {
      // 多列同名：按列序粗略匹配（本期期初/期末在前，上期在后）
      const openCloseLabels = columns
        .map((c, i) => ({ i, label: String(c.label ?? '') }))
        .filter((x) => x.label === '期初余额' || x.label === '期末余额')
      const pos = openCloseLabels.findIndex((x) => x.i === index)
      const vals = [t.currentOpening, t.currentClosing, t.priorOpening, t.priorClosing]
      sums[index] = pos >= 0 && pos < vals.length ? fmt(vals[pos]) : ''
    } else {
      sums[index] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.g11-return-rate { font-size: var(--wp-font-size, 13px); }
.guide-strip {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 8px;
  background: linear-gradient(135deg, #ecf5ff 0%, #f0f9eb 100%);
  border: 1px solid #d9ecff;
}
.guide-step { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #303133; }
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%;
  background: #409eff; color: #fff; font-size: 12px; font-weight: 600; flex-shrink: 0;
}
.methodology-panel {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 10px 12px; margin-bottom: 10px; font-size: 12px;
}
.methodology-panel p { margin: 4px 0; }
.guidance-details {
  margin-top: 12px; margin-bottom: 8px;
  border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.warn-alert { margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card, .conclusion-card { margin-top: 10px; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; gap: 8px; flex-wrap: wrap; }
.card-actions { display: flex; gap: 8px; align-items: center; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.proc-hint { margin: 10px 0 4px; font-size: 12px; color: #606266; line-height: 1.5; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
:deep(.note-missing-row) { background-color: #fef0f0 !important; }
:deep(.note-required .el-textarea__inner) { border-color: #f56c6c; }
</style>
