<template>
  <div class="k4-tab-adjustment">
    <!-- Section标题栏 + 复核按钮右对齐 -->
    <div class="section-head">
      <h3 class="sheet-title">K4-3 调整分录汇总</h3>
      <div class="head-actions">
        <el-button size="small" type="success" :disabled="isReadonly || !isBalanced" @click="handleSaveWriteback">
          保存&amp;回写
        </el-button>
        <el-button v-if="!isReadonly && pendingAbnormalCount > 0" size="small" type="warning" plain @click="importFromK44Abnormal">
          从K4-4异常带入（{{ pendingAbnormalCount }}笔）
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
        <el-button size="small" type="primary" link @click="handleAiGenerate">🤖 AI辅助</el-button>
        <el-button size="small" @click="openReview('K4-3-adjustment')">💬复核</el-button>
      </div>
    </div>

    <!-- 借贷不平衡警告 -->
    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmtAmt(totalDebits) }} ≠ 贷方合计 {{ fmtAmt(totalCredits) }}，差额 {{ fmtAmt(Math.abs(balanceDiff)) }}
    </el-alert>

    <!-- 负债类方向提示 -->
    <div class="direction-hint">
      <span class="dh-tag credit">贷方 2245 = 增加负债（少计→补提）</span>
      <span class="dh-tag debit">借方 2245 = 减少负债（多计→冲回）</span>
      <span class="dh-example">示例：借 管理费用 / 贷 其他流动负债—预提XX费用 → 补提预提费用(增加负债)</span>
    </div>

    <!-- 工具栏 -->
    <div class="k4-adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增分录</el-button>
      <el-button size="small" :disabled="isReadonly" @click="handleAddPairEntry">+ 新增借贷对</el-button>
      <span class="entry-count">共 {{ entries.length }} 条 | AJE {{ ajeCount }} 条 · RJE {{ rjeCount }} 条</span>
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
      <el-table-column prop="entryNo" label="编号" width="100">
        <template #default="{ row }">
          <span class="entry-no">{{ row.entryNo }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small" @change="(v: string) => updateCell(row.id, 'entryType', v)">
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
          <el-tag v-else :type="row.entryType === 'AJE' ? 'danger' : 'warning'" size="small">{{ row.entryType }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="科目代码" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountCode" size="small" placeholder="2245" @change="(v: string) => updateCell(row.id, 'accountCode', v)" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>

      <el-table-column label="科目名称" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateCell(row.id, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="对方科目" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.offsetAccount" size="small" placeholder="对方科目" @change="(v: string) => updateCell(row.id, 'offsetAccount', v)" />
          <span v-else>{{ row.offsetAccount || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="摘要" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.id, 'summary', v)" />
          <span v-else>{{ row.summary || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="来源" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.source" size="small" type="info">{{ row.source }}</el-tag>
          <span v-else class="muted">手工</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="46" align="center">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">🗑️</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- K4-3 ↔ K4-1 勾稽 -->
    <el-alert v-if="entries.length > 0 && !k4AdjReconciliation.isReconciled" type="warning" :closable="false" style="margin-top:8px">
      K4-3 ↔ K4-1 勾稽差异：AJE 差额 {{ fmtAmt(k4AdjReconciliation.ajeDiff) }}，RJE 差额 {{ fmtAmt(k4AdjReconciliation.rjeDiff) }}。请点击"保存&amp;回写"同步。
    </el-alert>

    <!-- 合计行 -->
    <div class="k4-adj-footer" :class="{ 'balance-fail': !isBalanced }">
      <span class="footer-label">合计</span>
      <span class="footer-debit">借方：{{ fmtAmt(totalDebits) }}</span>
      <span class="footer-credit">贷方：{{ fmtAmt(totalCredits) }}</span>
      <span class="footer-net">净影响：{{ fmtAmt(netImpact) }}（{{ netImpact >= 0 ? '增加负债' : '减少负债' }}）</span>
      <span v-if="isBalanced" class="footer-status ok">✓ 平衡</span>
      <span v-else class="footer-status err">✗ 不平衡 | 差额：{{ fmtAmt(Math.abs(balanceDiff)) }}</span>
    </div>

    <!-- 审计说明 + 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">审计说明与结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerateNote">🤖 AI生成说明</el-button>
        </div>
      </template>
      <div class="note-field">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          :placeholder="auditNotePlaceholder" @change="persistNote" />
      </div>
      <div class="note-field">
        <label>审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
          placeholder="基于上述调整事项，对其他流动负债审定数的影响及是否已获管理层确认..." @change="persistNote" />
      </div>
    </el-card>

    <!-- 隐藏file input for import -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileSelected" />

    <!-- 编制提示 -->
    <details class="k4-guide-details">
      <summary>📋 编制提示</summary>
      <div class="k4-guide-content">
        <p>1. 调整分录(AJE)用于更正被审计单位财务报表中的错报；重分类分录(RJE)用于分析性归类调整。</p>
        <p>2. 借贷必须平衡后方可保存回写。点击"保存&amp;回写"将汇总AJE/RJE数据回写K4-1审定表。</p>
        <p>3. 保存后自动发布 adjustment:created 事件联动 A13 错报汇总底稿。</p>
        <p>4. 其他流动负债科目代码 2245（<strong>负债类</strong>，贷方增加/借方减少）。</p>
        <p>5. 负债类AJE方向：借方记录=减少负债；贷方记录=增加负债。对方科目记反向。</p>
        <p>6. 编号规则：K4-AJE-001 / K4-RJE-001，便于A13引用追溯。</p>
        <p>7. "从K4-4异常带入"将自动填入异常凭证信息并标注来源，减少重复录入。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabAdjustment.vue — K4-3 调整分录汇总
 *
 * Spec: k4-other-current-liabilities Task 4.5
 * Requirements: 5.2
 *
 * 功能：
 * - 标准借贷平衡表：科目/摘要/借方/贷方+合计行
 * - 借贷平衡校验（合计借=合计贷，不平衡红色提示）
 * - 保存时 publish EventBus 'adjustment:created' → A13
 * - 导入导出（useK4ImportExport sheetCode='K4-3'）
 * - 动态行增删（ElMessageBox.prompt输入摘要确认后创建）
 *
 * 科目：2245 其他流动负债（负债类）
 */
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useK4ImportExport } from '@/components/workpaper/composables/useK4ImportExport'
import type { WorkpaperRuntimeContext } from '../../composables/useWorkpaperScaffold'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

const K4_ACCOUNT_CODE = '2245'
const ITEM_PREFIX = 'K4-3-adj'

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
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)

// ═══ 导入导出 ═══
const { exportTemplate, exportData, importData } = useK4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K4-3',
})

const fileInputRef = ref<HTMLInputElement | null>(null)

// ═══ 数据模型（扩展：对方科目/编号/来源）═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryNo: string            // 编号 K4-AJE-001
  entryType: 'AJE' | 'RJE'
  accountCode: string
  accountName: string
  offsetAccount: string      // 对方科目
  debitAmount: number
  creditAmount: number
  summary: string
  preparedBy: string
  source: string             // 来源：手工/K4-4/导入
  remark: string
}

const entries = ref<AdjustmentEntry[]>([])
const auditNote = ref('')
const auditConclusion = ref('')
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
  // 🔴 修复：兼容 remark/value/字符串三种格式
  const raw = saved?.remark ?? saved?.value ?? (typeof saved === 'string' ? saved : null)
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) {
        entries.value = parsed.map((e: any, idx: number) => ({
          id: e.id || `entry-${++nextId}`,
          seq: idx + 1,
          entryNo: e.entryNo || `K4-${e.entryType || 'AJE'}-${String(idx + 1).padStart(3, '0')}`,
          entryType: e.entryType || 'AJE',
          accountCode: e.accountCode || '',
          accountName: e.accountName || '',
          offsetAccount: e.offsetAccount || '',
          debitAmount: Number(e.debitAmount) || 0,
          creditAmount: Number(e.creditAmount) || 0,
          summary: e.summary || '',
          preparedBy: e.preparedBy || '',
          source: e.source || '手工',
          remark: e.remark || '',
        }))
        nextId = entries.value.length + 1
      }
    } catch { /* ignore parse error */ }
  }
  // 加载审计说明/结论
  const noteItem = props.allResponses.get(`${ITEM_PREFIX}-note`)
  auditNote.value = noteItem?.remark ?? noteItem?.value ?? ''
  const conclItem = props.allResponses.get(`${ITEM_PREFIX}-conclusion`)
  auditConclusion.value = conclItem?.remark ?? conclItem?.value ?? ''
}

