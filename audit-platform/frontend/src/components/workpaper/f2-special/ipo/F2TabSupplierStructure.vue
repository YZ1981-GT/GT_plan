<template>
  <div class="f2-supplier-structure">
    <h3 class="title">重要供应商结构分析 F2-68</h3>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="ss.addRow()">+ 新增供应商</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-68"
        :disabled="isReadonly"
        ai-section="supplier-analysis"
        :existing-content="ss.auditNote.value"
        review-section="F2-68-structure"
        @ai-filled="(t: string) => { ss.auditNote.value = t }"
      />
      <el-tag size="small" type="info">
        前5大占比 {{ ss.concentrationSummary.value.top5Ratio.toFixed(1) }}%
        | 前10大 {{ ss.concentrationSummary.value.top10Ratio.toFixed(1) }}%
      </el-tag>
    </div>

    <div class="table-scroll-wrap">
      <el-table
        :data="ss.enrichedRows.value"
        border
        size="small"
        max-height="480"
        :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''"
      >
        <!-- 固定列区 -->
        <el-table-column type="index" label="序号" width="55" fixed />
        <el-table-column label="供应商名称" width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supplierName" size="small"
              @change="(v: string) => ss.updateRow(row.id, { supplierName: v })" />
            <span v-else>{{ row.supplierName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="采购品类" width="100" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.category" size="small"
              @change="(v: string) => ss.updateRow(row.id, { category: v })" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合作年份" width="90" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.coopYear" size="small"
              @change="(v: string) => ss.updateRow(row.id, { coopYear: v })" />
            <span v-else>{{ row.coopYear }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方" width="80" fixed>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isRelated" size="small"
              @change="(v: '是'|'否') => ss.updateRow(row.id, { isRelated: v })">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isRelated }}</span>
          </template>
        </el-table-column>

        <!-- 滚动列区：各期金额/占比/排名 -->
        <el-table-column label="T期" align="center">
          <el-table-column label="金额" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.amountT" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ss.updateRow(row.id, { amountT: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="占比%" width="75" align="right">
            <template #default="{ row }">
              <span :class="{ 'ratio-warn': row.isHighConcentration }">{{ row.ratioT.toFixed(1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="排名" width="60" align="right">
            <template #default="{ row }"><span class="formula">{{ row.rankT || '—' }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-1期" align="center">
          <el-table-column label="金额" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.amountT1" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ss.updateRow(row.id, { amountT1: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="占比%" width="75" align="right">
            <template #default="{ row }">{{ row.ratioT1.toFixed(1) }}</template>
          </el-table-column>
          <el-table-column label="排名" width="60" align="right">
            <template #default="{ row }">{{ row.rankT1 || '—' }}</template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T-2期" align="center">
          <el-table-column label="金额" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.amountT2" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ss.updateRow(row.id, { amountT2: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="占比%" width="75" align="right">
            <template #default="{ row }">{{ row.ratioT2.toFixed(1) }}</template>
          </el-table-column>
          <el-table-column label="排名" width="60" align="right">
            <template #default="{ row }">{{ row.rankT2 || '—' }}</template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="T vs T-1" align="center">
          <el-table-column label="变动率" width="80" align="right">
            <template #default="{ row }">
              <span v-if="typeof row.changeTvsT1 === 'number'">{{ (row.changeTvsT1 * 100).toFixed(1) }}%</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="新增/退出" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.entryFlag" :type="row.isNewTop5 ? 'danger' : 'warning'" size="small">
              {{ row.entryFlag }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="集中度评价" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.concentrationEval" size="small"
              @change="(v: string) => ss.updateRow(row.id, { concentrationEval: v })" />
            <span v-else>{{ row.concentrationEval }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @change="(v: string) => ss.updateRow(row.id, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="55" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="ss.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="summary-bar">
      T期采购总额：{{ ss.concentrationSummary.value.totalT.toLocaleString() }}
      | 前5大集中度：{{ ss.concentrationSummary.value.top5Ratio.toFixed(1) }}%
      | 前10大：{{ ss.concentrationSummary.value.top10Ratio.toFixed(1) }}%
    </div>

    <h4>分析结论</h4>
    <el-input v-model="ss.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2SupplierStructure } from '../../composables/useF2SupplierStructure'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ss = useF2SupplierStructure({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-supplier-structure { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.table-scroll-wrap { overflow-x: auto; }
.formula { text-decoration: underline dotted #909399; }
.ratio-warn { color: #e6a23c; font-weight: 600; }
:deep(.warn-row) { background: #fdf6ec; }
.summary-bar { margin-top: 12px; font-size: 12px; color: #606266; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
