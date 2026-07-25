<template>
  <div class="m5-tab-disclosure-soe">
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
        <strong>国有企业盈余公积附注披露（12×16）：</strong>
        与上市公司结构相同，但需额外关注国有资本经营预算相关计提要求、
        特定用途盈余公积的使用限制。国企法定盈余公积计提通常还受国资委相关规定约束。
        数据自动从M5-1审定表/M5-2明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 盈余公积变动明细（国企格式） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>盈余公积变动明细（国有企业）</span>
          <el-button size="small" :loading="aiLoading === 'section-detail'" :disabled="isReadonly" @click="handleAI('section-detail')">
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
          <template #header>
            <el-tooltip content="贷方增加：法定计提/任意计提" placement="top">
              <span class="formula-col-header">本期增加</span>
            </el-tooltip>
          </template>
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
          <template #header>
            <el-tooltip content="借方减少：转增资本/弥补亏损" placement="top">
              <span class="formula-col-header">本期减少</span>
            </el-tooltip>
          </template>
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

    <!-- ═══ Section 2: 法定盈余公积变动说明（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>法定盈余公积变动说明</span>
          <el-button size="small" :loading="aiLoading === 'section-statutory-note'" :disabled="isReadonly" @click="handleAI('section-statutory-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="statutoryNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明法定盈余公积计提情况（按净利润10%计提，国有资本经营预算相关要求等）..."
        @change="handleStatutoryNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 任意盈余公积变动说明（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>任意盈余公积变动说明</span>
          <el-button size="small" :loading="aiLoading === 'section-discretionary-note'" :disabled="isReadonly" @click="handleAI('section-discretionary-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="discretionaryNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明任意盈余公积变动（国企章程规定的提取比例、特定用途使用限制等）..."
        @change="handleDiscretionaryNoteChange"
      />
    </el-card>

    <!-- ═══ Section 4: 国企专项说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国有企业专项披露</span>
          <el-button size="small" :loading="aiLoading === 'section-soe-special'" :disabled="isReadonly" @click="handleAI('section-soe-special')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeSpecialNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="国企专项说明（国有资本经营预算计提要求、特定用途盈余公积使用限制、国资委相关规定等）..."
        @change="handleSoeSpecialNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企格式与上市公司结构相同（法定+任意盈余公积）</li>
        <li>国有企业需额外关注国资委对盈余公积计提和使用的特殊规定</li>
        <li>数据从审定表和明细表自动拉取，订阅审定事件刷新</li>
        <li>期末 = 期初 + 本期增加 - 本期减少（权益类贷方）</li>
        <li>法定盈余公积：按净利润10%，累计达注册资本50%可不再计提</li>
        <li>格式：12行×16列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabDisclosureSoe — 附注披露信息（国有企业）12×16
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 4.6
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - Same structure as Listed but with SOE-specific sections
 * - 国有资本经营预算相关计提要求
 * - Subscribe to EventBus 'substantive:adjudicated' to auto-refresh
 * - textarea sections (autosize) for each disclosure area
 * - AI辅助 per section title
 * - 企业类型由主入口 GtM5SurplusReserve.vue 的 sheetName 分发决定
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM5FormData } from '../../composables/useM5FormData'
import { calcEquityEndBalance } from '../../composables/useM5FormulaEngine'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

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
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM5FormData({
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
  { item: '法定盈余公积', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { item: '任意盈余公积', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
])

const statutoryNote = ref('')
const discretionaryNote = ref('')
const soeSpecialNote = ref('')

// ─── 合计行 + 计算 ──────────────────────────────────────────────────────────

const disclosureRows = computed<DisclosureRow[]>(() => {
  const rows: DisclosureRow[] = dataRows.value.map(r => ({
    ...r,
    // 权益类贷方：期末=期初+增加(计提)-减少(转增/弥补)
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
    formData.debouncedSave(`M5-disclosure-soe-${index}-${field}`, { remark: String(val) })
  }
}

function getRowClassName({ row }: { row: DisclosureRow; rowIndex: number }): string {
  return row._isTotal ? 'total-row' : ''
}

function handleStatutoryNoteChange() {
  formData.debouncedSave('M5-disclosure-soe-statutory-note', { remark: statutoryNote.value || null })
}

function handleDiscretionaryNoteChange() {
  formData.debouncedSave('M5-disclosure-soe-discretionary-note', { remark: discretionaryNote.value || null })
}

function handleSoeSpecialNoteChange() {
  formData.debouncedSave('M5-disclosure-soe-special-note', { remark: soeSpecialNote.value || null })
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const totalRow = disclosureRows.value.find(r => r._isTotal)
    const context: Record<string, string> = {
      科目: '4101 盈余公积（权益类贷方）',
      企业类型: '国有企业',
      期初合计: fmtAmount(totalRow?.beginBalance ?? 0),
      本期增加合计: fmtAmount(totalRow?.increase ?? 0),
      本期减少合计: fmtAmount(totalRow?.decrease ?? 0),
      期末合计: fmtAmount(totalRow?.endBalance ?? 0),
    }
    let existing = ''
    if (section === 'section-statutory-note') existing = statutoryNote.value
    else if (section === 'section-discretionary-note') existing = discretionaryNote.value
    else if (section === 'section-soe-special') existing = soeSpecialNote.value
    const text = await generateAiText({ section: `m5-disclosure-soe-${section}`, context, existingContent: existing })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (section === 'section-statutory-note') { statutoryNote.value = text; handleStatutoryNoteChange() }
    else if (section === 'section-discretionary-note') { discretionaryNote.value = text; handleDiscretionaryNoteChange() }
    else if (section === 'section-soe-special') { soeSpecialNote.value = text; handleSoeSpecialNoteChange() }
    else ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M5-disclosure-soe', '盈余公积附注（国企）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  for (let i = 0; i < dataRows.value.length; i++) {
    for (const field of ['beginBalance', 'increase', 'decrease'] as const) {
      const resp = formData.allResponses.value.get(`M5-disclosure-soe-${i}-${field}`)
      if (resp?.remark) {
        dataRows.value[i][field] = Number(resp.remark) || 0
      }
    }
  }
  const statResp = formData.allResponses.value.get('M5-disclosure-soe-statutory-note')
  if (statResp?.remark) statutoryNote.value = statResp.remark
  const discResp = formData.allResponses.value.get('M5-disclosure-soe-discretionary-note')
  if (discResp?.remark) discretionaryNote.value = discResp.remark
  const soeResp = formData.allResponses.value.get('M5-disclosure-soe-special-note')
  if (soeResp?.remark) soeSpecialNote.value = soeResp.remark
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
.m5-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.total-row-label { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }
.m5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
