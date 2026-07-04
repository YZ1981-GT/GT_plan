<template>
  <div class="f2-capacity-energy">
    <h3 class="title">产量与产能/能耗分析 F2-63</h3>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="ce.addRow()">+ 新增产品线</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-63"
        :disabled="isReadonly"
        ai-section="capacity-analysis"
        :existing-content="ce.auditNote.value"
        review-section="F2-63-capacity"
        @ai-filled="(t: string) => { ce.auditNote.value = t }"
      />
      <el-tag v-if="ce.abnormalCount.value > 0" type="warning" size="small">
        {{ ce.abnormalCount.value }} 行异常
      </el-tag>
      <span class="hint">共 {{ ce.enrichedRows.value.length }} 行</span>
    </div>

    <div class="table-scroll-wrap">
      <el-table
        :data="ce.enrichedRows.value"
        border
        size="small"
        max-height="480"
        :row-class-name="rowClass"
      >
        <el-table-column label="产品名称" width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.productName" size="small"
              @change="(v: string) => ce.updateRow(row.id, { productName: v })" />
            <span v-else>{{ row.productName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="生产线" width="100" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.productLine" size="small"
              @change="(v: string) => ce.updateRow(row.id, { productLine: v })" />
            <span v-else>{{ row.productLine }}</span>
          </template>
        </el-table-column>
        <el-table-column label="设计产能" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.designCapacity" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => ce.updateRow(row.id, { designCapacity: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="实际产量" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.actualOutput" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => ce.updateRow(row.id, { actualOutput: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="产能利用率%" width="105" align="right">
          <template #default="{ row }">
            <span :class="{ 'cap-warn': row.isOverCapacity }">
              {{ fmtPct(row.utilizationPct) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="电耗" align="center">
          <el-table-column label="总量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.elecTotal" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ce.updateRow(row.id, { elecTotal: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="单位电耗" width="95" align="right">
            <template #default="{ row }">
              <span :class="{ 'energy-warn': row.isEnergyAbnormal, formula: true }">
                {{ fmtUnit(row.unitElec) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="水耗" align="center">
          <el-table-column label="总量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.waterTotal" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ce.updateRow(row.id, { waterTotal: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="单位水耗" width="95" align="right">
            <template #default="{ row }"><span class="formula">{{ fmtUnit(row.unitWater) }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="气耗" align="center">
          <el-table-column label="总量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.gasTotal" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ce.updateRow(row.id, { gasTotal: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="单位气耗" width="95" align="right">
            <template #default="{ row }"><span class="formula">{{ fmtUnit(row.unitGas) }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="上期产量" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorOutput" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => ce.updateRow(row.id, { priorOutput: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="上期利用率%" width="105" align="right">
          <template #default="{ row }"><span class="formula">{{ fmtPct(row.priorUtilizationPct) }}</span></template>
        </el-table-column>
        <el-table-column label="上期单位电耗" width="110" align="right">
          <template #default="{ row }"><span class="formula">{{ fmtUnit(row.priorUnitElec) }}</span></template>
        </el-table-column>
        <el-table-column label="上期电耗总量" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorElecTotal" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => ce.updateRow(row.id, { priorElecTotal: v ?? 0 })" />
          </template>
        </el-table-column>

        <el-table-column label="变动说明" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.changeNote" size="small"
              @change="(v: string) => ce.updateRow(row.id, { changeNote: v })" />
            <span v-else>{{ row.changeNote }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计关注" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditFocus" size="small"
              @change="(v: string) => ce.updateRow(row.id, { auditFocus: v })" />
            <span v-else>{{ row.auditFocus }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="55" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="ce.removeRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <h4>分析结论</h4>
    <el-input v-model="ce.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2CapacityEnergy } from '../../composables/useF2CapacityEnergy'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ce = useF2CapacityEnergy({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmtPct(v: number | 'N/A'): string {
  return v === 'N/A' ? 'N/A' : `${v.toFixed(1)}%`
}

function fmtUnit(v: number | '-'): string {
  return v === '-' ? '—' : v.toFixed(4)
}

function rowClass({ row }: { row: { isOverCapacity: boolean; isEnergyAbnormal: boolean } }): string {
  if (row.isOverCapacity) return 'cap-row'
  if (row.isEnergyAbnormal) return 'energy-row'
  return ''
}
</script>

<style scoped>
.f2-capacity-energy { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.hint { font-size: 12px; color: #909399; }
.table-scroll-wrap { overflow-x: auto; }
.formula { text-decoration: underline dotted #909399; }
.cap-warn { color: #f56c6c; font-weight: 600; }
.energy-warn { color: #e6a23c; font-weight: 600; }
:deep(.cap-row) { background: #fef0f0; }
:deep(.energy-row) { background: #fdf6ec; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
