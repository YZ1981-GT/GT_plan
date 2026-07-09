<template>
  <div class="h2-tab-cost-comparison">
    <!-- 造价比较表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>工程造价比较（H2-7）</span>
          <div class="section-header-actions">
            <GtIndexChip value="H2-2" label="→ H2-2明细" />
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-7')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table :data="displayRows" border stripe size="small" class="cost-table"
        :row-class-name="costRowClass">
        <el-table-column prop="name" label="工程项目" min-width="130" fixed />
        <el-table-column prop="contractAmount" label="合同金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.contractAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'contractAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.contractAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="budgetAmount" label="预算金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.budgetAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'budgetAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.budgetAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actualCost" label="实际造价" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.actualCost"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'actualCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.actualCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同差异" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=实际-合同">{{ fmtAmt(row.contractDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同差异率(%)" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.contractDiffRate ?? 0) > 10 }]"
              :title="`=(实际-合同)/合同×100`">
              {{ row.contractDiffRate != null ? row.contractDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="预算差异" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=实际-预算">{{ fmtAmt(row.budgetDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预算差异率(%)" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': (row.budgetDiffRate ?? 0) > 10 }]"
              :title="`=(实际-预算)/预算×100`">
              {{ row.budgetDiffRate != null ? row.budgetDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="materialCost" label="材料费" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.materialCost"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'materialCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.materialCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="laborCost" label="人工费" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.laborCost"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'laborCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.laborCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="材料占比(%)" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=材料/实际×100">
              {{ row.materialRate != null ? row.materialRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="人工占比(%)" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=人工/实际×100">
              {{ row.laborRate != null ? row.laborRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="unitCost" label="单位造价" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.unitCost"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'unitCost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.unitCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="超支标记" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="(row.budgetDiffRate ?? 0) > 10" type="danger" size="small">超支</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button v-if="!row.isTotal" size="small" type="danger" link
              @click="handleRemove(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增工程</el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写造价比较分析说明..." :disabled="isReadonly"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>16列中14列为公式自动计算（差异/差异率/占比等）</li>
        <li>预算差异率>10%红色高亮标记为"超支"</li>
        <li>数据从H2-2明细表自动取入(可手动覆盖)</li>
        <li>合计行自动SUM所有工程项目</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabCostComparison.vue — H2-7 造价比较
 * el-table 16列(14公式) + 超支红色高亮 + GtIndexChip→H2-2
 * Spec: Task 4.9 | Requirements: 8.1-8.7
 */
import { inject, toRef, computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2CostComparison } from '../../composables/useH2CostComparison'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2CostComparison({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
})

const displayRows = computed(() => [...state.detailRows.value, state.totalRow.value])

function costRowClass({ row }: any) {
  if (row.isTotal) return 'total-row'
  if ((row.budgetDiffRate ?? 0) > 10) return 'over-budget-row'
  return ''
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增工程', {
      confirmButtonText: '确认', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value)
  } catch { /* cancelled */ }
}

function handleRemove(rowId: string) {
  state.removeRow(rowId)
}

function handleAiGenerate() {
  console.log('AI generate H2-7')
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-cost-comparison { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.cost-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.add-row-bar { margin-top: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background-color: var(--el-fill-color-light) !important; }
:deep(.over-budget-row) { background-color: #fef0f0 !important; }
</style>
