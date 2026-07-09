<template>
  <div class="k11-tab-adjustment">
    <!-- ═══ Section标题 + 复核 ═══ -->
    <div class="section-header">
      <h3>调整分录汇总 K11-3</h3>
      <div class="header-actions">
        <el-dropdown trigger="click" @command="handleIECommand">
          <el-button size="small" plain>导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>资产减值损失（6701损益类借方科目）调整分录。借方增加减值、贷方冲减/转回。借贷平衡后回写K11-1审定表，同时发布 adjustment:created → A13。</p>
    </div>

    <!-- ═══ 操作按钮区 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="handleAddEntry">
        + 新增调整分录
      </el-button>
      <el-button
        type="success"
        size="small"
        :disabled="isReadonly || entries.length === 0"
        @click="handleSaveWriteback"
      >
        💾 保存并回写K11-1
      </el-button>
    </div>

    <!-- ═══ 分录表格 ═══ -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width: 100%; margin-top: 10px"
      :row-class-name="tableRowClassName"
      empty-text="暂无调整分录，点击上方按钮新增"
    >
      <el-table-column label="序号" width="56" align="center">
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="调整方向" width="100" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.entryType"
            size="small"
            style="width: 80px"
            @change="(v: string) => updateCell(row.id, 'entryType', v)"
          >
            <el-option label="AJE" value="AJE" />
            <el-option label="RJE" value="RJE" />
          </el-select>
          <el-tag v-else :type="row.entryType === 'RJE' ? 'warning' : 'primary'" size="small">{{ row.entryType }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="科目" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.accountName"
            size="small"
            placeholder="科目名称"
            @change="(v: string) => updateCell(row.id, 'accountName', v)"
          />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debitAmount"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.creditAmount"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.summary"
            size="small"
            placeholder="调整事项说明"
            @change="(v: string) => updateCell(row.id, 'summary', v)"
          />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleRemoveEntry(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 借贷平衡校验区 ═══ -->
    <div class="balance-section">
      <div class="balance-row">
        <span class="balance-label">借方合计：</span>
        <span class="balance-amount">{{ fmtAmt(totalDebits) }}</span>
      </div>
      <div class="balance-row">
        <span class="balance-label">贷方合计：</span>
        <span class="balance-amount">{{ fmtAmt(totalCredits) }}</span>
      </div>
      <div class="balance-row balance-diff" :class="{ balanced: isBalanced, unbalanced: !isBalanced }">
        <span class="balance-label">借贷差额：</span>
        <span class="balance-amount">{{ fmtAmt(balanceDiff) }}</span>
        <el-tag :type="isBalanced ? 'success' : 'danger'" size="small" style="margin-left: 8px">
          {{ isBalanced ? '已平衡' : '不平衡' }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>资产减值损失（6701）为损益类借方科目：借方=减值增加（计提），贷方=减值冲回</li>
        <li>AJE = 审计调整分录 / RJE = 重分类调整分录</li>
        <li>借贷必须平衡后才能回写K11-1审定表</li>
        <li>保存后自动发布 adjustment:created → 联动A13</li>
        <li>商誉减值不可转回，若出现商誉贷方(转回)请核查</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K11TabAdjustment.vue — K11-3 调整分录汇总
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/ | Task: 4.4
 * Requirements: 6.2
 *
 * 功能：
 * - 借贷平衡校验（借方合计 === 贷方合计）
 * - EventBus publish 'adjustment:created' → A13
 * - 双向同步K11-1 (AJE/RJE回写)
 * - 导入导出支持（useK11ImportExport）
 * - 动态行新增：ElMessageBox.prompt输入科目名确认后创建
 * - 每行：序号/调整方向/科目/借方/贷方/摘要
 * - 底部显示借贷差额提示
 */
import { ref, computed, onMounted, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useK11ImportExport } from '../../composables/useK11ImportExport'

const K11_ACCOUNT_CODE = '6701'
const ITEM_PREFIX = 'K11-3-adj'

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

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── 导入导出 ────────────────────────────────────────────────────────────────
const importExport = useK11ImportExport({
  wpId: computed(() => props.wpId) as any,
  projectId: computed(() => props.projectId) as any,
  sheetCode: 'K11-3',
})

// ═══ 数据模型 ═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  accountName: string
  debitAmount: number
  creditAmount: number
  summary: string
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
  const raw = saved?.remark ?? saved?.value ?? (typeof saved === 'string' ? saved : null)
  if (!raw) { entries.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) {
      entries.value = parsed.map((e: any, idx: number) => ({
        id: e.id || `entry-${++nextId}`,
        seq: idx + 1,
        entryType: e.entryType || 'AJE',
        accountName: e.accountName || '资产减值损失',
        debitAmount: Number(e.debitAmount) || 0,
        creditAmount: Number(e.creditAmount) || 0,
        summary: e.summary || '',
      }))
      nextId = entries.value.length + 1
    }
  } catch { /* ignore parse error */ }
}

// ═══ 行操作 ═══
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入科目名称', '新增调整分录', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：存货跌价准备 / 固定资产减值准备',
    })
    if (value?.trim()) {
      entries.value.push({
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        entryType: 'AJE',
        accountName: value.trim(),
        debitAmount: 0,
        creditAmount: 0,
        summary: '',
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

// ═══ 保存回写K11-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 损益类6701: AJE对科目影响 = 借方(增加减值) - 贷方(冲减减值)
  const ajeTotal = entries.value
    .filter(e => e.entryType === 'AJE')
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)
  const rjeTotal = entries.value
    .filter(e => e.entryType === 'RJE')
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)

  // 双向同步到allResponses供K11-1审定表读取
  emit('save', 'K11-1-aje-total', { remark: String(ajeTotal) })
  emit('save', 'K11-1-rje-total', { remark: String(rjeTotal) })
  persistEntries()

  // EventBus publish adjustment:created → A13
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K11',
      accountCode: K11_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      entryCount: entries.value.length,
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K11-1审定表，已通知A13')
}

// ═══ 导入导出 ═══
function handleIECommand(cmd: string): void {
  if (cmd === 'template') {
    importExport.exportTemplate()
  } else if (cmd === 'export') {
    importExport.exportData()
  } else if (cmd === 'import') {
    // 触发文件选择
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (event: Event) => {
      const file = (event.target as HTMLInputElement).files?.[0]
      if (file) {
        const result = await importExport.importData(file)
        if (result) {
          // 重新加载
          loadFromResponses()
        }
      }
    }
    input.click()
  }
}

// ═══ 复核 ═══
function handleReview(): void {
  openReviewDialog?.('K11-3-adjustment')
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
.k11-tab-adjustment { padding: 12px; font-size: 13px; }

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #fffbf0;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.methodology-context p { margin: 0; }

.action-bar { display: flex; gap: 8px; align-items: center; }

.balance-section {
  margin-top: 12px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  display: flex;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
}
.balance-row { display: flex; align-items: center; gap: 4px; }
.balance-label { color: #909399; font-size: 12px; }
.balance-amount { font-weight: 600; font-size: 13px; }
.balance-diff.balanced .balance-amount { color: #67c23a; }
.balance-diff.unbalanced .balance-amount { color: #f56c6c; }

:deep(.rje-row) { background-color: #fdf6ec !important; }

.compile-hint {
  margin-top: 12px;
  padding: 10px 14px;
  background: #fafafa;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
  margin-bottom: 6px;
}
.compile-hint ul { padding-left: 20px; margin: 0; line-height: 1.8; }
</style>
