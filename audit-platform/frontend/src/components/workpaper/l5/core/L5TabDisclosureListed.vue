<template>
  <div class="l5-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-listed')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button
          type="primary"
          plain
          size="small"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="l5-disclosure-listed-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（五、48）</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司附注披露要求：</strong>
        按款项性质列示长期应付款明细（融资租赁/分期付款/其他），披露合同金额、未确认融资费用、
        账面价值（净额）、到期时间分布、关联方交易及其公允性。数据自动从审定表/明细表拉取。
        <br />同步到附注仅推「长期应付款」主表（净额）；专项应付款行由 L6 底稿维护。
      </div>
    </div>

    <!-- ═══ 第一节：长期应付款按性质列示 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>一、长期应付款按性质列示</span>
          <el-button size="small" @click="handleAI('section1')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="categoryRows" border size="small" style="width: 100%">
        <el-table-column prop="category" label="项目" min-width="160" />
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.endBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateCategoryRow($index, 'endBalance', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.beginBalance" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateCategoryRow($index, 'beginBalance', val ?? 0)" />
            <span v-else>{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 第二节：未确认融资费用 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>二、未确认融资费用</span>
          <el-button size="small" @click="handleAI('section2')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="期末未确认融资费用">
          <el-input-number v-if="!isReadonly" v-model="unrecognizedEnd" :controls="false" size="small" style="width:160px" />
          <span v-else>{{ fmtAmount(unrecognizedEnd) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="期初未确认融资费用">
          <el-input-number v-if="!isReadonly" v-model="unrecognizedBegin" :controls="false" size="small" style="width:160px" />
          <span v-else>{{ fmtAmount(unrecognizedBegin) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="期末账面价值（净额）">
          <span class="formula-value">{{ fmtAmount(netBookValue) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="本期摊销额">
          <el-input-number v-if="!isReadonly" v-model="periodAmortizationAmount" :controls="false" size="small" style="width:160px" />
          <span v-else>{{ fmtAmount(periodAmortizationAmount) }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- ═══ 第三节：到期时间分布 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>三、到期时间分布</span>
        </div>
      </template>
      <el-table :data="maturityRows" border size="small" style="width: 100%">
        <el-table-column prop="period" label="到期期间" min-width="120" />
        <el-table-column label="金额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateMaturityRow($index, val ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 核对结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">核对结论</span>
          <el-button size="small" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="请填写附注核对结论..." :disabled="isReadonly" @change="saveConclusion" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从L5-1审定表和L5-2/L5-3明细自动拉取</li>
        <li>账面价值（净额）= 长期应付款余额 − 未确认融资费用余额</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabDisclosureListed — 附注披露信息（上市公司）
 * Requirements: 5.4-5.5
 */
import { computed, inject, onMounted, onUnmounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useL5FormData } from '../../composables/useL5FormData'
import { calcNetPayable } from '../../composables/useL5FormulaEngine'
import { L5_NOTE_SECTION, buildL5SyncPayload } from '../../composables/l5NoteSectionMap'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const router = useRouter()

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useL5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const categoryRows = ref([
  { category: '融资租赁款', endBalance: 0, beginBalance: 0 },
  { category: '分期付款购入资产款', endBalance: 0, beginBalance: 0 },
  { category: '其他长期应付款', endBalance: 0, beginBalance: 0 },
  { category: '合计', endBalance: 0, beginBalance: 0 },
])

const unrecognizedEnd = ref(0)
const unrecognizedBegin = ref(0)
const periodAmortizationAmount = ref(0)

const maturityRows = ref([
  { period: '1年以内', amount: 0 },
  { period: '1-2年', amount: 0 },
  { period: '2-3年', amount: 0 },
  { period: '3-5年', amount: 0 },
  { period: '5年以上', amount: 0 },
])

const netBookValue = computed(() => {
  const totalEnd = categoryRows.value[categoryRows.value.length - 1]?.endBalance || 0
  return calcNetPayable(totalEnd, unrecognizedEnd.value)
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateCategoryRow(index: number, field: 'endBalance' | 'beginBalance', val: number) {
  if (index >= 0 && index < categoryRows.value.length) {
    categoryRows.value[index][field] = val
    formData.debouncedSave(`L5-disclosure-listed-cat-${index}-${field}`, { remark: String(val) })
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  }
}

function updateMaturityRow(index: number, val: number) {
  if (index >= 0 && index < maturityRows.value.length) {
    maturityRows.value[index].amount = val
    formData.debouncedSave(`L5-disclosure-listed-maturity-${index}`, { remark: String(val) })
  }
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────
//
// 🔴 只推**主表**（长期应付款净额 / 专项应付款 / 合计）—— 这是能干净映射的部分。
//    源模板「（按款项性质列示）」明细表与本组件 categoryRows / 单一 unrecognized 标量
//    不同构（源为「售后租回 / 分期付款」毛额段 + 逐项未确认融资费用两段），
//    强推会自造 → 暂不推该明细表（宁缺勿造）。
//    「专项应付款」行由 L6 底稿负责，此处主表该行值 L5 无数据源 → 0（跨底稿聚合已知限制）。
const isSyncing = ref(false)

function watchUnrecognized() {
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

watch([unrecognizedEnd, unrecognizedBegin], watchUnrecognized)

function buildSnapshot() {
  const total = categoryRows.value[categoryRows.value.length - 1] || { endBalance: 0, beginBalance: 0 }
  const longTermEnd = calcNetPayable(Number(total.endBalance) || 0, Number(unrecognizedEnd.value) || 0)
  const longTermPrior = calcNetPayable(Number(total.beginBalance) || 0, Number(unrecognizedBegin.value) || 0)
  return {
    variant: 'listed' as const,
    longTerm: { end: longTermEnd, prior: longTermPrior },
    special: { end: 0, prior: 0 },
  }
}

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildL5SyncPayload(props.wpId, buildSnapshot())
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success('已同步到附注（五、48 长期应付款）')
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'L5',
      projectId: props.projectId,
      sectionIds: [L5_NOTE_SECTION.listed],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'L5', 'listed')
  if (route) router.push(route)
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l5-disclosure-listed-${section}`,
      prompt: `请基于长期应付款底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.() }

const conclusion = ref('')
function saveConclusion() { formData.debouncedSave('L5-disc-listed-conclusion', { remark: conclusion.value || null }) }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  // 刷新数据（从formData重新加载）
  formData.loadData()
}

onMounted(async () => {
  await formData.loadData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onBeforeUnmount(() => { autoSync.cancelPending() })
</script>

<style scoped>
.l5-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.formula-value { color: #409eff; font-weight: 500; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.conclusion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
