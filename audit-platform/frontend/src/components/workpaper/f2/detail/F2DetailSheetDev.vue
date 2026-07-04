<template>
  <div class="f2-dev-product">
    <h3 class="sheet-title">开发产品明细表 F2-10</h3>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="dev.addRow()">新增项目</el-button>
      <CycleImportExportDropdown
        :wp-id="wpId"
        api-prefix="f2"
        sheet="F2-10"
        :disabled="isReadonly"
      />
      <span class="account-tag">科目 1408</span>
      <el-tag v-if="dev.agingMismatchCount.value > 0" type="warning" size="small">
        {{ dev.agingMismatchCount.value }} 行库龄≠净值
      </el-tag>
    </div>

    <el-segmented v-model="dev.activeSegment.value" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="dev.enrichedRows.value" border size="small" max-height="480"
      :row-class-name="({ row }) => row.isLongTerm || row.agingMismatch ? 'warn-row' : ''">
      <el-table-column prop="projectName" label="项目名称" width="140" fixed />

      <template v-if="dev.activeSegment.value === 'basic'">
        <el-table-column label="楼栋" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.buildingNo" size="small"
              @change="(v: string) => dev.updateRow(row.id, { buildingNo: v })" />
            <span v-else>{{ row.buildingNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="产品类型" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.productType" size="small"
              @change="(v: string) => dev.updateRow(row.id, { productType: v })" />
            <span v-else>{{ row.productType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可售面积" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.area" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { area: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="已售面积" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.soldArea" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { soldArea: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="套数" width="80">
          <template #default="{ row }">
            <el-input-number :model-value="row.units" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { units: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>

      <template v-else-if="dev.activeSegment.value === 'land'">
        <el-table-column label="土地-期初" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.landOpen" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { landOpen: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="土地-增加" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.landIn" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { landIn: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="土地-减少" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.landOut" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { landOut: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="土地-期末" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.landClose.toLocaleString() }}</span></template>
        </el-table-column>
      </template>

      <template v-else-if="dev.activeSegment.value === 'construction'">
        <el-table-column label="建安-期初" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.buildOpen" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { buildOpen: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="建安-增加" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.buildIn" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { buildIn: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="建安-减少" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.buildOut" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { buildOut: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="建安-期末" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.buildClose.toLocaleString() }}</span></template>
        </el-table-column>
      </template>

      <template v-else-if="dev.activeSegment.value === 'interest'">
        <el-table-column label="利息-期初" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.intOpen" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { intOpen: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="利息-增加" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.intIn" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { intIn: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="利息-减少" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.intOut" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { intOut: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="利息-期末" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.intClose.toLocaleString() }}</span></template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="其他-期初" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.otherOpen" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { otherOpen: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="其他-增加" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.otherIn" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { otherIn: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="其他-减少" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.otherOut" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { otherOut: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="其他-期末" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.otherClose.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="结转转出" width="100">
          <template #default="{ row }">
            <el-input-number :model-value="row.transferOut" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { transferOut: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="成本合计" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.totalClose.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="存货净值" width="100" align="right">
          <template #default="{ row }"><span class="formula">{{ row.netInventory.toLocaleString() }}</span></template>
        </el-table-column>
        <el-table-column label="1年以内" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.agingLt1" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { agingLt1: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="3年以上" width="90">
          <template #default="{ row }">
            <el-input-number :model-value="row.agingGt3" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => dev.updateRow(row.id, { agingGt3: v ?? 0 })" />
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link type="danger" size="small" @click="dev.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-row">
      合计 — 土地: {{ dev.totals.value.landClose.toLocaleString() }}
      | 建安: {{ dev.totals.value.buildClose.toLocaleString() }}
      | 利息: {{ dev.totals.value.intClose.toLocaleString() }}
      | 净值: {{ dev.totals.value.netInventory.toLocaleString() }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2DevProductSheet } from '../../composables/useF2DevProductSheet'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'

const props = defineProps<{
  wpId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const segmentOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '土地成本', value: 'land' },
  { label: '建安成本', value: 'construction' },
  { label: '资本化利息', value: 'interest' },
  { label: '其他+结转', value: 'other' },
]

const dev = useF2DevProductSheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-dev-product { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 8px; }
.toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.account-tag { font-size: 12px; color: #909399; }
.segment-bar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; }
.totals-row { margin-top: 12px; font-size: 12px; }
:deep(.warn-row) { background: #fdf6ec; }
</style>
