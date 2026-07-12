<template>
  <div class="k3-tab-adjustment">
    <!-- Section标题栏 + 复核按钮右对齐 -->
    <div class="section-head">
      <h3 class="sheet-title">K3-3 调整分录汇总</h3>
      <div class="head-actions">
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
        <el-button size="small" @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 借贷不平衡警告 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmtAmt(totalDebits) }} ≠ 贷方合计 {{ fmtAmt(totalCredits) }}，差额 {{ fmtAmt(Math.abs(balanceDiff)) }}
    </el-alert>

    <!-- 工具栏 -->
    <div class="k3-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增</el-button>
      <span class="entry-count">共 {{ entries.length }} 条分录</span>
    </div>

    <!-- 调整分录表格 -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width:100%;font-size:13px"
      max-height="520"
      :row-class-name="tableRowClassName"
    >
      <el-table-column prop="seq" label="序号" width="56" align="center" />

      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.id, 'entryType', v)">
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
          <span v-else>{{ row.entryType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目代码" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountCode" size="small" placeholder="如2241" @change="(v: string) => updateCell(row.id, 'accountCode', v)" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateCell(row.id, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.id, 'summary', v)" />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="编制人" width="80">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.preparedBy" size="small" @change="(v: string) => updateCell(row.id, 'preparedBy', v)" />
          <span v-else>{{ row.preparedBy || '-' }}</span>
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

    <!-- 合计行 -->
    <div class="k3-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmtAmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmtAmt(totalCredits) }}</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">✗ 不平衡 | 差额：{{ fmtAmt(Math.abs(balanceDiff)) }}</span>
    </div>

    <!-- 隐藏file input for import -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileSelected" />

    <!-- 编制提示 -->
    <details class="k3-guide-details">
      <summary>📋 编制提示</summary>
      <div class="k3-guide-content">
        <p>1. 调整分录(AJE)用于更正被审计单位财务报表中的错报；重分类分录(RJE)用于分析性归类调整。</p>
        <p>2. 借贷必须平衡后方可保存回写。点击"保存&amp;回写"将汇总AJE/RJE数据回写K3-1审定表。</p>
        <p>3. 保存后自动发布 adjustment:created 事件联动 A13 错报汇总底稿。</p>
        <p>4. 其他应付款科目代码 2241（<strong>负债类</strong>，贷方增加/借方减少）。</p>
        <p>5. 负债类AJE方向：借方记录=减少负债；贷方记录=增加负债。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabAdjustment.vue — K3-3 调整分录汇总
 *
 * Spec: k3-other-payables Task 4.6
 * Requirements: 8.1-8.2
 *
 * 功能：
 * - 标准借贷平衡表：科目/摘要/借方/贷方+合计行
 * - 借贷平衡校验（合计借=合计贷，不平衡红色提示）
 * - 保存时 publish EventBus 'adjustment:created' → A13
 * - 导入导出（useK3ImportExport sheetCode='K3-3'）
 * - 动态行增删（ElMessageBox.prompt输入摘要确认后创建）
 */
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useK3ImportExport } from '@/components/workpaper/composables/useK3ImportExport'

const K3_ACCOUNT_CODE = '2241'
const ITEM_PREFIX = 'K3-3-adj'

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

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ═══ 导入导出 ═══
const { exportTemplate, exportData, importData } = useK3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K3-3',
})

const fileInputRef = ref<HTMLInputElement | null>(null)

// ═══ 数据模型 ═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  summary: string
  preparedBy: string
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
  const saved = props.allResponses.get(`${ITEM_PREFIX}-entries`)
  if (saved?.value) {
    try {
      const parsed = typeof saved.value === 'string' ? JSON.parse(saved.value) : saved.value
      if (Array.isArray(parsed)) {
        entries.value = parsed.map((e: any, idx: number) => ({
          id: e.id || `entry-${++nextId}`,
          seq: idx + 1,
          entryType: e.entryType || 'AJE',
          accountCode: e.accountCode || '',
          accountName: e.accountName || '',
          debitAmount: e.debitAmount || 0,
          creditAmount: e.creditAmount || 0,
          summary: e.summary || '',
          preparedBy: e.preparedBy || '',
          remark: e.remark || '',
        }))
        nextId = entries.value.length + 1
      }
    } catch { /* ignore parse error */ }
  }
}

// ═══ 行操作 ═══
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入分录摘要', '新增调整分录', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：调整其他应付款—保证金',
    })
    if (value?.trim()) {
      const entry: AdjustmentEntry = {
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        entryType: 'AJE',
        accountCode: K3_ACCOUNT_CODE,
        accountName: '其他应付款',
        debitAmount: 0,
        creditAmount: 0,
        summary: value.trim(),
        preparedBy: '',
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
  emit('save', `${ITEM_PREFIX}-entries`, JSON.stringify(entries.value))
}

// ═══ 保存回写K3-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 负债类2241: AJE对科目影响 = 贷方(增加负债) - 借方(减少负债)
  const ajeTotal = entries.value
    .filter(e => e.entryType === 'AJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)
  const rjeTotal = entries.value
    .filter(e => e.entryType === 'RJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)

  // 同步到allResponses供K3-1审定表读取
  props.allResponses.set('K3-1-aje-total', { item_id: 'K3-1-aje-total', value: ajeTotal })
  props.allResponses.set('K3-1-rje-total', { item_id: 'K3-1-rje-total', value: rjeTotal })

  // 持久化
  emit('save', 'K3-1-aje-total', ajeTotal)
  emit('save', 'K3-1-rje-total', rjeTotal)
  persistEntries()

  // EventBus publish adjustment:created → A13
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K3',
      accountCode: K3_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      entryCount: entries.value.length,
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K3-1审定表，已通知A13')
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
    // 重新加载数据（后端导入成功后数据已持久化，触发刷新）
    ElMessage.info('导入完成，请刷新查看最新数据')
  }
}

// ═══ 复核 ═══
function openReview(): void {
  openReviewDialog('K3-3-adjustment')
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
.k3-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.k3-adj-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.entry-count { font-size: 12px; color: #909399; }

/* 合计行 */
.k3-adj-footer { display: flex; align-items: center; gap: 16px; margin-top: 8px; padding: 10px 16px; background: #f0f9eb; border-radius: 4px; font-weight: 600; font-size: var(--wp-font-size, 13px); }
.k3-adj-footer.balance-fail { background: #fef0f0; border: 1px solid #f56c6c; }
.footer-label { color: #606266; }
.footer-debit, .footer-credit { color: #303133; }
.footer-status.ok { color: #67c23a; margin-left: auto; }
.footer-status.err { color: #f56c6c; margin-left: auto; font-weight: 700; }

/* RJE行浅色区分 */
:deep(.rje-row) { background-color: #fdf6ec !important; }

/* 编制提示 */
.k3-guide-details { margin-top: 16px; }
.k3-guide-content { padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; margin-top: 6px; font-size: 12px; line-height: 1.8; }
.k3-guide-content p { margin: 0; }
</style>
