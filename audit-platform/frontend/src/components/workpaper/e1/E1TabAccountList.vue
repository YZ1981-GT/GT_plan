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
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useE1AccountList,
  type AccountListRow,
} from '../composables/useE1AccountList'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
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
  updateRow,
} = useE1AccountList(options)

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)

// ─── 新增 / 编辑对话框 ──────────────────────────────────────────────────────

const editVisible = ref(false)
const editingRowId = ref('')
const editForm = ref<AccountListRow | null>(null)

function openEdit(row: AccountListRow): void {
  editingRowId.value = row.id
  editForm.value = { ...row }
  editVisible.value = true
}

async function promptAndAdd(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入开户银行或账户名称，确认后创建账户行。', '新增账户', {
      confirmButtonText: '创建并完善',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：中国工商银行北京分行',
      inputValidator: value => Boolean(value?.trim()) || '银行/账户名称不能为空',
    })
    const row = addRow(value.trim())
    if (row) openEdit(row)
  } catch {
    // 用户取消不提示错误。
  }
}

function saveEdit(): void {
  if (!editForm.value || props.isReadonly) return
  if (!editForm.value.bank.trim()) {
    ElMessage.warning('开户银行/账户名称不能为空')
    return
  }
  if (editForm.value.companyInfoConsistent === '不一致' && !editForm.value.inconsistencyReason.trim()) {
    ElMessage.warning('企业信息不一致时必须填写不一致原因')
    return
  }
  updateRow(editingRowId.value, editForm.value)
  editVisible.value = false
  ElMessage.success('账户信息已更新')
}

function accountAiContext(): Record<string, unknown> {
  return {
    summary: summary.value,
    accounts: rows.value.filter(row => row.bank.trim() || row.accountNo.trim()),
  }
}

