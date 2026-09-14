<!--
  K1TabBadDebtDetail.vue — K1-3 坏账准备明细表
-->
<template>
  <div class="k1-tab-bad-debt-detail">
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他应收款坏账准备是存在的；</li>
        <li><b>完整性：</b>所有应当记录的其他应收款坏账准备均已记录；</li>
        <li><b>计价和分摊：</b>坏账准备以恰当的金额包括在财务报表中，相关计价调整已恰当记录。</li>
      </ol>
    </el-alert>

    <div class="section-head">
      <h3 class="sheet-title">二、审计过程</h3>
      <div class="head-actions">
        <el-button v-if="!isReadonly" size="small" @click="handleAddSubRow">＋ 单项明细</el-button>
        <el-button v-if="!isReadonly" size="small" plain @click="syncStage">同步至三阶段表</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleReview('K1-3-baddebt')">💬 复核</el-button>
      </div>
    </div>

    <div class="block-title">（一）坏账准备明细表</div>
    <el-table :data="mainRows" border size="small" class="main-table" :max-height="420">
      <el-table-column label="项目" min-width="140" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly && row.isSubRow" :model-value="row.label" size="small"
            @change="(v: string) => updateMain(row.id, 'label', v)" />
          <span v-else :class="{ 'fixed-label': row.isFixed }">{{ row.label }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初数" align="center">
        <el-table-column label="账面金额" min-width="100" align="right">
          <template #default="{ row }">
            <num-cell :value="row.priorBook" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'priorBook', v)" />
          </template>
        </el-table-column>
        <el-table-column label="期后调整" min-width="100" align="right">
          <template #default="{ row }">
            <num-cell :value="row.priorAdj" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'priorAdj', v)" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期初审定=账面+调整">{{ fmtAmt(row.priorAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期增加" align="center">
        <el-table-column label="计提" min-width="95" align="right">
          <template #default="{ row }">
            <num-cell :value="row.currentProvision" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'currentProvision', v)" />
          </template>
        </el-table-column>
        <el-table-column label="其他增加" min-width="95" align="right">
          <template #default="{ row }">
            <num-cell :value="row.currentOtherIncrease" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'currentOtherIncrease', v)" />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期减少" align="center">
        <el-table-column label="转回" min-width="90" align="right">
          <template #default="{ row }">
            <num-cell :value="row.currentReversal" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'currentReversal', v)" />
          </template>
        </el-table-column>
        <el-table-column label="核销" min-width="90" align="right">
          <template #default="{ row }">
            <num-cell :value="row.currentWriteOff" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'currentWriteOff', v)" />
          </template>
        </el-table-column>
        <el-table-column label="其他减少" min-width="95" align="right">
          <template #default="{ row }">
            <num-cell :value="row.currentOtherDecrease" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'currentOtherDecrease', v)" />
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="期末数" align="center">
        <el-table-column label="账面金额" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末账面=期初审定+增加-减少">{{ fmtAmt(row.currentBook) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期后调整" min-width="100" align="right">
          <template #default="{ row }">
            <num-cell :value="row.currentAdj" :editable="!isReadonly && isEditable(row)"
              @change="(v) => updateMain(row.id, 'currentAdj', v)" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末审定=期末账面+调整">{{ fmtAmt(row.currentAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="单项计提减值、转回或核销原因" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly && isEditable(row) && row.category !== 'total'"
            :model-value="row.reason" size="small"
            @change="(v: string) => updateMain(row.id, 'reason', v)" />
          <span v-else>{{ row.reason || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="50" fixed="right" align="center">
        <template #default="{ row }">
          <el-button v-if="row.isSubRow" type="danger" link size="small" @click="removeSub(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="block-title stage-block">（二）三阶段的转入转出</div>
    <el-table :data="stageMovements" border size="small" class="stage-table">
      <el-table-column prop="label" label="项目" min-width="180" fixed />
      <el-table-column label="第一阶段" min-width="110" align="right">
        <template #default="{ row }">
          <num-cell :value="row.stage1" :editable="!isReadonly && row.editable"
            @change="(v) => updateStage(row.key, 'stage1', v)" />
        </template>
      </el-table-column>
      <el-table-column label="第二阶段" min-width="110" align="right">
        <template #default="{ row }">
          <num-cell :value="row.stage2" :editable="!isReadonly && row.editable"
            @change="(v) => updateStage(row.key, 'stage2', v)" />
        </template>
      </el-table-column>
      <el-table-column label="第三阶段" min-width="110" align="right">
        <template #default="{ row }">
          <num-cell :value="row.stage3" :editable="!isReadonly && row.editable"
            @change="(v) => updateStage(row.key, 'stage3', v)" />
        </template>
      </el-table-column>
      <el-table-column label="合计" min-width="110" align="right">
        <template #default="{ row }">
          <span :class="row.editable ? 'amount-cell' : 'formula-cell'">{{ fmtAmt(stageTotal(row)) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="与TB核查" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.key === 'closing'" :type="tbMatch ? 'success' : 'danger'" size="small">
            {{ tbMatch ? 'TRUE' : 'FALSE' }}
          </el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="cross-validation-panel">
      <h4 class="cv-title">勾稽核对</h4>
      <div class="cv-items">
        <div class="cv-item" :class="crossValidation.isMatch ? 'cv-pass' : 'cv-fail'">
          <span class="cv-label">vs K1-8 测算</span>
          <span class="cv-detail">
            账面期末 {{ fmtAmt(crossValidation.bookedProvision) }} |
            测算 {{ fmtAmt(crossValidation.calcProvision) }} |
            差异 <strong>{{ fmtAmt(crossValidation.diff) }}</strong>
          </span>
          <el-tag :type="crossValidation.isMatch ? 'success' : 'danger'" size="small" effect="plain">
            {{ crossValidation.isMatch ? '一致' : '有差异' }}
          </el-tag>
          <el-button v-if="!crossValidation.isMatch" size="small" link type="primary"
            @click="emit('navigate-sheet', 'K1-8 坏账准备测算')">跳转 K1-8 →</el-button>
        </div>
        <div class="cv-item" :class="adjudicationMatch.isMatch ? 'cv-pass' : 'cv-fail'">
          <span class="cv-label">vs K1-1 审定坏账</span>
          <span class="cv-detail">
            K1-3 期末 {{ fmtAmt(totalEndBadDebt) }} |
            K1-1 审定 {{ fmtAmt(adjudicationBadDebt) }} |
            差异 <strong>{{ fmtAmt(adjudicationMatch.diff) }}</strong>
          </span>
          <el-tag :type="adjudicationMatch.isMatch ? 'success' : 'danger'" size="small" effect="plain">
            {{ adjudicationMatch.isMatch ? '一致' : '有差异' }}
          </el-tag>
        </div>
        <div class="cv-item" :class="stageTbMatch.isMatch ? 'cv-pass' : 'cv-fail'">
          <span class="cv-label">三阶段 vs K1-1</span>
          <span class="cv-detail">
            三阶段期末 {{ fmtAmt(stageClosingTotal) }} |
            K1-1 审定 {{ fmtAmt(adjudicationBadDebt) }} |
            差异 <strong>{{ fmtAmt(stageTbMatch.diff) }}</strong>
          </span>
          <el-tag :type="stageTbMatch.isMatch ? 'success' : 'danger'" size="small" effect="plain">
            {{ stageTbMatch.isMatch ? '一致' : '有差异' }}
          </el-tag>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="text-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="概述坏账准备滚动核对、三阶段划分与 K1-7/K1-8 的印证、重大转回/核销原因等" @change="persist" />
    </el-card>

    <el-card shadow="never" class="text-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select"
        placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述调整事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大未调整事项，不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="形成审计结论..." @change="persist" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>期末审定 = 期初审定 + 计提 + 其他增加 − 转回 − 核销 − 其他减少 + 期末调整</li>
        <li>（二）各行代数和 = 期末余额；期末合计须与 K1-1/TB 一致（TRUE）</li>
        <li>单项明细可增删；有明细时「单项评估计提」自动合计</li>
        <li>与 K1-9 转回/核销合计须勾稽一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useK1BadDebt,
  parseK13Payload,
  type K1BadDebtMainRow,
  type K1StageMovementRow,
  type K1StageAmountKey,
  stageMovementTotal,
} from '../../composables/useK1BadDebt'
import { K1_CONCLUSION_TEMPLATES } from '../../composables/useK1AuditRows'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import NumCell from './K1BadDebtNumCell.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const {
  mainRows,
  stageMovements,
  totalEndBadDebt,
  crossValidation,
  loadRows,
  addSubRow,
  removeSubRow,
  updateMainRow,
  updateStageMovement,
  syncStageFromMain,
  isMainRowEditable,
  setAuditText,
  serializeRows,
  STORAGE_KEY,
} = useK1BadDebt({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const auditNote = ref('')
const conclusion = ref('')
const conclusionOption = ref('')

const { exportTemplate, exportData, importData } = useK1ImportExport({ wpId: toRef(props, 'wpId') })

const adjudicationBadDebt = computed(() => {
  const raw = props.allResponses.get('K1-1-audited-bad-debt')?.remark
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
})

const adjudicationMatch = computed(() => {
  const diff = totalEndBadDebt.value - adjudicationBadDebt.value
  return { diff, isMatch: Math.abs(diff) < 0.01 }
})

const stageClosingTotal = computed(() => {
  const closing = stageMovements.value.find((r) => r.key === 'closing')
  return closing ? stageMovementTotal(closing) : 0
})

const stageTbMatch = computed(() => {
  const diff = stageClosingTotal.value - adjudicationBadDebt.value
  return { diff, isMatch: Math.abs(diff) < 0.01 }
})

const tbMatch = computed(() => stageTbMatch.value.isMatch)

onMounted(() => {
  loadRows()
  const raw = props.allResponses.get(STORAGE_KEY)?.remark
  const p = parseK13Payload(raw)
  auditNote.value = p.auditNote
  conclusion.value = p.conclusion
  conclusionOption.value = p.conclusionOption
})

function persist() {
  setAuditText(auditNote.value, conclusion.value, conclusionOption.value)
  const json = serializeRows()
  props.allResponses.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
  emit('save', STORAGE_KEY, { remark: json })
  const endKey = 'K1-3-bad-debt-end'
  props.allResponses.set(endKey, { item_id: endKey, remark: String(totalEndBadDebt.value) })
  emit('save', endKey, { remark: String(totalEndBadDebt.value) })
}

function updateMain(id: string, field: keyof K1BadDebtMainRow, value: string | number) {
  updateMainRow(id, field, value)
  persist()
}

function updateStage(key: string, stage: K1StageAmountKey, value: number) {
  updateStageMovement(key, stage, value)
  persist()
}

function isEditable(row: K1BadDebtMainRow) {
  return isMainRowEditable(row)
}

async function handleAddSubRow() {
  try {
    const { value } = await ElMessageBox.prompt('债务人/项目名称', '新增单项明细', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    addSubRow(String(value || '').trim())
    persist()
  } catch { /* cancel */ }
}

function removeSub(id: string) {
  removeSubRow(id)
  persist()
}

function syncStage() {
  syncStageFromMain()
  persist()
  ElMessage.success('已将合计行计提/转回/核销同步至三阶段表（默认 Stage1，请按需拆分）')
}

function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  persist()
}

function stageTotal(row: K1StageMovementRow) {
  return stageMovementTotal(row)
}

function handleExportTemplate() { exportTemplate('K1-3') }
function handleExportData() { exportData('K1-3') }
function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    if (await importData('K1-3', file)) {
      loadRows()
      persist()
    }
  }
  input.click()
}

function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null || !Number.isFinite(Number(val))) return '—'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k1-tab-bad-debt-detail { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.audit-objective { margin-bottom: 10px; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.block-title { font-weight: 600; margin: 12px 0 8px; font-size: 13px; }
.stage-block { margin-top: 16px; }
.main-table, .stage-table { font-size: var(--wp-font-size, 13px); margin-bottom: 8px; }
.fixed-label { font-weight: 600; }
.amount-cell, .formula-cell { font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.muted { color: var(--el-text-color-secondary); }
.cross-validation-panel { margin-top: 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 12px 16px; }
.cv-title { font-size: 14px; font-weight: 600; margin: 0 0 10px; }
.cv-items { display: flex; flex-direction: column; gap: 8px; }
.cv-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 4px; font-size: 12px; flex-wrap: wrap; }
.cv-item.cv-pass { background: #f0fdf4; border: 1px solid #bbf7d0; }
.cv-item.cv-fail { background: #fef2f2; border: 1px solid #fecaca; }
.cv-label { font-weight: 600; min-width: 100px; }
.cv-detail { flex: 1; color: var(--el-text-color-regular); }
.text-card { margin-top: 12px; }
.text-card :deep(.el-card__header) { padding: 8px 14px; }
.text-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
</style>
