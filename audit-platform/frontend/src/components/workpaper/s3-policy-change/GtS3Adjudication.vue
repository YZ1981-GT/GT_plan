<template>
  <div class="s3-adjudication">
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审定表</span>
          <div class="header-actions">
            <span class="data-source-hint">回写：</span>
            <GtIndexChip value="审定报表" />
            <GtIndexChip value="B22" />
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleReview">复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="tableData"
        border
        stripe
        style="width: 100%; font-size: 13px"
        :cell-class-name="cellClassName"
      >
        <el-table-column prop="item" label="项目" min-width="240" />
        <el-table-column prop="unadjusted" label="未审数" min-width="140" align="right">
          <template #default="{ row }">
            {{ fmt(row.unadjusted) }}
          </template>
        </el-table-column>
        <el-table-column prop="adjustment" label="调整数" min-width="140" align="right">
          <template #default="{ row }">
            {{ fmt(row.adjustment) }}
          </template>
        </el-table-column>
        <el-table-column prop="audited" label="审定数" min-width="140" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定数 = 未审数 + 调整数">
              {{ fmt(row.audited) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="priorYear" label="上年审定数" min-width="140" align="right">
          <template #default="{ row }">
            {{ fmt(row.priorYear) }}
          </template>
        </el-table-column>
        <el-table-column label="非经常性损益" min-width="120" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isNonRecurring" type="warning" size="small">非经常性</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写审定结论..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>审定表汇总会计政策变更、前期差错更正和会计估计变更相关科目的审定数，回写试算表。非经常性损益事项需标注。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS3Adjudication.vue — S3 审定表
 *
 * 功能：
 * - 展示会计政策变更/前期差错/估计变更相关科目审定数
 * - 审定数 = 未审数 + 调整数（公式单元格只读）
 * - 非经常性损益标注（Req 6.4）
 * - 回写 trial_balance
 */
import { ref, inject, defineAsyncComponent } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { eventBus } from '@/utils/eventBus'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog')

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

const conclusion = ref('')

const tableData = ref([
  { item: '累积影响数（资产负债表）', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0, isNonRecurring: false },
  { item: '累积影响数（利润表）', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0, isNonRecurring: true },
  { item: '前期差错更正对净利润的影响', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0, isNonRecurring: true },
  { item: '会计估计变更对本期的影响', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0, isNonRecurring: false },
])

function cellClassName({ column }: any): string {
  if (column?.property === 'audited') return 'formula-col'
  return ''
}

function handleSave() {
  eventBus.emit('WORKPAPER_SAVED', { wpId: props.wpId, wpCode: 'S3', sheetName: '审定表' })
}

function handleReview() {
  openReviewDialog?.('s3-adjudication', '审定表')
}
</script>

<style scoped>
.s3-adjudication {
  padding: 12px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.data-source-hint {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
:deep(.formula-col) {
  background-color: #fafafa;
}
.conclusion-card {
  margin-top: 16px;
}
.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-hints summary {
  cursor: pointer;
  user-select: none;
}
</style>
