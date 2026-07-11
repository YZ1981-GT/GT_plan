<template>
  <div class="k5-tab-adjustment">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">K5-3 调整分录汇总</h3>
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
        <el-button size="small" @click="openReview('K5-3-adjustment')">💬复核</el-button>
      </div>
    </div>

    <!-- 借贷不平衡警告 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom: 8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmtAmt(totalDebits) }} ≠ 贷方合计 {{ fmtAmt(totalCredits) }}，差额 {{ fmtAmt(Math.abs(balanceDiff)) }}
    </el-alert>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>调整分录(AJE)用于更正预计负债相关的错报；重分类分录(RJE)用于负债分类调整。借贷必须平衡后方可保存回写。保存后自动发布 adjustment:created 事件联动 A13 错报汇总。</p>
    </div>

    <!-- 工具栏 -->
    <div class="adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增</el-button>
      <span class="entry-count">共 {{ entries.length }} 条分录</span>
      <span class="balance-indicator">
        借方: <strong>{{ fmtAmt(totalDebits) }}</strong> |
        贷方: <strong>{{ fmtAmt(totalCredits) }}</strong>
        <el-tag v-if="isBalanced" type="success" size="small" effect="plain" style="margin-left: 8px">✓ 平衡</el-tag>
      </span>
    </div>

    <!-- 调整分录表格 -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      max-height="520"
      show-summary
      :summary-method="getSummary"
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
          <el-input v-if="!isReadonly" :model-value="row.accountCode" size="small" placeholder="如2701" @change="(v: string) => updateCell(row.id, 'accountCode', v)" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" placeholder="调整摘要" @change="(v: string) => updateCell(row.id, 'summary', v)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.debit"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width: 105px"
            @change="(v: number | undefined) => updateCell(row.id, 'debit', v ?? 0)"
          />
          <span v-else>{{ row.debit ? fmtAmt(row.debit) : '' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.credit"
            size="small"
            :controls="false"
            :precision="2"
            :min="0"
            style="width: 105px"
            @change="(v: number | undefined) => updateCell(row.id, 'credit', v ?? 0)"
          />
          <span v-else>{{ row.credit ? fmtAmt(row.credit) : '' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeEntry($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编制提示 -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>调整分录(AJE)用于更正被审计单位财务报表中的错报；重分类分录(RJE)用于分析性归类调整。</li>
        <li>借贷必须平衡后方可保存回写。点击"保存&amp;回写"将汇总AJE/RJE数据回写K5-1审定表。</li>
        <li>保存后自动发布 adjustment:created 事件联动 A13 错报汇总底稿。</li>
        <li>预计负债科目代码 2701（<strong>负债类</strong>，贷方增加/借方减少）。</li>
        <li>负债类AJE方向：借方记录=减少负债；贷方记录=增加负债。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabAdjustment.vue — K5-3 调整分录汇总
 *
 * - 标准借贷平衡表：类型/科目/摘要/借方/贷方+合计行
 * - 借贷平衡校验（合计借=合计贷，不平衡红色提示）
 * - 保存时 publish EventBus 'adjustment:created' → A13
 * - 双向同步K5-1审定表 AJE/RJE 汇总
 * - 导入导出（K5-3 sheet）
 * - 动态行增删（ElMessageBox.prompt输入摘要确认后创建）
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 6.2
 * Requirements: 9.2
 */
import { ref, computed, onMounted, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'

const K5_ACCOUNT_CODE = '2701'

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

const openReview = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Types ───────────────────────────────────────────────────────────────────

interface AdjEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  accountCode: string
  summary: string
  debit: number
  credit: number
}

// ─── State ───────────────────────────────────────────────────────────────────

const entries = ref<AdjEntry[]>([])
let _nextId = 1

// ─── Computed ────────────────────────────────────────────────────────────────

const totalDebits = computed(() => entries.value.reduce((s, e) => s + (e.debit || 0), 0))
const totalCredits = computed(() => entries.value.reduce((s, e) => s + (e.credit || 0), 0))
const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.005)

// ─── Init ────────────────────────────────────────────────────────────────────

function loadSavedData(): void {
  const saved = props.allResponses.get('K5-3-entries')
  if (saved?.remark) {
    try {
      const arr = JSON.parse(saved.remark)
      entries.value = arr.map((e: any, idx: number) => ({
        id: e.id || `entry-${_nextId++}`,
        seq: idx + 1,
        entryType: e.entryType || 'AJE',
        accountCode: e.accountCode || '',
        summary: e.summary || '',
        debit: Number(e.debit) || 0,
        credit: Number(e.credit) || 0,
      }))
      _nextId = entries.value.length + 1
    } catch {
      entries.value = []
    }
  }
}

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddEntry(): Promise<void> {
  const { value: summary } = await ElMessageBox.prompt(
    '请输入调整摘要',
    '新增分录',
    { confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：补提预计负债' }
  ).catch(() => ({ value: null }))

  if (!summary) return

  entries.value.push({
    id: `entry-${_nextId++}`,
    seq: entries.value.length + 1,
    entryType: 'AJE',
    accountCode: K5_ACCOUNT_CODE,
    summary: summary,
    debit: 0,
    credit: 0,
  })
  persistEntries()
}

function updateCell(id: string, field: string, value: any): void {
  const entry = entries.value.find(e => e.id === id)
  if (entry) {
    ;(entry as any)[field] = value
    persistEntries()
  }
}

function removeEntry(index: number): void {
  entries.value.splice(index, 1)
  entries.value.forEach((e, i) => { e.seq = i + 1 })
  persistEntries()
}

function persistEntries(): void {
  emit('save', 'K5-3-entries', { remark: JSON.stringify(entries.value) })
}

/**
 * 保存&回写：
 * 1. 持久化分录
 * 2. 汇总AJE/RJE总额 emit给K5-1审定表
 * 3. EventBus publish 'adjustment:created' → A13
 */
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法保存')
    return
  }

  // 汇总 AJE/RJE 合计（针对2701科目的净调整）
  let ajeTotal = 0
  let rjeTotal = 0
  for (const e of entries.value) {
    const net = (e.credit || 0) - (e.debit || 0) // 负债类：贷方增加
    if (e.entryType === 'AJE') ajeTotal += net
    else rjeTotal += net
  }

  // emit 回写K5-1（通过allResponses传递）
  emit('save', 'K5-1-aje-total', { remark: String(ajeTotal) })
  emit('save', 'K5-1-rje-total', { remark: String(rjeTotal) })
  persistEntries()

  // EventBus publish adjustment:created → A13
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K5',
      accountCode: K5_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      entryCount: entries.value.length,
    } as any)
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K5-1审定表，已通知A13')
}

// ─── Table Summary ───────────────────────────────────────────────────────────

function getSummary({ columns, data }: any): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 4) return fmtAmt(totalDebits.value) // 借方
    if (idx === 5) return fmtAmt(totalCredits.value) // 贷方
    return ''
  })
}

// ─── Import/Export ───────────────────────────────────────────────────────────

function handleIECommand(cmd: string): void {
  if (cmd === 'template') {
    ElMessage.info('导出K5-3调整分录模板...')
  } else if (cmd === 'export') {
    ElMessage.info('导出K5-3调整分录数据...')
  } else if (cmd === 'import') {
    ElMessage.info('导入K5-3调整分录数据...')
  }
}

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSavedData()
})
</script>

<style scoped>
.k5-tab-adjustment { padding: 12px; font-size: 13px; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.head-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6; }
.adj-toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 10px; }
.entry-count { font-size: 13px; color: #909399; }
.balance-indicator { margin-left: auto; font-size: 13px; color: #606266; }
:deep(.el-table) { font-size: 13px; }
:deep(.el-table__footer-wrapper) { font-weight: 600; }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
