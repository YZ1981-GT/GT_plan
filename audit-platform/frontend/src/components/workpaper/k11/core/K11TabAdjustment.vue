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
        <GtReviewTrigger section-id="K11-3-adjustment" label="💬 复核" />
        <el-button
          size="small"
          type="primary"
          plain
          :loading="centralSyncing"
          :disabled="isReadonly || !isBalanced || entries.length === 0"
          @click="syncToCentral"
          title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
        >
          同步到集中登记
        </el-button>
        <el-tag
          v-if="centralStatus?.review_status"
          size="small"
          :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
          :title="centralStatus.rejection_reason || ''"
        >
          集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>资产减值损失（6701损益类借方科目）调整分录，对齐源模板 10 列。<strong>类别</strong>：报表调整（重分类，计入 RJE）/ 账项调整（计入 AJE）/ 其他（计入 AJE）。借方=增加减值、贷方=冲减/转回。借贷平衡后回写 K11-1 审定表 AJE/RJE 合计，同时发布 adjustment:created → A13。</p>
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
      <span class="bucket-hint">
        AJE 合计：<strong>{{ fmtAmt(ajeTotal) }}</strong>　RJE 合计：<strong>{{ fmtAmt(rjeTotal) }}</strong>
      </span>
    </div>

    <!-- ═══ 分录表格（对齐源模板10列） ═══ -->
    <el-table
      :data="entries"
      border
      size="small"
      style="width: 100%; margin-top: 10px"
      :row-class-name="tableRowClassName"
      empty-text="暂无调整分录，点击上方按钮新增"
    >
      <el-table-column label="序号" width="50" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="调整事项说明" min-width="150" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.description"
            size="small"
            placeholder="调整事项说明"
            @change="(v: string) => updateCell(row.id, 'description', v)"
          />
          <span v-else>{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="120" align="center">
        <template #header>
          <el-tooltip content="报表调整→重分类(RJE)；账项调整/其他→审计调整(AJE)" placement="top">
            <span class="formula-header">类别</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.category"
            size="small"
            style="width: 100px"
            @change="(v: string) => updateCell(row.id, 'category', v)"
          >
            <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
          </el-select>
          <el-tag v-else :type="row.category === '报表调整' ? 'warning' : 'primary'" size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" min-width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reportItem"
            size="small"
            placeholder="报表项目"
            @change="(v: string) => updateCell(row.id, 'reportItem', v)"
          />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="140">
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
      <el-table-column label="附注项目" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.noteItem"
            size="small"
            placeholder="附注项目"
            @change="(v: string) => updateCell(row.id, 'noteItem', v)"
          />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="120" align="right">
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
      <el-table-column label="贷方调整金额" width="120" align="right">
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
      <el-table-column label="索引" min-width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.indexRef"
            size="small"
            placeholder="索引"
            @change="(v: string) => updateCell(row.id, 'indexRef', v)"
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
            placeholder="备注"
            @change="(v: string) => updateCell(row.id, 'remark', v)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" align="center" fixed="right" v-if="!isReadonly">
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
        <li>对齐源模板 10 列：调整事项说明/类别/报表项目/科目名称/附注项目/……/借方/贷方/索引/备注</li>
        <li><strong>类别</strong>：报表调整=重分类（计入 RJE）；账项调整、其他=审计调整（计入 AJE）</li>
        <li>借贷必须平衡后才能回写K11-1审定表（AJE/RJE 分桶合计）</li>
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
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useK11ImportExport } from '../../composables/useK11ImportExport'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'

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

// ─── 导入导出 ────────────────────────────────────────────────────────────────
const importExport = useK11ImportExport({
  wpId: computed(() => props.wpId) as any,
  projectId: computed(() => props.projectId) as any,
  sheetCode: 'K11-3',
})

// ═══ 数据模型（对齐源模板10列） ═══
type AdjCategory = '报表调整' | '账项调整' | '其他'

interface AdjustmentEntry {
  id: string
  seq: number
  description: string   // 调整事项说明
  category: AdjCategory // 类别（报表调整/账项调整/其他）
  reportItem: string    // 报表项目
  accountName: string   // 科目名称
  noteItem: string      // 附注项目
  summary: string       // …… 摘要（源模板保留列）
  debitAmount: number
  creditAmount: number
  indexRef: string      // 索引
  remark: string        // 备注
}

