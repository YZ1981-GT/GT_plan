<template>
  <div class="s15-adjudication">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        汇总每股收益与净资产收益率相关科目（归母净利润、扣非净利润、净资产等）的审定数，核对未审数、调整数与审定数的勾稽关系，并回写试算表。
      </div>
    </el-alert>

    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审定表 S15-1</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              @click="handleSave"
            >保存</el-button>
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
        <el-table-column prop="item" label="项目" min-width="200" />
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
            <span class="formula-cell" :title="`审定数 = 未审数 + 调整数`">
              {{ fmt(row.audited) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="priorYear" label="上年审定数" min-width="140" align="right">
          <template #default="{ row }">
            {{ fmt(row.priorYear) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>审定表 S15-1 汇总每股收益与净资产收益率相关科目的审定数，将回写试算表。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS15Adjudication.vue — 审定表 S15-1
 *
 * 功能：
 * - 展示 EPS/ROE 相关科目审定表（归母净利润、扣非净利润、净资产等）
 * - 审定数 = 未审数 + 调整数（公式单元格只读）
 * - 回写 trial_balance
 */
import { ref, computed } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { useSExpertPersist } from '../composables/useSExpertPersist'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// 金额格式化
function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

// 示例数据（实际从 render-config 加载）
const tableData = ref([
  { item: '归属于母公司股东的净利润', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0 },
  { item: '扣除非经常性损益后归属于母公司股东的净利润', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0 },
  { item: '期末净资产', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0 },
  { item: '归属于母公司普通股股东的期末净资产', unadjusted: 0, adjustment: 0, audited: 0, priorYear: 0 },
])

// 公式列标记
function cellClassName({ column }: any): string {
  if (column?.property === 'audited') return 'formula-col'
  return ''
}

// ─── 持久化接线（load + save） ────────────────────────────────────────────────

const ROWS_ID = 'S15-adjudication-rows'
const { seedOnMount, save } = useSExpertPersist(() => props.allResponses)
seedOnMount([{ itemId: ROWS_ID, ref: tableData }])

function handleSave() {
  // 持久化审定表数据（EventBus WORKPAPER_SAVED 由主入口/回写链处理）
  save(ROWS_ID, tableData.value)
}
</script>

<style scoped>
.s15-adjudication {
  padding: 12px;
}
.audit-objective {
  margin-bottom: 12px;
}
.audit-objective-text {
  font-size: 13px;
  line-height: 1.6;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
:deep(.formula-col) {
  background-color: #fafafa;
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
