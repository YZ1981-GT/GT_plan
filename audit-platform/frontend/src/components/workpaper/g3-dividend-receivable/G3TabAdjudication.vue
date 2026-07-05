<!--
  G3TabAdjudication.vue — G3-1 审定表（22列，按被投资方分行）

  借方科目 1131 应收股利：
    期初审定 = 期初未审 + AJE + RJE
    期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)
    期末审定 = 期末未审 + AJE + RJE

  行结构：被投资方逐行(动态增删) + 合计(加粗) + 试算表数 + 差异(红色)

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.1
  Requirements: 3.1~3.10
-->
<template>
  <div class="g3-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G3-1 应收股利审定表</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="adj.addRow()">＋ 新增被投资方</el-button>
        <el-button size="small" @click="openReviewDialog('G3-1-adjudication')">💬复核</el-button>
      </div>
    </div>

    <el-table
      :data="tableData"
      border
      size="small"
      max-height="480"
      :row-class-name="rowClassName"
    >
      <!-- 被投资方名称 -->
      <el-table-column label="被投资方名称" width="160" fixed>
        <template #default="{ row }">
          <span v-if="row._type !== 'data'" :class="rowLabelClass(row)">{{ row.investeeName }}</span>
          <el-input
            v-else
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.id, 'investeeName', v)"
          />
        </template>
      </el-table-column>

      <!-- 持股比例 -->
      <el-table-column label="持股比例(%)" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row._type === 'data'"
            :model-value="row.shareholdingRatio"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            :precision="2"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'shareholdingRatio', v ?? 0)"
          />
          <span v-else :class="rowLabelClass(row)">{{ row._type === 'subtotal' ? '' : '' }}</span>
        </template>
      </el-table-column>

      <!-- 期初4列 group -->
      <el-table-column label="期初">
        <el-table-column label="未审" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.openingUnadjusted"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'openingUnadjusted', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.openingUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.openingAJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'openingAJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.openingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.openingRJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'openingRJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.openingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span
              :class="[rowLabelClass(row), { 'formula-cell': row._type === 'data' }]"
              :title="row._type === 'data' ? '期初审定 = 期初未审 + AJE + RJE' : ''"
            >
              {{ fmtNum(row.openingAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 本期宣告(借方) -->
      <el-table-column label="本期宣告(借方)" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row._type === 'data'"
            :model-value="row.currentDeclared"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'currentDeclared', v ?? 0)"
          />
          <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.currentDeclared) }}</span>
        </template>
      </el-table-column>

      <!-- 本期收回(贷方) -->
      <el-table-column label="本期收回(贷方)" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row._type === 'data'"
            :model-value="row.currentReceived"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => adj.updateCell(row.id, 'currentReceived', v ?? 0)"
          />
          <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.currentReceived) }}</span>
        </template>
      </el-table-column>

      <!-- 期末4列 group -->
      <el-table-column label="期末">
        <el-table-column label="未审" width="120" align="right">
          <template #default="{ row }">
            <span
              :class="[rowLabelClass(row), { 'formula-cell': row._type === 'data' }]"
              :title="row._type === 'data' ? '期末未审 = 期初审定 + 本期宣告 - 本期收回' : ''"
            >
              {{ fmtNum(row.closingUnadjusted) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.closingAJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'closingAJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.closingAJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row._type === 'data'"
              :model-value="row.closingRJE"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => adj.updateCell(row.id, 'closingRJE', v ?? 0)"
            />
            <span v-else :class="rowLabelClass(row)">{{ fmtNum(row.closingRJE) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="120" align="right">
          <template #default="{ row }">
            <span
              :class="[rowLabelClass(row), { 'formula-cell': row._type === 'data' }]"
              :title="row._type === 'data' ? '期末审定 = 期末未审 + AJE + RJE' : ''"
            >
              {{ fmtNum(row.closingAdjusted) }}
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" width="140">
        <template #default="{ row }">
          <el-input
            v-if="row._type === 'data'"
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => adj.updateCell(row.id, 'remark', v)"
          />
        </template>
      </el-table-column>

      <!-- 索引 -->
      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <GtIndexChip
            v-if="row._type === 'data' && row.indexRef"
            :value="row.indexRef"
          />
          <el-input
            v-else-if="row._type === 'data'"
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            placeholder="索引"
            @change="(v: string) => adj.updateCell(row.id, 'indexRef', v)"
          />
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column label="" width="50" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-icon
            v-if="row._type === 'data'"
            class="delete-icon"
            @click="adj.removeRow(row.id)"
          >
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 试算表数 + 差异 -->
    <div class="tb-diff-row">
      <span class="tb-label">试算平衡表数（1131）：</span>
      <el-input-number
        :model-value="adj.trialBalanceAmount.value"
        size="small"
        :controls="false"
        :disabled="isReadonly"
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
      <el-input
        v-model="adj.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="对应收股利审定表的复核结论..."
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { useG3Adjudication } from '../composables/useG3Adjudication'
import type { G3AdjudicationRow } from '../composables/useG3Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const adj = useG3Adjudication({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── Table data: data rows + subtotal + trial balance + variance ───
interface DisplayRow extends G3AdjudicationRow {
  _type: 'data' | 'subtotal' | 'tb' | 'variance'
}

const tableData = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = adj.dataRows.value.map((r) => ({ ...r, _type: 'data' as const }))

  // 合计行
  rows.push({
    ...adj.subtotalRow.value,
    _type: 'subtotal',
  })

  // 试算表数行
  rows.push({
    id: 'tb',
    investeeName: '试算表数(1131)',
    shareholdingRatio: 0,
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    openingAdjusted: 0,
    closingUnadjusted: 0,
    closingAJE: 0,
    closingRJE: 0,
    closingAdjusted: adj.trialBalanceAmount.value,
    currentDeclared: 0,
    currentReceived: 0,
    remark: '',
    indexRef: '',
    _type: 'tb',
  })

  // 差异行
  rows.push({
    id: 'variance',
    investeeName: '差异',
    shareholdingRatio: 0,
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    openingAdjusted: 0,
    closingUnadjusted: 0,
    closingAJE: 0,
    closingRJE: 0,
    closingAdjusted: adj.variance.value,
    currentDeclared: 0,
    currentReceived: 0,
    remark: '',
    indexRef: '',
    _type: 'variance',
  })

  return rows
})

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._type === 'subtotal') return 'row-subtotal'
  if (row._type === 'variance' && adj.hasVarianceHighlight.value) return 'row-variance-red'
  if (row._type === 'tb') return 'row-tb'
  return ''
}

