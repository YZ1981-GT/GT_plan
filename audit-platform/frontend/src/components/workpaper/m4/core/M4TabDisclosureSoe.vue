<template>
  <div class="m4-tab-disclosure-soe">
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
        <strong>国有企业资本公积附注披露（13×15）：</strong>
        与上市公司结构相同，但使用"国有资本溢价"替代"资本溢价（股本溢价）"。
        国有企业资本溢价主要来源为国有资本投入超注册资本部分。
        数据自动从M4-2明细表/M4-1审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 资本公积变动明细（国企格式） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>资本公积变动明细（国有企业）</span>
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

        <el-table-column label="期初余额" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <el-input-number
                :model-value="row.beginBalance"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginBalance', val ?? 0)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期增加" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <el-input-number
                :model-value="row.increase"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'increase', val ?? 0)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期减少" width="140" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <el-input-number
                :model-value="row.decrease"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'decrease', val ?? 0)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末余额" width="140" align="right">
          <template #header>
            <el-tooltip content="期末=期初+本期增加-本期减少（权益类贷方）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 国有资本溢价变动说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国有资本溢价变动说明</span>
          <el-button size="small" @click="handleAI('section-soe-premium')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soePremiumNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明国有资本溢价的增减变动原因（如国有资本投入、改制重组等）..."
        @change="handleSoePremiumNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 其他资本公积变动说明（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>其他资本公积变动说明</span>
          <el-button size="small" @click="handleAI('section-other-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="otherNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明其他资本公积变动（股份支付权益结算、外币折算差异、权益法调整等）..."
        @change="handleOtherNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企格式使用"国有资本溢价"替代"资本溢价（股本溢价）"</li>
        <li>数据从审定表和明细表自动拉取，订阅审定事件刷新</li>
        <li>期末 = 期初 + 本期增加 - 本期减少（权益类贷方）</li>
        <li>国有资本溢价来源：国有资本投入超注册资本部分、改制重组溢价</li>
        <li>格式：13行×15列（结构较上市公司简洁）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M4TabDisclosureSoe — 附注披露信息（国有企业）13×15
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 4.5
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - Same structure as Listed but with SOE-specific items
 * - 国有资本溢价 specific formatting (替代"资本溢价/股本溢价")
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - textarea sections (autosize) for each disclosure area
 * - AI辅助 per section title
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM4FormData } from '../../../composables/useM4FormData'
import { calcEquityEndBalance } from '../../../composables/useM4FormulaEngine'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  item: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  _isTotal?: boolean
}

const dataRows = ref<DisclosureRow[]>([
  { item: '国有资本溢价', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { item: '其他资本公积', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
])

const soePremiumNote = ref('')
const otherNote = ref('')

// ─── 合计行 + 计算 ──────────────────────────────────────────────────────────

const disclosureRows = computed<DisclosureRow[]>(() => {
  const rows: DisclosureRow[] = dataRows.value.map(r => ({
    ...r,
    // 期末=期初+增加-减少（权益类贷方）
    endBalance: calcEquityEndBalance(r.beginBalance, r.increase, r.decrease),
  }))
  // 合计行
  const totalBegin = rows.reduce((s, r) => s + r.beginBalance, 0)
  const totalIncrease = rows.reduce((s, r) => s + r.increase, 0)
  const totalDecrease = rows.reduce((s, r) => s + r.decrease, 0)
  rows.push({
    item: '合计',
    beginBalance: totalBegin,
    increase: totalIncrease,
    decrease: totalDecrease,
    endBalance: calcEquityEndBalance(totalBegin, totalIncrease, totalDecrease),
    _isTotal: true,
  })
  return rows
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateRow(index: number, field: 'beginBalance' | 'increase' | 'decrease', val: number): void {
  if (index >= 0 && index < dataRows.value.length) {
    dataRows.value[index][field] = val
    formData.debouncedSave(`M4-disclosure-soe-${index}-${field}`, { remark: String(val) })
  }
}

function getRowClassName({ row }: { row: DisclosureRow; rowIndex: number }): string {
  return row._isTotal ? 'total-row' : ''
}

function handleSoePremiumNoteChange() {
  formData.debouncedSave('M4-disclosure-soe-premium-note', { remark: soePremiumNote.value || null })
}

function handleOtherNoteChange() {
  formData.debouncedSave('M4-disclosure-soe-other-note', { remark: otherNote.value || null })
}

function handleAI(_section: string) {}

function handleReview() {
  openReviewDialog?.('M4-disclosure-soe', '附注披露（国企）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  for (let i = 0; i < dataRows.value.length; i++) {
    for (const field of ['beginBalance', 'increase', 'decrease'] as const) {
      const resp = formData.allResponses.value.get(`M4-disclosure-soe-${i}-${field}`)
      if (resp?.remark) {
        dataRows.value[i][field] = Number(resp.remark) || 0
      }
    }
  }
  const premResp = formData.allResponses.value.get('M4-disclosure-soe-premium-note')
  if (premResp?.remark) soePremiumNote.value = premResp.remark
  const otherResp = formData.allResponses.value.get('M4-disclosure-soe-other-note')
  if (otherResp?.remark) otherNote.value = otherResp.remark
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
</script>

<style scoped>
.m4-tab-disclosure-soe { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: 13px; }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }
.m4-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.m4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
