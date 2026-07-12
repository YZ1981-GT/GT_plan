<template>
  <div class="f2-capacity-energy">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表分析各产品线产量与设计产能、单位能耗（电/水/气）的匹配性，识别 IPO 存货舞弊迹象。</p>
        <p>2. 灰底列为自动计算列（产能利用率、单位能耗、上期对比），不可手动编辑。</p>
        <p>3. 产能利用率超过 100%（标红）或单位能耗异常波动（标黄）须重点关注并说明原因。</p>
        <p>4. 结合采购价格（F2-61）与供应商访谈（F2-71/72）交叉验证产销量真实性。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：通过产量、产能利用率与单位能耗的匹配性分析，验证产销量数据的真实性与合理性。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ce.addRow()">+ 新增产品线</el-button>
        <el-tag v-if="ce.abnormalCount.value > 0" type="warning" size="small">
          {{ ce.abnormalCount.value }} 行异常
        </el-tag>
      </div>
      <div class="toolbar-right">
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
        <GtIndexChip value="wp:F2-63" />
        <el-tag size="small" type="info">共 {{ ce.enrichedRows.value.length }} 行</el-tag>
      </div>
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
        <el-table-column label="产能利用率%" width="105" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="产能利用率 = 实际产量 / 设计产能" placement="top">
              <span class="formula" :class="{ 'cap-warn': row.isOverCapacity }">
                {{ fmtPct(row.utilizationPct) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column label="电耗" align="center">
          <el-table-column label="总量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.elecTotal" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ce.updateRow(row.id, { elecTotal: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="单位电耗" width="95" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="单位电耗 = 电耗总量 / 实际产量" placement="top">
                <span :class="{ 'energy-warn': row.isEnergyAbnormal, formula: true }">
                  {{ fmtUnit(row.unitElec) }}
                </span>
              </el-tooltip>
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
          <el-table-column label="单位水耗" width="95" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="单位水耗 = 水耗总量 / 实际产量" placement="top">
                <span class="formula">{{ fmtUnit(row.unitWater) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="气耗" align="center">
          <el-table-column label="总量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.gasTotal" size="small" :controls="false" :disabled="isReadonly"
                @change="(v: number) => ce.updateRow(row.id, { gasTotal: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="单位气耗" width="95" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="单位气耗 = 气耗总量 / 实际产量" placement="top">
                <span class="formula">{{ fmtUnit(row.unitGas) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="上期产量" width="95">
          <template #default="{ row }">
            <el-input-number :model-value="row.priorOutput" size="small" :controls="false" :disabled="isReadonly"
              @change="(v: number) => ce.updateRow(row.id, { priorOutput: v ?? 0 })" />
          </template>
        </el-table-column>
        <el-table-column label="上期利用率%" width="105" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="上期利用率 = 上期产量 / 设计产能" placement="top">
              <span class="formula">{{ fmtPct(row.priorUtilizationPct) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="上期单位电耗" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="上期单位电耗 = 上期电耗总量 / 上期产量" placement="top">
              <span class="formula">{{ fmtUnit(row.priorUnitElec) }}</span>
            </el-tooltip>
          </template>
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

    <!-- 分析结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">分析结论</span>
        </div>
      </template>
      <el-input v-model="ce.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请说明产能利用率、单位能耗分析结果及异常原因，评价产销量数据合理性……" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2CapacityEnergy } from '../../composables/useF2CapacityEnergy'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

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
.f2-capacity-energy { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-capacity-energy :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-capacity-energy :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.table-scroll-wrap { overflow-x: auto; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.cap-warn { color: #f56c6c; font-weight: 600; }
.energy-warn { color: #e6a23c; font-weight: 600; }
:deep(.cap-row) { background: #fef0f0; }
:deep(.energy-row) { background: #fdf6ec; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
