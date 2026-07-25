<template>
  <div class="m1-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'disclosure-listed'" :disabled="isReadonly" @click="handleAI('disclosure-listed')">
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
        <strong>上市公司附注披露要求（20×17）：</strong>
        按股东性质列示应付股利明细，披露期末数和上年年末数。
        数据自动从审定表/明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 应付股利明细 ═══ -->
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
        <el-table-column prop="item" label="股东名称/项目" min-width="180" />
        <el-table-column label="期末数" min-width="140" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.endAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateDetailRow($index, 'endAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末数" min-width="140" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorYearEnd"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateDetailRow($index, 'priorYearEnd', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorYearEnd) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 超期应付股利说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>超过1年未支付的重大应付股利说明</span>
          <el-button size="small" :loading="aiLoading === 'section-overdue'" :disabled="isReadonly" @click="handleAI('section-overdue')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overdueNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="列明超过1年未支付的重大应付股利项目、金额及未支付原因..."
        @change="handleOverdueNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 分红政策及执行情况 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>分红政策及执行情况</span>
          <el-button size="small" :loading="aiLoading === 'section-policy'" :disabled="isReadonly" @click="handleAI('section-policy')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="policyNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明公司利润分配政策，现金分红占比，最近三年实际分红情况..."
        @change="handlePolicyNoteChange"
      />
    </el-card>

    <!-- ═══ Section 4: 本年利润分配方案 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>本年利润分配方案</span>
          <el-button size="small" :loading="aiLoading === 'section-plan'" :disabled="isReadonly" @click="handleAI('section-plan')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="planNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明本年拟定的利润分配方案、每10股分红金额、分配总额、分配比例..."
        @change="handlePlanNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从M1-1审定表和M1-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司需额外披露分红政策、超期未支付说明</li>
        <li>格式：20行×17列（含合计行）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M1TabDisclosureListed — 附注披露信息（上市公司）20×17
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 4.6
 * Requirements: 6.4
 *
 * 功能：
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - 根据企业类型默认展示上市公司附注模板
 * - textarea sections (autosize) for each disclosure area
 * - AI辅助 per section title
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useM1FormData } from '../../composables/useM1FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

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

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM1FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const detailRows = ref([
  { item: '股东A（境内法人）', endAmount: 0, priorYearEnd: 0 },
  { item: '股东B（境内自然人）', endAmount: 0, priorYearEnd: 0 },
  { item: '股东C（境外法人）', endAmount: 0, priorYearEnd: 0 },
  { item: '股东D（其他）', endAmount: 0, priorYearEnd: 0 },
  { item: '合计', endAmount: 0, priorYearEnd: 0 },
])

const overdueNote = ref('')
const policyNote = ref('')
const planNote = ref('')
const disclosureConclusion = ref('')

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateDetailRow(index: number, field: 'endAmount' | 'priorYearEnd', val: number) {
  if (index >= 0 && index < detailRows.value.length) {
    detailRows.value[index][field] = val
    formData.debouncedSave(`M1-disclosure-listed-${index}-${field}`, { remark: String(val) })
  }
}

function handleOverdueNoteChange() {
  formData.debouncedSave('M1-disclosure-listed-overdue', { remark: overdueNote.value || null })
}

function handlePolicyNoteChange() {
  formData.debouncedSave('M1-disclosure-listed-policy', { remark: policyNote.value || null })
}

function handlePlanNoteChange() {
  formData.debouncedSave('M1-disclosure-listed-plan', { remark: planNote.value || null })
}

function handleConclusionChange() {
  formData.debouncedSave('M1-disc-listed-conclusion', { remark: disclosureConclusion.value || null })
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    // 按区段回填对应文本框：overdue/policy/plan；header/detail 默认回填分红政策
    let target: 'overdue' | 'policy' | 'plan' = 'policy'
    if (section.includes('overdue')) target = 'overdue'
    else if (section.includes('policy')) target = 'policy'
    else if (section.includes('plan')) target = 'plan'
    const existing = target === 'overdue' ? overdueNote.value : target === 'plan' ? planNote.value : policyNote.value
    const totalRow = detailRows.value.find(r => r.item === '合计')
    const context: Record<string, string> = {
      科目: '2232 应付股利 / 附注披露信息（上市公司）',
      区段: section,
      期末数合计: fmtAmount(totalRow?.endAmount ?? 0),
      上年年末数合计: fmtAmount(totalRow?.priorYearEnd ?? 0),
    }
    const text = await generateAiText({ section: `m1-disclosure-listed-${section}`, context, existingContent: existing })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (target === 'overdue') { overdueNote.value = text; handleOverdueNoteChange() }
    else if (target === 'plan') { planNote.value = text; handlePlanNoteChange() }
    else { policyNote.value = text; handlePolicyNoteChange() }
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview() { openReviewDialog?.('M1-disclosure-listed', '附注披露（上市）') }

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
  overdueNote.value = responses.get('M1-disclosure-listed-overdue')?.remark || ''
  policyNote.value = responses.get('M1-disclosure-listed-policy')?.remark || ''
  planNote.value = responses.get('M1-disclosure-listed-plan')?.remark || ''
  disclosureConclusion.value = responses.get('M1-disc-listed-conclusion')?.remark || ''
  // Restore detail rows
  for (let i = 0; i < detailRows.value.length; i++) {
    const endResp = responses.get(`M1-disclosure-listed-${i}-endAmount`)
    const priorResp = responses.get(`M1-disclosure-listed-${i}-priorYearEnd`)
    if (endResp?.remark) detailRows.value[i].endAmount = Number(endResp.remark) || 0
    if (priorResp?.remark) detailRows.value[i].priorYearEnd = Number(priorResp.remark) || 0
  }
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m1-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
