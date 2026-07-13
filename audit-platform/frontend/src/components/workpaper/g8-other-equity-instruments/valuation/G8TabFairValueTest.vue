<template>
  <div class="g8-fv" data-testid="g8-fv-test">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实其他权益工具投资以公允价值计量的准确性，验证公允价值层次（Level 1/2/3）划分恰当，Level 3 估值技术与不可观察输入值合理，为审定表 G8-1（科目1503）提供计价支撑。"
    />
    <div class="toolbar">
      <div class="methodology">公允价值三层次：Level1 活跃市场报价 / Level2 可观察输入值 / Level3 不可观察输入值（估值技术）</div>
      <G8ImportExportDropdown :wp-id="wpId" sheet="G8-4" @imported="onImported" />
    </div>
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-4" /></span>
        <el-tag size="small" type="info">共 {{ fv.rows.value.length }} 行</el-tag>
      </div>
    </div>
    <el-segmented v-model="fv.activeTab.value" :options="[{ label: '基础+审定', value: 'basic' }, { label: '估值详情', value: 'detail' }]" size="small" />
    <el-button v-if="!isReadonly" size="small" style="margin:8px 0" @click="fv.addRow()">+ 新增</el-button>
    <el-table :data="fv.rows.value" border size="small" style="font-size:13px" max-height="480"
      highlight-current-row @current-change="onRowChange">
      <el-table-column label="被投资单位" min-width="110" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.investeeName" size="small" @update:model-value="(v: string) => fv.updateRow(row.rowId, { investeeName: v })" />
          <span v-else>{{ row.investeeName }}</span>
        </template>
      </el-table-column>
      <template v-if="fv.activeTab.value === 'basic'">
        <el-table-column label="投资日" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.initialInvestDate" size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { initialInvestDate: v })" />
            <span v-else>{{ row.initialInvestDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数量" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingUnadjustedQty" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingUnadjustedQty: v ?? 0 })" />
            <span v-else>{{ row.closingUnadjustedQty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审单价" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingUnadjustedPrice" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingUnadjustedPrice: v ?? 0 })" />
            <span v-else>{{ row.closingUnadjustedPrice }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审FV" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingUnadjustedFV" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingUnadjustedFV: v ?? 0 })" />
            <span v-else>{{ row.closingUnadjustedFV }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数量" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAuditedQty" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingAuditedQty: v ?? 0 })" />
            <span v-else>{{ row.closingAuditedQty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定单价" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAuditedPrice" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingAuditedPrice: v ?? 0 })" />
            <span v-else>{{ row.closingAuditedPrice }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定FV" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAuditedFV" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingAuditedFV: v ?? 0 })" />
            <span v-else>{{ row.closingAuditedFV }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="88" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.fairValueDiff }}</span></template>
        </el-table-column>
        <el-table-column label="层次" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small" @update:model-value="(v: string) => fv.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="o in fv.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="估值方法" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.valuationMethod" size="small" @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationMethod: v })">
              <el-option v-for="o in fv.valuationMethodOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.methodConsistentWithPrior" size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { methodConsistentWithPrior: v })">
              <el-option label="是" value="yes" /><el-option label="否" value="no" />
            </el-select>
            <span v-else>{{ row.methodConsistentWithPrior === 'yes' ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值技术" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.valuationTechnique" size="small"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.valuationTechnique }"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationTechnique: v })" />
            <span v-else>{{ row.valuationTechnique }}</span>
          </template>
        </el-table-column>
        <el-table-column label="不可观察输入值" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unobservableInputDesc" size="small" type="textarea" :rows="1"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.unobservableInputDesc }"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { unobservableInputDesc: v })" />
            <span v-else>{{ row.unobservableInputDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="输入值" width="96">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unobservableInputValue" size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { unobservableInputValue: v })" />
            <span v-else>{{ row.unobservableInputValue }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值来源" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.valuationSource" size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationSource: v })" />
            <span v-else>{{ row.valuationSource }}</span>
          </template>
        </el-table-column>
        <el-table-column label="输入值来源" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.inputSourceAndAdjustment" size="small" type="textarea" :rows="1"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { inputSourceAndAdjustment: v })" />
            <span v-else>{{ row.inputSourceAndAdjustment }}</span>
          </template>
        </el-table-column>
        <el-table-column label="底稿索引" width="96">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.valuationDocIndex" size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationDocIndex: v })" />
            <span v-else>{{ row.valuationDocIndex }}</span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <el-card shadow="never" class="conclusion-card">
      <template #header>审计说明</template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="填写审计说明：公允价值取数来源、层次划分依据及 Level 3 估值技术/输入值的核实情况与异常事项。" />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-head">
          <span>审计结论</span>
          <el-button size="small" :loading="fv.aiLoading.value" :disabled="isReadonly"
            data-testid="g8-fv-ai-btn" @click="fv.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="fv.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="fv.updateConclusion" />
    </el-card>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      Level3 层次须填写估值技术与不可观察输入值；差异列 = 审定 FV − 未审 FV。
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, toRef } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import { useG8FairValueTest } from '../../composables/useG8FairValueTest'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const fv = useG8FairValueTest({
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const AUDIT_NOTE_KEY = 'G8-4-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

function onImported() { emit('imported') }

function onRowChange(row: { seq?: number } | undefined) {
  if (row?.seq) fv.activeRowIndex.value = row.seq - 1
}
</script>

<style scoped>
.g8-fv { font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.methodology { flex: 1; border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; }
.l3-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.formula-cell { border-bottom: 1px dashed #909399; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
.methodology-hint { margin-top: 8px; font-size: 12px; color: #909399; }
</style>
