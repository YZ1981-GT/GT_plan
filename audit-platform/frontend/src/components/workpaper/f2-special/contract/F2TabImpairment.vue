<template>
  <div class="f2-spe-impairment">
    <h3 class="title">合同履约成本减值准备测算 F2-57</h3>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="imp.addRow()">+ 新增项目</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-57"
        :disabled="isReadonly"
        ai-section="impairment-analysis"
        :existing-content="imp.auditNote.value"
        review-section="F2-57-impairment"
        @ai-filled="(t: string) => { imp.auditNote.value = t }"
      />
      <el-tag size="small" type="info">减值合计: {{ imp.impairmentTotal.value.toLocaleString() }}</el-tag>
      <el-tag v-if="imp.diffCount.value > 0" size="small" type="danger">差异 {{ imp.diffCount.value }} 笔</el-tag>
    </div>
    <el-table :data="imp.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.hasDifference ? 'error-row' : ''">
      <el-table-column label="项目" width="120" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
            @change="(v: string) => imp.updateRow(row.id, { projectName: v })" />
          <span v-else>{{ row.projectName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预计总收入" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.estimatedTotalRevenue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { estimatedTotalRevenue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="已确认收入" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.recognizedRevenue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { recognizedRevenue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="完工进度" width="90" align="right">
        <template #default="{ row }">
          <span v-if="typeof row.completionRate === 'number'">{{ (row.completionRate * 100).toFixed(1) }}%</span>
          <span v-else>N/A</span>
        </template>
      </el-table-column>
      <el-table-column label="账面价值" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.bookValue" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { bookValue: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="可收回金额" width="110" align="right">
        <template #default="{ row }"><span class="formula">{{ row.recoverableAmount.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="减值金额" width="100" align="right">
        <template #default="{ row }"><span class="formula">{{ row.impairmentAmount.toLocaleString() }}</span></template>
      </el-table-column>
      <el-table-column label="管理层计提" width="110">
        <template #default="{ row }">
          <el-input-number :model-value="row.managementProvision" size="small" :controls="false" :disabled="isReadonly"
            @change="(v: number) => imp.updateRow(row.id, { managementProvision: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="90" align="right">
        <template #default="{ row }">{{ row.difference.toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="imp.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <h4>审计说明</h4>
    <el-input v-model="imp.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2Impairment } from '../../composables/useF2Impairment'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const imp = useF2Impairment({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-spe-impairment { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.formula { text-decoration: underline dotted #909399; }
:deep(.error-row) { background: #fef0f0; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
