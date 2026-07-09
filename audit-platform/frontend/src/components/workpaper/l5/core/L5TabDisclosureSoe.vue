<template>
  <div class="l5-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（国有企业）</h3>
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
        <strong>国有企业附注披露要求：</strong>
        除上市公司通用披露外，需额外列示：①国有资本相关融资安排 ②政府贴息/补贴明细
        ③关联方国资体系内交易公允性评价。格式按国资委报表体系要求组织。
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
        <el-table-column prop="category" label="项目" min-width="180" />
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

    <!-- ═══ 第二节：未确认融资费用及净额 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>二、未确认融资费用及账面价值</span>
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

    <!-- ═══ 第三节：国资体系专项 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>三、国资体系专项披露</span>
          <el-button size="small" @click="handleAI('section3')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeSpecialNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="国资体系内融资安排、政府贴息/补贴明细、国有股东借款等专项说明..."
        @change="handleSoeNoteChange"
      />
    </el-card>

    <!-- ═══ 第四节：关联方长期应付款公允性 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>四、关联方长期应付款公允性说明</span>
          <el-button size="small" @click="handleAI('section4')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="relatedPartyNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="关联方长期应付款交易定价公允性评价..."
        @change="handleRelatedPartyNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企需额外披露国资体系内融资安排</li>
        <li>政府贴息/补贴需单独列示</li>
        <li>数据从审定表和明细表自动拉取，订阅审定事件刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L5TabDisclosureSoe — 附注披露信息（国有企业）
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
  { category: '国有资本融资安排', endBalance: 0, beginBalance: 0 },
  { category: '其他长期应付款', endBalance: 0, beginBalance: 0 },
  { category: '合计', endBalance: 0, beginBalance: 0 },
])

const unrecognizedEnd = ref(0)
const unrecognizedBegin = ref(0)
const periodAmortizationAmount = ref(0)
const soeSpecialNote = ref('')
const relatedPartyNote = ref('')

const netBookValue = computed(() => {
  const totalEnd = categoryRows.value[categoryRows.value.length - 1]?.endBalance || 0
  return calcNetPayable(totalEnd, unrecognizedEnd.value)
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateCategoryRow(index: number, field: 'endBalance' | 'beginBalance', val: number) {
  if (index >= 0 && index < categoryRows.value.length) {
    categoryRows.value[index][field] = val
    formData.debouncedSave(`L5-disclosure-soe-cat-${index}-${field}`, { remark: String(val) })
  }
}

function handleSoeNoteChange() {
  formData.debouncedSave('L5-disclosure-soe-special', { remark: soeSpecialNote.value || null })
}

function handleRelatedPartyNoteChange() {
  formData.debouncedSave('L5-disclosure-soe-related', { remark: relatedPartyNote.value || null })
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe ─────────────────────────────────────────────────────

function onAdjudicatedRefresh() {
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
.l5-tab-disclosure-soe { padding: 12px; font-size: 13px; }
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
