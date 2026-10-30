<template>
  <div class="k13-tab-disclosure-soe">
    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按去向披露本期确认的营业外支出金额（国有企业版）。数据来源K13-1审定表，subscribe 'substantive:adjudicated' + 'adjustment:created' 事件自动刷新。国企版18行×5列，简化格式侧重分类汇总。</p>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K13-1" :context-project-id="props.projectId" />
      <GtIndexChip value="K13-2" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 主表：营业外支出按去向分类披露（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">营业外支出披露明细（国有企业）</span>
          <div class="section-actions">
            <el-button size="small" type="primary" link @click="applyAutoFill()">
              <el-icon><Refresh /></el-icon>从审定表取数
            </el-button>
            <el-button size="small" type="primary" link @click="generateAI('disclosure-soe')">
              <el-icon><MagicStick /></el-icon>AI辅助
            </el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="syncToDisclosureNotes">同步到附注</el-button>
            <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
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
        <el-table-column prop="category" label="项目（去向分类）" min-width="180" />
        <el-table-column prop="currentAmount" label="本期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'amount-zero': !row.currentAmount }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="nonRecurring" label="计入当期非经常性损益的金额" min-width="180" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              v-model="row.nonRecurring"
              placeholder="0.00"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ fmtAmt(row.nonRecurring) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="160">
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
        placeholder="输入营业外支出附注披露说明（国企格式）..."
        @change="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-tips">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从K13-1审定表自动拉取（按去向分类行）</li>
        <li>订阅 'substantive:adjudicated' + 'adjustment:created' 事件自动刷新</li>
        <li>国企需额外关注国有资产处置损失等特有项目</li>
        <li>营业外支出中罚款/捐赠为典型非经常性损益项目</li>
        <li>与日常活动无关的损失才纳入营业外支出</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabDisclosureSoe.vue — K13 附注披露信息（国有企业）
 *
 * 18行×5列，按去向披露+自动取数+AI辅助
 * Spec: .kiro/specs/k13-non-operating-expense/ Task 4.6
 * Requirements: 6.1
 *
 * 功能：
 * - 按去向分类披露营业外支出信息（国有企业版）
 * - 自动从K13-1审定表取数（subscribe EventBus 'substantive:adjudicated'）
 * - AI辅助文本生成按钮（每个section标题行右侧放AI按钮）
 * - GtIndexChip跨底稿引用：K13-1 / K13-2 / A13
 * - el-card包裹
 * - 编制提示details折叠底部
 *
 * EventBus:
 * - subscribe: 'substantive:adjudicated' (filter accountCode=6711 or wpCode='K13')
 * - subscribe: 'adjustment:created' (filter wpCode='K13') — 调整分录变化时刷新
 * - publish: 'disclosure:note-text-updated' (noteId='non_operating_expense')
 */
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { generateK13AiText } from '../../composables/useK13AiText'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { K13_NOTE_SECTION, buildK13SyncPayload } from '../../composables/k13NoteSectionMap'
import {
  K13_DISCLOSURE_CATEGORIES,
  K13_DISCLOSURE_DYN_PREFIX,
  K13_DISCLOSURE_NARRATIVE_ITEM,
  applyK13AutoFill,
  k13DefaultDisclosureRows,
  k13DisclosureSyncRows,
  loadK13DisclosureState,
  loadK13DynamicRows,
  type K13DisclosureTabRow,
} from '../../composables/k13DisclosureTabState'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'K13', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ACCOUNT_CODE = '6711'
const ABNORMAL_THRESHOLD = 0.5
const VARIANT = 'soe'
const DYN_PREFIX = K13_DISCLOSURE_DYN_PREFIX[VARIANT]

/** 营业外支出标准去向分类（国企版，精简分类） */
const CATEGORIES = K13_DISCLOSURE_CATEGORIES[VARIANT]

// ─── Types / State ───────────────────────────────────────────────────────────
// 去向分类、披露行、读回 / 动态行 / 审定表取数与附注页离屏同步共用（k13DisclosureTabState，spec note-pull-followup-closure R1）

type DisclosureRow = K13DisclosureTabRow

const disclosureRows = ref<DisclosureRow[]>(k13DefaultDisclosureRows(VARIANT))
const narrativeText = ref('')
const totalAdjudicated = ref(0)

// ─── Load saved data from allResponses ───────────────────────────────────────

function loadSavedData(): void {
  const saved = loadK13DisclosureState(props.allResponses, VARIANT)
  disclosureRows.value = saved.rows
  if (saved.narrative != null) narrativeText.value = saved.narrative
}

/** 加载动态追加披露行（K13-1 中未匹配固定分类的去向） */
function loadDynamicRows(): void {
  loadK13DynamicRows(disclosureRows.value, props.allResponses, VARIANT)
}

