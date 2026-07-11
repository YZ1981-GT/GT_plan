<template>
  <div class="h8-tab-disposal-check">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H8-12减少检查表：租赁终止/提前退租检查。核心公式：终止损益=租赁负债余额-使用权资产净值。终止时H9租赁负债同步终止确认。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-12" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 区段Tab切换 -->
    <el-tabs v-model="activeTab" type="border-card">
      <!-- 区段1: 基本信息 -->
      <el-tab-pane label="基本信息" name="basic">
        <el-card shadow="never" class="table-card">
          <template #header>
            <div class="section-title">
              <span>租赁终止基本信息</span>
              <div class="title-actions">
                <el-button v-if="!isReadonly" size="small" @click="handleAddRow">+ 新增行</el-button>
                <el-button size="small" type="primary" plain @click="$emit('open-ai', 'disposal-basic')">AI 辅助</el-button>
                <el-button size="small" @click="$emit('open-review', 'disposal-basic')">复核</el-button>
              </div>
            </div>
          </template>
          <el-table :data="rows" border size="small" class="formula-table">
            <el-table-column prop="contractNo" label="合同号" min-width="110">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
                  @change="updateCell(row.rowId, 'contractNo', row.contractNo)" />
                <span v-else>{{ row.contractNo }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="assetName" label="承租资产" min-width="100">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
                  @change="updateCell(row.rowId, 'assetName', row.assetName)" />
                <span v-else>{{ row.assetName }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="terminationReason" label="终止原因" min-width="120">
              <template #default="{ row }">
                <el-select v-if="!isReadonly" v-model="row.terminationReason" size="small"
                  @change="updateCell(row.rowId, 'terminationReason', row.terminationReason)">
                  <el-option label="到期终止" value="到期终止" />
                  <el-option label="提前退租" value="提前退租" />
                  <el-option label="双方协商" value="双方协商" />
                  <el-option label="违约终止" value="违约终止" />
                  <el-option label="不可抗力" value="不可抗力" />
                </el-select>
                <span v-else>{{ row.terminationReason }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="terminationDate" label="终止日期" width="130">
              <template #default="{ row }">
                <el-date-picker v-if="!isReadonly" v-model="row.terminationDate" type="date"
                  size="small" value-format="YYYY-MM-DD" style="width:100%"
                  @change="updateCell(row.rowId, 'terminationDate', row.terminationDate)" />
                <span v-else>{{ row.terminationDate }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="remainingMonths" label="剩余期(月)" width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.remainingMonths" :controls="false" size="small" :min="0"
                  @change="(v: number | undefined) => updateCell(row.rowId, 'remainingMonths', v)" />
                <span v-else>{{ row.remainingMonths }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="approvalStatus" label="审批状态" width="100">
              <template #default="{ row }">
                <el-select v-if="!isReadonly" v-model="row.approvalStatus" size="small"
                  @change="updateCell(row.rowId, 'approvalStatus', row.approvalStatus)">
                  <el-option label="已审批" value="已审批" />
                  <el-option label="待审批" value="待审批" />
                </el-select>
                <el-tag v-else :type="row.approvalStatus === '已审批' ? 'success' : 'warning'" size="small">
                  {{ row.approvalStatus || '-' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="50" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="deleteRow(row.rowId)">✕</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 区段2: 终止计算 -->
      <el-tab-pane label="终止计算" name="calculation">
        <el-card shadow="never" class="table-card">
          <template #header>
            <div class="section-title">
              <span>终止损益计算</span>
              <div class="title-actions">
                <el-button size="small" type="primary" plain @click="$emit('open-ai', 'disposal-calc')">AI 辅助</el-button>
              </div>
            </div>
          </template>
          <el-table :data="rows" border size="small" class="formula-table" show-summary :summary-method="getCalcSummary">
            <el-table-column prop="contractNo" label="合同号" min-width="110" />
            <el-table-column prop="rouNetValue" label="使用权净值" width="120" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.rouNetValue" :controls="false" size="small"
                  @change="(v: number | undefined) => updateCell(row.rowId, 'rouNetValue', v)" />
                <span v-else>{{ fmtAmt(row.rouNetValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="liabilityBalance" label="租赁负债余额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.liabilityBalance" :controls="false" size="small"
                  @change="(v: number | undefined) => updateCell(row.rowId, 'liabilityBalance', v)" />
                <span v-else>{{ fmtAmt(row.liabilityBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="终止损益" width="130" align="right" class-name="formula-col">
              <template #default="{ row }">
                <span class="formula-value" :class="row.gainLoss >= 0 ? 'gain' : 'loss'"
                  title="公式：租赁负债余额 - 使用权资产净值">
                  {{ row.gainLoss >= 0 ? '+' : '' }}{{ fmtAmt(row.gainLoss) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="H9同步" width="130" align="center">
              <template #default="{ row }">
                <div class="h9-sync-cell">
                  <el-button v-if="!row.h9Synced && !isReadonly" size="small" type="warning" plain
                    @click="handleSyncH9(row.rowId)">
                    同步H9
                  </el-button>
                  <el-tag v-else-if="row.h9Synced" type="success" size="small">已同步</el-tag>
                  <span v-else>-</span>
                  <GtIndexChip v-if="row.contractNo" value="H9-2" :context-project-id="props.projectId"
                    context="终止后H9租赁负债也应终止确认" @click="emit('navigate-sheet', 'H9-2')" :prevent-navigate="true" />
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.remark" size="small"
                  @change="updateCell(row.rowId, 'remark', row.remark)" />
                <span v-else>{{ row.remark }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 未同步H9警告 -->
        <el-alert v-if="unsyncedRows.length > 0" type="warning" :closable="false" show-icon
          class="unsync-alert">
          <template #title>
            {{ unsyncedRows.length }}笔终止尚未同步H9，终止时租赁负债也应终止确认
          </template>
        </el-alert>

        <!-- 摘要卡片 -->
        <div class="stats-row">
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">终止损益合计</div>
            <div class="stat-value" :class="gainLossTotal >= 0 ? 'gain' : 'loss'">
              {{ gainLossTotal >= 0 ? '+' : '' }}{{ fmtAmt(gainLossTotal) }} 元
            </div>
          </el-card>
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">收益笔数</div>
            <div class="stat-value gain">{{ gainCount }}</div>
          </el-card>
          <el-card shadow="never" class="stat-card">
            <div class="stat-label">损失笔数</div>
            <div class="stat-value loss">{{ lossCount }}</div>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>终止损益=租赁负债余额-使用权资产净值（正=收益/负=损失）</li>
        <li>终止时必须同步H9：租赁负债也应终止确认（同步按钮）</li>
        <li>提前退租需检查是否存在违约金、需额外确认损益</li>
        <li>到期终止时净值和负债余额应接近0（正常摊销完毕）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDisposalCheck.vue — H8-12 减少检查表（租赁终止）
 * 39行28列，2区段Tab（基本信息/终止计算），H9同步按钮
 * Spec: Task 4.8 | Requirements: 7.3-7.5
 */
import { ref, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8DisposalCheck } from '../../composables/useH8DisposalCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const activeTab = ref('basic')

const {
  rows, gainLossTotal, gainCount, lossCount, unsyncedRows,
  addRow, deleteRow, updateCell, syncToH9,
} = useH8DisposalCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入合同号', '新增终止行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：LEASE-2024-001',
  })
  if (value) addRow(value)
}

function handleSyncH9(rowId: string) {
  syncToH9(rowId)
}

function getCalcSummary({ columns }: { columns: any[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 3) return `${gainLossTotal.value >= 0 ? '+' : ''}${fmtAmt(gainLossTotal.value)}`
    return ''
  })
}
</script>

<style scoped>
.h8-tab-disposal-check { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.table-card { margin-bottom: 12px; }
.formula-table { font-size: 13px; }
.formula-table :deep(.formula-col) { background: #fefce8; }
.formula-value { border-bottom: 1px dashed #d97706; cursor: help; }
.gain { color: #16a34a; }
.loss { color: #dc2626; }

.unsync-alert { margin: 12px 0; }

.stats-row { display: flex; gap: 16px; margin-top: 16px; }
.stat-card { flex: 1; text-align: center; }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.stat-value { font-size: 20px; font-weight: 700; color: var(--el-color-primary); }

.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }

.h9-sync-cell { display: flex; align-items: center; gap: 4px; justify-content: center; flex-wrap: wrap; }
</style>
