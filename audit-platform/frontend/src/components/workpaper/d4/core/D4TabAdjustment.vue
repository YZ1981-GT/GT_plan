<script setup lang="ts">
/**
 * D4TabAdjustment — D4-4 调整分录
 *
 * el-table 8列 + "新增调整分录" + 借贷合计+平衡指示
 * "推送至A13"按钮 + 与调整分录模块双向联动 + 导入导出三级
 *
 * Requirements: 5.1-5.7
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4Adjustment, type D4AdjustmentRow } from '../../composables/useD4Adjustment'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Composable ───────────────────────────────────────────────────────
const {
  rows,
  debitTotal,
  creditTotal,
  isBalanced,
  balanceDiff,
  addRow,
  removeRow,
  updateCell,
  publishAdjustment,
  pushToA13,
} = useD4Adjustment({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 导入导出 ─────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
})

function handleImportUpload(file: File): boolean {
  importData('D4-4', file)
  return false
}

// ─── 选中行（用于推送A13） ─────────────────────────────────────────────
const selectedRows = ref<D4AdjustmentRow[]>([])

function handleSelectionChange(selection: D4AdjustmentRow[]) {
  selectedRows.value = selection
}

function handlePushToA13() {
  const ids = selectedRows.value.map(r => r.rowId)
  if (ids.length === 0) return
  pushToA13(ids)
}

// ─── 分类选项 ─────────────────────────────────────────────────────────
const categoryOptions = [
  { label: '账项调整', value: '账项调整' },
  { label: '报表调整', value: '报表调整' },
  { label: '其他', value: '其他' },
]

// ─── 审计说明/结论（allResponses存取，与D4-2一致） ────────────────────
const auditNote = computed({
  get: () => props.allResponses.get('D4-4-note')?.remark || '',
  set: (val: string) => (props.allResponses as Map<string, any>).set('D4-4-note', { item_id: 'D4-4-note', conclusion: null, remark: val }),
})
const auditConclusion = computed({
  get: () => props.allResponses.get('D4-4-conclusion')?.remark || '',
  set: (val: string) => (props.allResponses as Map<string, any>).set('D4-4-conclusion', { item_id: 'D4-4-conclusion', conclusion: null, remark: val }),
})

// ─── AI辅助（真实接入） ──────────────────────────────────────────────
const aiAvailable = ref(false)
const aiLoadingKey = ref<string | null>(null)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

async function callD4Ai(section: string, existing: string): Promise<string> {
  const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
    section, existingContent: existing, relatedContext: {},
  }, { _silent: true } as any)
  return res.data?.data?.content ?? res.data?.content ?? ''
}

async function generateNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const ctx = rows.value.map(r =>
      `${r.description || '调整'}: ${r.accountName} 借${fmtAmount(r.debitAmount)}/贷${fmtAmount(r.creditAmount)} [${r.category}]`
    ).join('\n') || '（暂无调整分录）'
    const text = await callD4Ai('adj-note', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    auditNote.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n借贷${isBalanced.value ? '平衡' : '不平衡差异' + fmtAmount(balanceDiff.value)}`
    const text = await callD4Ai('adj-conclusion', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    auditConclusion.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
</script>

<template>
  <div class="d4-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 记录审计过程中发现的需要调整的会计分录。</p>
        <p>2. "账项调整"(AJE)：涉及科目余额的调整；"报表调整"(RJE)：仅影响报表列报的重分类调整。</p>
        <p>3. 借贷合计必须平衡（借方合计=贷方合计），不平衡时无法确认。</p>
        <p>4. 确认后的调整分录将同步更新D4-1审定表的AJE/RJE列。</p>
        <p>5. 可选中分录推送至A13错报汇总表。</p>
        <p>6. 本表与"调整分录"模块双向联动：此处新增的分录会同步到调整分录模块，反之亦然。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tooltip placement="top" :show-after="300">
          <template #content>
            本表与调整分录模块双向联动。<br/>
            此处新增的分录会自动同步至调整分录模块(科目6001/6051)，<br/>
            调整分录模块中涉及营业收入科目的分录也会自动回写至此表。
          </template>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
            + 新增调整分录
          </el-button>
        </el-tooltip>
        <el-button
          size="small"
          :disabled="isReadonly || selectedRows.length === 0"
          @click="handlePushToA13"
        >
          推送至A13
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('D4-4')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('D4-4')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImportUpload"
                  :disabled="importing"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !isBalanced || rows.length === 0"
          @click="publishAdjustment"
        >
          确认调整
        </el-button>
      </div>
    </div>

    <!-- 借贷平衡指示 -->
    <div class="balance-indicator">
      <span class="balance-item">
        借方合计：<strong>{{ fmtAmount(debitTotal) }}</strong>
      </span>
      <span class="balance-item">
        贷方合计：<strong>{{ fmtAmount(creditTotal) }}</strong>
      </span>
      <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">
        不平衡 差异{{ fmtAmount(balanceDiff) }}
      </el-tag>
    </div>

    <!-- 主表 -->
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%; margin-bottom: 12px"
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="40" />

      <!-- 1. 摘要 -->
      <el-table-column label="摘要" min-width="200">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="摘要"
            @change="(v: string) => updateCell(row.rowId, 'description', v)"
          />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 2. 分类 -->
      <el-table-column label="分类" width="110">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'category', v)"
          >
            <el-option
              v-for="opt in categoryOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <!-- 3. 报表项目 -->
      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            placeholder="报表项目"
            @change="(v: string) => updateCell(row.rowId, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 4. 会计科目 -->
      <el-table-column label="会计科目" width="150">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="如 6001-主营业务收入"
            @change="(v: string) => updateCell(row.rowId, 'accountName', v)"
          />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 5. 附注项目 -->
      <el-table-column label="附注项目" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 6. 借方金额 -->
      <el-table-column label="借方" width="120" align="right">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            type="number"
            @change="(v: string) => updateCell(row.rowId, 'debitAmount', v)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 7. 贷方金额 -->
      <el-table-column label="贷方" width="120" align="right">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            type="number"
            @change="(v: string) => updateCell(row.rowId, 'creditAmount', v)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 8. 索引号 -->
      <el-table-column label="索引号" width="80">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'indexRef', v)"
          />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly"
            type="danger"
            size="small"
            link
            @click="removeRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空状态 -->
    <div v-if="rows.length === 0" class="empty-hint">
      暂无调整分录。点击"新增调整分录"添加，或从调整分录模块自动同步。
    </div>

    <!-- 审计意见区（卡片式，与D4-1/D4-2/D4-5统一） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
            <GtIndexChip value="wp:A13" :context-project-id="projectId" />
          </div>
        </div>
      </template>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">1. 审计说明</span>
          <div class="opinion-actions">
            <el-tooltip :content="aiTip" placement="top">
              <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'"
                :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button>
            </el-tooltip>
            <el-button size="small" @click="openReviewDialog?.('D4-4-note')">💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditNote"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 8 }"
          placeholder="请输入审计说明（汇总营业收入相关调整事项的原因与影响）..."
          :disabled="isReadonly"
        />
      </div>

      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">2. 审计结论</span>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'"
              :disabled="isReadonly || !aiAvailable" @click="generateConclusion">🤖 AI辅助</el-button>
          </el-tooltip>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.d4-tab-adjustment {
  padding: 12px;
}
.d4-tab-adjustment :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.d4-tab-adjustment :deep(.el-table .cell) {
  font-size: 13px !important;
}
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
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
}
.toolbar-right {
  display: flex;
  gap: 6px;
}
.balance-indicator {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 13px;
}
.balance-item {
  color: #606266;
}
.balance-item strong {
  color: #303133;
}
.empty-hint {
  text-align: center;
  color: #909399;
  padding: 24px;
  font-size: 13px;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 16px;
}
.opinion-section:last-child {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
