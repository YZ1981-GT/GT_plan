<template>
  <div class="h2-tab-detail">
    <!-- 区段Tab切换 -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <!-- 主表区域 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>在建工程明细表 — {{ segmentLabel }}</span>
          <div class="section-header-actions">
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportCmd">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('H2-2')">💬</el-button>
          </div>
        </div>
      </template>

      <!-- 区段1: 基本信息 -->
      <el-table v-if="activeSegment === 'basic'" :data="displayRows" border stripe size="small"
        class="detail-table" :row-class-name="detailRowClass" highlight-current-row
        @current-change="handleRowSelect">
        <el-table-column prop="name" label="工程项目" min-width="140" fixed />
        <el-table-column prop="budget" label="预算金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.budget"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'budget', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.budget) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="startDate" label="开工日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.startDate"
              type="date" size="small" value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'startDate', $event)" />
            <span v-else>{{ row.startDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="plannedEndDate" label="预计竣工" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.plannedEndDate"
              type="date" size="small" value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'plannedEndDate', $event)" />
            <span v-else>{{ row.plannedEndDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actualEndDate" label="实际竣工" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.actualEndDate"
              type="date" size="small" value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'actualEndDate', $event)" />
            <span v-else>{{ row.actualEndDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完工进度(%)" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=累计投入/预算×100">
              {{ row.completionRate != null ? row.completionRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="accumulatedInput" label="累计投入" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.accumulatedInput"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'accumulatedInput', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.accumulatedInput) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fundSource" label="资金来源" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.fundSource" size="small"
              @change="onCellChange(row.rowId, 'fundSource', $event)" />
            <span v-else>{{ row.fundSource || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="工程类别" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.category" size="small"
              @change="onCellChange(row.rowId, 'category', $event)" />
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 区段2: 增减 -->
      <el-table v-if="activeSegment === 'movement'" :data="displayRows" border stripe size="small"
        class="detail-table" :row-class-name="detailRowClass" highlight-current-row
        @current-change="handleRowSelect">
        <el-table-column prop="name" label="工程项目" min-width="140" fixed />
        <el-table-column prop="cipBegin" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.cipBegin"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'cipBegin', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.cipBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseMaterial" label="增加-材料" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.increaseMaterial"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'increaseMaterial', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.increaseMaterial) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseLabor" label="增加-人工" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.increaseLabor"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'increaseLabor', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.increaseLabor) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseMachinery" label="增加-机械" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.increaseMachinery"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'increaseMachinery', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.increaseMachinery) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseInterest" label="增加-利息" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.increaseInterest"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'increaseInterest', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.increaseInterest) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseOther" label="增加-其他" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.increaseOther"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'increaseOther', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.increaseOther) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="增加合计" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=材料+人工+机械+利息+其他">{{ fmtAmt(row.increaseTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.decrease"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'decrease', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 区段3: 竣工结转 -->
      <el-table v-if="activeSegment === 'transfer'" :data="displayRows" border stripe size="small"
        class="detail-table" :row-class-name="detailRowClass" highlight-current-row
        @current-change="handleRowSelect">
        <el-table-column prop="name" label="工程项目" min-width="140" fixed />
        <el-table-column prop="transferAmount" label="转固金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.transferAmount"
              :controls="false" size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'transferAmount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transferAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transferDate" label="转固日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.transferDate"
              type="date" size="small" value-format="YYYY-MM-DD" style="width:100%"
              @change="onCellChange(row.rowId, 'transferDate', $event)" />
            <span v-else>{{ row.transferDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少-转固">{{ fmtAmt(row.cipEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transferTo" label="转入固定资产类别" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.transferTo" size="small"
              @change="onCellChange(row.rowId, 'transferTo', $event)" />
            <span v-else>{{ row.transferTo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新增行 -->
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增工程项目</el-button>
      </div>
    </el-card>

    <!-- 交叉验证 H2-1 -->
    <el-alert v-if="crossDiff !== 0" type="warning" :closable="false" show-icon style="margin-bottom:12px">
      <template #title>交叉验证：明细合计期末余额 vs H2-1审定数差异 {{ fmtAmt(crossDiff) }}</template>
    </el-alert>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>50列宽表拆分为3区段Tab(基本信息/增减/竣工结转)，行选中同步高亮</li>
        <li>三角勾稽(含转固)：期末=期初+增加合计-减少-转固</li>
        <li>增加合计=材料+人工+机械+利息+其他（公式列自动计算）</li>
        <li>完工进度=累计投入/预算×100%（公式列自动计算）</li>
        <li>各区段合计行自动SUM所有工程项目行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabDetail.vue — H2-2 明细表
 * 3区段Tab切换(基本/增减/竣工结转) + 行同步 + 固定列
 * Spec: Task 4.3 | Requirements: 3.1-3.12
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Detail } from '../../composables/useH2Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const activeSegment = ref<'basic' | 'movement' | 'transfer'>('basic')
const segmentOptions = [
  { label: '基本信息', value: 'basic' },
  { label: '增减变动', value: 'movement' },
  { label: '竣工结转', value: 'transfer' },
]

const segmentLabel = computed(() => {
  const map: Record<string, string> = { basic: '基本信息', movement: '增减变动', transfer: '竣工结转' }
  return map[activeSegment.value]
})

const state = useH2Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
})

const displayRows = computed(() => [...state.rows.value, state.subtotalRow.value])
const crossDiff = computed(() => state.crossValidationH1.value.diff)

function detailRowClass({ row }: any) {
  if (row.isTotal) return 'total-row'
  return ''
}

const selectedRowId = ref('')
function handleRowSelect(row: any) {
  if (row) selectedRowId.value = row.rowId
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增工程', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value)
  } catch { /* cancelled */ }
}

function handleExportCmd(cmd: string) {
  console.log('export command:', cmd)
}

function handleAiGenerate() {
  console.log('AI generate H2-2')
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
.h2-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.segment-bar { margin-bottom: 16px; }
.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.add-row-bar { margin-top: 12px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.total-row) { font-weight: 600; background-color: var(--el-fill-color-light) !important; }
</style>
