<script setup lang="ts">
/**
 * E1TabBankDetail.vue — E1-3 银行存款及其他货币资金明细表 (双variant)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.3
 *
 * 渲染：
 * - 顶部 el-segmented variant切换("仅人民币" / "人民币及外币")
 * - 三分组(存款本金/存放财务公司/其他货币资金) + group header + subtotal
 * - 每组内动态行增删
 * - 函证差异橙色高亮(hasConfirmDiff)
 * - GtIndexChip跳E0 询证函索引号
 * - el-skeleton加载占位
 *
 * Requirements: 2.1-2.6, 4.1-4.7
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import {
  useE1BankDetail,
  type BankDetailRow,
  type BankDetailVariant,
  type BankDetailGroup,
} from '../composables/useE1BankDetail'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'

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

// ─── Variant ─────────────────────────────────────────────────────────────────

const variant = ref<BankDetailVariant>('rmb')
const variantOptions = [
  { label: '仅人民币', value: 'rmb' },
  { label: '人民币及外币', value: 'multi' },
]

// Detect initial variant from sheetName
if (props.sheetName?.includes('人民币及外币')) {
  variant.value = 'multi'
}

// ─── Composable ──────────────────────────────────────────────────────────────

const options = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant,
}

const {
  groupedRows,
  groupTotals,
  isLoading,
  addRow,
  removeRow,
  updateCell,
  hasConfirmDiff,
  GROUP_NAMES,
} = useE1BankDetail(options)

// ─── Groups ──────────────────────────────────────────────────────────────────

const groups: BankDetailGroup[] = ['principal', 'finance', 'other']

function getRowClass({ row }: { row: BankDetailRow }): string {
  if (hasConfirmDiff(row)) return 'e1-bank-confirm-diff'
  return ''
}
</script>

<template>
  <div class="e1-tab-bank-detail">
    <!-- Variant Segmented -->
    <div class="variant-switch">
      <el-segmented v-model="variant" :options="variantOptions" size="small" />
    </div>

    <el-skeleton :loading="isLoading" :rows="10" animated>
      <template #default>
        <div v-for="group in groups" :key="group" class="group-section">
          <!-- Group Header -->
          <div class="group-header">
            <span class="group-title">{{ GROUP_NAMES[group] }}</span>
            <el-button
              v-if="!isReadonly"
              type="primary"
              size="small"
              @click="addRow(group)"
            >
              + 新增行
            </el-button>
          </div>

          <!-- Group Table -->
          <el-table
            :data="groupedRows[group]"
            border
            size="small"
            :row-class-name="getRowClass"
            style="width: 100%"
          >
            <!-- 开户银行 -->
            <el-table-column label="开户银行" width="140">
              <template #default="{ row }">
                <el-input
                  :model-value="row.bankName"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'bankName', val)"
                />
              </template>
            </el-table-column>

            <!-- 银行账号 -->
            <el-table-column label="银行账号" width="160">
              <template #default="{ row }">
                <el-input
                  :model-value="row.accountNo"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'accountNo', val)"
                />
              </template>
            </el-table-column>

            <!-- 账户性质 -->
            <el-table-column label="账户性质" width="120">
              <template #default="{ row }">
                <el-input
                  :model-value="row.accountType"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'accountType', val)"
                />
              </template>
            </el-table-column>

            <!-- 外币列 (multi variant only) -->
            <template v-if="variant === 'multi'">
              <el-table-column label="币种" width="80">
                <template #default="{ row }">
                  <el-input
                    :model-value="row.fxCurrency"
                    :disabled="isReadonly"
                    size="small"
                    @change="(val: string) => updateCell(row.id, 'fxCurrency', val)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="汇率" width="80" align="right">
                <template #default="{ row }">
                  <el-input-number
                    :model-value="row.fxRate"
                    :disabled="isReadonly"
                    :controls="false"
                    :precision="4"
                    size="small"
                    @change="(val: number | undefined) => updateCell(row.id, 'fxRate', val ?? 1)"
                  />
                </template>
              </el-table-column>
            </template>

            <!-- 期初余额 -->
            <el-table-column label="期初余额" width="120" align="right">
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
            <el-table-column label="本期增加" width="120" align="right">
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
            <el-table-column label="本期减少" width="120" align="right">
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

            <!-- 期末余额 (readonly) -->
            <el-table-column label="期末余额" width="120" align="right">
              <template #default="{ row }">
                <span class="readonly-val">{{ displayPrefs.fmtAmount(row.ending) }}</span>
              </template>
            </el-table-column>

            <!-- 账项调整 -->
            <el-table-column label="账项调整" width="120" align="right">
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

            <!-- 审定数 (readonly) -->
            <el-table-column label="审定数" width="120" align="right">
              <template #default="{ row }">
                <span class="readonly-val">{{ displayPrefs.fmtAmount(row.audited) }}</span>
              </template>
            </el-table-column>

            <!-- 回函确认金额 -->
            <el-table-column label="回函确认金额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="row.confirmAmount"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number | undefined) => updateCell(row.id, 'confirmAmount', val ?? 0)"
                />
              </template>
            </el-table-column>

            <!-- 函证差异 (readonly) -->
            <el-table-column label="函证差异" width="110" align="right">
              <template #default="{ row }">
                <span :class="{ 'orange-text': hasConfirmDiff(row) }">
                  {{ displayPrefs.fmtAmount(row.confirmDiff) }}
                </span>
              </template>
            </el-table-column>

            <!-- 询证函索引号 -->
            <el-table-column label="询证函索引号" width="130">
              <template #default="{ row }">
                <GtIndexChip
                  v-if="row.confirmIndexNo"
                  :index-no="row.confirmIndexNo"
                  target-wp-code="E0"
                />
                <el-input
                  v-else
                  :model-value="row.confirmIndexNo"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="索引号"
                  @change="(val: string) => updateCell(row.id, 'confirmIndexNo', val)"
                />
              </template>
            </el-table-column>

            <!-- 备注 -->
            <el-table-column label="备注" min-width="120">
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
                <el-button type="danger" text size="small" @click="removeRow(row.id)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- Group Subtotal -->
          <div class="group-subtotal">
            <span>小计：</span>
            <span>期初 {{ displayPrefs.fmtAmount(groupTotals[group].opening) }}</span>
            <span>期末 {{ displayPrefs.fmtAmount(groupTotals[group].ending) }}</span>
            <span>审定 {{ displayPrefs.fmtAmount(groupTotals[group].audited) }}</span>
          </div>
        </div>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-bank-detail {
  padding: 12px 0;
}
.variant-switch {
  margin-bottom: 16px;
}
.group-section {
  margin-bottom: 20px;
}
.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #ecf5ff;
  border-radius: 4px;
  margin-bottom: 8px;
}
.group-title {
  font-weight: 700;
  color: #303133;
}
.group-subtotal {
  display: flex;
  gap: 16px;
  padding: 8px 12px;
  margin-top: 4px;
  background: #f5f7fa;
  border-radius: 4px;
  font-weight: 600;
  font-size: 13px;
  color: #606266;
}
.readonly-val {
  color: #909399;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 2px;
}
.orange-text {
  color: #e6a23c;
  font-weight: 600;
}

:deep(.e1-bank-confirm-diff) {
  background-color: #fdf6ec !important;
}
</style>
