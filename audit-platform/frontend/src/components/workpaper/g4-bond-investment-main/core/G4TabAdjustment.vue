<template>
  <div class="g4-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认针对债权投资的审计调整(AJE)与重分类(RJE)分录依据充分、借贷平衡，并正确汇总回写至 G4-1 审定表。"
      style="margin-bottom: 12px"
    />
    <!-- Section标题栏 + 复核按钮右对齐 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-3 调整分录汇总</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleSaveWriteback">
          保存&amp;回写
        </el-button>
        <!-- 导入导出 el-dropdown -->
        <el-dropdown trigger="click" size="small" @command="handleIECommand">
          <el-button size="small">
            导入导出 ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx"
                  :auto-upload="false"
                  :disabled="isReadonly || ie.importing.value"
                  @change="onImportFile"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 借贷不平衡警告 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmt(totalDebits) }} ≠ 贷方合计 {{ fmt(totalCredits) }}，差额 {{ fmt(Math.abs(balanceDiff)) }}
    </el-alert>

    <!-- 工具栏：新增按钮 -->
    <div class="g4-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">
        + 新增
      </el-button>
    </div>

    <!-- 10列调整分录表格 -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width:100%;font-size:13px"
      max-height="520"
      :row-class-name="tableRowClassName"
    >
      <el-table-column prop="seq" label="序号" width="56" align="center" />

      <el-table-column label="分录类型" width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.entryType"
            size="small"
            @change="(v: string) => updateCell(row.id, 'entryType', v)"
          >
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.date"
            size="small"
            placeholder="YYYY-MM-DD"
            @change="(v: string) => updateCell(row.id, 'date', v)"
          />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.summary"
            size="small"
            @change="(v: string) => updateCell(row.id, 'summary', v)"
          />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目代码" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.accountCode"
            size="small"
            filterable
            @change="(v: string) => updateCell(row.id, 'accountCode', v)"
          >
            <el-option
              v-for="opt in accountOptions"
              :key="opt.code"
              :value="opt.code"
              :label="`${opt.code} ${opt.name}`"
            />
          </el-select>
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="140">
        <template #default="{ row }">
          <span>{{ row.accountName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width:100%"
            @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width:100%"
            @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="编制人" width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.preparedBy"
            size="small"
            @change="(v: string) => updateCell(row.id, 'preparedBy', v)"
          />
          <span v-else>{{ row.preparedBy }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => updateCell(row.id, 'remark', v)"
          />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">
            🗑️
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行（借贷不平衡时红色高亮） -->
    <div class="g4-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmt(totalCredits) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">
        ✗ 不平衡 | 差额：{{ fmt(Math.abs(balanceDiff)) }}
      </span>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：调整分录的依据、借贷平衡与回写情况，拟调整/未调整事项及其影响。"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述调整事项予以调整外，其余未见异常。C、存在重大未调整事项，不可确认。"
        @change="(v: string) => saveAuditConclusion(v)"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="g4-guide-details">
      <summary>📋 编制提示</summary>
      <div class="g4-guide-content">
        <p>1. 调整分录(AJE)用于更正被审计单位财务报表中的错报；重分类分录(RJE)用于分析性归类调整。</p>
        <p>2. 借贷必须平衡后方可保存回写。点击"保存&amp;回写"将汇总数据回写G4-1审定表。</p>
        <p>3. 科目代码选择后自动带出科目名称，支持筛选搜索。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabAdjustment.vue — G4-3 调整分录汇总
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 5.4
 * Requirements: 6.1~6.5, 11.1, 11.5
 *
 * 功能：
 * - 10列调整分录表格（序号|分录类型|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注）
 * - 借贷不平衡时红色高亮显示差额
 * - 动态行增删 + ElMessageBox.prompt输入摘要确认
 * - 保存时自动汇总回写G4-1审定表
 * - section标题栏右侧复核按钮
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useG4MainAdjustment } from '../../composables/useG4MainAdjustment'
import { useG4MainImportExport } from '../../composables/useG4MainImportExport'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── allResponses 本地状态管理 ───
// 当父组件未传递 allResponses 时，在本组件中创建本地 Map
// useG4MainAdjustment 会使用此 Map 进行数据持久化
const allResponses = ref<Map<string, ChecklistResponse>>(new Map())

// ─── 审计说明 / 审计结论（走 checklist_responses，conclusion:null + remark 文本） ───
const NOTE_KEY = 'G4-3-adjustment-audit-note'
const CONCLUSION_KEY = 'G4-3-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function readSaved(key: string): string {
  const cr = props.htmlData?.checklist_responses
  if (cr && typeof cr === 'object' && (cr as Record<string, any>)[key]) {
    const v = (cr as Record<string, any>)[key]
    return typeof v === 'object' ? (v.remark ?? '') : String(v ?? '')
  }
  const resp = props.htmlData?.responses
  if (Array.isArray(resp)) {
    const found = resp.find((r: any) => r?.item_id === key)
    if (found?.remark) return found.remark
  }
  return ''
}

async function saveAudit(key: string, val: string): Promise<void> {
  if (props.isReadonly) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{ item_id: key, conclusion: null, remark: val }],
    })
  } catch { /* silent */ }
}

