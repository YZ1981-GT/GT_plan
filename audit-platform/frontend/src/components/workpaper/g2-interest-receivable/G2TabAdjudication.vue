<template>
  <div class="g2-adjudication">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表审定应收利息（科目1132）期初/期末余额，验证审定数与试算平衡表的勾稽一致性。</p>
        <p>2. 借方公式链：期初审定=期初未审+AJE+RJE；期末未审=期初审定+借方发生额-贷方发生额；期末审定=期末未审+AJE+RJE。</p>
        <p>3. 灰色底纹列为自动计算列（期初审定/期末未审/期末审定），不可手工编辑。</p>
        <p>4. 审定合计与试算平衡表（1132）差异应为0，否则红色标记须查明原因。</p>
        <p>5. 依据：CAS 22《金融工具确认和计量》（实际利率法、应收利息确认）、CAS 37《金融工具列报》。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证应收利息（科目1132）期末余额的存在、完整与准确，确认审定数与试算平衡表勾稽一致，为报表列报提供审定依据。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-1 应收利息审定表</span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-1" /></span>
        <el-tag size="small" type="info">共 {{ adj.dataRows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G2-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <el-table :data="adj.dataRows.value" border size="small" max-height="400">
      <el-table-column label="项目" prop="item" width="140" fixed>
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal' }">{{ row.item }}</span>
        </template>
      </el-table-column>

      <!-- 期初4列 -->
      <el-table-column label="期初未审" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.openingUnadjusted"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'openingUnadjusted', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.openingUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.openingAJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'openingAJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.openingAJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初RJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.openingRJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'openingRJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.openingRJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初审定" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal', 'formula-cell': row.id !== 'subtotal' }"
            :title="row.id !== 'subtotal' ? '期初审定 = 期初未审 + AJE + RJE' : ''">
            {{ fmtNum(row.openingAdjusted) }}
          </span>
        </template>
      </el-table-column>

      <!-- 期末4列 -->
      <el-table-column label="期末未审" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal', 'formula-cell': row.id !== 'subtotal' }"
            :title="row.id !== 'subtotal' ? '期末未审 = 期初审定 + 借方 - 贷方' : ''">
            {{ fmtNum(row.closingUnadjusted) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="期末AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.closingAJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'closingAJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.closingAJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末RJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.id !== 'subtotal'"
            :model-value="row.closingRJE"
            size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'closingRJE', v ?? 0)"
          />
          <span v-else class="row-bold">{{ fmtNum(row.closingRJE) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末审定" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="{ 'row-bold': row.id === 'subtotal', 'formula-cell': row.id !== 'subtotal' }"
            :title="row.id !== 'subtotal' ? '期末审定 = 期末未审 + AJE + RJE' : ''">
            {{ fmtNum(row.closingAdjusted) }}
          </span>
        </template>
      </el-table-column>

      <!-- 索引 -->
      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <el-input
            v-if="row.id !== 'subtotal'"
            :model-value="row.indexRef"
            size="small" :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.id, 'indexRef', v)"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        期初审定 {{ fmtNum(adj.subtotalRow.value.openingAdjusted) }} ·
        期末审定 {{ fmtNum(adj.subtotalRow.value.closingAdjusted) }}
      </div>
    </div>

    <!-- 试算表数 + 差异 -->
    <div class="tb-diff-row">
      <span class="tb-label">试算平衡表数（1132）：</span>
      <el-input-number
        :model-value="adj.trialBalanceAmount.value"
        size="small" :controls="false" :disabled="isReadonly"
        style="width:140px"
        @update:model-value="(v: number) => adj.setTrialBalance(v ?? 0)"
      />
      <span :class="['diff-value', { 'diff-red': adj.hasVarianceHighlight.value }]">
        差异：{{ fmtNum(adj.variance.value) }}
        <template v-if="!adj.hasVarianceHighlight.value"> ✓</template>
        <template v-else> ✗</template>
      </span>
    </div>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="adj.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对应收利息审定表的复核结论..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { useG2Adjudication } from '../composables/useG2Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const adj = useG2Adjudication({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g2-adjudication { padding: 12px; font-size: 13px; }
.g2-adjudication :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.g2-adjudication :deep(.el-table .cell) { font-size: 13px !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.row-bold { font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.tb-diff-row { display: flex; gap: 16px; margin: 16px 0; align-items: center; font-size: 13px; }
.tb-label { font-weight: 500; }
.diff-value { font-weight: 600; }
.diff-red { color: #f56c6c; }
.conclusion-card { margin-top: 12px; }
</style>