function persistDynamicRow(row: DisclosureRow): void {
  const safeKey = DYN_PREFIX + row.category.replace(/[^\w\u4e00-\u9fa5]/g, '_')
  emit('save', safeKey, JSON.stringify({
    category: row.category,
    currentAmount: row.currentAmount,
    priorAmount: row.priorAmount,
    nonRecurring: row.nonRecurring,
    remark: row.remark,
  }))
}

/**
 * 从 K13-1 审定表取数（读 `K13-1-rows` 按 name 匹配）：固定分类命中的行逐行保存，未匹配的去向追加 / 更新为动态行并保存。
 * @param silent true 时不弹提示（EventBus 自动刷新用）
 */
function applyAutoFill(silent = false): void {
  const res = applyK13AutoFill(disclosureRows.value, props.allResponses, VARIANT, {
    onFixedFilled: handleRowChange,
    onDynamicFilled: persistDynamicRow,
  })
  if (!res) {
    if (!silent) ElMessage.warning('未找到 K13-1 审定表数据，请先编制审定表')
    return
  }
  totalAdjudicated.value = res.totalAudited
  if (!silent) ElMessage.success(res.matched > 0 ? `已从审定表取数（匹配 ${res.matched} 项）` : '审定表暂无可匹配去向金额')
}

// ─── EventBus: subscribe 'substantive:adjudicated' + 'adjustment:created' ────

function handleAdjudicated(payload: any): void {
  if (!payload) return
  if (payload.accountCode === ACCOUNT_CODE || payload.wpCode === 'K13') {
    if (payload.auditedAmount != null) {
      totalAdjudicated.value = Number(payload.auditedAmount)
    }
    applyAutoFill(true)
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload) return
  // 调整分录变化时刷新附注数据（K13-3 → A13 + 附注刷新）
  if (payload.wpCode === 'K13') {
    applyAutoFill(true)
  }
}

// ─── Save handlers ───────────────────────────────────────────────────────────

function handleRowChange(row: DisclosureRow): void {
  const idx = disclosureRows.value.indexOf(row)
  if (idx >= 0) {
    emit('save', `K13-disc-soe-row-${idx}`, JSON.stringify({
      currentAmount: row.currentAmount,
      priorAmount: row.priorAmount,
      nonRecurring: row.nonRecurring,
      remark: row.remark,
    }))
  }
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleNarrativeSave(): void {
  emit('save', K13_DISCLOSURE_NARRATIVE_ITEM[VARIANT], { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    noteId: 'non_operating_expense',
    wpCode: 'K13',
    variant: 'soe',
    accountCode: ACCOUNT_CODE,
    projectId: props.projectId,
    sectionIds: [K13_NOTE_SECTION.soe],
    text: narrativeText.value,
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId || props.isReadonly) return
  // 含第 4 列「计入当期非经常性损益的金额」（源模板必填列）
  const payload = buildK13SyncPayload(VARIANT, props.wpId || '', k13DisclosureSyncRows(disclosureRows.value), narrativeText.value)
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'K13', variant: 'soe', accountCode: '6711',
      projectId: props.projectId, sectionIds: [K13_NOTE_SECTION.soe],
    })
    ElMessage.success('已同步到附注')
  } catch { /* silent */ }
}

// ─── AI generation ───────────────────────────────────────────────────────────

async function generateAI(section: string): Promise<void> {
  if (!props.wpId) return
  // context 必须是 dict[str,str]（原 JSON.stringify 整个数组 → 后端 422 静默失败）
  const lines = disclosureRows.value
    .filter(r => r.currentAmount || r.priorAmount)
    .map(r => `${r.category}：本期${r.currentAmount}｜上期${r.priorAmount}`)
    .join('；')
  const content = await generateK13AiText(props.wpId, {
    section,
    prompt: '为 K13 营业外支出底稿生成国有企业附注披露文本，需包含各去向分类的本期/上期发生额及重大变动说明。口径以致同 2025 修订版底稿源模板与附注模版为准；只能使用已提供的项目名称与金额，不得虚构项目、金额或业务背景，无把握的内容留空由审计师补充。',
    context: {
      科目: '6711 营业外支出（国有企业版）',
      去向分类: CATEGORIES.join('/'),
      披露明细: lines || '（暂无数据）',
      审定发生额合计: totalAdjudicated.value,
    },
    existingContent: section === 'narrative' ? narrativeText.value : '',
  })
  if (content && section === 'narrative') {
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
    if (col.property === 'nonRecurring') {
      return fmtAmt(disclosureRows.value.reduce((s, r) => s + (r.nonRecurring || 0), 0))
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

/** 只读金额展示：委托平台金额格式单一真源，保留底稿「0 显示 -」语义 */
function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return fmtAmount(val)
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSavedData()
  loadDynamicRows()
  applyAutoFill(true)
  eventBus.on('substantive:adjudicated' as any, handleAdjudicated)
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
})
</script>

<style scoped>
.k13-tab-disclosure-soe {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #78350f;
}

.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

.cross-refs-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
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