function saveAuditNote(val: string): void {
  auditNote.value = val
  void saveAudit(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  auditConclusion.value = val
  void saveAudit(CONCLUSION_KEY, val)
}

onMounted(() => {
  auditNote.value = readSaved(NOTE_KEY)
  auditConclusion.value = readSaved(CONCLUSION_KEY)
})

// ─── 初始化 composable ───
const isReadonlyRef = ref(props.isReadonly)
const {
  entries,
  totalDebits,
  totalCredits,
  balanceDiff,
  isBalanced,
  addEntry,
  removeEntry,
  updateCell,
  saveAndWriteback,
  accountOptions,
} = useG4MainAdjustment({
  allResponses,
  isReadonly: isReadonlyRef,
})

// ─── 导入导出 ───
const ie = useG4MainImportExport({ wpId: computed(() => props.wpId) })

function handleIECommand(cmd: string): void {
  if (cmd === 'template') ie.exportTemplate('G4-3')
  else if (cmd === 'export') ie.exportData('G4-3')
}

async function onImportFile(f: { raw?: File } | File): Promise<void> {
  const file = f instanceof File ? f : (f.raw ?? null)
  if (!file) return
  await ie.importData('G4-3', file)
}

// ─── 事件处理 ───

/** 新增行（composable内部弹 ElMessageBox.prompt） */
function handleAddEntry(): void {
  addEntry()
}

/** 删除行（确认后删除） */
async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    removeEntry(id)
  } catch {
    // 用户取消
  }
}

/** 保存并回写G4-1审定表 */
function handleSaveWriteback(): void {
  saveAndWriteback()
}

/** 打开复核对话 */
function openReview(): void {
  openReviewDialog('G4-3-adjustment')
}

/** 格式化金额 */
function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

/** 表格行class（用于视觉区分） */
function tableRowClassName({ row }: { row: any }): string {
  if (row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.g4-tab-adjustment {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 审计说明/结论卡片 */
.audit-note-card { margin-top: 12px; }
.audit-note-card .card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 500; }

.g4-adj-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

/* 合计行 */
.g4-adj-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  padding: 10px 16px;
  background: #f0f9eb;
  border-radius: 4px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
}

.g4-adj-footer.balance-fail {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

.footer-label {
  color: #606266;
}

.footer-debit,
.footer-credit {
  color: #303133;
}

.footer-status.ok {
  color: #67c23a;
  margin-left: auto;
}

.footer-status.err {
  color: #f56c6c;
  margin-left: auto;
  font-weight: 700;
}

/* RJE行浅色区分 */
:deep(.rje-row) {
  background-color: #fdf6ec !important;
}

/* 编制提示 */
.g4-guide-details {
  margin-top: 16px;
}

.g4-guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}

.g4-guide-content p {
  margin: 0;
}
</style>
