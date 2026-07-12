<template>
  <div class="g9-l3" data-testid="g9-l3-reconciliation">
    <div class="toolbar">
      <div class="methodology">L3 变动分析：期初 + 购入 − 处置 + 转入 − 转出 + FV(损益) + FV(OCI) + 利息 − 减值 + 其他 = 期末</div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:G9-5" />
        <el-tag size="small" type="info">共 {{ l3.rows.value.length }} 行</el-tag>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-5" @imported="onImported" />
      </div>
    </div>
    <el-button v-if="!isReadonly" size="small" @click="l3.addRow()">+ 新增</el-button>
    <el-table :data="l3.rows.value" border size="small" style="font-size:13px;margin-top:8px" max-height="480">
      <el-table-column label="资产名称" min-width="110" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.assetName" size="small"
            @update:model-value="(v: string) => l3.updateRow(row.rowId, 'assetName', v)" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.openingFairValue" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'openingFairValue', v ?? 0)" />
          <span v-else>{{ row.openingFairValue }}</span>
        </template>
      </el-table-column>
      <el-table-column label="购入" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.purchaseAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'purchaseAmount', v ?? 0)" />
          <span v-else>{{ row.purchaseAmount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="处置" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.disposalAmount" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'disposalAmount', v ?? 0)" />
          <span v-else>{{ row.disposalAmount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转入" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.transferIn" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'transferIn', v ?? 0)" />
          <span v-else>{{ row.transferIn }}</span>
        </template>
      </el-table-column>
      <el-table-column label="转出" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.transferOut" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'transferOut', v ?? 0)" />
          <span v-else>{{ row.transferOut }}</span>
        </template>
      </el-table-column>
      <el-table-column label="FV损益" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.fvChangePL" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'fvChangePL', v ?? 0)" />
          <span v-else>{{ row.fvChangePL }}</span>
        </template>
      </el-table-column>
      <el-table-column label="FV(OCI)" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.fvChangeOCI" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'fvChangeOCI', v ?? 0)" />
          <span v-else>{{ row.fvChangeOCI }}</span>
        </template>
      </el-table-column>
      <el-table-column label="利息" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.interestIncome" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'interestIncome', v ?? 0)" />
          <span v-else>{{ row.interestIncome }}</span>
        </template>
      </el-table-column>
      <el-table-column label="减值" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.impairmentLoss" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'impairmentLoss', v ?? 0)" />
          <span v-else>{{ row.impairmentLoss }}</span>
        </template>
      </el-table-column>
      <el-table-column label="其他" width="80" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.otherChanges" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'otherChanges', v ?? 0)" />
          <span v-else>{{ row.otherChanges }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末(公式)" width="100" align="right">
        <template #default="{ row }"><span class="formula-cell" title="期末 = 期初 + 购入 − 处置 + 转入 − 转出 + FV损益 + FV(OCI) + 利息 − 减值 + 其他">{{ row.closingFairValue }}</span></template>
      </el-table-column>
      <el-table-column label="企业报告" width="96" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.reportedClosing" size="small" :controls="false" style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'reportedClosing', v ?? 0)" />
          <span v-else>{{ row.reportedClosing }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="88" align="right">
        <template #default="{ row }">
          <span :class="{ 'var-warn': row.varianceHighlight }">{{ row.variance }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-row" data-testid="g9-l3-totals">
      <span>期初合计 {{ l3.totals.value.openingFairValue }}</span>
      <span>公式期末 {{ l3.totals.value.closingFairValue }}</span>
      <span>企业报告 {{ l3.totals.value.reportedClosing }}</span>
      <span :class="{ 'var-warn': Math.abs(l3.totals.value.variance) > 0.01 }">差异 {{ l3.totals.value.variance }}</span>
    </div>

    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="conclusion-head">
          <span>审计结论</span>
          <el-button size="small" :loading="l3.aiLoading.value" :disabled="isReadonly"
            data-testid="g9-l3-ai-btn" @click="l3.generateAiConclusion()">🤖 AI</el-button>
        </div>
      </template>
      <el-input v-model="l3.conclusion.value" type="textarea" :rows="3" placeholder="审计结论"
        :disabled="isReadonly" @change="l3.updateConclusion(l3.conclusion.value)" />
    </el-card>

    <details class="methodology-hint">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>第三层次（Level3）公允价值调节表按 CAS 39 公允价值计量：逐项列示期初至期末的十因子变动，公式期末应与企业报告期末勾稽，差异须查明原因。</p>
        <p>FV(损益) 计入当期损益，FV(OCI) 计入其他综合收益，两者需分别列示不得混淆。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import { useG9L3Reconciliation } from '../../composables/useG9L3Reconciliation'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const l3 = useG9L3Reconciliation({
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

function onImported() { emit('imported') }
</script>

<style scoped>
.g9-l3 { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.methodology { flex: 1; border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; }
.methodology-hint { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.var-warn { color: #f56c6c; font-weight: 600; }
.totals-row { margin-top: 8px; display: flex; gap: 16px; flex-wrap: wrap; padding: 8px; background: #f5f7fa; font-size: 12px; }
.conclusion-card { margin-top: 12px; }
.conclusion-head { display: flex; justify-content: space-between; align-items: center; }
</style>
