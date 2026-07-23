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
      <el-table-column label="类别" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.category" size="small" @change="(v: string) => updateCell(row.id, 'category', v)">
            <el-option value="报表调整" label="报表调整" />
            <el-option value="账项调整" label="账项调整" />
            <el-option value="其他" label="其他" />
          </el-select>
          <el-tag v-else :type="row.category === '报表调整' ? 'warning' : row.category === '其他' ? 'info' : 'danger'" size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" @change="(v: string) => updateCell(row.id, 'reportItem', v)" />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateCell(row.id, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" @change="(v: string) => updateCell(row.id, 'noteItem', v)" />
          <span v-else>{{ row.noteItem || '-' }}</span>
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
      <el-table-column label="索引" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" @change="(v: string) => updateCell(row.id, 'indexRef', v)" />
          <span v-else>{{ row.indexRef || '-' }}</span>
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
        <li>类别（对齐源模板）：<strong>账项调整</strong>（更正错报，计入 K8-1 审定表账项调整列）/<strong>报表调整</strong>（重分类，计入重分类调整列）/<strong>其他</strong></li>
        <li>损益类6601销售费用：借方=增加费用，贷方=冲减费用</li>
        <li>填写报表项目/科目名称/附注项目/索引，便于追溯与附注联动</li>
        <li>借贷必须平衡后方可保存回写</li>
        <li>保存后自动发布 adjustment:created 事件联动A13，并同步 K8-1 审定表账项/重分类调整</li>
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

// ═══ 数据模型（对齐源模板 K8-3：调整事项说明/类别/报表项目/科目名称/附注项目/借方/贷方/索引/备注）═══
type AdjCategory = '报表调整' | '账项调整' | '其他'

interface AdjustmentEntry {
  id: string
  seq: number
  /** 类别（对齐源模板：报表调整/账项调整/其他） */
  category: AdjCategory
  /** 调整事项说明 */
  summary: string
  /** 报表项目 */
  reportItem: string
  /** 科目名称 */
  accountName: string
  /** 附注项目 */
  noteItem: string
  debitAmount: number
  creditAmount: number
  /** 索引 */
  indexRef: string
  remark: string
}

/** 类别 → K8-1 审定表 AJE/RJE 桶映射：账项调整/其他→AJE，报表调整→RJE(重分类) */
function categoryToBucket(cat: AdjCategory): 'aje' | 'rje' {
  return cat === '报表调整' ? 'rje' : 'aje'
}

/** legacy entryType(AJE/RJE) → category 兼容迁移 */
function legacyTypeToCategory(t: string): AdjCategory {
  if (t === 'RJE') return '报表调整'
  if (t === 'AJE') return '账项调整'
  return '账项调整'
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
        // 兼容旧数据：无 category 时从 entryType 迁移
        category: (e.category as AdjCategory) || legacyTypeToCategory(e.entryType || 'AJE'),
        summary: e.summary || '',
        reportItem: e.reportItem || '销售费用',
        accountName: e.accountName || '销售费用',
        noteItem: e.noteItem || '',
        debitAmount: Number(e.debitAmount) || 0,
        creditAmount: Number(e.creditAmount) || 0,
        indexRef: e.indexRef || '',
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
        category: '账项调整',
        summary: value.trim(),
        reportItem: '销售费用',
        accountName: '销售费用',
        noteItem: '',
        debitAmount: 0,
        creditAmount: 0,
        indexRef: '',
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

  // 损益类6601: 对科目影响 = 借方(增加费用) - 贷方(冲减费用)
  // 类别→桶：账项调整/其他→AJE(账项调整)，报表调整→RJE(重分类调整)
  const ajeTotal = entries.value
    .filter(e => categoryToBucket(e.category) === 'aje')
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)
  const rjeTotal = entries.value
    .filter(e => categoryToBucket(e.category) === 'rje')
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
    // 推送错报至 A13（对齐 K10-3；crossWpEventBridge 白名单事件）
    eventBus.emit('a13:push-misstatement' as any, {
      wpCode: 'K8',
      accountCode: K8_ACCOUNT_CODE,
      ajeTotal,
      rjeTotal,
      entries: entries.value.map(e => ({
        summary: e.summary,
        category: e.category,
        reportItem: e.reportItem,
        accountName: e.accountName,
        debit: e.debitAmount,
        credit: e.creditAmount,
        indexRef: e.indexRef,
      })),
      timestamp: Date.now(),
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K8-1审定表，已通知A13')
}

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  return categoryToBucket(row.category) === 'rje' ? 'rje-row' : ''
}
</script>

<style scoped>
.k8-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.adj-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.entry-count { font-size: 12px; color: #909399; }
.adj-footer { display: flex; align-items: center; gap: 20px; margin-top: 10px; padding: 10px 14px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.adj-footer.balance-fail { background: #fef0f0; border: 1px solid #fbc4c4; }
.footer-label { font-weight: 600; color: #303133; }
.footer-debit { color: #606266; }
.footer-credit { color: #606266; }
.footer-status.ok { color: #67c23a; font-weight: 600; }
.footer-status.err { color: #f56c6c; font-weight: 600; }
:deep(.rje-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
