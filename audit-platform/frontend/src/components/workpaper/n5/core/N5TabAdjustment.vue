<template>
  <div class="n5-tab-adjustment">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>调整分录汇总 N5-3</span>
        <el-tag size="small" type="info">借贷平衡</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增分录</el-button>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
        <el-button size="small" type="primary" plain :loading="centralSyncing" :disabled="isReadonly || !isBalanced || entries.length === 0" @click="syncToCentral" title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅">同步到集中登记</el-button>
        <el-tag v-if="centralStatus?.review_status" size="small" :type="centralStatus.review_status==='approved'?'success':(centralStatus.review_status==='rejected'?'danger':'info')" :title="centralStatus.rejection_reason||''">集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status]||centralStatus.review_status }}</el-tag>
      </div>
    </div>

    <!-- ═══ 借贷平衡校验 ═══ -->
    <div class="balance-check" :class="isBalanced ? 'balanced' : 'unbalanced'">
      <span class="balance-label">借贷平衡校验：</span>
      <span class="balance-debit">借方合计 {{ fmtAmount(totalDebit) }}</span>
      <span class="balance-sep">|</span>
      <span class="balance-credit">贷方合计 {{ fmtAmount(totalCredit) }}</span>
      <span class="balance-sep">|</span>
      <span class="balance-result">{{ isBalanced ? '✓ 平衡' : '⚠ 差额 ' + fmtAmount(balanceDiff) }}</span>
    </div>

    <!-- ═══ AJE 调整分录 ═══ -->
    <el-card shadow="never" class="entry-card">
      <template #header>
        <div class="entry-header">
          <span>AJE 审计调整分录</span>
          <el-tag size="small" type="danger">{{ ajeEntries.length }} 笔</el-tag>
        </div>
      </template>
      <el-table :data="ajeEntries" border size="small" v-if="ajeEntries.length > 0">
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="accountCode" label="科目编码" width="100" />
        <el-table-column prop="accountName" label="科目名称" min-width="160" />
        <el-table-column prop="debit" label="借方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleEntryChange(row)" />
            <span v-else>{{ fmtAmount(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="贷方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleEntryChange(row)" />
            <span v-else>{{ fmtAmount(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="摘要" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="调整说明..." @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDeleteEntry(row, 'aje')">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无AJE分录" :image-size="40" />
    </el-card>

    <!-- ═══ RJE 重分类分录 ═══ -->
    <el-card shadow="never" class="entry-card">
      <template #header>
        <div class="entry-header">
          <span>RJE 重分类调整分录</span>
          <el-tag size="small" type="warning">{{ rjeEntries.length }} 笔</el-tag>
        </div>
      </template>
      <el-table :data="rjeEntries" border size="small" v-if="rjeEntries.length > 0">
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="accountCode" label="科目编码" width="100" />
        <el-table-column prop="accountName" label="科目名称" min-width="160" />
        <el-table-column prop="debit" label="借方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleEntryChange(row)" />
            <span v-else>{{ fmtAmount(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="贷方" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleEntryChange(row)" />
            <span v-else>{{ fmtAmount(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="摘要" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="重分类说明..." @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDeleteEntry(row, 'rje')">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无RJE分录" :image-size="40" />
    </el-card>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header><span class="notes-title">审计说明与结论</span></template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请输入..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="请输入..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>每笔分录必须<strong>借贷平衡</strong>（借方合计 = 贷方合计）</li>
        <li>AJE影响审定数（未审+AJE=调整后），RJE仅做重分类（不影响合计）</li>
        <li>新增分录后自动发布EventBus 'adjustment:created' 事件同步N5-1审定表</li>
        <li>所得税费用调整通常涉及：借6801所得税费用 / 贷2221应交所得税 / 借/贷递延所得税资产(1811)/负债(2901)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabAdjustment — 调整分录汇总 N5-3
 * 借贷平衡+EventBus+双向同步N5-1
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.4
 * Requirements: 9.3
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { eventBus } from '@/utils/eventBus'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((s: string) => void) | undefined>('openReviewDialog', undefined)
const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })

// ─── Types ───────────────────────────────────────────────────────────────────

interface JournalEntry {
  id: string; seq: number; type: 'aje' | 'rje'
  accountCode: string; accountName: string
  debit: number; credit: number; description: string
}

const entries = ref<JournalEntry[]>([])
const auditNotes = ref('')
const auditConclusion = ref('')

const ajeEntries = computed(() => entries.value.filter(e => e.type === 'aje'))
const rjeEntries = computed(() => entries.value.filter(e => e.type === 'rje'))

// ─── 借贷平衡 ────────────────────────────────────────────────────────────────

const totalDebit = computed(() => entries.value.reduce((s, e) => s + (e.debit || 0), 0))
const totalCredit = computed(() => entries.value.reduce((s, e) => s + (e.credit || 0), 0))
const balanceDiff = computed(() => totalDebit.value - totalCredit.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.01)

// ─── 集中登记同步 ────────────────────────────────────────────────────────────

const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: auditYear,
  wpId: () => props.wpId,
  wpCode: 'N5',
  itemId: 'N5-3-entries',
  buildLineItems: () => entries.value.map((e: any) => ({
    account_name: e.accountName,
    standard_account_code: e.accountCode || undefined,
    debit_amount: e.debit,
    credit_amount: e.credit,
  })),
  buildMeta: () => ({
    description: entries.value.find((e: any) => e.description)?.description || 'N5 所得税费用调整',
    adjustmentType: 'aje',
  }),
})

// ─── 数据加载 ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  const saved = formData.getField('3', 'entries')
  if (saved && Array.isArray(saved)) entries.value = saved
  auditNotes.value = formData.getField('3', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('3', 'audit-conclusion') ?? ''
  refreshStatus()
})

// ─── 新增分录 ────────────────────────────────────────────────────────────────

async function handleAddEntry() {
  try {
    const { value: entryType } = await ElMessageBox.confirm(
      '请选择分录类型',
      '新增调整分录',
      { confirmButtonText: 'AJE审计调整', cancelButtonText: 'RJE重分类', distinguishCancelAndClose: true },
    ).then(() => ({ value: 'aje' as const })).catch((action: string) => {
      if (action === 'cancel') return { value: 'rje' as const }
      throw new Error('closed')
    })

    const newEntry: JournalEntry = {
      id: `${entryType}-${Date.now()}`,
      seq: entries.value.filter(e => e.type === entryType).length + 1,
      type: entryType,
      accountCode: '6801',
      accountName: '所得税费用',
      debit: 0, credit: 0, description: '',
    }
    entries.value.push(newEntry)
    await saveEntries()

    // EventBus发布
    eventBus.emit('adjustment:created' as any, {
      wpCode: 'N5', entryType, entryId: newEntry.id, timestamp: Date.now(),
    })
    ElMessage.success(`已新增${entryType.toUpperCase()}分录`)
  } catch { /* closed */ }
}

async function handleDeleteEntry(row: JournalEntry, _type: string) {
  entries.value = entries.value.filter(e => e.id !== row.id)
  await saveEntries()
}

async function handleEntryChange(_row: JournalEntry) {
  await saveEntries()
}

async function saveEntries() {
  await formData.setField('3', 'entries', entries.value)
  // 汇总6801 AJE/RJE回填N5-1 + 发布A13事件
  const ajeNet = ajeEntries.value
    .filter((e: any) => e.accountCode === '6801' || e.accountName === '所得税费用')
    .reduce((s: number, e: any) => s + (e.debit || 0) - (e.credit || 0), 0)
  const rjeNet = rjeEntries.value
    .filter((e: any) => e.accountCode === '6801' || e.accountName === '所得税费用')
    .reduce((s: number, e: any) => s + (e.debit || 0) - (e.credit || 0), 0)
  const currentRow = formData.getField('1', 'current-row')
  if (currentRow && typeof currentRow === 'object') {
    await formData.setField('1', 'current-row', { ...currentRow, aje: ajeNet, rje: rjeNet })
  }
  // 发布调整分录更新→A13审计差异汇总
  eventBus.emit('adjustment:entries-updated' as any, {
    wpCode: 'N5', accountCode: '6801',
    ajeCount: ajeEntries.value.length, rjeCount: rjeEntries.value.length,
    ajeNet, rjeNet,
    totalDebit: totalDebit.value, totalCredit: totalCredit.value,
    timestamp: Date.now(),
  })
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function saveNotes() { await formData.setField('3', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('3', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-adjustment',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog ? openReviewDialog('N5-3-调整分录') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n5-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.balance-check { display: flex; align-items: center; gap: 12px; padding: 10px 16px; margin-bottom: 16px; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.balanced { background: #e8f5e9; border: 1px solid #a5d6a7; }
.unbalanced { background: #fef0f0; border: 1px solid #fab6b6; }
.balance-label { font-weight: 500; color: #303133; }
.balance-debit { color: #e6a23c; font-weight: 500; }
.balance-credit { color: #409eff; font-weight: 500; }
.balance-sep { color: #c0c4cc; }
.balance-result { font-weight: 600; }
.balanced .balance-result { color: #43a047; }
.unbalanced .balance-result { color: #f56c6c; }

.entry-card { margin-bottom: 16px; }
.entry-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }

.audit-notes-card { margin-bottom: 16px; }
.notes-title { font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
