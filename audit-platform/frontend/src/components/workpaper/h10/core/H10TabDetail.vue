<template>
  <div class="h10-detail" data-testid="h10-detail-table">
    <div class="section-head">
      <h3 class="sheet-title">H10-2 资产处置明细表</h3>
      <div class="head-actions">
        <H10ImportExportDropdown :wp-id="wpId" sheet="H10-2" @imported="onImported" />
        <GtReviewTrigger section-id="H10-2-detail" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" data-testid="h10-detail-add" @click="detail.addRow()">+ 新增</el-button>
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 逐项列示本期处置的各类非流动资产（固定资产/在建工程/使用权资产/生产性生物资产/油气资产/无形资产等），来源底稿应可追溯至 H1/H2/H5~H8/I1（投资性房地产、金融工具、长投处置不进 6115）。</p>
        <p>2. 处置损益 = 处置收入 − 账面净值 − 处置费用 − 相关税费；账面净值 = 原值 − 累计折旧 − 减值准备。</p>
        <p>3. 依据财会〔2017〕30 号，资产处置损益（6115）核算处置非流动资产（不含金融工具、长期股权投资、投资性房地产）产生的利得或损失。</p>
        <p>4. 关注处置审批文件、评估报告、合同/发票等审计证据的完整性，损失项目重点核查减值计提是否充分（CAS 8 号资产减值）。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实各项资产处置的原值、累计折旧、账面净值、处置收入及处置损益计算的准确性与完整性，验证处置损益来源可追溯至各资产底稿。" />

    <el-alert
      v-if="detail.excludedClassWarning.value"
      type="error"
      :closable="false"
      show-icon
      class="objective-alert"
      data-testid="h10-excluded-class-warn"
      :title="detail.excludedClassWarning.value"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H10-2" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-segmented v-model="activeTab" :options="detail.tabOptions" size="small" data-testid="h10-detail-tabs" />

    <div class="stats-bar" data-testid="h10-detail-stats">
      <span>行数 {{ detail.statsSummary.value.count }}</span>
      <span>处置收入 {{ fmt(detail.statsSummary.value.totalIncome) }}</span>
      <span>损益合计 {{ fmt(detail.statsSummary.value.totalGainLoss) }}</span>
      <span>盈利 {{ detail.statsSummary.value.profitCount }} / 亏损 {{ detail.statsSummary.value.lossCount }}</span>
    </div>

    <el-table :data="detail.rows.value" border stripe size="small" style="font-size:13px;margin-top:8px" max-height="560"
      :row-class-name="({ row }) => row.isLoss ? 'loss-row' : ''">
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed />
      <el-table-column label="资产名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.assetName" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { assetName: v })" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>

      <template v-if="activeTab === 'basic'">
        <el-table-column label="资产类型" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.assetType" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { assetType: v })" />
            <span v-else>{{ row.assetType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源底稿" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.sourceWp" size="small"
              @change="(v: string) => detail.updateRow(row.id, { sourceWp: v })">
              <el-option v-for="o in detail.sourceWpOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <template v-else>
              <GtIndexChip v-if="row.sourceIndex" :value="row.sourceIndex" />
              <el-tag v-else size="small">{{ row.sourceWp }}</el-tag>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="原值" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.originalCost" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { originalCost: v ?? 0 })" />
            <span v-else>{{ fmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计折旧" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.accumulatedDepreciation" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { accumulatedDepreciation: v ?? 0 })" />
            <span v-else>{{ fmt(row.accumulatedDepreciation) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.impairmentProvision" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { impairmentProvision: v ?? 0 })" />
            <span v-else>{{ fmt(row.impairmentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净值" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell" title="原值−累计折旧−减值准备">{{ fmt(row.netBookValue) }}</span></template>
        </el-table-column>
      </template>

      <template v-else-if="activeTab === 'disposal'">
        <el-table-column label="处置收入" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.disposalIncome" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { disposalIncome: v ?? 0 })" />
            <span v-else>{{ fmt(row.disposalIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置费用" width="96" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.disposalExpenses" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { disposalExpenses: v ?? 0 })" />
            <span v-else>{{ fmt(row.disposalExpenses) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="税费" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.disposalTax" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { disposalTax: v ?? 0 })" />
            <span v-else>{{ fmt(row.disposalTax) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置损益" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ loss: row.isLoss }" title="收入-净值-费用-税费">{{ fmt(row.disposalGainLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置方式" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.disposalMethod" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { disposalMethod: v })" />
            <span v-else>{{ row.disposalMethod }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="审批文件" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.approvalDoc" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { approvalDoc: v })" />
            <span v-else>{{ row.approvalDoc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="评估报告" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.appraisalReport" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { appraisalReport: v })" />
            <span v-else>{{ row.appraisalReport }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同/发票" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.contractRef" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { contractRef: v })" />
            <span v-else>{{ row.contractRef || row.invoiceRef }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计结论" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditConclusion" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.id, { auditConclusion: v })" />
            <span v-else>{{ row.auditConclusion }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="56" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述处置明细的取数与核对情况、来源底稿追溯结果、异常或损失项目的分析。"
        @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项调整外，其余未见异常。C、存在重大未调整事项或范围受限，不可确认。"
        @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, onMounted } from 'vue'
import { useH10Detail } from '../../composables/useH10Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import H10ImportExportDropdown from '../H10ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useH10Detail({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const activeTab = detail.activeTab

async function onImported() {
  emit('imported')
  detail.reloadFromStore()
}

const NOTE_KEY = 'H10-2-detail-audit-note'
const CONCLUSION_KEY = 'H10-2-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h10-detail { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; }
.formula-cell.loss { color: #f56c6c; }
.stats-bar { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 8px; padding: 10px; background: #f5f7fa; font-size: 12px; }
:deep(.loss-row) { background: #fef0f0 !important; }
.guidance-details { margin-bottom: 8px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 12px; }
</style>
