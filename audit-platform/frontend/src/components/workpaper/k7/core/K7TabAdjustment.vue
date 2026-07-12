<template>
  <div class="k7-tab-adjustment">
    <!-- ═══ Section标题 + 导入导出 + 复核 ═══ -->
    <div class="section-header">
      <h3>K7-3 调整分录汇总</h3>
      <div class="header-actions">
        <el-button size="small" type="success" :disabled="isReadonly || !isBalanced" @click="handleSaveWriteback">
          保存&amp;回写
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleIECommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog?.('K7-3-adjustment')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>调整分录（AJE/RJE）影响审定表K7-1审定数。<strong>借贷必须平衡</strong>（Σ借方 === Σ贷方）。保存后自动发布 'adjustment:created' 事件通知A13，并双向同步K7-1审定表。</p>
    </div>

    <!-- ═══ 借贷不平衡警告 ═══ -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" show-icon style="margin-bottom:8px">
      <template #title>
        ⚠️ 借贷不平衡：借方合计 {{ fmtAmt(totalDebits) }} ≠ 贷方合计 {{ fmtAmt(totalCredits) }}，差额 {{ fmtAmt(Math.abs(balanceDiff)) }}
      </template>
    </el-alert>

    <!-- ═══ 工具栏 ═══ -->
    <div class="k7-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增</el-button>
      <span class="entry-count">共 {{ entries.length }} 条分录</span>
    </div>

    <!-- ═══ 调整分录表格 ═══ -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width:100%;font-size:13px"
      max-height="520"
      :row-class-name="tableRowClassName"
    >
      <el-table-column prop="seq" label="序号" width="56" align="center" />

      <el-table-column label="调整事项说明" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" placeholder="事项说明" @change="(v: string) => updateCell(row.id, 'summary', v)" />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类别" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.id, 'entryType', v)">
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
          <el-tag v-else :type="row.entryType === 'AJE' ? 'danger' : 'warning'" size="small">{{ row.entryType }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="报表项目" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" placeholder="递延收益" @change="(v: string) => updateCell(row.id, 'reportItem', v)" />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateCell(row.id, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="附注项目" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" placeholder="附注项目" @change="(v: string) => updateCell(row.id, 'noteItem', v)" />
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

      <el-table-column label="索引" width="80">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="" @change="(v: string) => updateCell(row.id, 'indexRef', v)" />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.id, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">🗑️</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行 ═══ -->
    <div class="k7-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmtAmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmtAmt(totalCredits) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">✗ 不平衡 | 差额：{{ fmtAmt(Math.abs(balanceDiff)) }}</span>
    </div>

    <!-- 隐藏file input for import -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileSelected" />

    <!-- ═══ 编制提示 ═══ -->
    <details class="k7-details-tip">
      <summary>📋 编制提示</summary>
      <div class="k7-guide-content">
        <p>1. 调整分录(AJE)用于更正被审计单位财务报表中的错报；重分类分录(RJE)用于分析性归类调整。</p>
        <p>2. 借贷必须平衡后方可保存回写。点击"保存&amp;回写"将汇总AJE/RJE数据回写K7-1审定表。</p>
        <p>3. 保存后自动发布 adjustment:created 事件联动 A13 错报汇总底稿。</p>
        <p>4. 递延收益科目代码 2401（<strong>负债类</strong>，贷方增加/借方减少）。</p>
        <p>5. 负债类AJE方向：借方记录=减少负债；贷方记录=增加负债。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabAdjustment.vue — K7-3 调整分录汇总
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.5
 * Requirements: 6.2
 *
 * 功能：
 * - 标准借贷平衡表：调整事项说明/类别/报表项目/科目名称/附注项目/借方/贷方/索引/备注
 * - 借贷平衡校验（Σ借方 === Σ贷方，不平衡红色提示）
 * - 保存时 publish EventBus 'adjustment:created' → A13
 * - 双向同步K7-1（AJE/RJE汇总写入allResponses）
 * - 导入导出（useK7ImportExport sheetCode='K7-3'）
 * - 动态行增删（ElMessageBox.prompt输入事项说明确认后创建）
 */
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useK7ImportExport } from '@/components/workpaper/composables/useK7ImportExport'
import type { Ref } from 'vue'

