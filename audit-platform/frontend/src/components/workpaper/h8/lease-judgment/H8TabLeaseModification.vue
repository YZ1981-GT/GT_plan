<template>
  <div class="h8-tab-lease-modification">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第28-30条：租赁变更会计处理——①增加范围+价格合理→单独租赁 ②减少范围→按比例终止 ③其他变更→重新计量租赁负债+调整使用权资产(calcRemeasurement)。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-7" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 标题行 -->
    <div class="section-header">
      <div class="header-left">
        <span class="section-title-text">租赁变更记录</span>
        <el-tag type="info" size="small">{{ rows.length }} 笔变更</el-tag>
        <el-tag v-if="typeStats.separateLease > 0" type="success" size="small">单独租赁：{{ typeStats.separateLease }}</el-tag>
        <el-tag v-if="typeStats.scopeReduction > 0" type="warning" size="small">范围减少：{{ typeStats.scopeReduction }}</el-tag>
        <el-tag v-if="typeStats.otherModification > 0" type="primary" size="small">其他变更：{{ typeStats.otherModification }}</el-tag>
      </div>
      <div class="title-actions">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRow">+ 新增变更</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'lease-modification')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'lease-modification')">复核</el-button>
      </div>
    </div>

    <!-- 变更表格 -->
    <el-table :data="rows" border size="small" class="mod-table">
      <el-table-column prop="contractNo" label="合同号" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" @change="onCell(row.rowId, 'contractNo', row.contractNo)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="modificationDate" label="变更日期" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.modificationDate" size="small" placeholder="YYYY-MM-DD"
            @change="onCell(row.rowId, 'modificationDate', row.modificationDate)" />
          <span v-else>{{ row.modificationDate }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="modificationType" label="变更类型" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.modificationType" size="small" placeholder="选择"
            @change="onCell(row.rowId, 'modificationType', row.modificationType)">
            <el-option label="单独租赁" value="单独租赁" />
            <el-option label="范围减少" value="范围减少" />
            <el-option label="其他变更" value="其他变更" />
          </el-select>
          <el-tag v-else :type="getModTypeTag(row.modificationType)" size="small">{{ row.modificationType || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="originalTerms" label="原租赁条款" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.originalTerms" size="small" @change="onCell(row.rowId, 'originalTerms', row.originalTerms)" />
          <span v-else>{{ row.originalTerms }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="newTerms" label="新条款" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.newTerms" size="small" @change="onCell(row.rowId, 'newTerms', row.newTerms)" />
          <span v-else>{{ row.newTerms }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="originalROUAmount" label="原使用权资产" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.originalROUAmount" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'originalROUAmount', v)" />
          <span v-else>{{ fmtAmt(row.originalROUAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="adjustmentAmount" label="调整额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.adjustmentAmount" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'adjustmentAmount', v)" />
          <span v-else>{{ fmtAmt(row.adjustmentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="重新计量后" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：原值+调整额">{{ fmtAmt(row.remeasuredROUAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accountingTreatment" label="会计处理" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.accountingTreatment" size="small" @change="onCell(row.rowId, 'accountingTreatment', row.accountingTreatment)" />
          <span v-else>{{ row.accountingTreatment }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="结论" width="90" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" placeholder="—"
            @change="onCell(row.rowId, 'conclusion', row.conclusion)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleDelete(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部合计 -->
    <div class="stat-bar">
      <span>变更调整合计：{{ fmtAmt(totalAdjustment) }}元</span>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>单独租赁：变更增加租赁范围且对价与单独价格相符→作为新租赁单独核算</li>
        <li>范围减少：终止部分按比例冲减使用权资产与租赁负债，差额计入损益</li>
        <li>其他变更：以修订折现率重新计量租赁负债，对应调整使用权资产账面价值</li>
        <li>重新计量后 = 原使用权资产 + 调整额（calcRemeasurement）</li>
        <li>变更类型判断结论影响后续折旧基数与摊销安排</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabLeaseModification.vue — H8-7 租赁变更（表格型100行11列）
 * CAS21第28-30条变更类型判断+重新计量
 * Spec: Task 4.4 | Requirements: 4.3, 4.4
 */
import { toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8LeaseModification } from '../../composables/useH8LeaseModification'
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
}>()

const {
  rows, totalAdjustment, typeStats,
  addRow, deleteRow, updateCell,
} = useH8LeaseModification({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getModTypeTag(type: string): 'success' | 'warning' | 'primary' | 'info' {
  const map: Record<string, 'success' | 'warning' | 'primary'> = { '单独租赁': 'success', '范围减少': 'warning', '其他变更': 'primary' }
  return map[type] ?? 'info'
}

function onCell(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号', '新增租赁变更', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：ZL-2024-001',
  })
  if (value) addRow(value)
}

function handleDelete(rowId: string) { deleteRow(rowId) }
</script>

<style scoped>
.h8-tab-lease-modification { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }

.section-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.header-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-title-text { font-weight: 600; font-size: 14px; }
.title-actions { display: flex; gap: 6px; }

.mod-table { font-size: 13px; margin-bottom: 12px; }
.mod-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }

.stat-bar {
  display: flex; gap: 24px; padding: 10px 0; font-size: 12px;
  color: var(--el-text-color-secondary); border-top: 1px solid var(--el-border-color-lighter);
}
</style>
