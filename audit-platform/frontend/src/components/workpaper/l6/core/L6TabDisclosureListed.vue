<template>
  <div class="l6-tab-disclosure-listed">
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
        按专项项目列示专项应付款明细，披露期初数、本期增加（拨入）、本期减少（结转+返还）、
        期末数、形成原因。数据自动从L6-2明细表审定数区（P~T列）拉取，仅供核对。
      </div>
    </div>

    <!-- ═══ 专项应付款明细表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（2）专项应付款</span>
          <el-button size="small" @click="handleAI('section-detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%">
        <el-table-column prop="project" label="项目" min-width="160" />
        <el-table-column label="期初数" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="130" align="right">
          <template #header>
            <div>
              <div>本期减少</div>
              <div class="sub-header">（结转+返还）</div>
            </div>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="形成原因" min-width="180">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.reason"
              size="small"
              placeholder="形成原因"
              @change="(val: string) => updateReason($index, val)"
            />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="total-row">
        <span>合计：</span>
        <span>期初 <strong>{{ fmtAmount(totalBegin) }}</strong></span>
        <span>本期增加 <strong>{{ fmtAmount(totalIncrease) }}</strong></span>
        <span>本期减少 <strong>{{ fmtAmount(totalDecrease) }}</strong></span>
        <span>期末 <strong>{{ fmtAmount(totalEnd) }}</strong></span>
      </div>
    </el-card>

    <!-- ═══ 数据来源说明 ═══ -->
    <div class="auto-pull-notice">
      <el-icon><InfoFilled /></el-icon>
      <span>数据自动从L6-2明细表审定数区（P~T列）拉取，订阅审定事件自动刷新</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据自动从L6-2明细表审定数区拉取（只读）</li>
        <li>本期减少 = 结转金额 + 返还金额</li>
        <li>期末数 = 期初数 + 本期增加 − 本期减少</li>
        <li>形成原因需手动填写（如"政府科技专项拨款"等）</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>【长期应付款与专项应付款的合计数披露详见P5-1】</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L6TabDisclosureListed — 附注披露信息（上市公司）
 * Requirements: 5.2, 5.3
 *
 * 功能：
 * - 表结构：项目 | 期初数 | 本期增加 | 本期减少(结转+返还) | 期末数 | 形成原因
 * - Data from L6-2 detail（审定数区 P~T列）— auto-computed from responses
 * - Subscribe EventBus 'substantive:adjudicated' to refresh
 * - Read-only table (data auto-pulled from L6-2)
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check, InfoFilled } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useL6FormData } from '../../../composables/useL6FormData'

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

const formData = useL6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

/** 附注披露行（自动从L6-2审定数区P~T列拉取） */
interface DisclosureRow {
  /** 项目名称 */
  project: string
  /** 期初数 */
  beginBalance: number
  /** 本期增加 */
  increase: number
  /** 本期减少（结转+返还） */
  decrease: number
  /** 期末数 */
  endBalance: number
  /** 形成原因（手动填写） */
  reason: string
}

const disclosureRows = ref<DisclosureRow[]>([])

// ─── Computed totals ─────────────────────────────────────────────────────────

const totalBegin = computed(() => disclosureRows.value.reduce((s, r) => s + r.beginBalance, 0))
const totalIncrease = computed(() => disclosureRows.value.reduce((s, r) => s + r.increase, 0))
const totalDecrease = computed(() => disclosureRows.value.reduce((s, r) => s + r.decrease, 0))
const totalEnd = computed(() => disclosureRows.value.reduce((s, r) => s + r.endBalance, 0))

// ─── Load from responses (L6-2 审定数区自动填充) ─────────────────────────────

function loadDisclosureData() {
  const responses = formData.responses.value
  const rows: DisclosureRow[] = []

  // 从L6-2明细表审定数区(P~T列)拉取数据
  // item_id 格式: L6-L6-2-row{n}-{field}
  for (let i = 1; i <= 20; i++) {
    const projectName = responses.get(`L6-L6-2-row${i}-project`)?.remark
    if (!projectName) continue

    const beginBalance = parseFloat(responses.get(`L6-L6-2-row${i}-audited_begin`)?.remark || '0') || 0
    const increase = parseFloat(responses.get(`L6-L6-2-row${i}-audited_increase`)?.remark || '0') || 0
    const settleAmount = parseFloat(responses.get(`L6-L6-2-row${i}-audited_settle`)?.remark || '0') || 0
    const returnAmount = parseFloat(responses.get(`L6-L6-2-row${i}-audited_return`)?.remark || '0') || 0
    const endBalance = parseFloat(responses.get(`L6-L6-2-row${i}-audited_end`)?.remark || '0') || 0
    const reason = responses.get(`L6-disclosure-listed-reason-${i}`)?.remark || ''

    rows.push({
      project: projectName,
      beginBalance,
      increase,
      decrease: settleAmount + returnAmount,
      endBalance,
      reason,
    })
  }

  // 如果没有数据则显示默认空行
  if (rows.length === 0) {
    rows.push(
      { project: '（暂无数据，请先在L6-2明细表填写）', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, reason: '' },
    )
  }

  disclosureRows.value = rows
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateReason(index: number, val: string) {
  if (index >= 0 && index < disclosureRows.value.length) {
    disclosureRows.value[index].reason = val
    formData.debouncedSave(`L6-disclosure-listed-reason-${index + 1}`, { remark: val || null })
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
  formData.loadData().then(() => loadDisclosureData())
}

onMounted(async () => {
  await formData.loadData()
  loadDisclosureData()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
})
</script>

<style scoped>
.l6-tab-disclosure-listed { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.formula-value { color: #409eff; font-weight: 500; }
.sub-header { font-size: 11px; color: #909399; }
.total-row { display: flex; gap: 20px; padding: 10px 16px; margin-top: 8px; background: #f5f7fa; border-radius: 4px; font-size: 13px; color: #606266; }
.auto-pull-notice { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: #ecf5ff; border-radius: 4px; margin-bottom: 12px; font-size: 12px; color: #409eff; }
:deep(.el-table) { font-size: 13px; }
.l6-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.l6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