// ═══ 行操作 ═══
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入分录摘要', '新增调整分录', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：调整其他流动负债—预提费用',
    })
    if (value?.trim()) {
      const entry: AdjustmentEntry = {
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        entryNo: generateEntryNo('AJE'),
        entryType: 'AJE',
        accountCode: K4_ACCOUNT_CODE,
        accountName: '其他流动负债',
        offsetAccount: '',
        debitAmount: 0,
        creditAmount: 0,
        summary: value.trim(),
        preparedBy: '',
        source: '手工',
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

// ═══ 持久化（修复：存到 remark 字段）═══
function persistEntries(): void {
  emit('save', `${ITEM_PREFIX}-entries`, { remark: JSON.stringify(entries.value) })
  scheduleAutoSnapshot()
}

function persistNote(): void {
  emit('save', `${ITEM_PREFIX}-note`, { remark: auditNote.value })
  emit('save', `${ITEM_PREFIX}-conclusion`, { remark: auditConclusion.value })
}

function scheduleAutoSnapshot(): void {
  try { runtime?.version?.scheduleAutoSnapshot?.() } catch { /* silent */ }
}

// ═══ 分录编号生成 ═══
function generateEntryNo(type: 'AJE' | 'RJE'): string {
  const existing = entries.value.filter(e => e.entryType === type)
  const maxNo = existing.reduce((max, e) => {
    const match = e.entryNo?.match(/(\d+)$/)
    return match ? Math.max(max, parseInt(match[1])) : max
  }, 0)
  return `K4-${type}-${String(maxNo + 1).padStart(3, '0')}`
}

// ═══ 统计 ═══
const ajeCount = computed(() => entries.value.filter(e => e.entryType === 'AJE').length)
const rjeCount = computed(() => entries.value.filter(e => e.entryType === 'RJE').length)
const netImpact = computed(() => totalCredits.value - totalDebits.value)

// ═══ 保存回写K4-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 负债类2245: AJE对科目影响 = 贷方(增加负债) - 借方(减少负债)
  const ajeTotal = entries.value
    .filter(e => e.entryType === 'AJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)
  const rjeTotal = entries.value
    .filter(e => e.entryType === 'RJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)

  // 同步到allResponses供K4-1审定表读取
  props.allResponses.set('K4-1-aje-total', { item_id: 'K4-1-aje-total', value: ajeTotal })
  props.allResponses.set('K4-1-rje-total', { item_id: 'K4-1-rje-total', value: rjeTotal })

  // 持久化
  emit('save', 'K4-1-aje-total', ajeTotal)
  emit('save', 'K4-1-rje-total', rjeTotal)
  persistEntries()

  // EventBus publish adjustment:created → 附注/其他消费者
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K4',
      accountCode: K4_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      entryCount: entries.value.length,
    })
  } catch { /* silent */ }

  // 推送到 A13 错报汇总
  try {
    eventBus.emit('a13:push-misstatement', {
      wpCode: 'K4',
      accountCode: K4_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      source: 'K4-3',
      description: `K4其他流动负债调整分录${entries.value.length}条(AJE净额${ajeTotal},RJE净额${rjeTotal})`,
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K4-1审定表，已通知A13')
}

// ═══ K4-3 ↔ K4-1 勾稽验证 ═══
const k4AdjReconciliation = computed(() => {
  // K4-1 审定表 AJE/RJE 合计
  const k41Aje = (() => {
    const item = props.allResponses.get('K4-1-aje-total')
    const v = item?.remark ?? item?.value ?? item
    return Number(v) || 0
  })()
  const k41Rje = (() => {
    const item = props.allResponses.get('K4-1-rje-total')
    const v = item?.remark ?? item?.value ?? item
    return Number(v) || 0
  })()
  // K4-3 本地计算的 AJE/RJE (负债类: 贷方-借方)
  const localAje = entries.value
    .filter(e => e.entryType === 'AJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)
  const localRje = entries.value
    .filter(e => e.entryType === 'RJE')
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)
  const ajeDiff = Math.abs(k41Aje - localAje)
  const rjeDiff = Math.abs(k41Rje - localRje)
  return {
    k41Aje, k41Rje, localAje, localRje,
    ajeDiff, rjeDiff,
    isReconciled: ajeDiff < 0.01 && rjeDiff < 0.01,
  }
})

// ═══ K4-4 异常凭证"需调整"项（跨sheet带入）═══
const pendingAbnormalCount = computed(() => {
  const stored = props.allResponses.get('K4-4-voucher-check')
  if (!stored) return 0
  const raw = stored.remark ?? stored.value
  if (!raw) return 0
  try {
    const parsed = JSON.parse(typeof raw === 'string' ? raw : JSON.stringify(raw))
    const rows = parsed.occurrenceRows || parsed.rows || []
    return rows.filter((r: any) => r.abnormal && r.disposalDecision === 'adjust').length
  } catch { return 0 }
})

function importFromK44Abnormal(): void {
  const stored = props.allResponses.get('K4-4-voucher-check')
  if (!stored) return
  const raw = stored.remark ?? stored.value
  if (!raw) return
  try {
    const parsed = JSON.parse(typeof raw === 'string' ? raw : JSON.stringify(raw))
    const rows = (parsed.occurrenceRows || parsed.rows || [])
      .filter((r: any) => r.abnormal && r.disposalDecision === 'adjust')
    if (rows.length === 0) { ElMessage.info('无需调整的异常凭证'); return }
    let imported = 0
    for (const r of rows) {
      if (entries.value.some(e => e.remark?.includes(r.voucherNo) && e.source === 'K4-4')) continue
      entries.value.push({
        id: `entry-${Date.now()}-${++nextId}`,
        seq: entries.value.length + 1,
        entryNo: generateEntryNo('AJE'),
        entryType: 'AJE',
        accountCode: K4_ACCOUNT_CODE,
        accountName: '其他流动负债',
        offsetAccount: r.offsetAccount || '',
        debitAmount: 0,
        creditAmount: r.creditAmount || r.debitAmount || 0,
        summary: `调整：${r.debtorName || '异常凭证'} (凭证${r.voucherNo || '-'})`,
        preparedBy: '',
        source: 'K4-4',
        remark: `来源K4-4 ${r.voucherNo || ''} ${r.remark || ''}`.trim(),
      })
      imported++
    }
    reSequence()
    persistEntries()
    ElMessage.success(`已从K4-4带入 ${imported} 笔，请补充金额和对方科目`)
  } catch { ElMessage.warning('读取K4-4数据失败') }
}

// ═══ 快捷新增借贷对 ═══
async function handleAddPairEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入调整事项摘要', '新增借贷对', {
      confirmButtonText: '确定', cancelButtonText: '取消',
      inputPlaceholder: '如：补提预提费用—XX服务费',
    })
    if (!value?.trim()) return
    const no = generateEntryNo('AJE')
    entries.value.push({
      id: `entry-${Date.now()}-${++nextId}`, seq: entries.value.length + 1,
      entryNo: no, entryType: 'AJE', accountCode: '', accountName: '',
      offsetAccount: K4_ACCOUNT_CODE, debitAmount: 0, creditAmount: 0,
      summary: `${value.trim()}（借方）`, preparedBy: '', source: '手工', remark: '',
    })
    entries.value.push({
      id: `entry-${Date.now()}-${++nextId}`, seq: entries.value.length + 1,
      entryNo: no, entryType: 'AJE', accountCode: K4_ACCOUNT_CODE, accountName: '其他流动负债',
      offsetAccount: '', debitAmount: 0, creditAmount: 0,
      summary: `${value.trim()}（贷方）`, preparedBy: '', source: '手工', remark: '',
    })
    persistEntries()
    ElMessage.info('已创建借贷对，请填写科目和金额')
  } catch { /* cancelled */ }
}

