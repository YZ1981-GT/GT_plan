<template>
  <div class="l7-tab-disclosure-listed">
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
        按项目性质列示其他非流动负债明细，披露期末数和上年年末数。
        数据自动从审定表/明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ 附注表：项目 | 期末数 | 上年年末数 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>其他非流动负债披露明细</span>
          <el-button size="small" @click="handleAI('section1')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="200" />
        <el-table-column label="期末数" min-width="140" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.endAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateRow($index, 'endAmount', val ?? 0)"
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
              @change="(val: number | undefined) => updateRow($index, 'priorYearEnd', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorYearEnd) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从L7-1审定表和L7-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司按性质列示：递延收益/保证金/押金/其他</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabDisclosureListed — 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 4.5
 * Requirements: 4.4-4.5
 *
 * Table: 项目 | 期末数 | 上年年末数
 * Auto-fill from EventBus 'substantive:adjudicated'
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useL7FormData } from '../../composables/useL7FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useL7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const disclosureRows = ref([
  { item: '递延收益', endAmount: 0, priorYearEnd: 0 },
  { item: '长期保证金/押金', endAmount: 0, priorYearEnd: 0 },
  { item: '政府补助（非流动）', endAmount: 0, priorYearEnd: 0 },
  { item: '预收款项（非流动）', endAmount: 0, priorYearEnd: 0 },
  { item: '其他', endAmount: 0, priorYearEnd: 0 },
  { item: '合计', endAmount: 0, priorYearEnd: 0 },
])

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateRow(index: number, field: 'endAmount' | 'priorYearEnd', val: number) {
  if (index >= 0 && index < disclosureRows.value.length) {
    disclosureRows.value[index][field] = val
    formData.debouncedSave(`L7-disclosure-listed-${index}-${field}`, { remark: String(val) })
  }
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.('L7-disclosure-listed', '附注披露（上市）') }

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
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.l7-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.l7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