const K7_ACCOUNT_CODE = '2401'
const ITEM_PREFIX = 'K7-3-adj'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包顶层 ref → 子组件收到纯 Map；重新包成 ref 供内部逻辑使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ═══ 导入导出 ═══
const { exportTemplate, exportData, importData } = useK7ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K7-3',
})

const fileInputRef = ref<HTMLInputElement | null>(null)

// ═══ 数据模型 ═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  summary: string
  reportItem: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
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
onMounted(() => {
  loadFromResponses()
})

function loadFromResponses(): void {
  const saved = allResponsesRef.value.get(`${ITEM_PREFIX}-entries`)
  const raw = saved?.remark ?? saved?.value ?? null
  if (!raw) { entries.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) {
      entries.value = parsed.map((e: any, idx: number) => ({
        id: e.id || `entry-${++nextId}`,
        seq: idx + 1,
        entryType: e.entryType || 'AJE',
        summary: e.summary || e.description || '',
        reportItem: e.reportItem || '递延收益',
        accountName: e.accountName || '',
        noteItem: e.noteItem || '',
        debitAmount: e.debitAmount || 0,
        creditAmount: e.creditAmount || 0,
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
      inputPlaceholder: '如：调整递延收益—XX补助分摊',
    })
    if (value?.trim()) {
      const entry: AdjustmentEntry = {
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        entryType: 'AJE',
        summary: value.trim(),
        reportItem: '递延收益',
        accountName: '递延收益',
        noteItem: '',
        debitAmount: 0,
        creditAmount: 0,
        indexRef: '',
        remark: '',
      }
      entries.value.push(entry)
      persistEntries()
    }
  } catch { /* cancelled */ }
}

async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    entries.value = entries.value.filter(e => e.id !== id)
    reSequence()
    persistEntries()
  } catch { /* cancelled */ }
}

function updateCell(id: string, field: keyof AdjustmentEntry, value: any): void {
  const entry = entries.value.find(e => e.id === id)
  if (entry) {
    ;(entry as any)[field] = value
    persistEntries()
  }
}

function reSequence(): void {
  entries.value.forEach((e, i) => { e.seq = i + 1 })
}

// ═══ 持久化 ═══
function persistEntries(): void {
  emit('save', `${ITEM_PREFIX}-entries`, { remark: JSON.stringify(entries.value) })
}

// ═══ 保存回写K7-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 负债类2401: AJE对科目影响 = 贷方(增加负债) - 借方(减少负债)
  const ajeTotal = entries.value
    .filter(e => e.entryType === 'AJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)
  const rjeTotal = entries.value
    .filter(e => e.entryType === 'RJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)

  // 双向同步到allResponses供K7-1审定表读取
  allResponsesRef.value.set('K7-1-aje-total', { item_id: 'K7-1-aje-total', remark: String(ajeTotal) })
  allResponsesRef.value.set('K7-1-rje-total', { item_id: 'K7-1-rje-total', remark: String(rjeTotal) })

  // 持久化
  emit('save', 'K7-1-aje-total', { remark: String(ajeTotal) })
  emit('save', 'K7-1-rje-total', { remark: String(rjeTotal) })
  persistEntries()

  // EventBus publish adjustment:created → A13
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K7',
      accountCode: K7_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      entryCount: entries.value.length,
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K7-1审定表，已通知A13')
}

// ═══ 导入导出 ═══
function handleIECommand(cmd: string): void {
  if (cmd === 'template') {
    exportTemplate()
  } else if (cmd === 'export') {
    exportData()
  } else if (cmd === 'import') {
    fileInputRef.value?.click()
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = '' // reset

  const result = await importData(file)
  if (result && result.rowCount > 0) {
    ElMessage.info('导入完成，请刷新查看最新数据')
  }
}

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  if (row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.k7-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.k7-adj-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.entry-count { font-size: 12px; color: #909399; }

/* 合计行 */
.k7-adj-footer { display: flex; align-items: center; gap: 20px; margin-top: 10px; padding: 10px 14px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.k7-adj-footer.balance-fail { background: #fef0f0; border: 1px solid #fbc4c4; }
.footer-label { font-weight: 600; color: #303133; }
.footer-debit { color: #606266; }
.footer-credit { color: #606266; }
.footer-status.ok { color: #67c23a; font-weight: 600; }
.footer-status.err { color: #f56c6c; font-weight: 600; }
:deep(.rje-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k7-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
.k7-guide-content p { margin: 4px 0; line-height: 1.7; }
</style>
