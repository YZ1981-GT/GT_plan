<template>
  <div class="n4-tab-adjustment">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate-sheet', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">N4-3 调整分录汇总</h3>
        <el-tag type="success" effect="dark" size="small" class="account-badge">
          科目6403·借方增加=调增费用
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
        <el-button
          type="primary"
          size="small"
          :disabled="isReadonly"
          @click="handleAddEntry"
        >
          + 新增分录
        </el-button>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="N4-1" :context-project-id="projectId" />
      <GtIndexChip value="N2-1" :context-project-id="projectId" />
      <GtIndexChip value="A13" :context-project-id="projectId" />
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>税金及附加（6403）调整分录方向说明：</strong>
        税金及附加为损益类借方科目 —
        <strong>借方增加 = 调增费用</strong>（如补提城建税/印花税/房产税等），
        <strong>贷方增加 = 调减费用</strong>（如冲回多提税费）。
        对方科目通常为2221应交税费。
      </div>
    </div>

    <!-- ═══ 借贷平衡校验 ═══ -->
    <div class="balance-check" :class="isBalanced ? 'balanced' : 'unbalanced'">
      <span class="balance-label">借贷平衡校验：</span>
      <span class="balance-debit">借方合计 {{ fmtAmount(totalDebit) }}</span>
      <span class="balance-sep">|</span>
      <span class="balance-credit">贷方合计 {{ fmtAmount(totalCredit) }}</span>
      <span class="balance-sep">|</span>
      <span class="balance-result">
        {{ isBalanced ? '✓ 平衡' : `⚠ 不平衡 (差异: ${fmtAmount(balanceDiff)})` }}
      </span>
    </div>

    <!-- ═══ AJE 审计调整分录 ═══ -->
    <el-card shadow="never" class="entry-card">
      <template #header>
        <div class="entry-header">
          <span>AJE 审计调整分录</span>
          <el-tag size="small" type="danger">{{ ajeEntries.length }} 笔</el-tag>
        </div>
      </template>
      <el-table :data="ajeEntries" border size="small" v-if="ajeEntries.length > 0" class="entry-table">
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="accountCode" label="科目编码" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountName" label="科目名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountName" size="small" @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.accountName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="摘要" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="调整说明..." @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
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
      <el-table :data="rjeEntries" border size="small" v-if="rjeEntries.length > 0" class="entry-table">
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="accountCode" label="科目编码" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountName" label="科目名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountName" size="small" @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.accountName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="摘要" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" placeholder="重分类说明..." @change="() => handleEntryChange(row)" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
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
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请输入税金及附加调整事项的说明..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="请输入审计结论..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>每笔分录必须<strong>借贷平衡</strong>（借方合计 = 贷方合计）</li>
        <li>AJE影响审定数（未审+AJE=调整后），RJE仅做重分类（不影响合计）</li>
        <li>保存后自动发布EventBus <code>adjustment:created</code> 事件同步N4-1审定表及A13汇总</li>
        <li>税金及附加调整常见场景：<strong>借6403税金及附加 / 贷2221应交税费</strong>（补提城建税/印花税/房产税等）</li>
        <li>冲回多提税费：<strong>借2221应交税费 / 贷6403税金及附加</strong></li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N4TabAdjustment — 调整分录汇总 N4-3
 * 借贷平衡+EventBus+双向同步N4-1
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/ Task 4.4
 * Requirements: 5.1
 *
 * 功能要素：
 * 1. 调整分录表：调整类型(AJE/RJE) | 科目编码 | 科目名称 | 摘要 | 借方 | 贷方
 * 2. 借贷平衡校验（sum of debits == sum of credits）
 * 3. 动态行新增/删除
 * 4. EventBus publish 'adjustment:created' → A13
 * 5. 双向同步N4-1的AJE/RJE列
 * 6. 平衡状态指示：Green "✓ 平衡" or red "⚠ 不平衡 (差异: xxx)"
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN4FormData } from '../../composables/useN4FormData'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<((s: string) => void) | undefined>('openReviewDialog', undefined)
const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const formData = useN4FormData({ wpId: wpIdRef, projectId: projectIdRef })

// ─── Types ───────────────────────────────────────────────────────────────────

