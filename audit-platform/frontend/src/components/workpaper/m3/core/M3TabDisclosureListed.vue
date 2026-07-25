<template>
  <div class="m3-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">库存股·上市</el-tag>
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
        <strong>上市公司库存股附注披露（16×11）：</strong>
        按回购批次/目的列示库存股变动情况。数据自动从审定表/明细表拉取
        （subscribe 'substantive:adjudicated' 事件刷新）。
        披露期初/本期回购增加/本期注销减少/期末库存股金额及股数。
      </div>
    </div>

    <!-- ═══ Section 1: 库存股变动明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>库存股变动明细</span>
          <div style="display:flex;align-items:center;gap:8px">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handlePullFromAdjudication">
              从审定表/明细表带入
            </el-button>
            <el-button size="small" :loading="aiLoading === 'section-treasury-change'" :disabled="isReadonly" @click="handleAI('section-treasury-change')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>
      <el-table :data="treasuryChangeRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="160" />
        <el-table-column label="期初金额" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateTreasuryRow($index, 'beginAmount', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.beginAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期回购增加" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.repurchaseIncrease"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateTreasuryRow($index, 'repurchaseIncrease', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.repurchaseIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期注销减少" min-width="130" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.cancelDecrease"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(val: number | undefined) => updateTreasuryRow($index, 'cancelDecrease', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.cancelDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="公式: 期初 + 回购增加 − 注销减少（备抵借方）" placement="top">
              <span class="formula-col-header">期末金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 回购目的说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>回购目的及用途说明</span>
          <el-button size="small" :loading="aiLoading === 'section-purpose'" :disabled="isReadonly" @click="handleAI('section-purpose')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="purposeNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明回购股份的目的（如：员工持股计划/市值管理/减少注册资本/转换可转债等）及期末持有情况..."
        @change="handleNoteChange('purpose', purposeNote)"
      />
    </el-card>

    <!-- ═══ Section 3: 回购方案执行情况 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>回购方案执行情况</span>
          <el-button size="small" :loading="aiLoading === 'section-execution'" :disabled="isReadonly" @click="handleAI('section-execution')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="executionNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="披露回购方案的审议日期/回购价格区间/回购期限/已回购股数占比/资金来源..."
        @change="handleNoteChange('execution', executionNote)"
      />
    </el-card>

    <!-- ═══ Section 4: 对权益影响说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>对所有者权益的影响说明</span>
          <el-button size="small" :loading="aiLoading === 'section-equity-impact'" :disabled="isReadonly" @click="handleAI('section-equity-impact')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="equityImpactNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="库存股作为权益备抵在资产负债表所有者权益项下以负数列示。对每股净资产/每股收益的影响..."
        @change="handleNoteChange('equity-impact', equityImpactNote)"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>库存股在资产负债表所有者权益项下以<strong>负数</strong>列示（借方余额）</li>
        <li>数据优先从M3-1审定表和M3-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>需额外披露：回购目的/方案执行/对权益影响</li>
        <li>期末金额 = 期初 + 本期回购(借方增加) − 本期注销(贷方减少)（备抵借方方向）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M3TabDisclosureListed — 附注披露信息（上市公司）库存股
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 4.6
 * Requirements: 6.2-6.3
 *
 * 功能：
 * - 上市公司版附注（库存股变动明细）
 * - Subscribe EventBus 'substantive:adjudicated' refresh
 * - 回购目的/方案执行/权益影响 textarea sections
 * - AI辅助 per section
 *
 * 科目：4002 库存股（**借方/权益备抵类！**）
 */
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM3FormData } from '../../composables/useM3FormData'
import { calcContraEquityEndBalance } from '../../composables/useM3FormulaEngine'
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

const formData = useM3FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

interface TreasuryDisclosureRow {
  item: string
  beginAmount: number
  repurchaseIncrease: number
  cancelDecrease: number
  endAmount: number
}

const treasuryChangeRows = ref<TreasuryDisclosureRow[]>([
  { item: '一、库存股合计', beginAmount: 0, repurchaseIncrease: 0, cancelDecrease: 0, endAmount: 0 },
  { item: '  其中：员工持股计划', beginAmount: 0, repurchaseIncrease: 0, cancelDecrease: 0, endAmount: 0 },
  { item: '  市值管理/减少注册资本', beginAmount: 0, repurchaseIncrease: 0, cancelDecrease: 0, endAmount: 0 },
  { item: '  股权激励', beginAmount: 0, repurchaseIncrease: 0, cancelDecrease: 0, endAmount: 0 },
  { item: '  其他', beginAmount: 0, repurchaseIncrease: 0, cancelDecrease: 0, endAmount: 0 },
])

const purposeNote = ref('')
const executionNote = ref('')
const equityImpactNote = ref('')

// ─── Computed: 期末 = 期初 + 回购增加 − 注销减少（备抵借方） ───────────────

function recalcEnd(): void {
  treasuryChangeRows.value.forEach(row => {
    row.endAmount = calcContraEquityEndBalance(row.beginAmount, row.repurchaseIncrease, row.cancelDecrease)
  })
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateTreasuryRow(index: number, field: 'beginAmount' | 'repurchaseIncrease' | 'cancelDecrease', val: number) {
  if (index >= 0 && index < treasuryChangeRows.value.length) {
    treasuryChangeRows.value[index][field] = val
    recalcEnd()
    formData.debouncedSave('M3-disclosure-listed-treasury-rows', {
      remark: JSON.stringify(treasuryChangeRows.value),
    })
  }
}

function handleNoteChange(section: string, value: string) {
  formData.debouncedSave(`M3-disclosure-listed-${section}`, { remark: value || null })
}

/**
 * 从审定表(M3-1)和明细表(M3-2)主动拉取数据填入附注变动明细。
 * 读取 allResponses 中已持久化的 M3-1/M3-2 审定合计值填充库存股合计行。
 * 仅在合计行全0时自动seed，否则让审计师确认覆盖。
 */
async function handlePullFromAdjudication() {
  // 重新加载确保最新数据
  await formData.loadData()

  // 从M3-1审定表取期初/期末审定合计
  const adjTotalAudited = _parseNum(formData.allResponses.value.get('M3-M3-1-total-audited')?.remark)

  // 从M3-2明细表取回购/注销合计
  // 尝试遍历明细行求和
  let totalRepurchase = 0
  let totalCancel = 0
  let totalBegin = 0
  for (const [key, resp] of formData.allResponses.value) {
    if (key.startsWith('M3-M3-2-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const row = JSON.parse(resp.remark)
        totalRepurchase += _parseNum(row.repurchaseAmount)
        totalCancel += _parseNum(row.cancelAmount)
        totalBegin += _parseNum(row.beginAmount)
      } catch { /* skip */ }
    }
  }

  // 填入合计行(index 0)
  const sumRow = treasuryChangeRows.value[0]
  if (sumRow) {
    const hasExisting = sumRow.beginAmount !== 0 || sumRow.repurchaseIncrease !== 0 || sumRow.cancelDecrease !== 0
    if (hasExisting) {
      // 有旧值，确认覆盖
      try {
        await import('element-plus').then(({ ElMessageBox }) =>
          ElMessageBox.confirm(
            `将覆盖合计行现有数据：期初${fmtAmount(sumRow.beginAmount)}→${fmtAmount(totalBegin)}，回购${fmtAmount(sumRow.repurchaseIncrease)}→${fmtAmount(totalRepurchase)}，注销${fmtAmount(sumRow.cancelDecrease)}→${fmtAmount(totalCancel)}`,
            '确认从底稿带入',
            { confirmButtonText: '确认覆盖', cancelButtonText: '取消', type: 'warning' },
          ),
        )
      } catch {
        return // 取消
      }
    }
    sumRow.beginAmount = totalBegin
    sumRow.repurchaseIncrease = totalRepurchase
    sumRow.cancelDecrease = totalCancel
    recalcEnd()
    formData.debouncedSave('M3-disclosure-listed-treasury-rows', {
      remark: JSON.stringify(treasuryChangeRows.value),
    })
    import('element-plus').then(({ ElMessage }) => {
      ElMessage.success(`已从审定表/明细表带入：期初${fmtAmount(totalBegin)}，回购+${fmtAmount(totalRepurchase)}，注销-${fmtAmount(totalCancel)}`)
    })
  }
}

function _parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const sumRow = treasuryChangeRows.value[0]
    const context: Record<string, string> = {
      科目: '4002 库存股（权益备抵类·借方，附注披露-上市公司）',
      期初金额: fmtAmount(sumRow?.beginAmount || 0),
      本期回购增加: fmtAmount(sumRow?.repurchaseIncrease || 0),
      本期注销减少: fmtAmount(sumRow?.cancelDecrease || 0),
      期末金额: fmtAmount(sumRow?.endAmount || 0),
    }
    let target: 'purpose' | 'execution' | 'equity-impact' | '' = ''
    if (section === 'section-purpose') target = 'purpose'
    else if (section === 'section-execution') target = 'execution'
    else if (section === 'section-equity-impact') target = 'equity-impact'
    const existing =
      target === 'purpose' ? purposeNote.value
      : target === 'execution' ? executionNote.value
      : target === 'equity-impact' ? equityImpactNote.value
      : ''
    const text = await generateAiText({ section: `m3-disclosure-listed-${section}`, context, existingContent: existing })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (target === 'purpose') { purposeNote.value = text; handleNoteChange('purpose', text) }
    else if (target === 'execution') { executionNote.value = text; handleNoteChange('execution', text) }
    else if (target === 'equity-impact') { equityImpactNote.value = text; handleNoteChange('equity-impact', text) }
    else { ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {}) }
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = ''
  }
}
function handleReview() { openReviewDialog?.('M3-disclosure-listed', '附注披露（上市）') }

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Restore state ──────────────────────────────────────────────────────────

function _restoreFromResponses(): void {
  const rowData = formData.allResponses.value.get('M3-disclosure-listed-treasury-rows')
  if (rowData?.remark) {
    try {
      const parsed = JSON.parse(rowData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        treasuryChangeRows.value = parsed
        recalcEnd()
      }
    } catch { /* ignore */ }
  }

  const purpose = formData.allResponses.value.get('M3-disclosure-listed-purpose')
  if (purpose?.remark) purposeNote.value = purpose.remark

  const execution = formData.allResponses.value.get('M3-disclosure-listed-execution')
  if (execution?.remark) executionNote.value = execution.remark

  const equity = formData.allResponses.value.get('M3-disclosure-listed-equity-impact')
  if (equity?.remark) equityImpactNote.value = equity.remark
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
.m3-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.m3-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
