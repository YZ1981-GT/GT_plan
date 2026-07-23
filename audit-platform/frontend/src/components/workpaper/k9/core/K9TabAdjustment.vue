<template>
  <div class="k9-tab-adjustment">
    <!-- ═══ Section标题 + 操作 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate-sheet', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">K9-3 调整分录汇总</h3>
        <el-tag type="warning" effect="dark" size="small" class="account-badge">
          科目6602·借方=增加费用
        </el-tag>
      </div>
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
        <el-button size="small" :loading="aiLoading" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger section-id="K9-3-adjustment" label="💬 复核" />
        <el-button
          size="small"
          type="success"
          :disabled="isReadonly || !isBalanced || entries.length === 0"
          @click="handleSaveWriteback"
        >
          💾 保存并回写K9-1
        </el-button>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="wp:K9-1" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K9-8" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        管理费用（6602损益类借方科目）调整分录，对齐源模板 10 列。
        <strong>类别</strong>：报表调整（重分类，计入 RJE）/ 账项调整（计入 AJE）/ 其他（计入 AJE）。
        损益类 6602：<strong>借方=增加费用</strong>，<strong>贷方=冲减费用</strong>。
        借贷平衡后回写 K9-1 审定表 AJE/RJE 合计，同时发布 adjustment:created 与 a13:push-misstatement → A13 错报汇总。
      </p>
    </div>

    <!-- ═══ 借贷不平衡警告 ═══ -->
    <el-alert v-if="!isBalanced && entries.length > 0" type="error" :closable="false" show-icon style="margin-bottom:8px">
      <template #title>
        ⚠️ 借贷不平衡：借方合计 {{ fmtAmt(totalDebits) }} ≠ 贷方合计 {{ fmtAmt(totalCredits) }}，差额 {{ fmtAmt(Math.abs(balanceDiff)) }}
      </template>
    </el-alert>

    <!-- ═══ 操作按钮区 ═══ -->
    <div class="adj-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddEntry">+ 新增调整分录</el-button>
      <span class="entry-count">共 {{ entries.length }} 条分录</span>
      <span class="bucket-hint">
        AJE 合计：<strong>{{ fmtAmt(ajeTotal) }}</strong>　RJE 合计：<strong>{{ fmtAmt(rjeTotal) }}</strong>
      </span>
    </div>

    <!-- ═══ 调整分录表格（对齐源模板10列） ═══ -->
    <el-table :data="entries" border size="small" style="width:100%;font-size:13px" max-height="480" :row-class-name="tableRowClassName">
      <el-table-column label="序号" width="50" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="调整事项说明" min-width="150" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.description" size="small" placeholder="调整事项说明" @change="(v: string) => updateCell(row.id, 'description', v)" />
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
          <el-select v-if="!isReadonly" :model-value="row.category" size="small" style="width:100px" @change="(v: string) => updateCell(row.id, 'category', v)">
            <el-option v-for="c in CATEGORY_OPTIONS" :key="c" :label="c" :value="c" />
          </el-select>
          <el-tag v-else :type="row.category === '报表调整' ? 'warning' : 'primary'" size="small">{{ row.category }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="报表项目" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reportItem" size="small" placeholder="报表项目" @change="(v: string) => updateCell(row.id, 'reportItem', v)" />
          <span v-else>{{ row.reportItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" placeholder="如：管理费用" @change="(v: string) => updateCell(row.id, 'accountName', v)" />
          <span v-else>{{ row.accountName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附注项目" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.noteItem" size="small" placeholder="附注项目" @change="(v: string) => updateCell(row.id, 'noteItem', v)" />
          <span v-else>{{ row.noteItem || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方调整金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" :precision="2" :min="0" style="width:100%" @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="索引" @change="(v: string) => updateCell(row.id, 'indexRef', v)" />
          <span v-else>{{ row.indexRef || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(row.id, 'remark', v)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link size="small" type="danger" @click="handleRemoveEntry(row.id)">删除</el-button>
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
        <el-tag :type="isBalanced ? 'success' : 'danger'" size="small" style="margin-left:8px">
          {{ isBalanced ? '已平衡' : '不平衡' }}
        </el-tag>
      </div>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>管理费用（6602）为损益类借方科目：借方=增加费用，贷方=冲减费用</li>
        <li>对齐源模板 10 列：调整事项说明/类别/报表项目/科目名称/附注项目/……/借方/贷方/索引/备注</li>
        <li><strong>类别</strong>：报表调整=重分类（计入 RJE）；账项调整、其他=审计调整（计入 AJE）</li>
        <li>借贷必须平衡后才能回写 K9-1 审定表（AJE/RJE 分桶合计）</li>
        <li>保存后自动发布 adjustment:created 与 a13:push-misstatement → 联动 A13 错报汇总</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K9TabAdjustment.vue — K9-3 管理费用调整分录汇总
 *
 * Spec: .kiro/specs/k9-admin-expenses/ | Task: 4.6
 * Requirements: 8.2
 *
 * 功能（对齐源模板10列，镜像 K11-3 / K10-3）：
 * - 10列：调整事项说明/类别(报表调整/账项调整/其他)/报表项目/科目名称/附注项目/……/借方/贷方/索引/备注
 * - 类别→桶：报表调整=RJE，账项调整/其他=AJE（categoryToBucket）
 * - legacy entryType(AJE/RJE) → category 向后兼容迁移
 * - 借贷平衡校验（Σ借方===Σ贷方）
 * - publish EventBus 'adjustment:created' + 'a13:push-misstatement' → A13
 * - 双向同步 K9-1 审定表（K9-1-aje-total / K9-1-rje-total）
 * - 导入导出（useK9ImportExport，sheet K9-3）
 * - 动态行增删（ElMessageBox.prompt确认）
 * - AI 顾问式建议
 */
import { ref, computed, inject, onMounted, toRef, type Ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useK9ImportExport } from '../../composables/useK9ImportExport'
import { generateK9AiText } from '../../composables/useK9AiText'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const K9_ACCOUNT_CODE = '6602'
const ITEM_PREFIX = 'K9-3-adj'

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
const importExport = useK9ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  sheetCode: 'K9-3',
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

/** 类别 → K9-1 审定表调整桶：报表调整=重分类(RJE)，账项调整/其他=审计调整(AJE) */
function categoryToBucket(category: AdjCategory): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

/** legacy entryType(AJE/RJE) → category（向后兼容旧5列数据） */
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

// ═══ AJE/RJE 桶合计（供顶部展示 + 回写K9-1）═══
// 损益类6602：桶影响 = 借方(增加费用) - 贷方(冲减费用)
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

// ═══ 初始化加载 ═══
onMounted(() => { loadFromResponses() })

function loadFromResponses(): void {
  const saved = props.allResponses.get(`${ITEM_PREFIX}-entries`)
  const raw = saved?.remark ?? saved?.conclusion ?? (typeof saved === 'string' ? saved : null)
  if (!raw) { entries.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) {
      entries.value = parsed.map((e: any, idx: number) => ({
        id: e.id || `entry-${++nextId}`,
        seq: idx + 1,
        description: e.description ?? e.summary ?? '',
        // 优先用 category；缺失时从 legacy entryType 迁移
        category: (CATEGORY_OPTIONS.includes(e.category) ? e.category : legacyEntryTypeToCategory(e.entryType)) as AdjCategory,
        reportItem: e.reportItem ?? '',
        accountName: e.accountName || '管理费用',
        noteItem: e.noteItem ?? '',
        summary: e.summary ?? '',
        debitAmount: Number(e.debitAmount) || 0,
        creditAmount: Number(e.creditAmount) || 0,
        indexRef: e.indexRef ?? e.refIndex ?? '',
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
      inputPlaceholder: '如：调增管理费用—XX咨询费 / 重分类至XX',
    })
    if (value?.trim()) {
      entries.value.push({
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        description: value.trim(),
        category: '账项调整',
        reportItem: '',
        accountName: '管理费用',
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

// ═══ 保存回写K9-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  const aje = ajeTotal.value
  const rje = rjeTotal.value

  // 双向同步到allResponses供K9-1审定表读取（adjustmentReconcile 消费）
  emit('save', 'K9-1-aje-total', { remark: String(aje) })
  emit('save', 'K9-1-rje-total', { remark: String(rje) })
  persistEntries()

  // EventBus publish adjustment:created → A13 / K9-1
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K9',
      accountCode: K9_ACCOUNT_CODE,
      projectId: props.projectId,
      ajeTotal: aje,
      rjeTotal: rje,
      entryCount: entries.value.length,
    })
    // 显式推送错报至 A13（crossWpEventBridge 白名单事件）
    eventBus.emit('a13:push-misstatement' as any, {
      wpCode: 'K9',
      accountCode: K9_ACCOUNT_CODE,
      accountName: '管理费用',
      entries: entries.value.map(e => ({
        description: e.description,
        category: e.category,
        reportItem: e.reportItem,
        accountName: e.accountName,
        debitAmount: e.debitAmount,
        creditAmount: e.creditAmount,
        indexRef: e.indexRef,
      })),
      ajeTotal: aje,
      rjeTotal: rje,
      timestamp: Date.now(),
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K9-1审定表，已通知A13')
}

// ═══ AI 辅助（顾问式弹窗） ═══
const aiLoading = ref(false)
async function handleAI(): Promise<void> {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const content = await generateK9AiText(props.wpId, {
      section: 'K9-3-adjustment',
      prompt: '为K9管理费用(6602)调整分录提供审计建议：常见调整场景（费用跨期/多计漏计更正、错误科目重分类、待摊费用摊销调整）、类别选择(报表调整=重分类/账项调整/其他)与借贷方向、借贷平衡校验要点。',
      context: {
        科目: '6602 管理费用（损益类·借方=增加费用）',
        借方合计: String(totalDebits.value),
        贷方合计: String(totalCredits.value),
        AJE合计: String(ajeTotal.value),
        RJE合计: String(rjeTotal.value),
        分录: entries.value.map(e => `${e.category} ${e.description} 借${e.debitAmount}/贷${e.creditAmount}`).join('；') || '（暂无）',
      },
    })
    if (content) {
      await ElMessageBox.alert(content, 'AI 调整分录建议', { confirmButtonText: '知道了' })
    }
  } finally {
    aiLoading.value = false
  }
}

// ═══ 导入导出 ═══
function handleIECommand(cmd: string): void {
  if (cmd === 'template') {
    importExport.exportTemplate()
  } else if (cmd === 'export') {
    importExport.exportData()
  } else if (cmd === 'import') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (event: Event) => {
      const file = (event.target as HTMLInputElement).files?.[0]
      if (file) {
        const result = await importExport.importData(file)
        if (result) loadFromResponses()
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
.k9-tab-adjustment { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.account-badge { font-size: 11px; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.cross-ref-bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; padding: 6px 12px; background: #f5f7fa; border-radius: 6px; }
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.methodology-context p { margin: 0; }
.methodology-context strong { color: #b45309; }

.adj-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.entry-count { font-size: 12px; color: #909399; }
.bucket-hint { margin-left: auto; font-size: 12px; color: #909399; }
.bucket-hint strong { color: #303133; font-family: 'JetBrains Mono', monospace; }
.formula-header { border-bottom: 1px dashed #909399; cursor: help; }

.balance-section { margin-top: 12px; padding: 10px 16px; background: #f5f7fa; border-radius: 6px; display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
.balance-row { display: flex; align-items: center; gap: 4px; }
.balance-label { color: #909399; font-size: 12px; }
.balance-amount { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.balance-diff.balanced .balance-amount { color: #67c23a; }
.balance-diff.unbalanced .balance-amount { color: #f56c6c; }

:deep(.rje-row) { background-color: #fdf6ec !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
