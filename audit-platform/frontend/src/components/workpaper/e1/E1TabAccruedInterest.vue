<script setup lang="ts">
/**
 * E1TabAccruedInterest.vue — E1-20 应计利息
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.14
 *
 * - Uses useE1InterestCalc with variant='accrued'
 * - Dynamic rows: 开户银行 | 账号 | 用途 | 币种 | 原币金额 | 结息日 | 截止日 |
 *   天数(readonly) | 日利率 | 应计利息原币(readonly) | 汇率 | 应计利息人民币(readonly) | 备注
 * - Total row at bottom
 *
 * Requirements: 10.3-10.4
 */
import { ref, computed, inject, toRef, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useE1InterestCalc,
  type AccruedInterestRow,
} from '../composables/useE1InterestCalc'
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
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: 'accrued' } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: 'accrued',
}

const {
  rows,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1InterestCalc(options)

// ─── 导入导出（E1-20） ────────────────────────────────────────────────────────

const sheetCode = computed(() => 'E1-20')
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
  return false
}

// ─── Computed ────────────────────────────────────────────────────────────────

function asAccrued(row: any): AccruedInterestRow { return row }

const totalAccruedRmb = computed(() => {
  return (rows.value as AccruedInterestRow[]).reduce((sum, r) => sum + (r as AccruedInterestRow).accruedRmb, 0)
})

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

const NOTE_KEY = 'E1-accrued-audit-note'
const CONCLUSION_KEY = 'E1-accrued-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const noteResp = props.allResponses.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
})

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}
</script>

<template>
  <div class="e1-tab-accrued-interest">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按各存款账户余额、约定利率与计息天数独立测算应计利息，验证利息收入及应收利息计提。</p>
        <p>2. 灰色底纹列（天数/应计利息原币/应计利息人民币）为自动计算列，不可手工编辑。</p>
        <p>3. 天数=结息日至截止日；外币应计利息按期末汇率折算人民币。</p>
        <p>4. 测算数与账面计提数比较，差异重大应提请调整；关注定期存款、大额存单利率合理性。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：独立测算应计利息，验证利息收入及应收利息计提的准确性与完整性。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
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

    <el-skeleton :loading="isLoading" :rows="10" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="550" style="width: 100%">
          <el-table-column label="开户银行" width="130">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).bank" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'bank', val)" />
            </template>
          </el-table-column>
          <el-table-column label="账号" width="150">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).accountNo" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'accountNo', val)" />
            </template>
          </el-table-column>
          <el-table-column label="用途" width="100">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).usage" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'usage', val)" />
            </template>
          </el-table-column>
          <el-table-column label="币种" width="80">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).currency" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'currency', val)" />
            </template>
          </el-table-column>
          <el-table-column label="原币金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="asAccrued(row).fcAmount" :disabled="isReadonly"
                :controls="false" size="small"
                @change="(val: number) => updateCell(row.id, 'fcAmount', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="结息日" width="120">
            <template #default="{ row }">
              <el-date-picker :model-value="asAccrued(row).settleDate" :disabled="isReadonly"
                type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'settleDate', val || '')" />
            </template>
          </el-table-column>
          <el-table-column label="截止日" width="120">
            <template #default="{ row }">
              <el-date-picker :model-value="asAccrued(row).cutoffDate" :disabled="isReadonly"
                type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'cutoffDate', val || '')" />
            </template>
          </el-table-column>
          <el-table-column label="天数" width="70" align="center" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="auto-calc-value">{{ asAccrued(row).days }}</span>
            </template>
          </el-table-column>
          <el-table-column label="日利率" width="100" align="center">
            <template #default="{ row }">
              <el-input-number :model-value="asAccrued(row).dailyRate" :disabled="isReadonly"
                :controls="false" :precision="8" size="small"
                @change="(val: number) => updateCell(row.id, 'dailyRate', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="应计利息原币" width="130" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="auto-calc-value">{{ displayPrefs.fmtAmount(asAccrued(row).accruedFc) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="汇率" width="90" align="center">
            <template #default="{ row }">
              <el-input-number :model-value="asAccrued(row).fxRate" :disabled="isReadonly"
                :controls="false" :precision="4" size="small"
                @change="(val: number) => updateCell(row.id, 'fxRate', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="应计利息人民币" width="140" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="auto-calc-value">{{ displayPrefs.fmtAmount(asAccrued(row).accruedRmb) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="asAccrued(row).note" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'note', val)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="footer-row">
          <span class="total-label">应计利息人民币合计：
            <strong class="total-amount">{{ displayPrefs.fmtAmount(totalAccruedRmb) }}</strong>
          </span>
        </div>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计说明</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明：可概述（1）各存款账户应计利息的测算方法（结息日至资产负债表日、按约定利率与天数计提）；（2）外币应计利息按期末汇率折算的处理；（3）测算数与账面计提利息收入/应收利息的比较及差异分析。"
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计结论</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论：A、应计利息测算数与账面计提相符，利息收入完整、准确。B、除上述差异应提请调整外，其余未见异常。C、由于存在以下重大差异（或资料受限），需进一步核查。"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-accrued-interest {
  padding: 12px 0;
}
.e1-tab-accrued-interest :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-accrued-interest :deep(.el-table .cell) {
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
.footer-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-top: 10px;
}
.total-label {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.total-amount {
  color: #303133;
}
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
