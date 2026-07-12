<script setup lang="ts">
/**
 * E1TabCashCount.vue — E1-7/8 现金盘点 (variant: rmb/fx)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.7
 *
 * - RMB模式：面值×张数=金额小计 + 汇总卡(实盘/账面/差异/原因)
 * - FX模式：币种+面值+张数+原币+汇率+折算人民币
 * - variant从sheetName检测: E1-7→rmb, E1-8→fx
 *
 * Requirements: 7.1-7.5
 */
import { inject, toRef, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useE1CashCount,
  type CashCountVariant,
  type RmbCountRow,
  type FxCountRow,
} from '../composables/useE1CashCount'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Variant Detection ───────────────────────────────────────────────────────

const variant = computed<CashCountVariant>(() => {
  const name = props.sheetName || ''
  if (name.includes('E1-8') || name.includes('外币')) return 'fx'
  return 'rmb'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: CashCountVariant } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: variant.value,
}

const {
  rows,
  rmbSummary,
  rmbTotal,
  isLoading,
  hasDiff,
  addRow,
  removeRow,
  updateCell,
  updateSummary,
} = useE1CashCount(options)

// ─── 导入导出（E1-7 rmb / E1-8 fx） ───────────────────────────────────────────

const sheetCode = computed(() => (variant.value === 'fx' ? 'E1-8' : 'E1-7'))
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false // 阻止 el-upload 自动上传
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function asRmb(row: any): RmbCountRow { return row }
function asFx(row: any): FxCountRow { return row }
</script>

<template>
  <div class="e1-tab-cash-count">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 库存现金盘点应由审计人员现场监盘，出纳当面清点，会计主管在场见证。</p>
        <p>2. 盘点日与资产负债表日不一致时，应通过盘点日至资产负债表日的收付记录倒轧至资产负债表日余额。</p>
        <p>3. 人民币按面值×张数汇总；外币按原币金额×期末汇率折算人民币。</p>
        <p>4. 盘点差异应查明原因，关注白条抵库、坐支现金等异常，差异≠0时须在差异原因中说明。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实资产负债表日库存现金的存在性与准确性，确认账实相符，识别白条抵库、坐支等异常。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" :type="variant === 'fx' ? 'warning' : 'success'">
          {{ variant === 'fx' ? '外币盘点 (E1-8)' : '人民币盘点 (E1-7)' }}
        </el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- RMB 模式 -->
        <template v-if="variant === 'rmb'">
          <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
            <el-table-column label="面值" width="120" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asRmb(row).denomination"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'denomination', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="张数" width="120" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asRmb(row).quantity"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'quantity', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="金额小计" width="150" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="auto-calc-value">{{ displayPrefs.fmtAmount(asRmb(row).subtotal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="removeRow(row.id)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- Summary Card -->
          <el-card class="summary-card" shadow="never">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="实盘合计">
                <span class="auto-calc-value">{{ displayPrefs.fmtAmount(rmbTotal) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="账面余额">
                <el-input-number
                  :model-value="rmbSummary.bookBalance"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateSummary('bookBalance', val ?? 0)"
                />
              </el-descriptions-item>
              <el-descriptions-item label="盘点差异">
                <span :class="['auto-calc-value', { 'orange-text': hasDiff() }]">
                  {{ displayPrefs.fmtAmount(rmbSummary.countDiff) }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="差异原因">
                <el-input
                  :model-value="rmbSummary.diffReason"
                  :disabled="isReadonly"
                  placeholder="差异≠0时必填"
                  size="small"
                  @change="(val: string) => updateSummary('diffReason', val)"
                />
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </template>

        <!-- FX 模式 -->
        <template v-else>
          <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
            <el-table-column label="币种" width="100">
              <template #default="{ row }">
                <el-input
                  :model-value="asFx(row).currency"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'currency', val)"
                />
              </template>
            </el-table-column>
            <el-table-column label="面值" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).denomination"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'denomination', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="张数" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).quantity"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'quantity', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="原币金额" width="130" align="right">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).fcAmount"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'fcAmount', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="汇率" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).fxRate"
                  :disabled="isReadonly"
                  :controls="false"
                  :precision="4"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'fxRate', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="折算人民币" width="150" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="auto-calc-value">{{ displayPrefs.fmtAmount(asFx(row).rmbAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="removeRow(row.id)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-cash-count {
  padding: 12px 0;
}
.e1-tab-cash-count :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-cash-count :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #606266;
}
.orange-text {
  color: #e6a23c;
  font-weight: 600;
}
.summary-card {
  margin-top: 16px;
}
</style>
