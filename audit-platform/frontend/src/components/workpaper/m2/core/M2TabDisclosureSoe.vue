<template>
  <div class="m2-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（国有企业）</h3>
        <el-tag type="success" size="small">国企·元</el-tag>
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
        <strong>国有企业实收资本附注披露要求（20×19）：</strong>
        按出资方式和出资人类型列示实收资本变动情况（单位：元）。
        国有企业须单独列示国有资本出资比例变动。
        数据自动从审定表/明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 实收资本变动明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>实收资本变动明细（单位：元）</span>
          <el-button size="small" :loading="aiLoading === 'section-capital-change'" :disabled="isReadonly" @click="handleAI('section-capital-change')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="capitalChangeRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="出资人/出资方式" min-width="180" />
        <el-table-column label="期初余额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateCapitalRow($index, 'beginAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increaseAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateCapitalRow($index, 'increaseAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.decreaseAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateCapitalRow($index, 'decreaseAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 期初 + 本期增加 − 本期减少（权益类贷方）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出资比例" width="90" align="center">
          <template #default="{ row }">
            <span>{{ row.ratio ? `${(row.ratio * 100).toFixed(2)}%` : '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 国有资本出资说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国有资本出资情况说明</span>
          <el-button size="small" :loading="aiLoading === 'section-state-capital'" :disabled="isReadonly" @click="handleAI('section-state-capital')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="stateCapitalNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明国有资本出资方/持股比例/增减资审批情况/国资监管要求..."
        @change="handleNoteChange('state-capital', stateCapitalNote)"
      />
    </el-card>

    <!-- ═══ Section 3: 出资方式说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>出资方式说明</span>
          <el-button size="small" :loading="aiLoading === 'section-method'" :disabled="isReadonly" @click="handleAI('section-method')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="methodNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明各出资人的出资方式：货币资金/实物资产/无形资产/土地使用权等..."
        @change="handleNoteChange('method', methodNote)"
      />
    </el-card>

    <!-- ═══ Section 4: 验资及工商登记情况 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>验资及工商登记情况</span>
          <el-button size="small" :loading="aiLoading === 'section-registration'" :disabled="isReadonly" @click="handleAI('section-registration')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="registrationNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="验资报告编号/工商登记注册资本/变更登记完成情况..."
        @change="handleNoteChange('registration', registrationNote)"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国有企业实收资本单位：元（区别于上市公司"万股"）</li>
        <li>须单独列示国有资本出资比例及变动情况</li>
        <li>数据优先从M2-1审定表和M2-2明细表(非上市版)自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>需额外披露国资审批/出资方式/验资工商登记</li>
        <li>期末余额 = 期初 + 本期增加 − 本期减少（权益类贷方）</li>
        <li>格式：20行×19列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabDisclosureSoe — 附注披露信息（国有企业）20×19
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 4.6
 * Requirements: 6.2-6.3
 *
 * 功能：
 * - 国有企业版附注（金额单位：元）
 * - Subscribe EventBus 'substantive:adjudicated' refresh
 * - 实收资本变动明细 + 期末公式计算
 * - 国资/出资方式/验资登记 textarea sections
 * - AI辅助 per section
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useM2FormData } from '../../composables/useM2FormData'

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

const formData = useM2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

interface SoeCapitalRow {
  item: string
  beginAmount: number
  increaseAmount: number
  decreaseAmount: number
  endAmount: number
  ratio: number
}

const capitalChangeRows = ref<SoeCapitalRow[]>([
  { item: '一、国家资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '  中央国有资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '  地方国有资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '二、集体资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '三、法人资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '  国有法人资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '  民营法人资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '  外商法人资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '四、个人资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '五、外商资本', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
  { item: '合计', beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 },
])

const stateCapitalNote = ref('')
const methodNote = ref('')
const registrationNote = ref('')

// ─── Computed: 期末 = 期初+增-减, 占比 ──────────────────────────────────────

function recalcEndAndRatio(): void {
  const totalEnd = capitalChangeRows.value.reduce((sum, row) => {
    const end = row.beginAmount + row.increaseAmount - row.decreaseAmount
    return sum + end
  }, 0)

  capitalChangeRows.value.forEach(row => {
    row.endAmount = row.beginAmount + row.increaseAmount - row.decreaseAmount
    row.ratio = totalEnd > 0 ? row.endAmount / totalEnd : 0
  })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateCapitalRow(index: number, field: 'beginAmount' | 'increaseAmount' | 'decreaseAmount', val: number) {
  if (index >= 0 && index < capitalChangeRows.value.length) {
    capitalChangeRows.value[index][field] = val
    recalcEndAndRatio()
    formData.debouncedSave('M2-disclosure-soe-capital-rows', {
      remark: JSON.stringify(capitalChangeRows.value),
    })
  }
}

function handleNoteChange(section: string, value: string) {
  formData.debouncedSave(`M2-disclosure-soe-${section}`, { remark: value || null })
}

// section → { ref, 持久化key } 映射
const AI_TARGETS: Record<string, { get: () => string; set: (v: string) => void; key: string }> = {
  'section-method': { get: () => methodNote.value, set: (v) => (methodNote.value = v), key: 'method' },
  'section-registration': { get: () => registrationNote.value, set: (v) => (registrationNote.value = v), key: 'registration' },
  'section-state-capital': { get: () => stateCapitalNote.value, set: (v) => (stateCapitalNote.value = v), key: 'state-capital' },
  // 顶部/实收资本变动明细（表格无独立文本区）→ 归入"国有资本出资情况说明"
  'disclosure-soe': { get: () => stateCapitalNote.value, set: (v) => (stateCapitalNote.value = v), key: 'state-capital' },
  'section-capital-change': { get: () => stateCapitalNote.value, set: (v) => (stateCapitalNote.value = v), key: 'state-capital' },
}

function buildContext(): Record<string, string> {
  const totalRow = capitalChangeRows.value.find((r) => r.item === '合计')
  return {
    披露类型: '国有企业实收资本附注（单位：元）',
    科目: '4001 实收资本',
    期末余额合计: totalRow ? fmtAmount(totalRow.endAmount) : '—',
    本期增加合计: totalRow ? fmtAmount(totalRow.increaseAmount) : '—',
    本期减少合计: totalRow ? fmtAmount(totalRow.decreaseAmount) : '—',
  }
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  const target = AI_TARGETS[section] || AI_TARGETS['disclosure-soe']
  aiLoading.value = section
  try {
    const text = await generateAiText({
      section: `m2-disclosure-soe-${target.key}`,
      context: buildContext(),
      existingContent: target.get(),
    })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    target.set(text)
    handleNoteChange(target.key, text)
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = ''
  }
}
function handleReview() { openReviewDialog?.('M2-disclosure-soe', '附注披露（国企）') }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Restore state ──────────────────────────────────────────────────────────

function _restoreFromResponses(): void {
  const rowData = formData.allResponses.value.get('M2-disclosure-soe-capital-rows')
  if (rowData?.remark) {
    try {
      const parsed = JSON.parse(rowData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        capitalChangeRows.value = parsed
        recalcEndAndRatio()
      }
    } catch { /* ignore */ }
  }

  const sc = formData.allResponses.value.get('M2-disclosure-soe-state-capital')
  if (sc?.remark) stateCapitalNote.value = sc.remark

  const method = formData.allResponses.value.get('M2-disclosure-soe-method')
  if (method?.remark) methodNote.value = method.remark

  const reg = formData.allResponses.value.get('M2-disclosure-soe-registration')
  if (reg?.remark) registrationNote.value = reg.remark
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(_restoreFromResponses)
}

onMounted(async () => {
  await formData.loadData()
  _restoreFromResponses()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m2-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.m2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