// ═══ AI 辅助 ═══
function handleAiGenerate(): void { handleAiGenerateNote() }

async function handleAiGenerateNote(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请根据调整分录情况，生成K4-3调整分录汇总的审计说明',
      context: {
        科目: '2245 其他流动负债（负债类）',
        分录笔数: String(entries.value.length),
        净影响: String(netImpact.value),
        来源K44: String(entries.value.filter(e => e.source === 'K4-4').length),
      },
      existingContent: auditNote.value || '',
      section: 'K4-3-adjustment-note',
    })
    const content = res?.data?.data?.content || res?.data?.content || ''
    if (content) {
      auditNote.value = auditNote.value ? `${auditNote.value}\n\n${content}` : content
      persistNote()
      ElMessage.success('AI 已生成审计说明')
    } else { ElMessage.warning('AI 未返回内容') }
  } catch { ElMessage.warning('AI 生成失败') }
}

const auditNotePlaceholder = '说明调整原因、影响金额、是否已获管理层确认'

// ═══ 导入导出处理 ═══
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
    // 导入走后端→前端 allResponses Map 未更新，需通知父组件 reload
    // 先尝试从最新 allResponses 读（如果父已刷新）
    loadFromResponses()
    // 如果 entries 仍为空说明 Map 未刷新，提示用户切换 tab 刷新
    if (entries.value.length === 0) {
      ElMessage.info(`导入完成（${result.rowCount} 条），请切换页签后返回查看最新数据`)
    } else {
      ElMessage.success(`导入完成（${result.rowCount} 条）`)
    }
    scheduleAutoSnapshot()
  }
}