async function generateAiContent(target: 'note' | 'conclusion'): Promise<void> {
  if (props.isReadonly) return
  const isNote = target === 'note'
  const text = await generateText({
    section: isNote ? 'account-list-audit-note' : 'account-list-audit-conclusion',
    prompt: isNote
      ? '请根据银行账户清单完整性核对结果生成审计说明，说明清单获取途径、与账面及企业信息核对情况、开户目的合理性、受限账户及疑似账外账户的核查与应对。不要虚构未提供事实。'
      : '请根据银行账户清单核对结果生成审计结论，明确账户完整性、账外账户、开户目的合理性、受限或不一致事项及是否需要追加程序。不要虚构未提供事实。',
    context: accountAiContext(),
    existingContent: isNote ? auditNote.value : auditConclusion.value,
    confirmTitle: isNote ? 'AI 生成审计说明' : 'AI 生成审计结论',
  })
  if (!text) return
  if (isNote) saveAuditNote(text)
  else saveAuditConclusion(text)
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

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
  if (isInconsistent(row) || isSuspectedOffBook(row) || row.companyInfoConsistent === '不一致') return 'e1-acct-red-row'
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
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAndAdd">+ 新增账户</el-button>
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
      <el-tag v-if="summary.restrictedCount > 0" size="small" type="warning">受限账户 {{ summary.restrictedCount }}</el-tag>
      <el-tag v-if="summary.companyInconsistentCount > 0" size="small" type="danger">企业信息不一致 {{ summary.companyInconsistentCount }}</el-tag>
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
          <el-table-column label="开户银行/账户名称" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">{{ row.bank || '-' }}</template>
          </el-table-column>
          <el-table-column label="账号" min-width="170" show-overflow-tooltip>
            <template #default="{ row }">{{ row.accountNo || '-' }}</template>
          </el-table-column>
          <el-table-column label="账户性质" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.accountType || '-' }}</template>
          </el-table-column>
          <el-table-column label="账户状态" width="105" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.accountStatus === '已注销' ? 'info' : row.accountStatus === '正常' ? 'success' : 'warning'">
                {{ row.accountStatus || '未填写' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="开户/销户日期" min-width="180">
            <template #default="{ row }">
              <div>{{ row.openDate || '-' }}</div>
              <div v-if="row.closeDate" class="minor-text">销户：{{ row.closeDate }}</div>
            </template>
          </el-table-column>
          <el-table-column label="受限状态" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <el-tag v-if="row.restrictionStatus && row.restrictionStatus !== '无'" size="small" type="warning">
                {{ row.restrictionStatus }}
              </el-tag>
              <span v-else>无</span>
            </template>
          </el-table-column>
          <el-table-column label="企业信息" width="110" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.companyInfoConsistent" size="small" :type="row.companyInfoConsistent === '一致' ? 'success' : 'danger'">
                {{ row.companyInfoConsistent }}
              </el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="openEdit(row)">
                {{ isReadonly ? '查看' : '编辑' }}
              </el-button>
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

    <el-dialog
      v-model="editVisible"
      :title="isReadonly ? '查看账户完整信息' : '新增/编辑账户完整信息'"
      width="820px"
      destroy-on-close
    >
      <el-form v-if="editForm" :model="editForm" label-width="120px" class="account-edit-form">
        <div class="form-grid">
          <el-form-item label="开户银行/账户名称" required>
            <el-input v-model="editForm.bank" :disabled="isReadonly" />
          </el-form-item>
          <el-form-item label="银行账号">
            <el-input v-model="editForm.accountNo" :disabled="isReadonly" />
          </el-form-item>
          <el-form-item label="账户性质">
            <el-select v-model="editForm.accountType" :disabled="isReadonly" filterable allow-create style="width: 100%">
              <el-option label="基本存款账户" value="基本存款账户" />
              <el-option label="一般存款账户" value="一般存款账户" />
              <el-option label="专用存款账户" value="专用存款账户" />
              <el-option label="临时存款账户" value="临时存款账户" />
            </el-select>
          </el-form-item>
          <el-form-item label="账户状态">
            <el-select v-model="editForm.accountStatus" :disabled="isReadonly" style="width: 100%">
              <el-option label="正常" value="正常" />
              <el-option label="已注销" value="已注销" />
              <el-option label="久悬" value="久悬" />
              <el-option label="休眠" value="休眠" />
              <el-option label="其他" value="其他" />
            </el-select>
          </el-form-item>
          <el-form-item label="开户日期">
            <el-date-picker v-model="editForm.openDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item label="销户日期">
            <el-date-picker v-model="editForm.closeDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item label="本期新开（兼容）">
            <el-select v-model="editForm.isNewThisPeriod" :disabled="isReadonly" style="width: 100%">
              <el-option label="是" value="Y" /><el-option label="否" value="N" />
            </el-select>
          </el-form-item>
          <el-form-item label="本期注销（兼容）">
            <el-select v-model="editForm.isClosedThisPeriod" :disabled="isReadonly" style="width: 100%">
              <el-option label="是" value="Y" /><el-option label="否" value="N" />
            </el-select>
          </el-form-item>
          <el-form-item label="账面有记录（兼容）">
            <el-select v-model="editForm.hasBookRecord" :disabled="isReadonly" style="width: 100%">
              <el-option label="有" value="Y" /><el-option label="无" value="N" />
            </el-select>
          </el-form-item>
          <el-form-item label="清单与账面核对">
            <el-select v-model="editForm.checkResult" :disabled="isReadonly" style="width: 100%">
              <el-option label="一致" value="一致" /><el-option label="不一致" value="不一致" />
            </el-select>
          </el-form-item>
          <el-form-item label="企业信息一致性">
            <el-select v-model="editForm.companyInfoConsistent" :disabled="isReadonly" style="width: 100%">
              <el-option label="一致" value="一致" /><el-option label="不一致" value="不一致" />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item label="开户原因">
          <el-input v-model="editForm.openReason" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" />
        </el-form-item>
        <el-form-item label="开户目的（兼容）">
          <el-input v-model="editForm.openPurpose" :disabled="isReadonly" placeholder="保留旧 JSON 字段，可与开户原因一致" />
        </el-form-item>
        <el-form-item label="销户原因">
          <el-input v-model="editForm.closeReason" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" />
        </el-form-item>
        <el-form-item label="受限状态说明">
          <el-input
            v-model="editForm.restrictionStatus"
            :disabled="isReadonly"
            type="textarea"
            :autosize="{ minRows: 2 }"
            placeholder="填写无，或说明冻结/抵押/质押类型、金额、期限及权利人"
          />
        </el-form-item>
        <el-form-item label="企业信息不一致原因" :required="editForm.companyInfoConsistent === '不一致'">
          <el-input v-model="editForm.inconsistencyReason" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" />
        </el-form-item>
        <el-form-item label="账面核对差异说明" :required="editForm.checkResult === '不一致'">
          <el-input v-model="editForm.reason" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 2 }" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">{{ isReadonly ? '关闭' : '取消' }}</el-button>
        <el-button v-if="!isReadonly" type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" plain :loading="isGenerating('account-list-audit-note')" :disabled="isReadonly" @click="generateAiContent('note')">🤖 AI辅助</el-button>
        </div>
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
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :loading="isGenerating('account-list-audit-conclusion')" :disabled="isReadonly" @click="generateAiContent('conclusion')">🤖 AI辅助</el-button>
        </div>
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

.minor-text {
  margin-top: 2px;
  color: #909399;
  font-size: 12px;
}
.account-edit-form .form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
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
