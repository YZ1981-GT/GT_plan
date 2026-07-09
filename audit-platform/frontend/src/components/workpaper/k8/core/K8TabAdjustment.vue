<template>
  <div class="k8-tab-adjustment">
    <!-- ═══ Section标题 + 保存回写 + 复核 ═══ -->
    <div class="section-header">
      <h3>K8-3 调整分录汇总</h3>
      <div class="header-actions">
        <GtIndexChip value="A13" :context-project-id="props.projectId" />
        <el-button size="small" type="success" :disabled="isReadonly || !isBalanced" @click="handleSaveWriteback">
          保存&amp;回写
        </el-button>
        <el-button size="small" @click="openReviewDialog?.('K8-3-adjustment')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>调整分录（AJE/RJE）影响审定表K8-1审定数。<strong>借贷必须平衡</strong>（Σ借方 === Σ贷方）。保存后自动发布 'adjustment:created' 事件通知A13，并双向同步K8-1审定表。损益类6601：借方=增加费用，贷方=冲减费用。</p>
    </div>

    <!-- ═══ 借贷不平衡警告 ═══ -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" show-icon style="margin-bottom:8px">
      <template #title>
        ⚠️ 借贷不平衡：借方合计 {{ fmtAmt(totalDebits) }} ≠ 贷方合计 {{ fmtAmt(totalCredits) }}，差额 {{ fmtAmt(Math.abs(balanceDiff)) }}
      </template>
    </el-alert>

    <!-- ═══ 工具栏 ═══ -->
    <div class="adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增</el-button>
      <span class="entry-count">共 {{ entries.length }} 条分录</span>
    </div>

    <!-- ═══ 调整分录表格 ═══ -->
    <el-table :data="entries" border size="small" style="width:100%;font-size:13px" max-height="480" :row-class-name="tableRowClassName">
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column label="摘要" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" placeholder="调整事项" @change="(v: string) => updateCell(row.id, 'summary', v)" />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="85">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.id, 'entryType', v)">
            <el-option value="AJE" label="AJE" /><el-option value="RJE" label="RJE" />
          </el-select>
          <el-tag v-else :type="row.entryType === 'AJE' ? 'danger' : 'warning'" size="small">{{ row.entryType }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="科目" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateCell(row.id, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.id, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">🗑️</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行 ═══ -->
    <div class="adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmtAmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmtAmt(totalCredits) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">✗ 不平衡 | 差额：{{ fmtAmt(Math.abs(balanceDiff)) }}</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>AJE：更正被审计单位财务报表中的错报</li>
        <li>RJE：分析性归类调整（不影响报表净额）</li>
        <li>损益类6601销售费用：借方=增加费用，贷方=冲减费用</li>
        <li>借贷必须平衡后方可保存回写</li>
        <li>保存后自动发布 adjustment:created 事件联动A13</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabAdjustment.vue — K8-3 调整分录汇总
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.6
 * Requirements: 8.2
 *
 * 功能：
 * - 标准借贷平衡表：序号/摘要/科目/借方/贷方/备注
 * - 借贷平衡校验（Σ借方===Σ贷方）
 * - publish EventBus 'adjustment:created' → A13
 * - 双向同步K8-1审定表
 * - 动态行增删（ElMessageBox.prompt确认）
 */
import { ref, computed, inject, onMounted, defineAsyncComponent } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import type { Ref } from 'vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const K8_ACCOUNT_CODE = '6601'
const ITEM_PREFIX = 'K8-3-adj'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheet: string): void
}>()

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ═══ 数据模型 ═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  summary: string
  accountName: string
  debitAmount: number
  creditAmount: number
  remark: string
}

const entries = ref<AdjustmentEntry[]>([])
let nextId = 1

// ═══ 计算属性：借贷平衡 ═══
const totalDebits = computed(() => entries.value.reduce((sum, e) => sum + (e.debitAmount || 0), 0))
const totalCredits = computed(() => entries.value.reduce((sum, e) => sum + (e.creditAmount || 0), 0))
const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.005)