// ═══ 复核 ═══
function openReview(id: string): void {
  openReviewDialog(id)
}

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  if (row.entryType === 'RJE') return 'rje-row'
  if (row.source === 'K4-4') return 'from-k44-row'
  return ''
}
</script>

<style scoped>
.k4-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.k4-adj-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.entry-count { font-size: 12px; color: #909399; }

/* 合计行 */
.k4-adj-footer { display: flex; align-items: center; gap: 16px; margin-top: 8px; padding: 10px 16px; background: #f0f9eb; border-radius: 4px; font-weight: 600; font-size: var(--wp-font-size, 13px); }
.k4-adj-footer.balance-fail { background: #fef0f0; border: 1px solid #f56c6c; }
.footer-label { color: #606266; }
.footer-debit, .footer-credit { color: #303133; }
.footer-status.ok { color: #67c23a; margin-left: auto; }
.footer-status.err { color: #f56c6c; margin-left: auto; font-weight: 700; }

/* RJE行浅色区分 */
:deep(.rje-row) { background-color: #fdf6ec !important; }
:deep(.from-k44-row) { background-color: #ecf5ff !important; }

/* 方向提示 */
.direction-hint { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; padding: 6px 10px; background: #f5f7fa; border-radius: 4px; font-size: 11px; }
.dh-tag { padding: 2px 8px; border-radius: 3px; font-weight: 500; }
.dh-tag.credit { background: #e1f3d8; color: #529b2e; }
.dh-tag.debit { background: #fef0f0; color: #c45656; }
.dh-example { color: var(--el-text-color-secondary); font-style: italic; }

/* 编号列 */
.entry-no { font-family: monospace; font-size: 11px; color: var(--el-color-primary); }

/* 金额 */
.amount-cell { font-variant-numeric: tabular-nums; }
.muted { color: var(--el-text-color-placeholder); }

/* 合计行净影响 */
.footer-net { color: #606266; font-size: 12px; }

/* 审计说明卡 */
.note-card { margin-top: 12px; }
.note-card :deep(.el-card__header) { padding: 8px 14px; }
.note-card :deep(.el-card__body) { padding: 12px 14px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-weight: 600; }
.note-field { margin-bottom: 10px; display: flex; flex-direction: column; gap: 4px; }
.note-field label { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 500; }

/* 编制提示 */
.k4-guide-details { margin-top: 16px; }
.k4-guide-content { padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; margin-top: 6px; font-size: 12px; line-height: 1.8; }
.k4-guide-content p { margin: 0; }
</style>
