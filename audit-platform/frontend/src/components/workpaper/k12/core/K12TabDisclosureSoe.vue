<template>
  <div class="k12-tab-disclosure-soe">
    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按来源披露本期确认的营业外收入金额（国有企业版）。数据来源K12-1审定表，subscribe 'substantive:adjudicated' 事件自动刷新。国企版29行×5列，分类及格式与上市版略有差异，增加"国有资产处置收益"等国企特有项目。</p>
    </div>

    <!-- ═══ 主表：营业外收入按来源分类披露（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">营业外收入披露明细（国有企业）</span>
          <div class="section-actions">
            <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
            <el-button size="small" type="primary" link @click="applyAutoFill">
              <el-icon><Refresh /></el-icon>从审定表取数
            </el-button>
            <el-button size="small" type="primary" link @click="generateAI('disclosure-soe')">
              <el-icon><MagicStick /></el-icon>AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="disclosureRows"
        border
        size="small"
        show-summary
        :summary-method="summaryMethod"
        class="disclosure-table"
      >
        <el-table-column prop="category" label="项目（来源分类）" min-width="160" />
        <el-table-column prop="currentAmount" label="本期发生额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.currentAmount"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 100%"
              @change="(v: number | undefined) => { row.currentAmount = v ?? 0; handleRowChange(row) }"
            />
            <span v-else :class="{ 'amount-zero': !row.currentAmount }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 100%"
              @change="(v: number | undefined) => { row.priorAmount = v ?? 0; handleRowChange(row) }"
            />
            <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="nonRecurringAmount" label="计入当期非经常性损益的金额" min-width="150" align="right">
          <template #header>
            <el-tooltip content="源模板必填列：与日常活动无关的利得多列为非经常性损益" placement="top">
              <span style="border-bottom:1px dashed #909399;cursor:help">计入非经常性损益</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.nonRecurringAmount"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 100%"
              @change="(v: number | undefined) => { row.nonRecurringAmount = v ?? 0; handleRowChange(row) }"
            />
            <span v-else>{{ fmtAmt(row.nonRecurringAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同比变动" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'abnormal-rate': isAbnormal(row) }">{{ formatRate(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="披露说明"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 与企业日常活动无关的政府补助明细（源模板国企版子表） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">与企业日常活动无关的政府补助明细</span>
          <el-button v-if="!isReadonly" size="small" type="primary" plain @click="addGovGrantRow">+ 新增明细</el-button>
        </div>
      </template>
      <el-table :data="govGrantRows" border size="small" class="disclosure-table" empty-text="暂无政府补助明细">
        <el-table-column type="index" label="#" width="42" align="center" />
        <el-table-column prop="item" label="项目" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item" size="small" placeholder="政府补助项目名称" @change="(v: string) => updateGovGrant(row.rowKey, 'item', v)" />
            <span v-else>{{ row.item || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentAmount" label="本期发生额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateGovGrant(row.rowKey, 'currentAmount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateGovGrant(row.rowKey, 'priorAmount', v ?? 0)" />
            <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button link size="small" type="danger" @click="removeGovGrantRow(row.rowKey)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="govgrant-total">
        合计　本期：{{ fmtAmt(govGrantTotalCurrent) }}　|　上期：{{ fmtAmt(govGrantTotalPrior) }}
      </div>
    </el-card>

    <!-- ═══ 审计说明（AI辅助文本区域） ═══ -->
    <el-card shadow="never" class="narrative-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">附注披露说明</span>
          <el-button size="small" type="primary" link @click="generateAI('narrative')">
            <el-icon><MagicStick /></el-icon>AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="输入营业外收入附注披露说明（国企格式）..."
        @change="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-tips">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从K12-1审定表自动拉取（按来源分类行）</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>国企需额外关注国有资产处置收益等特有项目</li>
        <li>营业外收入各来源占比超过50%时标注重大项目</li>
        <li>与日常活动无关的利得才纳入营业外收入（非其他收益6117）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabDisclosureSoe.vue — K12 附注披露信息（国有企业）
 *
 * 29行5列，按来源披露+自动取数+AI辅助
 * Spec: .kiro/specs/k12-non-operating-income/ Task 6.1
 * Requirements: 6.1
 *
 * 功能：
 * - 按来源分类披露营业外收入信息（国有企业版）
 * - 自动从K12-1审定表取数（subscribe EventBus 'substantive:adjudicated'）
 * - AI辅助文本生成按钮（每个section标题行右侧放AI按钮）
 * - el-card包裹
 * - 编制提示details折叠底部
 *
 * EventBus:
 * - subscribe: 'substantive:adjudicated' (filter accountCode=6301)
 * - publish: 'disclosure:note-text-updated' (noteId='non_operating_income')
 */
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { generateK12AiText } from '../../composables/useK12AiText'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildK12SyncPayload } from '../../composables/k12NoteSectionMap'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

// ─── Constants ───────────────────────────────────────────────────────────────

const ACCOUNT_CODE = '6301'
const ABNORMAL_THRESHOLD = 0.5

/**
 * 营业外收入标准来源分类（国企版）
 * P0-6 修复：删除臆造的「国有资产处置收益」—— 源模板国企版分类与上市版相同，
 * 无此项目（违「禁止自造披露内容」铁律）。
 */
const CATEGORIES = [
  '与日常活动无关的政府补助',
  '捐赠利得',
  '盘盈利得（不包括存货盘盈及固定资产盘盈）',
  '碳排放配额出售利得',
  '其他',
]

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  category: string
  currentAmount: number
  priorAmount: number
  /** 计入当期非经常性损益的金额（源模板必填列） */
  nonRecurringAmount: number
  remark: string
}

/** 与企业日常活动无关的政府补助明细行（源模板国企版子表） */
interface GovGrantRow {
  rowKey: string
  item: string
  currentAmount: number
  priorAmount: number
}

// ─── State ───────────────────────────────────────────────────────────────────

const disclosureRows = ref<DisclosureRow[]>(
  CATEGORIES.map(c => ({ category: c, currentAmount: 0, priorAmount: 0, nonRecurringAmount: 0, remark: '' }))
)
const govGrantRows = ref<GovGrantRow[]>([])
const narrativeText = ref('')
const totalAdjudicated = ref(0)

// ─── Load saved data from allResponses ───────────────────────────────────────

function loadSavedData(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const key = `K12-disc-soe-row-${i}`
    const saved = props.allResponses.get(key)
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          disclosureRows.value[i] = {
            category: CATEGORIES[i],
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            nonRecurringAmount: Number(parsed.nonRecurringAmount || 0),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore parse errors */ }
    }
  }

  const narrativeSaved = props.allResponses.get('K12-disclosure-soe-narrative')
  if (narrativeSaved) {
    narrativeText.value = narrativeSaved.remark || narrativeSaved.conclusion || ''
  }

  // 政府补助明细子表
  const ggSaved = props.allResponses.get('K12-disc-soe-govgrant-rows')
  if (ggSaved) {
    try {
      const raw = ggSaved.remark ?? ggSaved.conclusion ?? ggSaved
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) govGrantRows.value = parsed
    } catch { /* ignore */ }
  }
}

// ─── Auto-fill from K12-1 adjudicated data ───────────────────────────────────

/**
 * 从 K12-1 审定表取数（P0 修复：原读 `K12-1-row-${i}-audited` 死键，
 * useK12Adjudication 从不写 → 恒 no-op；改读 `K12-1-rows` 按 name 匹配）。
 * @param silent true 时不弹提示（EventBus 自动刷新用）
 */
function applyAutoFill(silent = false): void {
  const saved = props.allResponses.get('K12-1-rows')
  if (!saved) {
    if (!silent) ElMessage.warning('未找到 K12-1 审定表数据，请先编制审定表')
    return
  }
  let k12Rows: any[] = []
  try {
    const raw = saved.remark ?? saved.conclusion ?? saved
    k12Rows = typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch { return }
  if (!Array.isArray(k12Rows)) return

  const byName = new Map<string, { audited: number; prior: number }>()
  for (const r of k12Rows) {
    const audited = Number(
      r.audited ?? (Number(r.unadjusted || 0) + Number(r.aje || 0) + Number(r.rje || 0)),
    )
    const prior = Number(
      r.priorAudited ?? (Number(r.priorUnadj || 0) + Number(r.priorAje || 0) + Number(r.priorRje || 0)),
    )
    byName.set(String(r.name || '').trim(), { audited, prior })
  }

  let matched = 0
  for (const row of disclosureRows.value) {
    const hit = byName.get(row.category.trim())
    if (hit) {
      row.currentAmount = hit.audited
      row.priorAmount = hit.prior
      handleRowChange(row)
      matched++
    }
  }
  totalAdjudicated.value = k12Rows.reduce((s, r) => s + Number(r.audited ?? 0), 0)
  if (!silent) ElMessage.success(`已从 K12-1 审定表带入 ${matched} 项`)
}

// ─── EventBus: subscribe 'substantive:adjudicated' ───────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload) return
  if (payload.accountCode === ACCOUNT_CODE || payload.wpCode === 'K12') {
    if (payload.auditedAmount != null) {
      totalAdjudicated.value = Number(payload.auditedAmount)
    }
    applyAutoFill(true)
  }
}

// ─── Save handlers ───────────────────────────────────────────────────────────

function handleRowChange(row: DisclosureRow): void {
  const idx = disclosureRows.value.indexOf(row)
  if (idx >= 0) {
    emit('save', `K12-disc-soe-row-${idx}`, {
      currentAmount: row.currentAmount,
      priorAmount: row.priorAmount,
      nonRecurringAmount: row.nonRecurringAmount,
      remark: row.remark,
    })
  }
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 政府补助明细子表 CRUD ────────────────────────────────────────────────────

let ggIdCounter = Date.now()

function persistGovGrant(): void {
  emit('save', 'K12-disc-soe-govgrant-rows', JSON.stringify(govGrantRows.value))
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function addGovGrantRow(): void {
  govGrantRows.value.push({ rowKey: `gg-${++ggIdCounter}`, item: '', currentAmount: 0, priorAmount: 0 })
  persistGovGrant()
}

function removeGovGrantRow(rowKey: string): void {
  govGrantRows.value = govGrantRows.value.filter(r => r.rowKey !== rowKey)
  persistGovGrant()
}

function updateGovGrant(rowKey: string, field: keyof GovGrantRow, value: any): void {
  const r = govGrantRows.value.find(x => x.rowKey === rowKey)
  if (r) { (r as any)[field] = value; persistGovGrant() }
}

const govGrantTotalCurrent = computed(() => govGrantRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0))
const govGrantTotalPrior = computed(() => govGrantRows.value.reduce((s, r) => s + (r.priorAmount || 0), 0))

function handleNarrativeSave(): void {
  emit('save', 'K12-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    noteId: 'non_operating_income',
    wpCode: 'K12',
    variant: 'soe',
    text: narrativeText.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  const payload = buildK12SyncPayload('soe', props.wpId || '',
    disclosureRows.value.map(r => ({ project: r.category, currentAmount: r.currentAmount, priorAmount: r.priorAmount })),
    narrativeText.value)
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K12', variant: 'soe', accountCode: '6301',
      projectId: props.projectId, sectionIds: ['八、76'],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── AI generation ───────────────────────────────────────────────────────────

async function generateAI(section: string): Promise<void> {
  if (!props.wpId) return
  // P0 修复：context 必须是 dict[str,str]（原传 JSON.stringify 字符串 → 后端 422）
  const context: Record<string, unknown> = {
    来源分类: CATEGORIES.join('/'),
    审定发生额合计: totalAdjudicated.value,
    各来源本期发生额: disclosureRows.value
      .map(r => `${r.category}=${fmtAmt(r.currentAmount)}`)
      .join('；'),
  }
  const content = await generateK12AiText(props.wpId, {
    prompt: '你是资深审计师。请为营业外收入生成国有企业附注披露文本，按来源分类说明本期发生额、同比变动及非经常性损益列报（国企格式，关注与日常活动无关的政府补助明细）。',
    section: section === 'narrative' ? 'K12-disclosure-soe-narrative' : section,
    context,
    existingContent: narrativeText.value,
  })
  if (content) {
    narrativeText.value = content
    handleNarrativeSave()
  }
}

// ─── Table helpers ───────────────────────────────────────────────────────────

const totalCurrentAmount = computed(() =>
  disclosureRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0)
)

function summaryMethod({ columns }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'currentAmount') return fmtAmt(totalCurrentAmount.value)
    if (col.property === 'priorAmount') {
      return fmtAmt(disclosureRows.value.reduce((s, r) => s + (r.priorAmount || 0), 0))
    }
    if (col.property === 'nonRecurringAmount') {
      return fmtAmt(disclosureRows.value.reduce((s, r) => s + (r.nonRecurringAmount || 0), 0))
    }
    return ''
  })
}

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

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSavedData()
  applyAutoFill(true)
  eventBus.on('substantive:adjudicated' as any, handleAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
})
</script>

<style scoped>
.k12-tab-disclosure-soe {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
}

.disclosure-card,
.narrative-card {
  margin: 0;
}

.disclosure-table {
  font-size: var(--wp-font-size, 13px);
}

.amount-zero {
  color: var(--el-text-color-placeholder);
}

.abnormal-rate {
  color: var(--el-color-danger);
  font-weight: 600;
}

.govgrant-total {
  margin-top: 8px;
  text-align: right;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
}

.compile-tips {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-tips summary {
  cursor: pointer;
  font-weight: 500;
}

.compile-tips ul {
  margin: 8px 0 0;
  padding-left: 20px;
}
</style>
