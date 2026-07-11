<template>
  <div class="g9-fv" data-testid="g9-fv-test">
    <div class="toolbar">
      <div class="methodology">公允价值三层次：Level1 活跃市场报价 / Level2 可观察输入值 / Level3 不可观察输入值（估值技术）</div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:G9-4" />
        <el-tag size="small" type="info">共 {{ fv.rows.value.length }} 行</el-tag>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-4" @imported="onImported" />
      </div>
    </div>
    <el-segmented v-model="fv.activeTab.value" :options="[{ label: '基础+审定', value: 'basic' }, { label: '估值详情', value: 'detail' }]" size="small" />
    <el-button v-if="!isReadonly" size="small" style="margin:8px 0" @click="fv.addRow()">+ 新增</el-button>
    <el-table :data="fv.rows.value" border size="small" style="font-size:13px" max-height="480">
      <el-table-column label="资产名称" min-width="110" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.assetName" size="small" @update:model-value="(v: string) => fv.updateRow(row.rowId, { assetName: v })" />
          <span v-else>{{ row.assetName }}</span>
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
          <template #default="{ row }"><span class="formula-cell" title="差异 = 审定FV − 未审FV">{{ row.fairValueDiff }}</span></template>
        </el-table-column>
        <el-table-column label="层次" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small" @update:model-value="(v: string) => fv.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="o in fv.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
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
      </template>
      <template v-else>
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
        <el-table-column label="非流动性折扣" width="108" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.nonLiquidityDiscount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { nonLiquidityDiscount: v ?? 0 })" />
            <span v-else>{{ row.nonLiquidityDiscount }}</span>
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
      <template #header>
        <div class="conclusion-head">
          <span>审计结论</span>
          <el-button size="small" :loading="fv.aiLoading.value" :disabled="isReadonly"
            data-testid="g9-fv-ai-btn" @click="fv.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input :model-value="fv.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly" @update:model-value="fv.updateConclusion" />
    </el-card>

    <details class="methodology-hint">
      <summary>📋 编制提示</summary>
      Level3 层次须填写估值技术与不可观察输入值；差异列 = 审定 FV − 未审 FV。
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import { useG9FairValueTest } from '../../composables/useG9FairValueTest'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const fv = useG9FairValueTest({
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

function onImported() { emit('imported') }
</script>

<style scoped>
.g9-fv { font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.methodology { flex: 1; border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.l3-required :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
.methodology-hint { margin-top: 8px; font-size: 12px; color: #909399; }
</style>
