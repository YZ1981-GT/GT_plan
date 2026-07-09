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
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司附注披露要求：</strong>
        按款项性质列示长期应付款明细（融资租赁/分期付款/其他），披露合同金额、未确认融资费用、
        账面价值（净额）、到期时间分布、关联方交易及其公允性。数据自动从审定表/明细表拉取。
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
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useL5FormData } from '../../../composables/useL5FormData'
import { calcNetPayable } from '../../../composables/useL5FormulaEngine'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

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
  }
}

function updateMaturityRow(index: number, val: number) {
  if (index >= 0 && index < maturityRows.value.length) {
    maturityRows.value[index].amount = val
    formData.debouncedSave(`L5-disclosure-listed-maturity-${index}`, { remark: String(val) })
  }
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

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
</script>

<style scoped>
.l5-tab-disclosure-listed { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.formula-value { color: #409eff; font-weight: 500; }
:deep(.el-table) { font-size: 13px; }
.l5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
