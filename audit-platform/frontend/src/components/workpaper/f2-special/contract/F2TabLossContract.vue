<template>
  <div class="f2-loss-contract">
    <h3 class="title">亏损合同预计损失测算 F2-58</h3>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="loss.addRow()">+ 新增项目</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-58"
        :disabled="isReadonly"
        ai-section="loss-analysis"
        :existing-content="loss.auditNote.value"
        review-section="F2-58-loss"
        @ai-filled="(t: string) => { loss.auditNote.value = t }"
      />
      <el-tag size="small" type="warning">亏损合同: {{ loss.lossCount.value }}</el-tag>
      <el-tag v-if="loss.adjustCount.value > 0" size="small" type="danger">需调整 {{ loss.adjustCount.value }} 笔</el-tag>
    </div>
    <el-table :data="loss.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.isLoss ? 'warn-row' : row.needsAdjust ? 'error-row' : ''">
      <el-table-column label="项目" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
            @change="(v: string) => loss.updateRow(row.id, { projectName: v })" />
          <span v-else>{{ row.projectName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预计总收入" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.estimatedTotalRevenue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => loss.updateRow(row.id, { estimatedTotalRevenue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="预计总成本" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.estimatedTotalCost" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => loss.updateRow(row.id, { estimatedTotalCost: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="是否亏损" width="80">
        <template #default="{ row }">
          <el-tag :type="row.isLoss ? 'danger' : 'success'" size="small">{{ row.isLoss ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="完工进度" width="90" align="right">
        <template #default="{ row }">
          <span v-if="typeof row.completionRate === 'number'">{{ (row.rateNum * 100).toFixed(1) }}%</span>
          <span v-else>N/A</span>
        </template>
      </el-table-column>
      <el-table-column label="应确认损失" width="110" align="right">
        <template #default="{ row }"><span class="formula">{{ row.expectedLoss.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="本期应计提" width="110" align="right">
        <template #default="{ row }"><span class="formula">{{ row.currentProvision.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="管理层计提" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.managementProvision" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => loss.updateRow(row.id, { managementProvision: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="90" align="right">
        <template #default="{ row }">{{ row.difference.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="loss.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <h4>审计说明</h4>
    <el-input v-model="loss.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2LossContract } from '../../composables/useF2LossContract'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const loss = useF2LossContract({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-loss-contract { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.formula { text-decoration: underline dotted #909399; }
:deep(.warn-row) { background: #fdf6ec; }
:deep(.error-row) { background: #fef0f0; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
