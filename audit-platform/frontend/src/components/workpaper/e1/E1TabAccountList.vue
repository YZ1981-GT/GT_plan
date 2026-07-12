<script setup lang="ts">
/**
 * E1TabAccountList.vue — E1-10 账户核对
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.9
 *
 * - Dynamic rows with 核对结果(一致/不一致)
 * - 不一致 row red highlight + 原因required
 *
 * Requirements: 8.1-8.2
 */
import { inject, toRef, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useE1AccountList, type AccountListRow } from '../composables/useE1AccountList'
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
  isLoading,
  isInconsistent,
  isMissingReason,
  addRow,
  removeRow,
  updateCell,
} = useE1AccountList(options)

// ─── 导入导出（E1-10） ────────────────────────────────────────────────────────

const sheetCode = computed(() => 'E1-10')
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

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClass({ row }: { row: AccountListRow }): string {
  if (isInconsistent(row)) return 'e1-acct-red-row'
  return ''
}
</script>

<template>
  <div class="e1-tab-account-list">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 取得被审计单位全部银行账户清单，与开户许可证、征信报告（E1-18）核对账户完整性。</p>
        <p>2. 关注是否存在账外账户、久悬未用账户及未纳入审定表的账户。</p>
        <p>3. 核对结果为"不一致"时，须在原因栏说明差异内容（红色高亮提示）。</p>
        <p>4. 每个银行账户均应取得银行询证函回函予以支持，并与审定表勾稽一致。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实被审计单位银行账户的完整性，确认不存在账外账户及未入账资金往来。"
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

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          max-height="550"
          style="width: 100%"
          :row-class-name="getRowClass"
        >
          <el-table-column label="开户银行" width="150">
            <template #default="{ row }">
              <el-input
                :model-value="row.bank"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'bank', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="账号" width="180">
            <template #default="{ row }">
              <el-input
                :model-value="row.accountNo"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'accountNo', val)"
              />
            </template>
          </el-table-column>
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
          <el-table-column label="开户日期" width="130">
            <template #default="{ row }">
              <el-date-picker
                :model-value="row.openDate"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'openDate', val || '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="是否征信" width="90" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.inCreditReport"
                :disabled="isReadonly"
                size="small"
                placeholder="-"
                @change="(val: string) => updateCell(row.id, 'inCreditReport', val)"
              >
                <el-option label="Y" value="Y" />
                <el-option label="N" value="N" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="是否审定表" width="100" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.inAdjudication"
                :disabled="isReadonly"
                size="small"
                placeholder="-"
                @change="(val: string) => updateCell(row.id, 'inAdjudication', val)"
              >
                <el-option label="Y" value="Y" />
                <el-option label="N" value="N" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="核对结果" width="110" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.checkResult"
                :disabled="isReadonly"
                size="small"
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'checkResult', val)"
              >
                <el-option label="一致" value="一致" />
                <el-option label="不一致" value="不一致" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="原因" min-width="150">
            <template #default="{ row }">
              <el-input
                :model-value="row.reason"
                :disabled="isReadonly"
                :class="{ 'required-field': isMissingReason(row) }"
                :placeholder="isInconsistent(row) ? '不一致时必填' : ''"
                size="small"
                @change="(val: string) => updateCell(row.id, 'reason', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center" fixed="right">
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
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-account-list {
  padding: 12px 0;
}
.e1-tab-account-list :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-account-list :deep(.el-table .cell) {
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

.required-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
:deep(.e1-acct-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-acct-red-row td) {
  color: #f56c6c;
}
</style>
