<template>
  <div class="k5-tab-decommission">
    <!-- ═══ Section标题 ═══ -->
    <div class="section-header">
      <h3>K5-5 弃置费用检查表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI结论
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>弃置费用（弃置义务）现值折现：<strong>现值 = 预计弃置支出 / (1+折现率)^年数</strong>。期末 = 期初 + 本期增加 + 利息调整（期初×折现率）。K5-5期末合计应与K5-1弃置义务行审定数一致。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-5 期末合计: <strong>{{ fmtNum(crossCheck.decommissionTotal) }}</strong></span>
      <span>K5-1 弃置义务审定: <strong>{{ fmtNum(crossCheck.adjudicationDecommission) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══ 主表 ═══ -->
    <el-table :data="decommissionRows" border size="small" style="width: 100%" max-height="480">
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="资产名称" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.assetName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'assetName', row.assetName)" />
        </template>
      </el-table-column>
      <el-table-column label="预计弃置支出" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.futureExpense" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => save(row.rowId, 'futureExpense', v)" />
        </template>
      </el-table-column>
      <el-table-column label="年数" width="70" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.expectedYears" :disabled="isReadonly" size="small" :controls="false" :precision="0" :min="0" style="width:55px" @change="(v:number) => save(row.rowId, 'expectedYears', v)" />
        </template>
      </el-table-column>
      <el-table-column label="折现率" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.discountRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:75px" @change="(v:number) => save(row.rowId, 'discountRate', v)" />
          <el-icon v-if="row.discountRate <= 0 && row.futureExpense > 0" color="#f56c6c" style="margin-left:2px"><WarningFilled /></el-icon>
        </template>
      </el-table-column>
      <el-table-column label="现值" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="future / (1+rate)^years" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.presentValue) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期初" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'beginBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="增加" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.periodIncrease" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'periodIncrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="利息调整" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 × 折现率" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.interestAdjustment) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 + 增加 + 利息调整" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.conclusion" :disabled="isReadonly" size="small" placeholder="结论" @blur="save(row.rowId, 'conclusion', row.conclusion)" />
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行 ═══ -->
    <div class="summary-bar">
      <span>合计行数: {{ subtotals.count }}</span>
      <span>现值合计: {{ fmtNum(subtotals.presentValue) }}</span>
      <span>期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>现值 = 预计弃置支出 / (1+折现率)^年数</li>
        <li>利息调整 = 期初余额 × 折现率（时间价值累积增加负债）</li>
        <li>折现率为0或负时：现值=未来支出（兜底），利息调整=0</li>
        <li>适用资产：矿井、核电站、油气设施等有法定弃置义务的长期资产</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabDecommissionCheck.vue — K5-5 弃置费用检查表
 * 现值折现+利息调整+回连审定+错误状态
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.4
 * Requirements: 7.1-7.4
 */
import { toRef } from 'vue'
import { Plus, Delete, MagicStick, WarningFilled } from '@element-plus/icons-vue'
import { useK5Decommission } from '../../composables/useK5Decommission'
import type { Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  decommissionRows,
  subtotals,
  crossCheck,
  updateCell,
  addRow,
  removeRow,
} = useK5Decommission({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

function save(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }
function handleAddRow() { addRow() }
function handleAiGenerate() { emit('save', 'K5-5-ai-trigger', { remark: 'decommission-conclusion' }) }

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-decommission { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.cross-check-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
