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
        <strong>上市公司其他权益工具变动披露：</strong>
        本页维护各权益工具期初、本期增加、本期减少和期末的数量及账面价值。
        每行三组数量均已录入后才同步；基本情况和持有者信息由附注端维护，本页不会用空表覆盖。
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

        <el-table-column label="期初数量" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!row._isTotal && !isReadonly" :model-value="row.beginQty" :controls="false"
              @change="(val: number | undefined) => updateInstrumentRow($index, 'beginQty', val ?? null)" />
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初账面价值" width="140" align="right">
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

        <el-table-column label="本期增加数量" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!row._isTotal && !isReadonly" :model-value="row.increaseQty" :controls="false"
              @change="(val: number | undefined) => updateInstrumentRow($index, 'increaseQty', val ?? null)" />
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.increaseQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加账面价值" width="140" align="right">
          <template #header>
            <el-tooltip content="贷方增加：发行/转入（权益类贷方）" placement="top">
              <span class="formula-col-header">本期增加账面价值</span>
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

        <el-table-column label="本期减少数量" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!row._isTotal && !isReadonly" :model-value="row.decreaseQty" :controls="false"
              @change="(val: number | undefined) => updateInstrumentRow($index, 'decreaseQty', val ?? null)" />
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.decreaseQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少账面价值" width="140" align="right">
          <template #header>
            <el-tooltip content="借方减少：赎回/转换/注销（权益类借方）" placement="top">
              <span class="formula-col-header">本期减少账面价值</span>
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

        <el-table-column label="应付利息/股息（仅底稿）" width="160" align="right">
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

        <el-table-column label="期末数量" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末账面价值" width="140" align="right">
          <template #header>
            <el-tooltip content="期末=期初+本期发行-本期赎回（权益类贷方）" placement="top">
              <span class="formula-col-header">期末账面价值</span>
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
        <li>数量与账面价值逐项保存，完整行修改后自动同步附注</li>
        <li>审定事件会重新读取已保存数据，不会保留已删除的旧值</li>
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
import { computed, inject, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useM10FormData } from '../../composables/useM10FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import {
  buildM10DisclosurePayload,
  createM10Rows,
  m10DisplayRows,
  m10MovementItemId,
  m10NoteText,
  restoreM10Rows,
  type M10DisplayRow,
  type M10LocalField,
  type M10UiRow,
} from '../../composables/m10DisclosureForm'
import http from '@/utils/http'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  applicableStandards?: string[]
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
  const payload = buildM10DisclosurePayload({
    wpId: props.wpId,
    variant: 'listed',
    rows: dataRows.value,
    noteText: m10NoteText(formData.allResponses.value, 'listed'),
  })
  if (!payload || props.isReadonly) return
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── State ───────────────────────────────────────────────────────────────────


const dataRows = ref<M10UiRow[]>(createM10Rows('listed'))

const termsSummary = ref('')
const distributionNote = ref('')
const otherDisclosure = ref('')

// ─── 合计行 + 计算 ──────────────────────────────────────────────────────────

const instrumentRows = computed<M10DisplayRow[]>(() => m10DisplayRows(dataRows.value))

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateInstrumentRow(index: number, field: M10LocalField, val: number | null): void {
  if (props.isReadonly) return
  const row = dataRows.value[index]
  if (!row) return
  const parsed = val === null ? null : Number(val)
  row[field] = parsed !== null && Number.isFinite(parsed) ? parsed : null
  formData.debouncedSave(m10MovementItemId('listed', row.key, field), {
    remark: row[field] === null ? null : String(row[field]),
  })
  if (field !== 'interestDividend') autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function getRowClassName({ row }: { row: M10DisplayRow; rowIndex: number }): string {
  return row._isTotal ? 'total-row' : ''
}

function handleTermsSummaryChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M10-disclosure-listed-terms-summary', { remark: termsSummary.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleDistributionNoteChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M10-disclosure-listed-distribution-note', { remark: distributionNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleOtherDisclosureChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M10-disclosure-listed-other-disclosure', { remark: otherDisclosure.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const totalRow = instrumentRows.value.find(r => r._isTotal)
    const context: Record<string, string> = {
      科目: '4401 其他权益工具 / 附注披露信息（上市公司）',
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
  const responses = formData.allResponses.value
  dataRows.value = restoreM10Rows(responses, 'listed')
  termsSummary.value = responses.get('M10-disclosure-listed-terms-summary')?.remark || ''
  distributionNote.value = responses.get('M10-disclosure-listed-distribution-note')?.remark || ''
  otherDisclosure.value = responses.get('M10-disclosure-listed-other-disclosure')?.remark || ''
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
onBeforeUnmount(() => autoSync.cancelPending())
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
