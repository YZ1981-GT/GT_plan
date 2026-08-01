<template>
<div class="d6-tab-adjustment">
  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 记录审计过程中发现的需要调整的会计分录，确保借贷平衡。</p>
      <p>2. "账项调整"(AJE)：涉及科目余额的调整，影响审定数；"报表调整"(RJE)：仅影响报表列报的重分类调整。</p>
      <!-- 科目码依据（标准科目表实证）：1141 合同资产（借）/ 1142 合同资产减值准备（贷）；
           部分客户把合同资产减值并入 1231-05 坏账准备-合同资产。
           原文案写的 1403 是「原材料」（存货类），属误用。 -->
      <p>3. 合同资产相关调整科目：1141 合同资产 / 1142 合同资产减值准备（或 1231-05 坏账准备-合同资产）。</p>
      <p>4. 借贷合计必须平衡（借方合计=贷方合计），不平衡时无法确认。</p>
      <p>5. 确认后的调整分录将同步更新 D6-1 审定表的 AJE/RJE 列。</p>
      <p>6. 可选中分录推送至 A13 错报汇总表。</p>
      <p>7. 本表与"调整分录"模块双向联动：此处新增的分录会同步到调整分录模块，反之亦然。</p>
    </div>
  </details>

  <!-- 审计目标 -->
  <el-alert
    type="info"
    :closable="false"
    title="审计目标：验证调整分录的准确性与完整性，确认借贷平衡且调整事由充分合理。"
    class="objective-alert"
  />

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-tooltip placement="top" :show-after="300">
        <template #content>
          本表与调整分录模块双向联动。<br/>
          此处新增的分录会自动同步至调整分录模块(科目1141/1142)，<br/>
          调整分录模块中涉及合同资产科目的分录也会自动回写至此表。
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
        推送至A13（{{ selectedRows.length }}条）
      </el-button>
    </div>
    <div class="toolbar-right">
      <el-dropdown size="small" trigger="click" :disabled="isReadonly">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData">导出数据</el-dropdown-item>
            <el-dropdown-item>
              <el-upload
                :show-file-list="false"
                accept=".xlsx"
                :auto-upload="false"
                :disabled="isReadonly || importing"
                @change="(f: any) => onImportFile(f.raw || f)"
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
      <el-button
        size="small"
        type="primary"
        plain
        :loading="centralSyncing"
        :disabled="isReadonly || !isBalanced || rows.length === 0"
        @click="syncToCentral"
        title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
      >同步到集中登记</el-button>
      <el-tag
        v-if="centralStatus?.review_status"
        size="small"
        :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
        :title="centralStatus.rejection_reason || ''"
      >集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}</el-tag>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:A13" :context-project-id="projectId" /></span>
    </div>
  </div>

  <!-- 借贷平衡指示 -->
  <div class="balance-indicator">
    <span class="balance-item">借方合计：<strong>{{ fmtAmount(debitTotal) }}</strong></span>
    <span class="balance-item">贷方合计：<strong>{{ fmtAmount(creditTotal) }}</strong></span>
    <el-tag v-if="isBalanced" type="success" size="small">借贷平衡</el-tag>
    <el-tag v-else type="danger" size="small">不平衡 差异{{ fmtAmount(balanceDiff) }}</el-tag>
  </div>

  <!-- 主表 -->
  <el-table
    :data="rows"
    size="small"
    border
    stripe
    style="width:100%; margin-bottom:12px"
    @selection-change="handleSelectionChange"
  >
    <el-table-column type="selection" width="40" />

    <el-table-column label="调整事项说明" min-width="180">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.description"
          size="small"
          placeholder="摘要"
          @change="(val: string) => updateCell(row.rowId, 'description', val)"
        />
        <span v-else>{{ row.description || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="类别" width="110">
      <template #default="{ row }">
        <el-select
          v-if="!isReadonly"
          :model-value="row.category"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'category', val)"
        >
          <el-option v-for="opt in categoryOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <span v-else>{{ row.category }}</span>
      </template>
    </el-table-column>

    <el-table-column label="报表项目" width="120">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.reportItem"
          size="small"
          placeholder="报表项目"
          @change="(val: string) => updateCell(row.rowId, 'reportItem', val)"
        />
        <span v-else>{{ row.reportItem || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="科目名称" width="150">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.accountName"
          size="small"
          placeholder="如 1141-合同资产"
          @change="(val: string) => updateCell(row.rowId, 'accountName', val)"
        />
        <span v-else>{{ row.accountName || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="附注项目" width="100">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.noteItem"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'noteItem', val)"
        />
        <span v-else>{{ row.noteItem || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="预留" width="80">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.placeholder"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'placeholder', val)"
        />
        <span v-else>{{ row.placeholder || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="借方金额" width="120" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.debitAmount"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(val: number) => updateCell(row.rowId, 'debitAmount', val ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="贷方金额" width="120" align="right">
      <template #default="{ row }">
        <el-input-number
          v-if="!isReadonly"
          :model-value="row.creditAmount"
          :controls="false"
          size="small"
          style="width:100%"
          @change="(val: number) => updateCell(row.rowId, 'creditAmount', val ?? 0)"
        />
        <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
      </template>
    </el-table-column>

    <el-table-column label="索引" width="80">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.indexRef"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'indexRef', val)"
        />
        <span v-else>{{ row.indexRef || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column label="备注" min-width="120">
      <template #default="{ row }">
        <el-input
          v-if="!isReadonly"
          :model-value="row.remark"
          size="small"
          @change="(val: string) => updateCell(row.rowId, 'remark', val)"
        />
        <span v-else>{{ row.remark || '-' }}</span>
      </template>
    </el-table-column>

    <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
      <template #default="{ row }">
        <el-button type="danger" size="small" link @click="removeRow(row.rowId)">删</el-button>
      </template>
    </el-table-column>
  </el-table>

  <!-- 空状态 -->
  <div v-if="rows.length === 0" class="empty-hint">
    暂无调整分录。点击"新增调整分录"添加，或从调整分录模块自动同步。
  </div>

  <!-- 审计意见区（卡片式，对齐 D4-4 标准） -->
  <el-card class="opinion-card" shadow="never">
    <template #header>
      <div class="opinion-header">
        <span class="opinion-title">审计说明与结论</span>
        <div class="opinion-chips">
          <GtIndexChip value="wp:D6-1" :context-project-id="projectId" />
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
          <GtReviewTrigger section-id="D6-4-note" label="💬" />
        </div>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请输入审计说明（汇总合同资产相关调整事项的原因与影响）..."
      />
    </div>

    <div class="opinion-section">
      <div class="opinion-section-header">
        <span class="opinion-section-label">2. 审计结论</span>
        <div class="opinion-actions">
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'"
              :disabled="isReadonly || !aiAvailable" @click="generateConclusion">🤖 AI辅助</el-button>
          </el-tooltip>
          <GtReviewTrigger section-id="D6-4-conclusion" label="💬" />
        </div>
      </div>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        :disabled="isReadonly"
        placeholder="请输入审计结论..."
      />
    </div>
  </el-card>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabAdjustment.vue — 调整分录汇总表 D6-4（对齐 D4-4 标准）
 */
import { computed, ref, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD6Adjustment } from '../composables/useD6Adjustment'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import type { ChecklistResponse } from '../composables/useD6FormData'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import GtIndexChip from '../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

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
} = useD6Adjustment({
  allResponses: allResponsesRef,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

// ─── 同步到集中调整登记 ─────────────────────────────────────────────
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'D6',
  itemId: 'D6-4-rows',
  buildLineItems: () => rows.value.map((r) => ({
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: rows.value.find((r) => r.description)?.description || 'D6 合同资产调整',
    adjustmentType: rows.value.length > 0 && rows.value.every((r) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
refreshStatus()

// ─── 导入导出（参照 D4-4） ────────────────────────────────────────────
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-4',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
}

// ─── 选中行（推送 A13） ──────────────────────────────────────────────
const selectedRows = ref<any[]>([])

function handleSelectionChange(selection: any[]) {
  selectedRows.value = selection
}

function handlePushToA13() {
  const ids = selectedRows.value.map((r: any) => r.rowId)
  if (ids.length === 0) return
  pushToA13(ids)
}

// ─── 分类选项（对齐 D4） ─────────────────────────────────────────────
const categoryOptions = [
  { label: '账项调整', value: '账项调整' },
  { label: '报表调整', value: '报表调整' },
  { label: '其他', value: '其他' },
]

// ─── 审计说明/结论（computed getter/setter 对齐 D4 模式） ────────────
const auditNote = computed({
  get: () => allResponsesRef.value.get('D6-4-note')?.remark || '',
  set: (val: string) => {
    allResponsesRef.value.set('D6-4-note', { item_id: 'D6-4-note', conclusion: null, remark: val } as any)
    props.debouncedSave('D6-4-note', { remark: val })
  },
})
const auditConclusion = computed({
  get: () => allResponsesRef.value.get('D6-4-conclusion')?.remark || '',
  set: (val: string) => {
    allResponsesRef.value.set('D6-4-conclusion', { item_id: 'D6-4-conclusion', conclusion: null, remark: val } as any)
    props.debouncedSave('D6-4-conclusion', { remark: val })
  },
})

// ─── AI 辅助（真实接入） ─────────────────────────────────────────────
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

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function generateNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const ctx = rows.value.map(r =>
      `${r.description || '调整'}: ${r.accountName} 借${fmtAmount(r.debitAmount)}/贷${fmtAmount(r.creditAmount)} [${r.category}]`
    ).join('\n') || '（暂无调整分录）'
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'adj-note', existingContent: auditNote.value,
      context: { task: '合同资产调整分录审计说明', entries: ctx },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
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
    const ctx = `审计说明：${auditNote.value || '（未填写）'}\n借贷${isBalanced.value ? '平衡' : '不平衡差异' + fmtAmount(balanceDiff.value)}\n分录${rows.value.length}笔`
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'adj-conclusion', existingContent: auditConclusion.value,
      context: { task: '合同资产调整分录审计结论', summary: ctx },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    auditConclusion.value = text
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

// ─── 金额格式化 ───────────────────────────────────────────────────────
function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d6-tab-adjustment { padding: 12px; }
.d6-tab-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-tab-adjustment :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.balance-indicator {
  display: flex; align-items: center; gap: 16px;
  padding: 8px 12px; background: #f5f7fa; border-radius: 4px; margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
}
.balance-item { color: #606266; }
.balance-item strong { color: #303133; }
.empty-hint { text-align: center; color: #909399; padding: 24px; font-size: var(--wp-font-size, 13px); }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.opinion-section-label { font-size: 14px; font-weight: 500; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
</style>
