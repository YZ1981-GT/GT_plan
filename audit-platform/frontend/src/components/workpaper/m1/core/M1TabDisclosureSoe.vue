<template>
  <div class="m1-tab-disclosure-soe">
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
        <strong>国有企业附注披露要求（16×8）：</strong>
        除通用披露外，需按年初余额和期末余额列示应付股利（利润）。
        国企格式重点关注国有资本经营收益上缴和利润分配安排。
        数据自动从审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 应付股利（利润）明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>应付股利（利润）明细</span>
          <el-button size="small" :loading="aiLoading === 'section-detail'" :disabled="isReadonly" @click="handleAI('section-detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="detailRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="年初余额" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              @update:model-value="(val: number) => updateDetailRow($index, 'beginBalance', val)"
            />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.endBalance"
              @update:model-value="(val: number) => updateDetailRow($index, 'endBalance', val)"
            />
            <span v-else>{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 国有资本经营收益上缴说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国有资本经营收益上缴说明</span>
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
        placeholder="说明国有资本经营收益上缴比例、计算依据及执行情况..."
        @change="handleSoeCapitalNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 利润分配专项说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>利润分配专项说明</span>
          <el-button size="small" :loading="aiLoading === 'section-distribution'" :disabled="isReadonly" @click="handleAI('section-distribution')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="distributionNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明利润分配决议、审批程序及国资监管部门要求..."
        @change="handleDistributionNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企需额外披露国有资本经营收益上缴情况</li>
        <li>列报顺序为：项目 | 年初余额 | 期末余额（与上市公司不同）</li>
        <li>数据从审定表和明细表自动拉取，订阅审定事件刷新</li>
        <li>格式：16行×8列（结构较上市公司简洁）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabDisclosureSoe — 附注披露信息（国有企业）16×8
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 4.6
 * Requirements: 6.5
 *
 * 功能：
 * - Same pattern as Listed but for SOE (国有企业) template
 * - Simpler structure (16×8 vs 20×17)
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - textarea sections (autosize) for each disclosure area
 * - AI辅助 per section title
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useM1FormData } from '../../composables/useM1FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import WpAmountInput from '../../shared/WpAmountInput.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── 同步链路（浅合并推 K3 §八、42 的应付股利子表） ──────────────────────────
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildM1SyncPayload, type M1DividendRow } from '../../composables/m1NoteSectionMap'

async function syncToDisclosureNotes(): Promise<void> {
  const dividendRows: M1DividendRow[] = detailRows.value.map((r: any) => ({
    label: r.item || r.label || '',
    endAmount: Number(r.endAmount) || 0,
    priorAmount: Number(r.priorAmount) || 0,
  }))
  const payload = buildM1SyncPayload(props.wpId, 'soe', dividendRows)
  if (!payload) return
  try {
    const { default: request } = await import('@/utils/request')
    await request.post(`/api/workpapers/${props.wpId}/sync-from-workpaper`, payload)
  } catch { /* fail-open */ }
}

const { scheduleAutoSync } = useDisclosureAutoSync(syncToDisclosureNotes)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const detailRows = ref([
  { item: '应付国有股东股利', beginBalance: 0, endBalance: 0 },
  { item: '应付法人股东股利', beginBalance: 0, endBalance: 0 },
  { item: '应付其他股东股利', beginBalance: 0, endBalance: 0 },
  { item: '合计', beginBalance: 0, endBalance: 0 },
])

const soeCapitalNote = ref('')
const distributionNote = ref('')
const disclosureConclusion = ref('')

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateDetailRow(index: number, field: 'beginBalance' | 'endBalance', val: number) {
  if (index >= 0 && index < detailRows.value.length) {
    detailRows.value[index][field] = val
    formData.debouncedSave(`M1-disclosure-soe-${index}-${field}`, { remark: String(val) })
    scheduleAutoSync()
  }
}

function handleSoeCapitalNoteChange() {
  formData.debouncedSave('M1-disclosure-soe-capital', { remark: soeCapitalNote.value || null })
  scheduleAutoSync()
}

function handleDistributionNoteChange() {
  formData.debouncedSave('M1-disclosure-soe-distribution', { remark: distributionNote.value || null })
  scheduleAutoSync()
}

function handleConclusionChange() {
  formData.debouncedSave('M1-disc-soe-conclusion', { remark: disclosureConclusion.value || null })
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    // distribution → 利润分配专项说明；其余（header/detail/capital）→ 国有资本经营收益上缴说明
    const target = section.includes('distribution') ? 'distribution' : 'capital'
    const existing = target === 'distribution' ? distributionNote.value : soeCapitalNote.value
    const totalRow = detailRows.value.find(r => r.item === '合计')
    const context: Record<string, string> = {
      科目: '2232 应付股利 / 附注披露信息（国有企业）',
      区段: section,
      年初余额合计: fmtAmount(totalRow?.beginBalance ?? 0),
      期末余额合计: fmtAmount(totalRow?.endBalance ?? 0),
    }
    const text = await generateAiText({ section: `m1-disclosure-soe-${section}`, context, existingContent: existing })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (target === 'distribution') { distributionNote.value = text; handleDistributionNoteChange() }
    else { soeCapitalNote.value = text; handleSoeCapitalNoteChange() }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview() { openReviewDialog?.('M1-disclosure-soe', '附注披露（国企）') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData()
}

onMounted(async () => {
  await formData.loadData()
  // Restore saved text fields
  const responses = formData.allResponses.value
  soeCapitalNote.value = responses.get('M1-disclosure-soe-capital')?.remark || ''
  distributionNote.value = responses.get('M1-disclosure-soe-distribution')?.remark || ''
  disclosureConclusion.value = responses.get('M1-disc-soe-conclusion')?.remark || ''
  // Restore detail rows
  for (let i = 0; i < detailRows.value.length; i++) {
    const beginResp = responses.get(`M1-disclosure-soe-${i}-beginBalance`)
    const endResp = responses.get(`M1-disclosure-soe-${i}-endBalance`)
    if (beginResp?.remark) detailRows.value[i].beginBalance = Number(beginResp.remark) || 0
    if (endResp?.remark) detailRows.value[i].endBalance = Number(endResp.remark) || 0
  }
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m1-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.conclusion-card { margin-bottom: 16px; border: 1px solid #d9ecff; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.m1-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m1-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m1-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