const CATEGORY_OPTIONS: AdjCategory[] = ['报表调整', '账项调整', '其他']

/** 类别 → K11-1 审定表调整桶：报表调整=重分类(RJE)，账项调整/其他=审计调整(AJE) */
function categoryToBucket(category: AdjCategory): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

/** legacy entryType(AJE/RJE) → category（向后兼容旧数据） */
function legacyEntryTypeToCategory(entryType: unknown): AdjCategory {
  return entryType === 'RJE' ? '报表调整' : '账项调整'
}

const entries = ref<AdjustmentEntry[]>([])
let nextId = 1

// ═══ 计算属性：借贷平衡 ═══
const totalDebits = computed(() => entries.value.reduce((sum, e) => sum + (e.debitAmount || 0), 0))
const totalCredits = computed(() => entries.value.reduce((sum, e) => sum + (e.creditAmount || 0), 0))
const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.005)

// ═══ AJE/RJE 桶合计（供顶部展示 + 回写K11-1） ═══
const ajeTotal = computed(() =>
  entries.value
    .filter(e => categoryToBucket(e.category) === 'AJE')
    .reduce((sum, e) => sum + ((e.debitAmount || 0) - (e.creditAmount || 0)), 0),
)
const rjeTotal = computed(() =>
  entries.value
    .filter(e => categoryToBucket(e.category) === 'RJE')
    .reduce((sum, e) => sum + ((e.debitAmount || 0) - (e.creditAmount || 0)), 0),
)

// ═══ 同步到集中调整登记（workpaper-adjustment-centralization） ═══
const { year: auditYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: auditYear,
  wpId: () => props.wpId,
  wpCode: 'K11',
  itemId: `${ITEM_PREFIX}-entries`,
  buildLineItems: () => entries.value.map(e => ({
    account_name: e.accountName,
    report_line_code: e.reportItem || undefined,
    debit_amount: e.debitAmount,
    credit_amount: e.creditAmount,
  })),
  buildMeta: () => ({
    description: entries.value.find(e => e.description)?.description || 'K11 资产减值损失调整',
    adjustmentType: entries.value.length > 0 && entries.value.every(e => e.category === '报表调整') ? 'rje' : 'aje',
  }),
})

// ═══ 初始化加载 ═══
onMounted(() => { loadFromResponses(); refreshStatus() })

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
        description: e.description ?? '',
        // 优先用 category；缺失时从 legacy entryType 迁移
        category: (CATEGORY_OPTIONS.includes(e.category) ? e.category : legacyEntryTypeToCategory(e.entryType)) as AdjCategory,
        reportItem: e.reportItem ?? '',
        accountName: e.accountName || '资产减值损失',
        noteItem: e.noteItem ?? '',
        summary: e.summary ?? '',
        debitAmount: Number(e.debitAmount) || 0,
        creditAmount: Number(e.creditAmount) || 0,
        indexRef: e.indexRef ?? '',
        remark: e.remark ?? '',
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
      inputPlaceholder: '如：补提存货跌价准备 / 重分类至流动负债',
    })
    if (value?.trim()) {
      entries.value.push({
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        description: value.trim(),
        category: '账项调整',
        reportItem: '',
        accountName: '资产减值损失',
        noteItem: '',
        summary: '',
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

// ═══ 保存回写K11-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 损益类6701: 桶影响 = 借方(增加减值) - 贷方(冲减减值)；类别→桶(报表调整=RJE,账项/其他=AJE)
  const aje = ajeTotal.value
  const rje = rjeTotal.value

  // 双向同步到allResponses供K11-1审定表读取
  emit('save', 'K11-1-aje-total', { remark: String(aje) })
  emit('save', 'K11-1-rje-total', { remark: String(rje) })
  persistEntries()

  // EventBus publish adjustment:created → A13
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K11',
      accountCode: K11_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal: aje,
      rjeTotal: rje,
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

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  return row.category === '报表调整' ? 'rje-row' : ''
}
</script>

<style scoped>
.k11-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }

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
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
  line-height: 1.6;
}
.methodology-context p { margin: 0; }

.action-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.bucket-hint { margin-left: auto; font-size: 12px; color: #909399; }
.bucket-hint strong { color: #303133; font-family: 'JetBrains Mono', monospace; }
.formula-header { border-bottom: 1px dashed #909399; cursor: help; }

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
.balance-amount { font-weight: 600; font-size: var(--wp-font-size, 13px); }
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