interface JournalEntry {
  id: string
  seq: number
  type: 'aje' | 'rje'
  accountCode: string
  accountName: string
  debit: number
  credit: number
  description: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const entries = ref<JournalEntry[]>([])
const auditNotes = ref('')
const auditConclusion = ref('')
const isSaving = ref(false)

// ─── Computed ────────────────────────────────────────────────────────────────

const ajeEntries = computed(() => entries.value.filter(e => e.type === 'aje'))
const rjeEntries = computed(() => entries.value.filter(e => e.type === 'rje'))

// 借贷平衡
const totalDebit = computed(() => entries.value.reduce((s, e) => s + (e.debit || 0), 0))
const totalCredit = computed(() => entries.value.reduce((s, e) => s + (e.credit || 0), 0))
const balanceDiff = computed(() => totalDebit.value - totalCredit.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.01)

// ─── 数据加载 ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.selfLoad()
  // 读取已保存的分录
  const saved = formData.getResponse('N4-3-entries')
  if (saved && Array.isArray(saved)) entries.value = saved
  auditNotes.value = formData.getResponse('N4-3-audit-notes') ?? ''
  auditConclusion.value = formData.getResponse('N4-3-audit-conclusion') ?? ''
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
      accountCode: '6403',
      accountName: '税金及附加',
      debit: 0,
      credit: 0,
      description: '',
    }
    entries.value.push(newEntry)
    await saveEntries()
    ElMessage.success(`已新增${entryType.toUpperCase()}分录`)
  } catch { /* closed */ }
}

// ─── 删除分录 ────────────────────────────────────────────────────────────────

async function handleDeleteEntry(row: JournalEntry, _type: string) {
  entries.value = entries.value.filter(e => e.id !== row.id)
  // 重新排序
  const types: ('aje' | 'rje')[] = ['aje', 'rje']
  for (const t of types) {
    entries.value.filter(e => e.type === t).forEach((e, idx) => { e.seq = idx + 1 })
  }
  await saveEntries()
}

// ─── 分录变更 ────────────────────────────────────────────────────────────────

async function handleEntryChange(_row: JournalEntry) {
  await saveEntries()
}

// ─── 保存分录 + EventBus + 双向同步N4-1 ─────────────────────────────────────

async function saveEntries() {
  isSaving.value = true
  try {
    await formData.saveResponse('N4-3-entries', entries.value)

    // 计算AJE/RJE合计供N4-1双向同步
    const ajeDebit = ajeEntries.value.reduce((s, e) => s + (e.debit || 0), 0)
    const ajeCredit = ajeEntries.value.reduce((s, e) => s + (e.credit || 0), 0)
    const rjeDebit = rjeEntries.value.reduce((s, e) => s + (e.debit || 0), 0)
    const rjeCredit = rjeEntries.value.reduce((s, e) => s + (e.credit || 0), 0)

    // 净AJE影响额（6403借方科目：借方增加费用，所以净AJE=AJE借方-AJE贷方）
    const ajeNet = ajeDebit - ajeCredit
    const rjeNet = rjeDebit - rjeCredit

    // 保存AJE/RJE汇总供N4-1审定表引用
    await formData.saveBatch([
      { itemId: 'N4-3-aje-net', value: String(ajeNet) },
      { itemId: 'N4-3-rje-net', value: String(rjeNet) },
    ])

    // EventBus发布 'adjustment:created' → A13
    eventBus.emit('adjustment:created' as any, {
      wpCode: 'N4',
      accountCode: '6403',
      ajeAmount: ajeNet,
      rjeAmount: rjeNet,
      entryCount: entries.value.length,
      isBalanced: isBalanced.value,
      timestamp: Date.now(),
    })
  } catch {
    ElMessage.error('分录保存失败')
  } finally {
    isSaving.value = false
  }
}

// ─── 审计说明/结论保存 ───────────────────────────────────────────────────────

async function saveNotes() {
  await formData.saveResponse('N4-3-audit-notes', auditNotes.value)
}

async function saveConclusion() {
  await formData.saveResponse('N4-3-audit-conclusion', auditConclusion.value)
}

// ─── 辅助操作 ────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助：正在分析税金及附加调整建议...')
}

function handleReview() {
  openReviewDialog ? openReviewDialog('N4-3-调整分录') : ElMessage.info('复核对话未配置')
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n4-tab-adjustment { padding: 12px; font-size: 13px; }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 10px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { font-size: 15px; font-weight: 600; color: #303133; margin: 0; }
.account-badge { margin-left: 4px; }

.cross-ref-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.cross-refs-label { font-size: 12px; color: #909399; }

.methodology-context { margin-bottom: 16px; padding: 10px 16px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 0 6px 6px 0; }
.methodology-text { font-size: 13px; color: #606266; line-height: 1.6; }

.balance-check { display: flex; align-items: center; gap: 12px; padding: 10px 16px; margin-bottom: 16px; border-radius: 6px; font-size: 13px; }
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
.entry-table { font-size: 13px; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: 13px; }

.audit-notes-card { margin-bottom: 16px; }
.notes-title { font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: 13px; font-weight: 500; color: #606266; margin-bottom: 6px; }

.n4-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.n4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
