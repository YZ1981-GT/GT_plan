<template>
  <div class="m10-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息核对（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-listed')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司其他权益工具附注披露（47×19）：</strong>
        按CAS37《金融工具列报》要求，分项列示各权益工具（永续债/优先股等）的发行条款、分类依据、期初/本期变动/期末余额。
        数据自动从M10-1审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
        表内分为：①工具基本信息 ②权益工具变动明细 ③利息/股息信息。
      </div>
    </div>

    <!-- ═══ Section 1: 权益工具变动明细（核心表格） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>其他权益工具变动明细</span>
          <el-button size="small" @click="handleAI('section-instrument-changes')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="instrumentRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="项目" min-width="200" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal }">{{ row.item }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初余额" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <WpAmountInput
                :model-value="row.beginBalance"
                @update:model-value="(val: number) => updateInstrumentRow($index, 'beginBalance', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期发行" width="140" align="right">
          <template #header>
            <el-tooltip content="贷方增加：发行/转入（权益类贷方）" placement="top">
              <span class="formula-col-header">本期发行</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <WpAmountInput
                :model-value="row.issuance"
                @update:model-value="(val: number) => updateInstrumentRow($index, 'issuance', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.issuance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期赎回/转换" width="140" align="right">
          <template #header>
            <el-tooltip content="借方减少：赎回/转换/注销（权益类借方）" placement="top">
              <span class="formula-col-header">本期赎回/转换</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <WpAmountInput
                :model-value="row.redemption"
                @update:model-value="(val: number) => updateInstrumentRow($index, 'redemption', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.redemption) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="应付利息/股息" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <WpAmountInput
                :model-value="row.interestDividend"
                @update:model-value="(val: number) => updateInstrumentRow($index, 'interestDividend', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.interestDividend) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末余额" width="140" align="right">
          <template #header>
            <el-tooltip content="期末=期初+本期发行-本期赎回（权益类贷方）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 工具条款摘要 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>工具条款摘要（分类依据）</span>
          <el-button size="small" @click="handleAI('section-terms-summary')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="termsSummary"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :readonly="isReadonly"
        placeholder="摘要各权益工具的关键条款（票面利率、期限、赎回条款、转股条件、续期安排等），并说明按CAS37分类为权益工具的依据..."
        @change="handleTermsSummaryChange"
      />
    </el-card>

    <!-- ═══ Section 3: 利息/股息分配 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>利息/股息分配说明</span>
          <el-button size="small" @click="handleAI('section-distribution')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="distributionNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明各权益工具的利息/股息分配情况（是否递延、是否强制付息、是否可累积等）..."
        @change="handleDistributionNoteChange"
      />
    </el-card>

    <!-- ═══ Section 4: 其他披露事项 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>其他披露事项</span>
          <el-button size="small" @click="handleAI('section-other')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="otherDisclosure"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="其他需披露事项（投资者保护条款、违约事件、交叉违约、评级变化等）..."
        @change="handleOtherDisclosureChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从M10-1审定表自动拉取（审定数=期末余额）</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司需按CAS37详细披露分类依据和关键条款</li>
        <li>期末 = 期初 + 本期发行 - 本期赎回/转换（权益类贷方）</li>
        <li>需分别列示永续债、优先股等各类权益工具的变动情况</li>
        <li>利息/股息分配需说明是否递延（递延不构成违约=权益；强制付息=负债特征）</li>
        <li>格式：47行×19列（含多个子表区域）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabDisclosureListed — 附注披露信息核对（上市公司）47×19
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 4.6
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - 表格: 项目 | 期初 | 本期发行 | 本期赎回/转换 | 利息/股息 | 期末
 * - 行: 永续债(分项) | 优先股(分项) | 其他 | 合计
 * - Auto-refresh from M10-1 (subscribe 'substantive:adjudicated')
 * - 条款摘要/利息分配/其他披露textarea sections
 * - AI辅助 per section title
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useM10FormData } from '../../composables/useM10FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { calcEquityEndBalance } from '../../composables/useM10FormulaEngine'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildM10ListedSyncPayload, type M10BasicRow, type M10MovementRow, type M10HoldersRow } from '../../composables/m10NoteSectionMap'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM10FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 同步链路 ───────────────────────────────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  // M10 Listed Tab 当前只有一张变动表（暂无基本情况表/持有者信息表独立录入）
  // 将变动表数据映射到三表载荷
  const movementRows: M10MovementRow[] = dataRows.value.map((r: any) => ({
    label: r.item || '',
    beginQty: 0,  // UI 暂无数量维度
    beginValue: Number(r.beginBalance) || 0,
    increaseQty: 0,
    increaseValue: Number(r.issuance) || 0,
    decreaseQty: 0,
    decreaseValue: Number(r.redemption) || 0,
  }))
  // 基本情况表（空载荷，待 Tab 增强后填充）
  const basicRows: M10BasicRow[] = movementRows.map((r) => ({
    label: r.label,
    issueTime: '',
    classification: '',
    dividendRate: '',
    issuePrice: 0,
    quantity: 0,
    amount: r.beginValue,
    maturity: '',
    conversionTerms: '',
    conversionStatus: '',
  }))
  // 持有者信息表（空载荷）
  const holdersRows: M10HoldersRow[] = []
  const noteText = [termsSummary.value, distributionNote.value, otherDisclosure.value].filter(Boolean).join('\n\n')
  const payload = buildM10ListedSyncPayload(props.wpId, basicRows, movementRows, holdersRows, noteText || undefined)
  if (!payload) return
  try {
    const { default: request } = await import('@/utils/request')
    await request.post(`/api/workpapers/${props.wpId}/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const { scheduleAutoSync } = useDisclosureAutoSync(syncToDisclosureNotes)

// ─── State ───────────────────────────────────────────────────────────────────

interface InstrumentRow {
  item: string
  beginBalance: number
  issuance: number
  redemption: number
  interestDividend: number
  endBalance: number
  _isTotal?: boolean
}

const dataRows = ref<InstrumentRow[]>([
  { item: '永续债 — 第一期', beginBalance: 0, issuance: 0, redemption: 0, interestDividend: 0, endBalance: 0 },
  { item: '永续债 — 第二期', beginBalance: 0, issuance: 0, redemption: 0, interestDividend: 0, endBalance: 0 },
  { item: '永续债 — 第三期', beginBalance: 0, issuance: 0, redemption: 0, interestDividend: 0, endBalance: 0 },
  { item: '优先股 — A系列', beginBalance: 0, issuance: 0, redemption: 0, interestDividend: 0, endBalance: 0 },
  { item: '优先股 — B系列', beginBalance: 0, issuance: 0, redemption: 0, interestDividend: 0, endBalance: 0 },
  { item: '其他权益工具', beginBalance: 0, issuance: 0, redemption: 0, interestDividend: 0, endBalance: 0 },
])

const termsSummary = ref('')
const distributionNote = ref('')
const otherDisclosure = ref('')

// ─── 合计行 + 计算 ──────────────────────────────────────────────────────────

const instrumentRows = computed<InstrumentRow[]>(() => {
  const rows: InstrumentRow[] = dataRows.value.map(r => ({
    ...r,
    endBalance: calcEquityEndBalance(r.beginBalance, r.issuance, r.redemption),
  }))
  // 合计行
  const totalBegin = rows.reduce((s, r) => s + r.beginBalance, 0)
  const totalIssuance = rows.reduce((s, r) => s + r.issuance, 0)
  const totalRedemption = rows.reduce((s, r) => s + r.redemption, 0)
  const totalInterest = rows.reduce((s, r) => s + r.interestDividend, 0)
  rows.push({
    item: '合计',
    beginBalance: totalBegin,
    issuance: totalIssuance,
    redemption: totalRedemption,
    interestDividend: totalInterest,
    endBalance: calcEquityEndBalance(totalBegin, totalIssuance, totalRedemption),
    _isTotal: true,
  })
  return rows
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateInstrumentRow(index: number, field: 'beginBalance' | 'issuance' | 'redemption' | 'interestDividend', val: number): void {
  if (index >= 0 && index < dataRows.value.length) {
    dataRows.value[index][field] = val
    formData.debouncedSave(`M10-disclosure-listed-${index}-${field}`, { remark: String(val) })
    scheduleAutoSync()
  }
}

function getRowClassName({ row }: { row: InstrumentRow; rowIndex: number }): string {
  return row._isTotal ? 'total-row' : ''
}

function handleTermsSummaryChange() {
  formData.debouncedSave('M10-disclosure-listed-terms-summary', { remark: termsSummary.value || null })
  scheduleAutoSync()
}

function handleDistributionNoteChange() {
  formData.debouncedSave('M10-disclosure-listed-distribution-note', { remark: distributionNote.value || null })
  scheduleAutoSync()
}

function handleOtherDisclosureChange() {
  formData.debouncedSave('M10-disclosure-listed-other-disclosure', { remark: otherDisclosure.value || null })
  scheduleAutoSync()
}

const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const totalRow = instrumentRows.value.find(r => r._isTotal)
    const context: Record<string, string> = {
      科目: '4003 其他权益工具 / 附注披露信息（上市公司）',
      区段: section,
      期末余额合计: fmtAmount(totalRow?.endBalance ?? 0),
      本期发行合计: fmtAmount(totalRow?.issuance ?? 0),
      本期赎回合计: fmtAmount(totalRow?.redemption ?? 0),
      利息股息合计: fmtAmount(totalRow?.interestDividend ?? 0),
    }
    if (section === 'section-terms-summary') {
      const text = await generateAiText({ section: 'm10-disclosure-listed-terms', context, existingContent: termsSummary.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      termsSummary.value = text; handleTermsSummaryChange()
    } else if (section === 'section-distribution') {
      const text = await generateAiText({ section: 'm10-disclosure-listed-distribution', context, existingContent: distributionNote.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      distributionNote.value = text; handleDistributionNoteChange()
    } else if (section === 'section-other') {
      const text = await generateAiText({ section: 'm10-disclosure-listed-other', context, existingContent: otherDisclosure.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      otherDisclosure.value = text; handleOtherDisclosureChange()
    } else {
      const text = await generateAiText({ section: `m10-disclosure-listed-${section}`, context })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      ElMessageBox.alert(text, 'AI 辅助 — 其他权益工具附注建议', { confirmButtonText: '知道了' }).catch(() => { /* 用户关闭 */ })
    }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M10-disclosure-listed', '其他权益工具附注（上市）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  for (let i = 0; i < dataRows.value.length; i++) {
    for (const field of ['beginBalance', 'issuance', 'redemption', 'interestDividend'] as const) {
      const resp = formData.allResponses.value.get(`M10-disclosure-listed-${i}-${field}`)
      if (resp?.remark) {
        dataRows.value[i][field] = Number(resp.remark) || 0
      }
    }
  }
  const termsResp = formData.allResponses.value.get('M10-disclosure-listed-terms-summary')
  if (termsResp?.remark) termsSummary.value = termsResp.remark
  const distResp = formData.allResponses.value.get('M10-disclosure-listed-distribution-note')
  if (distResp?.remark) distributionNote.value = distResp.remark
  const otherResp = formData.allResponses.value.get('M10-disclosure-listed-other-disclosure')
  if (otherResp?.remark) otherDisclosure.value = otherResp.remark
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => restoreData())
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m10-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }
.m10-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m10-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m10-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
