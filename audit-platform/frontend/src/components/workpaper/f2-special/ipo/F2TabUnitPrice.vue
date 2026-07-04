<template>
  <div class="f2-unit-price">
    <h3 class="title">原材料单价分析 F2-62</h3>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="up.addRow()">+ 新增材料</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-62"
        :disabled="isReadonly"
        ai-section="price-analysis"
        :existing-content="up.auditNote.value"
        review-section="F2-62-price"
        @ai-filled="(t: string) => { up.auditNote.value = t }"
      />
      <el-input v-model="up.searchQuery.value" size="small" placeholder="搜索材料名称/规格" clearable class="search" />
      <el-tag v-if="up.abnormalCount.value > 0" type="danger" size="small">
        {{ up.abnormalCount.value }} 行偏离度异常
      </el-tag>
      <span class="hint">共 {{ up.filteredRows.value.length }} 行</span>
    </div>

    <div class="table-scroll-wrap">
      <el-table
        :data="up.filteredRows.value"
        border
        size="small"
        max-height="480"
        :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''"
      >
        <el-table-column prop="materialName" label="材料名称" width="120" fixed />
        <el-table-column label="规格" width="90" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.spec" size="small"
              @change="(v: string) => up.updateRow(row.id, { spec: v })" />
            <span v-else>{{ row.spec }}</span>
          </template>
        </el-table-column>
        <el-table-column label="单位" width="70" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unit" size="small"
              @change="(v: string) => up.updateRow(row.id, { unit: v })" />
            <span v-else>{{ row.unit }}</span>
          </template>
        </el-table-column>

        <el-table-column label="T期" align="center">
          <el-table-column label="单价" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.priceT" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { priceT: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.qtyT" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { qtyT: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购额" width="100" align="right">
            <template #default="{ row }">
              <span class="formula">{{ row.amountT.toLocaleString() }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-1期" align="center">
          <el-table-column label="单价" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.priceT1" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { priceT1: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.qtyT1" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { qtyT1: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购额" width="100" align="right">
            <template #default="{ row }">
              <span class="formula">{{ row.amountT1.toLocaleString() }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-2期" align="center">
          <el-table-column label="单价" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.priceT2" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { priceT2: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.qtyT2" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => up.updateRow(row.id, { qtyT2: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="采购额" width="100" align="right">
            <template #default="{ row }">
              <span class="formula">{{ row.amountT2.toLocaleString() }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="同比变动率" width="95" align="right">
          <template #default="{ row }">
            <span class="formula">{{ up.fmtRate(row.yoyChangeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="环比变动率" width="95" align="right">
          <template #default="{ row }">
            <span class="formula">{{ up.fmtRate(row.momChangeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="行业均价" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.industryAvgPrice" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => up.updateRow(row.id, { industryAvgPrice: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="偏离度%" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'dev-warn': row.isHighDeviation }">{{ row.deviationPct.toFixed(1) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分析结论" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.analysisConclusion" size="small"
              @change="(v: string) => up.updateRow(row.id, { analysisConclusion: v })" />
            <span v-else>{{ row.analysisConclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @change="(v: string) => up.updateRow(row.id, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="55" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="up.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <h4>分析结论</h4>
    <el-input v-model="up.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2UnitPrice } from '../../composables/useF2UnitPrice'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const up = useF2UnitPrice({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-unit-price { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search { width: 180px; }
.hint { font-size: 12px; color: #909399; }
.table-scroll-wrap { overflow-x: auto; }
.formula { text-decoration: underline dotted #909399; }
.dev-warn { color: #f56c6c; font-weight: 600; background: #fef0f0; padding: 0 4px; border-radius: 2px; }
:deep(.warn-row) { background: #fef0f0; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
