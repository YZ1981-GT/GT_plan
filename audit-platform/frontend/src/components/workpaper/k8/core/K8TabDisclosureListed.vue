<template>
  <div class="k8-disclosure-listed">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>附注披露信息（上市公司）</h3>
      <div class="header-actions">
        <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
        <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
          <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </el-tooltip>
        <el-button size="small" @click="openReviewDialog?.('K8-disclosure-listed')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按费用性质（职工薪酬/折旧摊销/办公费/差旅费/广告费/运输费/业务招待费/研发费等）披露销售费用本期与上期发生额。数据来自K8-1审定表，subscribe 'substantive:adjudicated' 事件自动刷新。上市42行×28列。</p>
    </div>

    <!-- ═══ 自动取数提示 ═══ -->
    <el-alert v-if="hasAutoData" type="success" :closable="true" style="margin-bottom:10px" show-icon>
      <template #title>已从K8-1审定表自动取数填充附注数据</template>
    </el-alert>

    <!-- ═══ 披露合计 ↔ K8-1审定合计 勾稽（附注销售费用须等于审定数）═══ -->
    <el-alert v-if="disclosureReconcile.hasData && !disclosureReconcile.isBalanced" type="warning" :closable="false" style="margin-bottom:10px" show-icon>
      <template #title>
        披露本期合计 {{ fmtAmt(disclosureCurrentTotal) }} 与 K8-1 审定合计 {{ fmtAmt(k81AuditedTotal) }} 差异 {{ fmtAmt(disclosureReconcile.diff) }}，请核对披露口径
      </template>
    </el-alert>

    <!-- ═══ 费用性质披露表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">销售费用—按费用性质分类</span>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width:100%" max-height="460" show-summary :summary-method="summaryMethod">
        <el-table-column prop="project" label="项目" min-width="140" fixed />
        <el-table-column prop="currentAmount" label="本期发生额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.currentAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateField(row.id, 'currentAmount', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.priorAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateField(row.id, 'priorAmount', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`变动 = 本期 - 上期 = ${row.currentAmount} - ${row.priorAmount}`">{{ fmtAmt(row.currentAmount - row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'abnormal-cell': isAbnormal(row) }">{{ formatRate(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && !row.isTotal" :model-value="row.remark" size="small" @change="(v: string) => updateField(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 附注说明文本 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">附注说明</span>
          <el-tooltip :content="aiAvailable ? 'AI 辅助生成' : 'AI 服务暂不可用'" placement="top">
            <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly || !aiAvailable" @click="handleAiNarrative"><el-icon><MagicStick /></el-icon> AI生成</el-button>
          </el-tooltip>
        </div>
      </template>
      <el-input v-model="narrativeText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="附注说明文本（可AI辅助生成）" @blur="handleNarrativeSave" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>上市公司按费用性质分类披露销售费用</li>
        <li>表格规格：42行×28列（含合计行，上市标准）</li>
        <li>变动额/变动率为公式列（虚线下划线+tooltip来源）</li>
        <li>数据来源：K8-1审定表，subscribe EventBus自动刷新</li>
        <li>异常波动（|变动率|>30%）红色标记</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabDisclosureListed.vue — 附注披露信息（上市公司）42行×28列
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.6, 6.2
 * Requirements: 8.1, 8.2
 *
 * 功能：
 * - 按费用性质分类披露
 * - 本期/上期/变动额/变动率
 * - 自动从K8-1取数 + subscribe EventBus 'substantive:adjudicated' 刷新
 * - subscribe EventBus 'adjustment:created' (accountCode=6601) 刷新
 * - AI辅助生成说明文本
 */
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'
import { useK8AiGenerate } from '../../composables/useK8AiGenerate'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildK8SyncPayload } from '../../composables/k8NoteSectionMap'
import type { Ref } from 'vue'

const K8_ACCOUNT_CODE = '6601'
const ABNORMAL_THRESHOLD = 0.3 // 30% 波动阈值

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const payload = buildK8SyncPayload('listed', props.wpId || '', disclosureRows.value, narrativeText.value)
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K8', variant: 'listed', accountCode: '6601',
      projectId: props.projectId, sectionIds: ['五、64'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface DisclosureRow {
  id: string
  project: string
  currentAmount: number
  priorAmount: number
  remark: string
  isTotal?: boolean
}

const disclosureRows = ref<DisclosureRow[]>([])
const narrativeText = ref('')
const hasAutoData = ref(false)

// ─── 默认行（上市公司费用性质分类） ──────────────────────────────────────────

const DEFAULT_PROJECTS = [
  '职工薪酬', '差旅费', '业务招待费', '广告宣传费', '运输费',
  '折旧费', '摊销费', '办公费', '通讯费', '物料消耗',
  '租赁费', '装卸费', '保险费', '修理费', '低值易耗品摊销',
  '包装费', '展览费', '会议费', '佣金及手续费', '售后服务费',
  '质量检验费', '样品费', '水电费', '差旅交通费', '仓储费',
  '劳动保护费', '代理费', '销售机构设备折旧', '其他',
]

function initDefaultRows(): void {
  disclosureRows.value = DEFAULT_PROJECTS.map((name, idx) => ({
    id: `row-${idx}`,
    project: name,
    currentAmount: 0,
    priorAmount: 0,
    remark: '',
  }))
}

// ─── 加载已保存数据 ──────────────────────────────────────────────────────────

/** 读 K8-1-audited-by-item（{项目名:{audited,prior}}） */
function _readK81Map(): Record<string, { audited?: number; prior?: number }> {
  const adjData = props.allResponses.get('K8-1-audited-by-item')
  if (!adjData?.remark) return {}
  try {
    const m = JSON.parse(adjData.remark)
    return m && typeof m === 'object' ? m : {}
  } catch { return {} }
}

/** 从 K8-1 审定表项目动态构建披露行（对齐源模板 B7='审定表K8-1'!A7） */
function buildRowsFromK81(): DisclosureRow[] | null {
  const map = _readK81Map()
  const names = Object.keys(map)
  if (!names.length) return null
  return names.map((name, idx) => ({
    id: `k81-${idx}`,
    project: name,
    currentAmount: Number(map[name].audited ?? 0),
    priorAmount: Number(map[name].prior ?? 0),
    remark: '',
  }))
}

function loadSavedData(): void {
  const saved = props.allResponses.get('K8-disclosure-listed-rows')
  if (saved?.remark) {
    try {
      disclosureRows.value = JSON.parse(saved.remark)
    } catch { initDefaultRows() }
  } else {
    // 无手工保存时：优先用 K8-1 审定表项目动态构建，否则回退默认清单
    const fromK81 = buildRowsFromK81()
    if (fromK81) { disclosureRows.value = fromK81; hasAutoData.value = true }
    else initDefaultRows()
  }

  const savedNarrative = props.allResponses.get('K8-disclosure-listed-narrative')
  if (savedNarrative?.remark) {
    narrativeText.value = savedNarrative.remark
  }
}

// ─── 自动取数（从K8-1审定表） ────────────────────────────────────────────────

function applyAutoFill(): void {
  const data = _readK81Map()
  const names = Object.keys(data)
  if (!names.length) return
  hasAutoData.value = true
  // 1) 填充已存在的同名行
  const existing = new Set(disclosureRows.value.map(r => r.project))
  for (const row of disclosureRows.value) {
    const src = (data as any)[row.project]
    if (src) {
      row.currentAmount = Number(src.currentAmount ?? src.audited ?? 0)
      row.priorAmount = Number(src.priorAmount ?? src.prior ?? 0)
    }
  }
  // 2) 追加 K8-1 有、披露表尚无的费用项目（动态项目对齐）
  let idx = disclosureRows.value.length
  for (const name of names) {
    if (!existing.has(name)) {
      const src = (data as any)[name]
      disclosureRows.value.push({
        id: `k81-${idx++}`,
        project: name,
        currentAmount: Number(src.audited ?? 0),
        priorAmount: Number(src.prior ?? 0),
        remark: '',
      })
    }
  }
  persistRows()
}

// ─── 字段更新 + 持久化 ──────────────────────────────────────────────────────

function updateField(id: string, field: string, value: any): void {
  const row = disclosureRows.value.find(r => r.id === id)
  if (row) {
    ;(row as any)[field] = value
    persistRows()
  }
}

function persistRows(): void {
  emit('save', 'K8-disclosure-listed-rows', { remark: JSON.stringify(disclosureRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleNarrativeSave(): void {
  emit('save', 'K8-disclosure-listed-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, { wpCode: 'K8', variant: 'listed', text: narrativeText.value })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 合计汇总方法 ────────────────────────────────────────────────────────────

function summaryMethod({ columns, data }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop === 'currentAmount') return fmtAmt(data.reduce((s, r) => s + (r.currentAmount || 0), 0))
    if (prop === 'priorAmount') return fmtAmt(data.reduce((s, r) => s + (r.priorAmount || 0), 0))
    if (idx === 3) {
      const totalCur = data.reduce((s, r) => s + (r.currentAmount || 0), 0)
      const totalPri = data.reduce((s, r) => s + (r.priorAmount || 0), 0)
      return fmtAmt(totalCur - totalPri)
    }
    return ''
  })
}

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K8_ACCOUNT_CODE || payload.wpCode === 'K8') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  // 过滤 accountCode=6601 的调整分录事件，触发数据刷新
  if (payload && payload.accountCode === K8_ACCOUNT_CODE) {
    applyAutoFill()
  }
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── UI Helpers ──────────────────────────────────────────────────────────────

// ─── 披露合计 ↔ K8-1审定合计 勾稽 ──────────────────────────────────────────
const disclosureCurrentTotal = computed(() => disclosureRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0))
const k81AuditedTotal = computed(() => {
  const m = _readK81Map()
  return Object.values(m).reduce((s: number, v: any) => s + Number(v?.audited ?? 0), 0)
})
const disclosureReconcile = computed(() => {
  const diff = disclosureCurrentTotal.value - k81AuditedTotal.value
  return { diff, hasData: Math.abs(k81AuditedTotal.value) > 0.005, isBalanced: Math.abs(diff) < 0.01 }
})

function isAbnormal(row: DisclosureRow): boolean {
  if (!row.priorAmount || row.priorAmount === 0) return false
  const rate = Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount)
  return rate > ABNORMAL_THRESHOLD
}

function formatRate(row: DisclosureRow): string {
  if (!row.priorAmount || row.priorAmount === 0) return '—'
  const rate = (row.currentAmount - row.priorAmount) / row.priorAmount
  return (rate * 100).toFixed(1) + '%'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── AI 辅助（统一 /ai/generate-text 端点）─────────────────────────────────
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useK8AiGenerate({
  wpId: computed(() => props.wpId),
})

function _disclosureContext(): Record<string, unknown> {
  const totalCur = disclosureRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0)
  const totalPri = disclosureRows.value.reduce((s, r) => s + (r.priorAmount || 0), 0)
  return {
    本期合计: totalCur,
    上期合计: totalPri,
    披露口径: '上市公司按费用性质分类披露销售费用',
  }
}

async function handleAiGenerate(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'k8-disclosure-listed-note',
    narrativeText.value || '',
    { ..._disclosureContext(), 任务: '请生成销售费用附注披露说明（按费用性质分类的构成概述、本期较上期主要变动及原因）' },
    'AI 生成 · 附注披露说明',
  )
  if (text) { narrativeText.value = text; handleNarrativeSave() }
}

async function handleAiNarrative(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'k8-disclosure-listed-narrative',
    narrativeText.value || '',
    { ..._disclosureContext(), 任务: '请生成销售费用附注说明文本（重大变动分析、异常波动解释）' },
    'AI 生成 · 附注说明',
  )
  if (text) { narrativeText.value = text; handleNarrativeSave() }
}
</script>

<style scoped>
.k8-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.disclosure-card { margin-bottom: 14px; }
.disclosure-card :deep(.el-card__header) { padding: 10px 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.formula-cell { text-decoration: underline dashed; cursor: help; color: #409eff; }
.abnormal-cell { color: #f56c6c; font-weight: 600; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table__footer-wrapper td) { font-weight: 600; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
