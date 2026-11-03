<template>
  <div class="m9-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（国有企业）</h3>
        <el-tag type="success" size="small">国企</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'disclosure-soe'" :disabled="isReadonly" @click="handleAI('disclosure-soe')">
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
        <strong>国有企业其他综合收益披露：</strong>
        按模板分别列示本期和上期的税前金额、所得税及税后净额；可重分类项目另录
        本期转入损益或转为被套期项目初始确认金额的调整额。
      </div>
    </div>

    <!-- ═══ Section 1: 不能重分类进损益的OCI（详细） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一、以后不能重分类进损益的其他综合收益</span>
          <el-button size="small" :loading="aiLoading === 'section-non-reclass'" :disabled="isReadonly" @click="handleAI('section-non-reclass')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="nonReclassRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="220" fixed />
        <el-table-column label="上期税前金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'beginBalance', val)"
            />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期所得税" min-width="110" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorTaxEffect"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'priorTaxEffect', val)"
            />
            <span v-else>{{ fmtAmount(row.priorTaxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期税前金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.preTaxAmount"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'preTaxAmount', val)"
            />
            <span v-else>{{ fmtAmount(row.preTaxAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期所得税" min-width="110" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.taxEffect"
              @update:model-value="(val: number) => updateNonReclassRow($index, 'taxEffect', val)"
            />
            <span v-else>{{ fmtAmount(row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期税后净额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 税前发生 - 所得税影响">{{ fmtAmount(row.preTaxAmount - row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期税后净额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.beginBalance - row.priorTaxEffect) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 能重分类进损益的OCI（详细） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>二、以后将重分类进损益的其他综合收益</span>
          <el-button size="small" :loading="aiLoading === 'section-reclass'" :disabled="isReadonly" @click="handleAI('section-reclass')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="reclassRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="220" fixed />
        <el-table-column label="上期税前金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              @update:model-value="(val: number) => updateReclassRow($index, 'beginBalance', val)"
            />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期所得税" min-width="110" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.priorTaxEffect"
              @update:model-value="(val: number) => updateReclassRow($index, 'priorTaxEffect', val)"
            />
            <span v-else>{{ fmtAmount(row.priorTaxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期税前金额" min-width="120" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.preTaxAmount"
              @update:model-value="(val: number) => updateReclassRow($index, 'preTaxAmount', val)"
            />
            <span v-else>{{ fmtAmount(row.preTaxAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期所得税" min-width="110" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.taxEffect"
              @update:model-value="(val: number) => updateReclassRow($index, 'taxEffect', val)"
            />
            <span v-else>{{ fmtAmount(row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期税后净额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 税前发生 - 所得税影响">{{ fmtAmount(row.preTaxAmount - row.taxEffect) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转入损益/调整额" min-width="150" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.transferToPL"
              @update:model-value="(val: number) => updateReclassRow($index, 'transferToPL', val)"
            />
            <span v-else>{{ fmtAmount(row.transferToPL) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期税后净额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.beginBalance - row.priorTaxEffect) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 3: OCI汇总 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>三、其他综合收益合计</span>
          <el-button size="small" :loading="aiLoading === 'section-total'" :disabled="isReadonly" @click="handleAI('section-total')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="上期不可重分类税后净额">{{ fmtAmount(nonReclassPriorNetTotal) }}</el-descriptions-item>
        <el-descriptions-item label="上期可重分类税后净额">{{ fmtAmount(reclassPriorNetTotal) }}</el-descriptions-item>
        <el-descriptions-item label="上期OCI税后净额">{{ fmtAmount(nonReclassPriorNetTotal + reclassPriorNetTotal) }}</el-descriptions-item>
        <el-descriptions-item label="本期不可重分类税后净额">{{ fmtAmount(nonReclassNetTotal) }}</el-descriptions-item>
        <el-descriptions-item label="本期可重分类税后净额">{{ fmtAmount(reclassNetTotal) }}</el-descriptions-item>
        <el-descriptions-item label="本期OCI税后净额">{{ fmtAmount(nonReclassNetTotal + reclassNetTotal) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- ═══ Section 4: 国有资本相关OCI说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>四、国有资本相关其他综合收益说明</span>
          <el-button size="small" :loading="aiLoading === 'section-soe-capital'" :disabled="isReadonly" @click="handleAI('section-soe-capital')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeCapitalNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明国有资本相关的其他综合收益项目、变动原因及对国有权益的影响..."
        @change="handleSoeCapitalNoteChange"
      />
    </el-card>

    <!-- ═══ Section 5: OCI转出及处置说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>五、OCI转出至损益/留存收益说明</span>
          <el-button size="small" :loading="aiLoading === 'section-transfer'" :disabled="isReadonly" @click="handleAI('section-transfer')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="transferNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明本期从其他综合收益转入损益或留存收益的项目、金额及原因（如处置金融资产、套期终止等）..."
        @change="handleTransferNoteChange"
      />
    </el-card>

    <!-- ═══ Section 6: 审计结论 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>六、审计结论</span>
          <el-button size="small" :loading="aiLoading === 'section-conclusion'" :disabled="isReadonly" @click="handleAI('section-conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusionNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="经审计，其他综合收益各项目列报完整、分类准确、税后净额计算正确..."
        @change="handleConclusionNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m9-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本期、上期税后净额均由税前金额减所得税自动计算</li>
        <li>可重分类项目按模板展开转入损益或调整额及小计行</li>
        <li>分两大类：不能重分类进损益 + 将重分类进损益</li>
        <li>数据从审定表和明细表加载，修改后自动同步附注</li>
        <li>国企需额外说明国有资本相关OCI影响</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M9TabDisclosureSoe — 附注披露信息（国有企业）67×21，20公式
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 4.5
 * Requirements: 5.2, 5.3, 5.4
 *
 * 功能：
 * - 国有企业附注模板（67×21, 20公式）
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - OCI分两大类表格（含20公式列）:
 *   - 税后净额 = 税前发生 - 所得税影响
 *   - 期末余额 = 期初 + 税后净额 - 转入损益 - 转入留存收益
 * - AI辅助按钮 each section
 * - autosize textarea for 文本段
 */
import { computed, inject, onBeforeUnmount, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM9FormData } from '../../composables/useM9FormData'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import {
  buildM9DisclosurePayload,
  createM9SoeRows,
  m9NoteText,
  restoreM9SoeRows,
  type M9Group,
  type M9SoeUiRow,
} from '../../composables/m9DisclosureForm'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM9FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 同步链路 ───────────────────────────────────────────────────────────────

const nonReclassRows = ref<M9SoeUiRow[]>(createM9SoeRows('nonReclass'))
const reclassRows = ref<M9SoeUiRow[]>(createM9SoeRows('reclass'))

async function syncToDisclosureNotes(): Promise<void> {
  const payload = buildM9DisclosurePayload({
    variant: 'soe',
    wpId: props.wpId,
    nonReclass: nonReclassRows.value,
    reclass: reclassRows.value,
    noteText: m9NoteText(formData.allResponses.value, 'soe'),
  })
  if (!payload || props.isReadonly) return
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

// ─── Types ───────────────────────────────────────────────────────────────────


// ─── State: 不可重分类OCI行（国企详细版） ────────────────────────────────────


// ─── State: 可重分类OCI行（国企详细版） ──────────────────────────────────────


// ─── State: 文本区 ──────────────────────────────────────────────────────────

const soeCapitalNote = ref('')
const transferNote = ref('')
const conclusionNote = ref('')

// ─── Formula: 期末余额 = 期初 + 税后净额 - 转入损益 - 转入留存收益 ─────────

const currentNet = (row: M9SoeUiRow) => row.preTaxAmount - row.taxEffect
const priorNet = (row: M9SoeUiRow) => row.beginBalance - row.priorTaxEffect

// ─── Computed ────────────────────────────────────────────────────────────────

const nonReclassPriorNetTotal = computed(() => nonReclassRows.value.reduce((sum, row) => sum + priorNet(row), 0))

const reclassPriorNetTotal = computed(() => reclassRows.value.reduce((sum, row) => sum + priorNet(row), 0))

const nonReclassNetTotal = computed(() => nonReclassRows.value.reduce((sum, row) => sum + currentNet(row), 0))

const reclassNetTotal = computed(() => reclassRows.value.reduce((sum, row) => sum + currentNet(row), 0))

// ─── Handlers ────────────────────────────────────────────────────────────────

type M9SoeNumericField = Exclude<keyof M9SoeUiRow, 'key' | 'item'>
function updateSoeRow(group: M9Group, index: number, field: M9SoeNumericField, val: number): void {
  if (props.isReadonly) return
  const rows = group === 'nonReclass' ? nonReclassRows.value : reclassRows.value
  const row = rows[index]
  if (!row) return
  row[field] = Number(val) || 0
  formData.debouncedSave(
    `M9-disclosure-soe-${group}-${row.key}-${field}`,
    { remark: String(val) },
  )
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}
function updateNonReclassRow(index: number, field: M9SoeNumericField, val: number) {
  updateSoeRow('nonReclass', index, field, val)
}

function updateReclassRow(index: number, field: M9SoeNumericField, val: number) {
  updateSoeRow('reclass', index, field, val)
}

function handleSoeCapitalNoteChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M9-disclosure-soe-capital', { remark: soeCapitalNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleTransferNoteChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M9-disclosure-soe-transfer', { remark: transferNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleConclusionNoteChange() {
  if (props.isReadonly) return
  formData.debouncedSave('M9-disclosure-soe-conclusion', { remark: conclusionNote.value || null })
}

const SOE_NOTE_TARGETS: Record<string, { get: () => string; set: (v: string) => void; save: () => void }> = {
  'section-soe-capital': { get: () => soeCapitalNote.value, set: (v) => { soeCapitalNote.value = v }, save: handleSoeCapitalNoteChange },
  'section-transfer': { get: () => transferNote.value, set: (v) => { transferNote.value = v }, save: handleTransferNoteChange },
  'section-conclusion': { get: () => conclusionNote.value, set: (v) => { conclusionNote.value = v }, save: handleConclusionNoteChange },
}

async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4003 其他综合收益 / 附注披露（国有企业，67×21）',
      不可重分类税后合计: fmtAmount(nonReclassNetTotal.value),
      可重分类税后合计: fmtAmount(reclassNetTotal.value),
      上期不可重分类税后合计: fmtAmount(nonReclassPriorNetTotal.value),
      上期可重分类税后合计: fmtAmount(reclassPriorNetTotal.value),
      上期OCI税后合计: fmtAmount(nonReclassPriorNetTotal.value + reclassPriorNetTotal.value),
    }
    const target = SOE_NOTE_TARGETS[section]
    const text = await generateAiText({ section: `m9-disclosure-soe-${section}`, context, existingContent: target ? target.get() : '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (target) { target.set(text); target.save() }
    else { ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {}) }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview() { openReviewDialog?.('M9-disclosure-soe', '附注披露（国企）') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function restoreData(): void {
  const responses = formData.allResponses.value
  nonReclassRows.value = restoreM9SoeRows(responses, 'nonReclass')
  reclassRows.value = restoreM9SoeRows(responses, 'reclass')
  soeCapitalNote.value = responses.get('M9-disclosure-soe-capital')?.remark || ''
  transferNote.value = responses.get('M9-disclosure-soe-transfer')?.remark || ''
  conclusionNote.value = responses.get('M9-disclosure-soe-conclusion')?.remark || ''
}
async function onAdjudicatedRefresh(): Promise<void> {
  await formData.loadData()
  restoreData()
}

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
.m9-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.formula-cell { color: #409eff; border-bottom: 1px dashed #409eff; cursor: help; }
.m9-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m9-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m9-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