function rowLabelClass(row: DisplayRow): string {
  if (row._type === 'subtotal') return 'row-bold'
  if (row._type === 'variance' && adj.hasVarianceHighlight.value) return 'row-bold diff-red'
  if (row._type === 'tb') return 'row-tb-label'
  return ''
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v ?? '')
}
</script>

<style scoped>
.g3-adjudication {
  padding: 12px;
  font-size: 13px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
}

.head-actions {
  display: flex;
  gap: 8px;
}

/* 公式列样式：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.row-bold {
  font-weight: 600;
}

.row-tb-label {
  color: #606266;
  font-style: italic;
}

/* 试算表数 + 差异行 */
.tb-diff-row {
  display: flex;
  gap: 16px;
  margin: 16px 0;
  align-items: center;
  font-size: 13px;
}

.tb-label {
  font-weight: 500;
}

.diff-value {
  font-weight: 600;
}

.diff-red {
  color: #f56c6c;
}

/* 行样式 */
:deep(.row-subtotal) {
  font-weight: 600;
  background-color: #f5f7fa;
}

:deep(.row-variance-red) {
  color: #f56c6c;
  font-weight: 600;
}

:deep(.row-tb) {
  color: #606266;
  font-style: italic;
  background-color: #fafafa;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}

.delete-icon:hover {
  color: #f56c6c;
}

/* 结论卡片 */
.conclusion-card {
  margin-top: 12px;
}
</style>
