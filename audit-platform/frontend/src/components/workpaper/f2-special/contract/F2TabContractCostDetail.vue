<template>
  <div class="f2-contract-cost">
    <h3 class="title">合同履约成本构成明细 F2-55</h3>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="cc.addRow()">+ 新增项目</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-55"
        :disabled="isReadonly"
        ai-section="contract-cost-note"
        :existing-content="cc.auditNote.value"
        review-section="F2-55-detail"
        @ai-filled="(t: string) => { cc.auditNote.value = t }"
      />
      <el-tag size="small" type="info">期末合计: {{ cc.totals.value.end_subtotal.toLocaleString() }}</el-tag>
    </div>

    <el-segmented v-model="cc.activeSegment.value" :options="segments" size="small" class="segment-bar" />

    <el-table :data="cc.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.notRecoverable ? 'warn-row' : ''">
      <el-table-column prop="projectName" label="项目名称" width="130" fixed />

      <template v-if="cc.activeSegment.value === 'basic'">
        <el-table-column label="项目编码" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.projectCode" size="small"
              @change="(v: string) => cc.updateRow(row.id, { projectCode: v })" />
            <span v-else>{{ row.projectCode }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收入合同" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.contractName" size="small"
              @change="(v: string) => cc.updateRow(row.id, { contractName: v })" />
            <span v-else>{{ row.contractName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同金额" width="110">
          <template #default="{ row }">
            <el-input-number :model-value="row.contractAmount" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => cc.updateRow(row.id, { contractAmount: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>

      <template v-else-if="cc.activeSegment.value === 'opening'">
        <el-table-column v-for="col in quadCols" :key="col.key" :label="col.label" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row[`opening_${col.key}`]" size="small" :controls="false"
              :disabled="isReadonly"
              @change="(v: number) => cc.updateRow(row.id, { [`opening_${col.key}`]: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="小计" width="100" align="right">
          <template #default="{ row }">{{ row.opening_subtotal.toLocaleString() }}</template>
        </el-table-column>
      </template>

      <template v-else-if="cc.activeSegment.value === 'increase'">
        <el-table-column v-for="col in quadCols" :key="col.key" :label="col.label" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row[`increase_${col.key}`]" size="small" :controls="false"
              :disabled="isReadonly"
              @change="(v: number) => cc.updateRow(row.id, { [`increase_${col.key}`]: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="小计" width="100" align="right">
          <template #default="{ row }">{{ row.increase_subtotal.toLocaleString() }}</template>
        </el-table-column>
      </template>

      <template v-else-if="cc.activeSegment.value === 'decrease'">
        <el-table-column v-for="col in quadCols" :key="col.key" :label="col.label" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row[`decrease_${col.key}`]" size="small" :controls="false"
              :disabled="isReadonly"
              @change="(v: number) => cc.updateRow(row.id, { [`decrease_${col.key}`]: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="小计" width="100" align="right">
          <template #default="{ row }">{{ row.decrease_subtotal.toLocaleString() }}</template>
        </el-table-column>
      </template>

      <template v-else-if="cc.activeSegment.value === 'end'">
        <el-table-column label="设备材料" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.end_equipment.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="建安分包" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.end_construction.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="人工" width="90" align="right">
          <template #default="{ row }"><span class="formula">{{ row.end_labor.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="其他" width="90" align="right">
          <template #default="{ row }"><span class="formula">{{ row.end_other.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="小计" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.end_subtotal.toLocaleString() }}</span></template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="直接相关" width="80">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isDirectlyRelated" size="small"
              @change="(v: '是'|'否') => cc.updateRow(row.id, { isDirectlyRelated: v })">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isDirectlyRelated }}</span>
          </template>
        </el-table-column>
        <el-table-column label="能收回" width="80">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isRecoverable" size="small"
              @change="(v: '是'|'否') => cc.updateRow(row.id, { isRecoverable: v })">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isRecoverable }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定小计" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.audited_subtotal.toLocaleString() }}</span></template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="cc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <h4>审计说明</h4>
    <el-input v-model="cc.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2ContractCost } from '../../composables/useF2ContractCost'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const segments = [
  { label: '基础信息', value: 'basic' },
  { label: '期初', value: 'opening' },
  { label: '增加', value: 'increase' },
  { label: '减少', value: 'decrease' },
  { label: '期末', value: 'end' },
  { label: '调整审定', value: 'audit' },
]

const quadCols = [
  { key: 'equipment', label: '设备材料' },
  { key: 'construction', label: '建安分包' },
  { key: 'labor', label: '人工' },
  { key: 'other', label: '其他' },
]

const cc = useF2ContractCost({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-contract-cost { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
.segment-bar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; }
:deep(.warn-row) { background: #fdf6ec; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
