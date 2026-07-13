<template>
  <div class="g11-return-rate">
    <div class="methodology-panel">
      <strong>收益率分析方法</strong>
      <p>平均投资余额 = (期初投资余额 + 期末投资余额) / 2</p>
      <p>投资收益率 = 本期投资收益 / 平均投资余额 × 100%</p>
      <p>收益率变动超过 5 个百分点视为异常波动，需追查原因。</p>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表以收益率分析法复核投资收益的合理性，将本期收益率与上期比较，识别异常波动。</p>
        <p>2. 平均投资余额取期初、期末投资账面余额的算术平均；平均余额为零时收益率不可计算（N/A）。</p>
        <p>3. 收益率变动 |&gt;5pp| 的项目须在"异常说明"注明原因（如新增/处置投资、投资收益确认口径变化、市场利率变动等）。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：通过收益率分析法复核投资收益的合理性，识别并追查异常波动，评估投资收益金额的准确与完整。"
    />

    <div class="section-head">
      <h3 class="sheet-title">G11-4 投资收益分析 — 投资收益率</h3>
      <div class="head-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-4" @imported="onImported" />
        <GtReviewTrigger section-id="G11-4-return-rate" />
        <el-button size="small" :loading="rr.aiLoading.value" :disabled="isReadonly" @click="rr.generateAiConclusion()">🤖 AI</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="rr.addRow()">+ 新增</el-button>
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G11-4" /></span>
        <el-tag size="small" type="info">共 {{ rr.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-alert v-if="rr.abnormalCount.value > 0" type="warning" :closable="false">
      {{ rr.abnormalCount.value }} 个项目收益率异常波动（|变动|&gt;5pp）
    </el-alert>
    <el-table :data="rr.rows.value" border size="small" style="font-size:13px" max-height="520" data-testid="g11-return-rate-table"
      :row-class-name="({ row }) => row.abnormalHighlight ? 'abnormal-row' : ''">
      <el-table-column label="项目名称" prop="itemName" min-width="160" fixed />
      <el-table-column label="本期数" align="center">
        <el-table-column label="发生额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentIncome" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateRow(row.id, { currentIncome: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentOpening" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'currentOpening', v ?? 0)" />
            <span v-else>{{ fmt(row.currentOpening) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentClosing" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'currentClosing', v ?? 0)" />
            <span v-else>{{ fmt(row.currentClosing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均投资" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="(期初+期末)/2">{{ fmt(row.currentAvgBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收益率" width="80" align="right">
          <template #default="{ row }">
            <el-tooltip v-if="row.currentReturnRate === null" content="平均余额为零，无法计算收益率">
              <span>N/A</span>
            </el-tooltip>
            <span v-else class="formula-cell">{{ fmtPct(row.currentReturnRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="上期数" align="center">
        <el-table-column label="审定数" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAudited" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateRow(row.id, { priorAudited: v ?? 0 })" />
            <span v-else>{{ fmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorOpening" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'priorOpening', v ?? 0)" />
            <span v-else>{{ fmt(row.priorOpening) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorClosing" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => rr.updateBalance(row.id, 'priorClosing', v ?? 0)" />
            <span v-else>{{ fmt(row.priorClosing) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均投资" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.priorAvgBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="收益率" width="80" align="right">
          <template #default="{ row }">{{ row.priorReturnRate === null ? 'N/A' : fmtPct(row.priorReturnRate) }}</template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="收益率变动" width="88" align="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.abnormalHighlight" content="收益率异常波动">
            <span class="rate-warn">{{ row.returnRateChange === null ? 'N/A' : fmtPctPoint(row.returnRateChange) }}</span>
          </el-tooltip>
          <span v-else>{{ row.returnRateChange === null ? 'N/A' : fmtPctPoint(row.returnRateChange) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="异常说明" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.abnormalNote" type="textarea" :autosize="{ minRows: 1, maxRows: 2 }" size="small"
            @update:model-value="(v: string) => rr.updateRow(row.id, { abnormalNote: v })" />
          <span v-else>{{ row.abnormalNote }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="rr.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：可概述收益率分析程序的执行情况、异常波动项目的追查过程与结果。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>审计结论</template>
      <el-input :model-value="rr.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }"
        :disabled="isReadonly" @update:model-value="rr.updateConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG11ReturnRateAnalysis } from '../../composables/useG11ReturnRateAnalysis'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const rr = useG11ReturnRateAnalysis({
  wpId: toRef(props, 'wpId'),
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计说明（结论由 rr.conclusion 提供）───
const NOTE_KEY = 'G11-return-rate-audit-note'
const auditNote = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

async function onImported() {
  emit('imported')
  rr.reloadFromStore()
}

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtPct(r: number) { return (r * 100).toFixed(2) + '%' }
function fmtPctPoint(r: number) { return (r * 100).toFixed(2) + 'pp' }
</script>

<style scoped>
.g11-return-rate { font-size: var(--wp-font-size, 13px); }
.methodology-panel { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 10px 12px; margin-bottom: 10px; font-size: 12px; }
.methodology-panel p { margin: 4px 0; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 8px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.conclusion-card { margin-top: 8px; }
:deep(.abnormal-row) { background-color: #fdf6ec !important; }
</style>
