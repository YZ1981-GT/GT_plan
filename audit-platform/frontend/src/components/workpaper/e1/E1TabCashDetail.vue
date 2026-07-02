<script setup lang="ts">
/**
 * E1TabCashDetail.vue — E1-2 现金明细表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.2
 *
 * 渲染：
 * - el-table 动态行：币种 | 期初余额 | 本期增加 | 本期减少 | 期末原币 | 汇率 |
 *   折算人民币 | 审计调整 | 审定人民币 | 备注
 * - 底部合计行(sticky bold)
 * - 动态行增删按钮
 * - 只读列灰色背景
 * - el-skeleton加载占位
 *
 * Requirements: 3.1-3.6
 */
import { inject, toRef, onMounted, type Ref } from 'vue'
import {
  useE1CashDetail,
  type CashDetailRow,
} from '../composables/useE1CashDetail'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  totalRow,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CashDetail(options)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  // hydration done inside composable
})
</script>

<template>
  <div class="e1-tab-cash-detail">
    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- Toolbar -->
        <div class="toolbar" v-if="!isReadonly">
          <el-button type="primary" size="small" @click="addRow">
            + 新增行
          </el-button>
        </div>

        <el-table
          :data="rows"
          border
          stripe
          size="small"
          style="width: 100%"
          max-height="600"
        >
          <!-- 币种 -->
          <el-table-column label="币种" width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.currency"
                :disabled="isReadonly || row.id === 'fixed-rmb'"
                size="small"
                @change="(val: string) => updateCell(row.id, 'currency', val)"
              />
            </template>
          </el-table-column>

          <!-- 期初余额 -->
          <el-table-column label="期初余额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.opening"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'opening', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 本期增加 -->
          <el-table-column label="本期增加" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.increase"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'increase', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 本期减少 -->
          <el-table-column label="本期减少" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decrease"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'decrease', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 期末原币 (readonly) -->
          <el-table-column label="期末原币" width="130" align="right">
            <template #default="{ row }">
              <span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingFc) }}</span>
            </template>
          </el-table-column>

          <!-- 汇率 -->
          <el-table-column label="汇率" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.fxRate"
                :disabled="isReadonly || row.id === 'fixed-rmb'"
                :controls="false"
                :precision="4"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'fxRate', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 折算人民币 (readonly) -->
          <el-table-column label="折算人民币" width="140" align="right">
            <template #default="{ row }">
              <span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingRmb) }}</span>
            </template>
          </el-table-column>

          <!-- 审计调整 -->
          <el-table-column label="审计调整" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.adjustment"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'adjustment', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 审定人民币 (readonly) -->
          <el-table-column label="审定人民币" width="140" align="right">
            <template #default="{ row }">
              <span class="readonly-val">{{ displayPrefs.fmtAmount(row.auditedRmb) }}</span>
            </template>
          </el-table-column>

          <!-- 备注 -->
          <el-table-column label="备注" min-width="150">
            <template #default="{ row }">
              <el-input
                :model-value="row.note"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'note', val)"
              />
            </template>
          </el-table-column>

          <!-- 操作 -->
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.id !== 'fixed-rmb'"
                type="danger"
                text
                size="small"
                @click="removeRow(row.id)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 合计行 -->
        <div class="total-row">
          <span class="total-label">合计</span>
          <span class="total-val">期初: {{ displayPrefs.fmtAmount(totalRow.opening) }}</span>
          <span class="total-val">增加: {{ displayPrefs.fmtAmount(totalRow.increase) }}</span>
          <span class="total-val">减少: {{ displayPrefs.fmtAmount(totalRow.decrease) }}</span>
          <span class="total-val">期末原币: {{ displayPrefs.fmtAmount(totalRow.endingFc) }}</span>
          <span class="total-val">折算人民币: {{ displayPrefs.fmtAmount(totalRow.endingRmb) }}</span>
          <span class="total-val">审定人民币: {{ displayPrefs.fmtAmount(totalRow.auditedRmb) }}</span>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-cash-detail {
  padding: 12px 0;
}
.toolbar {
  margin-bottom: 12px;
}
.readonly-val {
  color: #909399;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
  display: inline-block;
  width: 100%;
  text-align: right;
}
.total-row {
  display: flex;
  gap: 16px;
  padding: 10px 12px;
  margin-top: 8px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-weight: 700;
  font-size: 13px;
  flex-wrap: wrap;
}
.total-label {
  color: #303133;
  min-width: 40px;
}
.total-val {
  color: #606266;
}
</style>
