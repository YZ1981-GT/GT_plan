<template>
  <div class="k5-tab-warranty">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K5-4 产品质量保修检查表</h3>
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
      <p>产品质量保修准备计提：<strong>预计保修支出 = 销售收入 × 历史保修率</strong>。期末余额（负债类）= 期初 + 本期计提 − 本期使用。K5-4期末合计应与K5-1产品质保行审定数一致。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-4 期末合计: <strong>{{ fmtNum(crossCheck.warrantyTotal) }}</strong></span>
      <span>K5-1 产品质保审定: <strong>{{ fmtNum(crossCheck.adjudicationWarranty) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══ 主表 ═══ -->
    <el-table :data="warrantyRows" border size="small" style="width: 100%" max-height="480">
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="产品名称" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.productName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'productName', row.productName)" />
        </template>
      </el-table-column>
      <el-table-column label="销售收入" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.revenue" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => save(row.rowId, 'revenue', v)" />
        </template>
      </el-table-column>
      <el-table-column label="保修率" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.warrantyRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:75px" @change="(v:number) => save(row.rowId, 'warrantyRate', v)" />
        </template>
      </el-table-column>
      <el-table-column label="预计保修支出" width="120" align="right">
        <template #default="{ row }">
          <el-tooltip content="收入 × 保修率" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.estimatedExpense) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期初" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'beginBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="本期计提" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.periodProvision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'periodProvision', v)" />
        </template>
      </el-table-column>
      <el-table-column label="本期使用" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.periodUsed" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'periodUsed', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 + 计提 − 使用" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="130">
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
      <span>收入合计: {{ fmtNum(subtotals.revenue) }}</span>
      <span>期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>预计保修支出 = 相关产品本期销售收入 × 历史保修率</li>
        <li>负债类期末 = 期初 + 本期计提 − 本期使用（转销）</li>
        <li>K5-4 期末合计应与 K5-1 审定表"产品质量保证"行审定数一致</li>
        <li>历史保修率应基于最近3年保修支出/销售收入的加权平均</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabWarrantyCheck.vue — K5-4 产品质量保修检查表
 * 质保测算+回连审定+AI辅助
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.4
 * Requirements: 6.1-6.4
 */
import { toRef } from 'vue'
import { Plus, Delete, MagicStick } from '@element-plus/icons-vue'
import { useK5Warranty } from '../../composables/useK5Warranty'
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
  warrantyRows,
  subtotals,
  crossCheck,
  updateCell,
  addRow,
  removeRow,
} = useK5Warranty({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

function save(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }
function handleAddRow() { addRow() }
function handleAiGenerate() { emit('save', 'K5-4-ai-trigger', { remark: 'warranty-conclusion' }) }

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-warranty { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
