<template>
  <div class="m10-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息核对（国有企业）</h3>
        <el-tag type="success" size="small">国企</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-soe')">
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
        <strong>国有企业其他权益工具变动披露：</strong>
        分项列示期初、本期增加、本期减少和期末的数量及账面价值。
        每行三组数量均已录入后才同步，缺少数量来源时不会用默认零覆盖附注。
      </div>
    </div>

    <!-- ═══ Section 1: 权益工具变动明细（国企格式） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>其他权益工具变动明细（国有企业）</span>
          <el-button size="small" @click="handleAI('section-detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="项目" min-width="200" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal }">{{ row.item }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初数量" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!row._isTotal && !isReadonly" :model-value="row.beginQty" :controls="false"
              @change="(val: number | undefined) => updateRow($index, 'beginQty', val ?? null)" />
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初账面价值" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <WpAmountInput
                :model-value="row.beginBalance"
                @update:model-value="(val: number) => updateRow($index, 'beginBalance', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期增加数量" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!row._isTotal && !isReadonly" :model-value="row.increaseQty" :controls="false"
              @change="(val: number | undefined) => updateRow($index, 'increaseQty', val ?? null)" />
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
                @update:model-value="(val: number) => updateRow($index, 'issuance', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.issuance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期减少数量" width="120" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!row._isTotal && !isReadonly" :model-value="row.decreaseQty" :controls="false"
              @change="(val: number | undefined) => updateRow($index, 'decreaseQty', val ?? null)" />
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.decreaseQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少账面价值" width="140" align="right">
          <template #header>
            <el-tooltip content="借方减少：赎回/转换（权益类借方）" placement="top">
              <span class="formula-col-header">本期减少账面价值</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <WpAmountInput
                :model-value="row.redemption"
                @update:model-value="(val: number) => updateRow($index, 'redemption', val)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.redemption) }}</span>
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

    <!-- ═══ Section 2: 分类依据说明（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>分类依据说明</span>
          <el-button size="small" @click="handleAI('section-classification-basis')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="classificationBasis"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明按CAS37将各金融工具分类为权益工具的依据（无合同义务交付现金、非强制付息、续期安排等）..."
        @change="handleClassificationBasisChange"
      />
    </el-card>

    <!-- ═══ Section 3: 国企专项说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国有企业专项披露</span>
          <el-button size="small" @click="handleAI('section-soe-special')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeSpecialNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="国企专项说明（国资委审批情况、资金用途限制、对国有资本保值增值的影响、投资者保护条款等）..."
        @change="handleSoeSpecialNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企格式较上市公司简化（12行×19列）</li>
        <li>国有企业发行永续债/优先股需关注国资委审批和资金用途限制</li>
        <li>数量与账面价值逐项保存，完整行修改后自动同步附注</li>
        <li>期末 = 期初 + 本期发行 - 本期赎回/转换（权益类贷方）</li>
        <li>分类依据应明确说明按CAS37判定为权益工具的理由</li>
        <li>需说明对国有资本保值增值的影响</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabDisclosureSoe — 附注披露信息核对（国有企业）12×19
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 4.6
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - Same structure as Listed but simpler (fewer rows)
 * - 国资委审批/资金用途限制/国有资本保值增值
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - textarea sections (autosize) for each disclosure area
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
  type M10MovementField,
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
    variant: 'soe',
    rows: dataRows.value,
    noteText: m10NoteText(formData.allResponses.value, 'soe'),
  })
  if (!payload || props.isReadonly) return
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── State ───────────────────────────────────────────────────────────────────


const dataRows = ref<M10UiRow[]>(createM10Rows('soe'))

const classificationBasis = ref('')
const soeSpecialNote = ref('')

// ─── 合计行 + 计算 ──────────────────────────────────────────────────────────

const disclosureRows = computed<M10DisplayRow[]>(() => m10DisplayRows(dataRows.value))

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateRow(index: number, field: M10MovementField, val: number | null): void {
  if (props.isReadonly) return
  const row = dataRows.value[index]
  if (!row) return
  const parsed = val === null ? null : Number(val)
  row[field] = parsed !== null && Number.isFinite(parsed) ? parsed : null
  formData.debouncedSave(m10MovementItemId('soe', row.key, field), {
    remark: row[field] === null ? null : String(row[field]),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function getRowClassName({ row }: { row: M10DisplayRow; rowIndex: number }): string {
  return row._isTotal ? 'total-row' : ''
}

function handleClassificationBasisChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M10-disclosure-soe-classification-basis', { remark: classificationBasis.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleSoeSpecialNoteChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M10-disclosure-soe-special-note', { remark: soeSpecialNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const totalRow = disclosureRows.value.find(r => r._isTotal)
    const context: Record<string, string> = {
      科目: '4401 其他权益工具 / 附注披露信息（国有企业）',
      区段: section,
      期末余额合计: fmtAmount(totalRow?.endBalance ?? 0),
      本期发行合计: fmtAmount(totalRow?.issuance ?? 0),
      本期赎回合计: fmtAmount(totalRow?.redemption ?? 0),
    }
    if (section === 'section-classification-basis') {
      const text = await generateAiText({ section: 'm10-disclosure-soe-classification', context, existingContent: classificationBasis.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      classificationBasis.value = text; handleClassificationBasisChange()
    } else if (section === 'section-soe-special') {
      const text = await generateAiText({ section: 'm10-disclosure-soe-special', context, existingContent: soeSpecialNote.value })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      soeSpecialNote.value = text; handleSoeSpecialNoteChange()
    } else {
      const text = await generateAiText({ section: `m10-disclosure-soe-${section}`, context })
      if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
      ElMessageBox.alert(text, 'AI 辅助 — 其他权益工具附注建议', { confirmButtonText: '知道了' }).catch(() => { /* 用户关闭 */ })
    }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M10-disclosure-soe', '其他权益工具附注（国企）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const responses = formData.allResponses.value
  dataRows.value = restoreM10Rows(responses, 'soe')
  classificationBasis.value = responses.get('M10-disclosure-soe-classification-basis')?.remark || ''
  soeSpecialNote.value = responses.get('M10-disclosure-soe-special-note')?.remark || ''
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
.m10-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
