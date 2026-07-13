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
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
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
  summary,
  isInconsistent,
  isMissingReason,
  isSuspectedOffBook,
  addRow,
  removeRow,
  updateCell,
} = useE1AccountList(options)

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────
// 组件无 AI composable → 纯 textarea（不臆造 AI 按钮）

const NOTE_KEY = 'E1-acctlist-audit-note'
const CONCLUSION_KEY = 'E1-acctlist-audit-conclusion'
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
  if (isInconsistent(row) || isSuspectedOffBook(row)) return 'e1-acct-red-row'
  return ''
}
</script>

<template>
  <div class="e1-tab-account-list">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 获取被审计单位<strong>本期所有银行账户清单</strong>（含沿用、本期新开、本期注销及零余额账户），并询问办理货币资金业务的相关人员（如出纳），了解账户的开立、使用、注销情况。</p>
        <p>2. 对完整性存有疑虑时，应<strong>亲自到中国人民银行或基本存款账户开户行打印《已开立银行结算账户清单》</strong>与账面记录核对，识别是否存在账外账户。</p>
        <p>3. 检查账户完整性：清单中每一账户均应在账面有记录（"账面是否有记录"=N 时红色高亮，为疑似账外账户）；并结合企业信用报告（E1-18）分析各账户<strong>开户目的的合理性</strong>。</p>
        <p>4. 核对结果为"不一致"时须在"差异说明"栏说明差异内容；必要时（首次承接 / IPO / 上市公司 / 存在舞弊风险项目）取得管理层关于银行账户完整性的<strong>书面声明</strong>（见 E1-11）。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认被审计单位银行账户开立的完整性（不存在账外账户及未入账资金往来），并评价各账户开户目的的合理性。"
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
        <span class="chip-wrap"><GtIndexChip value="wp:E1-11" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-18" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 完整性核对小结 -->
    <div class="completeness-bar">
      <span class="cb-label">完整性核对：</span>
      <el-tag size="small" type="info">账户 {{ summary.total }} 个</el-tag>
      <el-tag size="small" type="success">本期新开 {{ summary.newCount }}</el-tag>
      <el-tag size="small" type="warning">本期注销 {{ summary.closedCount }}</el-tag>
      <el-tag v-if="summary.offBookCount > 0" size="small" type="danger">疑似账外 {{ summary.offBookCount }}</el-tag>
      <el-tag v-else size="small" type="success">无疑似账外账户</el-tag>
      <el-tag v-if="summary.inconsistentCount > 0" size="small" type="danger">核对不一致 {{ summary.inconsistentCount }}</el-tag>
      <el-tag v-else size="small" type="success">清单与账面核对一致</el-tag>
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
              <el-select
                :model-value="row.accountType"
                :disabled="isReadonly"
                size="small"
                filterable
                allow-create
                default-first-option
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'accountType', val)"
              >
                <el-option label="基本存款账户" value="基本存款账户" />
                <el-option label="一般存款账户" value="一般存款账户" />
                <el-option label="专用存款账户" value="专用存款账户" />
                <el-option label="临时存款账户" value="临时存款账户" />
              </el-select>
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
          <el-table-column label="开户目的" min-width="140">
            <template #header>
              <span>开户目的</span>
              <el-tooltip content="说明该账户的用途，评价开户目的的合理性（如：日常结算 / 工资代发 / 募集资金专户 / 项目专用等）" placement="top">
                <span class="hint-mark">?</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input
                :model-value="row.openPurpose"
                :disabled="isReadonly"
                size="small"
                placeholder="账户用途"
                @change="(val: string) => updateCell(row.id, 'openPurpose', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期新开" width="90" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.isNewThisPeriod"
                :disabled="isReadonly"
                size="small"
                placeholder="-"
                @change="(val: string) => updateCell(row.id, 'isNewThisPeriod', val)"
              >
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="本期注销" width="90" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="row.isClosedThisPeriod"
                :disabled="isReadonly"
                size="small"
                placeholder="-"
                @change="(val: string) => updateCell(row.id, 'isClosedThisPeriod', val)"
              >
                <el-option label="是" value="Y" />
                <el-option label="否" value="N" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="账面有记录" width="100" align="center">
            <template #header>
              <span>账面有记录</span>
              <el-tooltip content="清单中该账户是否在账面（总账/明细账）有记录。选择'否'即清单有而账面无，为疑似账外账户，行标红" placement="top">
                <span class="hint-mark">?</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-select
                :model-value="row.hasBookRecord"
                :disabled="isReadonly"
                size="small"
                placeholder="-"
                @change="(val: string) => updateCell(row.id, 'hasBookRecord', val)"
              >
                <el-option label="有" value="Y" />
                <el-option label="无" value="N" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="清单核对一致" width="120" align="center">
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
          <el-table-column label="差异说明" min-width="150">
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
        placeholder="说明银行账户清单的获取途径（企业提供 / 人行《已开立银行结算账户清单》打印）、与账面核对情况、各账户开户目的合理性分析，以及是否存在账外账户、久悬未用或零余额账户等..."
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
        placeholder="对银行账户开立完整性发表结论（如：已开立银行账户清单与账面核对一致，未发现账外账户，各账户开户目的合理）..."
        @change="(val: string) => saveAuditConclusion(val)"
      />
    </el-card>
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

/* 完整性核对小结 */
.completeness-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}
.cb-label {
  color: #909399;
}

/* 表头提示标记 */
.hint-mark {
  display: inline-block;
  margin-left: 4px;
  width: 14px;
  height: 14px;
  line-height: 14px;
  text-align: center;
  border-radius: 50%;
  background: #c0c4cc;
  color: #fff;
  font-size: 11px;
  cursor: help;
}

.required-field :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}

/* 审计说明 / 审计结论 */
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
:deep(.e1-acct-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-acct-red-row td) {
  color: #f56c6c;
}
</style>
