<template>
  <div class="k5-tab-warranty">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>符合确认条件的产品质量保证（保修）义务均已计提预计负债；</li>
        <li><b>计价和分摊：</b>保修费用计提基于历史保修率/销售规模的最佳估计，计量合理；</li>
        <li><b>列报与披露：</b>产品质量保证准备按 CAS13 恰当列报披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K5-4 产品质量保修检查表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI结论
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>产品质量保修准备计提：<strong>应计提金额 = 计提基数（销售收入）× 历史保修率</strong>。历史保修率基于近3年"实际发生额/销售收入"加权平均。期末余额（负债类）= 期初 + 本期计提 − 本期使用。K5-4期末合计应与K5-1产品质保行审定数一致。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-4 期末合计: <strong>{{ fmtNum(crossCheck.warrantyTotal) }}</strong></span>
      <span>K5-1 产品质保审定: <strong>{{ fmtNum(crossCheck.adjudicationWarranty) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══（一）产品质量保修政策 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header><span class="card-title">（一）产品质量保修政策</span></template>
      <el-input
        v-model="policyText"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="描述被审计单位产品质量保修政策：保修范围、保修期限、计提方法、计提基础等"
        @change="(v: string) => updatePolicy(v)"
      />
    </el-card>

    <!-- ═══（二）历史质量保修情况（评估计提比例是否合理）═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（二）检查历史质量保修情况，评估计提比例是否合理</span>
          <el-button v-if="!isReadonly" size="small" @click="addHistoryRow()">＋ 新增产品</el-button>
        </div>
      </template>
      <el-table :data="historyRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="产品类别" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.productName" :disabled="isReadonly" size="small" @change="(v: string) => updateHistoryCell(row.rowId, 'productName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="本期实际发生" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.currentActual" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'currentActual', v)" /></template>
        </el-table-column>
        <el-table-column label="本期收入" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.currentRevenue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'currentRevenue', v)" /></template>
        </el-table-column>
        <el-table-column label="前1年实际发生" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year1Actual" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year1Actual', v)" /></template>
        </el-table-column>
        <el-table-column label="前1年收入" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year1Revenue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year1Revenue', v)" /></template>
        </el-table-column>
        <el-table-column label="前2年实际发生" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year2Actual" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year2Actual', v)" /></template>
        </el-table-column>
        <el-table-column label="前2年收入" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year2Revenue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year2Revenue', v)" /></template>
        </el-table-column>
        <el-table-column label="3年平均保修率" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="∑实际发生 / ∑收入" placement="top">
              <span class="formula-cell formula-underline">{{ (row.avgRate * 100).toFixed(3) }}%</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeHistoryRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计平均保修率：{{ (historySubtotals.avgRate * 100).toFixed(3) }}%</div>
        </template>
      </el-table>
    </el-card>

    <!-- ═══（三）重新测算产品质量保证金 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（三）重新测算产品质量保证金</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAddRow"><el-icon><Plus /></el-icon> 新增行</el-button>
        </div>
      </template>
      <el-table :data="warrantyRows" border size="small" style="width: 100%" max-height="420">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="产品类别" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.productName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'productName', row.productName)" />
          </template>
        </el-table-column>
        <el-table-column label="计提基数(收入)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.revenue" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => save(row.rowId, 'revenue', v)" />
          </template>
        </el-table-column>
        <el-table-column label="计提比例" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.warrantyRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:80px" @change="(v:number) => save(row.rowId, 'warrantyRate', v)" />
          </template>
        </el-table-column>
        <el-table-column label="应计提金额" width="115" align="right">
          <template #default="{ row }">
            <el-tooltip content="计提基数 × 计提比例" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.estimatedExpense) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账面已计提" width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.bookProvision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => save(row.rowId, 'bookProvision', v)" />
          </template>
        </el-table-column>
        <el-table-column label="差异金额" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="应计提 − 账面已计提" placement="top">
              <span class="formula-cell formula-underline" :class="{ 'diff-warn': Math.abs(row.variance) > 0.01 }">{{ fmtNum(row.variance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="130">
          <template #default="{ row }">
            <el-input v-model="row.varianceReason" :disabled="isReadonly" size="small" placeholder="差异原因" @blur="save(row.rowId, 'varianceReason', row.varianceReason)" />
          </template>
        </el-table-column>
        <el-table-column label="期初" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => save(row.rowId, 'beginBalance', v)" />
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.periodProvision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => save(row.rowId, 'periodProvision', v)" />
          </template>
        </el-table-column>
        <el-table-column label="本期使用" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.periodUsed" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => save(row.rowId, 'periodUsed', v)" />
          </template>
        </el-table-column>
        <el-table-column label="期末" width="105" align="right">
          <template #default="{ row }">
            <el-tooltip content="期初 + 计提 − 使用" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="removeRow($index)"><el-icon><Delete /></el-icon></el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>合计行数: {{ subtotals.count }}</span>
        <span>应计提合计: {{ fmtNum(subtotals.estimatedExpense) }}</span>
        <span>期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
      </div>
    </el-card>

    <!-- ═══（四）预计保修发生时间 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（四）预计保修发生时间（流动/非流动划分）</span>
          <el-button v-if="!isReadonly" size="small" @click="addTimingRow()">＋ 新增产品</el-button>
        </div>
      </template>
      <el-table :data="timingRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="产品" min-width="140">
          <template #default="{ row }"><el-input v-model="row.productName" :disabled="isReadonly" size="small" @change="(v: string) => updateTimingCell(row.rowId, 'productName', v)" /></template>
        </el-table-column>
        <el-table-column label="期末数" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.endBalance" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateTimingCell(row.rowId, 'endBalance', v)" /></template>
        </el-table-column>
        <el-table-column label="1年以内" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.within1Year" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateTimingCell(row.rowId, 'within1Year', v)" /></template>
        </el-table-column>
        <el-table-column label="1年以上" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.over1Year" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateTimingCell(row.rowId, 'over1Year', v)" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeTimingRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　期末：{{ fmtNum(timingSubtotals.endBalance) }}　1年内：{{ fmtNum(timingSubtotals.within1Year) }}　1年上：{{ fmtNum(timingSubtotals.over1Year) }}</div>
        </template>
      </el-table>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>历史保修率 = 近3年实际保修支出合计 / 近3年销售收入合计（加权平均）</li>
        <li>应计提金额 = 计提基数（本期销售收入）× 历史保修率</li>
        <li>差异金额 = 应计提 − 账面已计提；差异较大应说明原因或提出调整</li>
        <li>负债类期末 = 期初 + 本期计提 − 本期使用（转销）</li>
        <li>预计发生时间用于流动/非流动划分：1年以内→流动，1年以上→非流动</li>
        <li>K5-4 期末合计应与 K5-1 审定表"产品质量保证"行审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabWarrantyCheck.vue — K5-4 产品质量保修检查表
 * 源模板4区段：政策 / 3年历史保修率对照 / 重新测算差异表 / 预计保修发生时间
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.4（源模板对齐增强）
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
  policyText,
  updatePolicy,
  historyRows,
  historySubtotals,
  updateHistoryCell,
  addHistoryRow,
  removeHistoryRow,
  timingRows,
  timingSubtotals,
  updateTimingCell,
  addTimingRow,
  removeTimingRow,
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
.k5-section-card { margin-bottom: 12px; }
.k5-section-card :deep(.el-card__header) { padding: 8px 14px; }
.k5-section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.hnum { width: 100%; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: #606266; font-weight: 600; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
