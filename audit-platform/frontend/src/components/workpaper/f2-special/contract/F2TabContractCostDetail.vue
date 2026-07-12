<template>
  <div class="f2-contract-cost">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按 CAS14 号列示合同履约成本的期初、增加、减少、期末构成（设备材料 / 建安分包 / 人工 / 其他）。</p>
        <p>2. 灰底列为自动计算列（各期小计、期末小计、审定小计），由明细自动汇总，不可手动编辑。</p>
        <p>3. "调整审定"段落中，"是否直接相关""是否能收回"用于判断资本化条件，不满足者应转出。</p>
        <p>4. 期末合计应与合同履约成本科目（1410）余额及审定表勾稽一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：核实合同履约成本各构成要素的完整性与准确性，确认期末余额符合资本化条件并与账面、审定表勾稽一致。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="cc.addRow()">+ 新增项目</el-button>
        <el-tag size="small" type="info">期末合计: {{ cc.totals.value.end_subtotal.toLocaleString() }}</el-tag>
      </div>
      <div class="toolbar-right">
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
        <GtIndexChip value="wp:F2-55" />
        <el-tag size="small" type="info">共 {{ cc.enrichedRows.value.length }} 行</el-tag>
      </div>
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
        <el-table-column label="小计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="小计 = 设备材料 + 建安分包 + 人工 + 其他" placement="top">
              <span class="formula">{{ row.opening_subtotal.toLocaleString() }}</span>
            </el-tooltip>
          </template>
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
        <el-table-column label="小计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="小计 = 设备材料 + 建安分包 + 人工 + 其他" placement="top">
              <span class="formula">{{ row.increase_subtotal.toLocaleString() }}</span>
            </el-tooltip>
          </template>
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
        <el-table-column label="小计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="小计 = 设备材料 + 建安分包 + 人工 + 其他" placement="top">
              <span class="formula">{{ row.decrease_subtotal.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <template v-else-if="cc.activeSegment.value === 'end'">
        <el-table-column label="设备材料" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 增加 − 减少" placement="top">
              <span class="formula">{{ row.end_equipment.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="建安分包" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 增加 − 减少" placement="top">
              <span class="formula">{{ row.end_construction.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="人工" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 增加 − 减少" placement="top">
              <span class="formula">{{ row.end_labor.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="其他" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 增加 − 减少" placement="top">
              <span class="formula">{{ row.end_other.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="小计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="期末小计 = 设备材料 + 建安分包 + 人工 + 其他" placement="top">
              <span class="formula">{{ row.end_subtotal.toLocaleString() }}</span>
            </el-tooltip>
          </template>
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
        <el-table-column label="审定小计" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="审定小计 = 期末小计经资本化条件判断后的审定金额" placement="top">
              <span class="formula">{{ row.audited_subtotal.toLocaleString() }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="cc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
        </div>
      </template>
      <el-input v-model="cc.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请说明合同履约成本构成的完整性、计量准确性及资本化条件判断结果……" :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2ContractCost } from '../../composables/useF2ContractCost'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

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
.f2-contract-cost { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-contract-cost :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-contract-cost :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.segment-bar { margin-bottom: 8px; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fdf6ec; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