// ═══ 初始化加载 ═══
onMounted(() => { loadFromResponses() })

function loadFromResponses(): void {
  const saved = props.allResponses.get(`${ITEM_PREFIX}-entries`)
  const raw = saved?.remark ?? (typeof saved === 'string' ? saved : null)
  if (!raw) { entries.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) {
      entries.value = parsed.map((e: any, idx: number) => ({
        id: e.id || `entry-${++nextId}`,
        seq: idx + 1,
        entryType: e.entryType || 'AJE',
        summary: e.summary || '',
        accountName: e.accountName || '销售费用',
        debitAmount: Number(e.debitAmount) || 0,
        creditAmount: Number(e.creditAmount) || 0,
        remark: e.remark || '',
      }))
      nextId = entries.value.length + 1
    }
  } catch { /* ignore parse error */ }
}

// ═══ 行操作 ═══
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入调整事项说明', '新增调整分录', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：调增销售费用—XX广告费',
    })
    if (value?.trim()) {
      entries.value.push({
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        entryType: 'AJE',
        summary: value.trim(),
        accountName: '销售费用',
        debitAmount: 0,
        creditAmount: 0,
        remark: '',
      })
      persistEntries()
    }
  } catch { /* cancelled */ }
}

async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', { type: 'warning' })
    entries.value = entries.value.filter(e => e.id !== id)
    entries.value.forEach((e, i) => { e.seq = i + 1 })
    persistEntries()
  } catch { /* cancelled */ }
}

function updateCell(id: string, field: string, value: any): void {
  const entry = entries.value.find(e => e.id === id)
  if (entry) {
    ;(entry as any)[field] = value
    persistEntries()
  }
}

// ═══ 持久化 ═══
function persistEntries(): void {
  emit('save', `${ITEM_PREFIX}-entries`, { remark: JSON.stringify(entries.value) })
}

// ═══ 保存回写K8-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 损益类6601: AJE对科目影响 = 借方(增加费用) - 贷方(冲减费用)
  const ajeTotal = entries.value
    .filter(e => e.entryType === 'AJE')
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)
  const rjeTotal = entries.value
    .filter(e => e.entryType === 'RJE')
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)

  // 双向同步到allResponses供K8-1审定表读取
  emit('save', 'K8-1-aje-total', { remark: String(ajeTotal) })
  emit('save', 'K8-1-rje-total', { remark: String(rjeTotal) })
  persistEntries()

  // EventBus publish adjustment:created → A13 + 附注subscribe
  // 按每条分录分别发布（AJE/RJE各一次），也发一次汇总
  try {
    // 汇总事件（供A13和附注刷新）
    eventBus.emit('adjustment:created', {
      entryType: 'AJE' as const,
      accountCode: K8_ACCOUNT_CODE,
      amount: ajeTotal,
      wpCode: 'K8',
      timestamp: Date.now(),
    })
    if (rjeTotal !== 0) {
      eventBus.emit('adjustment:created', {
        entryType: 'RJE' as const,
        accountCode: K8_ACCOUNT_CODE,
        amount: rjeTotal,
        wpCode: 'K8',
        timestamp: Date.now(),
      })
    }
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K8-1审定表，已通知A13')
}

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  return row.entryType === 'RJE' ? 'rje-row' : ''
}
</script>

<style scoped>
.k8-tab-adjustment { padding: 12px; font-size: 13px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6; }
.adj-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.entry-count { font-size: 12px; color: #909399; }
.adj-footer { display: flex; align-items: center; gap: 20px; margin-top: 10px; padding: 10px 14px; background: #f5f7fa; border-radius: 6px; font-size: 13px; }
.adj-footer.balance-fail { background: #fef0f0; border: 1px solid #fbc4c4; }
.footer-label { font-weight: 600; color: #303133; }
.footer-debit { color: #606266; }
.footer-credit { color: #606266; }
.footer-status.ok { color: #67c23a; font-weight: 600; }
.footer-status.err { color: #f56c6c; font-weight: 600; }
:deep(.rje-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: 13px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
