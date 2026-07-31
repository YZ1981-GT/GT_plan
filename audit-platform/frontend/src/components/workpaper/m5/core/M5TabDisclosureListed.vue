<template>
  <div class="m5-tab-disclosure-listed">
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
        <el-button
          type="primary"
          plain
          size="small"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="m5-disclosure-listed-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（五、59）</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司盈余公积附注披露（12×16）：</strong>
        按项目（法定盈余公积/任意盈余公积）列示期初余额、本期增加（计提）、本期减少（转增/弥补）、期末余额。
        数据自动从M5-1审定表/M5-2明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
        法定盈余公积按净利润10%计提，累计达注册资本50%可不再计提。
      </div>
    </div>

    <!-- ═══ Section 1: 盈余公积变动明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>盈余公积变动明细</span>
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

    <!-- ═══ Section 2: 法定盈余公积变动说明 ═══ -->
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
        placeholder="说明法定盈余公积变动（本期按净利润10%计提XXX元，累计已达/未达注册资本50%，转增资本/弥补亏损情况等）..."
        @change="handleStatutoryNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 任意盈余公积变动说明 ═══ -->
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
        placeholder="说明任意盈余公积变动（股东大会决议提取比例、用途说明等）..."
        @change="handleDiscretionaryNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从M5-1审定表和M5-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司需按法定盈余公积、任意盈余公积分项列示变动</li>
        <li>期末 = 期初 + 本期增加 - 本期减少（权益类贷方）</li>
        <li>法定盈余公积计提比例10%，累计达注册资本50%可不再计提</li>
        <li>格式：12行×16列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabDisclosureListed — 附注披露信息（上市公司）12×16
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 4.6
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - 表格: 项目 | 期初 | 本期增加(计提) | 本期减少(转增/弥补) | 期末
 * - 行: 法定盈余公积 | 任意盈余公积 | 合计
 * - Auto-refresh from M5-1 (subscribe 'substantive:adjudicated')
 * - textarea sections (autosize) for each disclosure area
 * - AI辅助 per section title
 * - 企业类型由主入口 GtM5SurplusReserve.vue 的 sheetName 分发决定
 */
import { computed, inject, onMounted, onUnmounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useM5FormData } from '../../composables/useM5FormData'
import { calcEquityEndBalance } from '../../composables/useM5FormulaEngine'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildMEquitySyncPayload, M_EQUITY_CONFIG } from '../../composables/mEquityChangeNoteSectionMap'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'

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
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const router = useRouter()
const isSyncing = ref(false)

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
    formData.debouncedSave(`M5-disclosure-listed-${index}-${field}`, { remark: String(val) })
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  }
}

function getRowClassName({ row }: { row: DisclosureRow; rowIndex: number }): string {
  return row._isTotal ? 'total-row' : ''
}

function handleStatutoryNoteChange() {
  formData.debouncedSave('M5-disclosure-listed-statutory-note', { remark: statutoryNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleDiscretionaryNoteChange() {
  formData.debouncedSave('M5-disclosure-listed-discretionary-note', { remark: discretionaryNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 同步到附注（五、59 盈余公积变动表） ─────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildMEquitySyncPayload(props.wpId, {
    cycle: 'M5',
    variant: 'listed',
    rows: dataRows.value.map((r) => ({
      label: r.item,
      begin: Number(r.beginBalance) || 0,
      increase: Number(r.increase) || 0,
      decrease: Number(r.decrease) || 0,
    })),
    note: [statutoryNote.value, discretionaryNote.value].filter(Boolean).join('\n') || undefined,
  })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success(`已同步到附注（${M_EQUITY_CONFIG.M5.section.listed} 盈余公积）`)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'M5',
      projectId: props.projectId,
      sectionIds: [M_EQUITY_CONFIG.M5.section.listed],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'M5', 'listed')
  if (route) router.push(route)
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const totalRow = disclosureRows.value.find(r => r._isTotal)
    const context: Record<string, string> = {
      科目: '4101 盈余公积（权益类贷方）',
      企业类型: '上市公司',
      期初合计: fmtAmount(totalRow?.beginBalance ?? 0),
      本期增加合计: fmtAmount(totalRow?.increase ?? 0),
      本期减少合计: fmtAmount(totalRow?.decrease ?? 0),
      期末合计: fmtAmount(totalRow?.endBalance ?? 0),
    }
    let existing = ''
    if (section === 'section-statutory-note') existing = statutoryNote.value
    else if (section === 'section-discretionary-note') existing = discretionaryNote.value
    const text = await generateAiText({ section: `m5-disclosure-listed-${section}`, context, existingContent: existing })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    if (section === 'section-statutory-note') { statutoryNote.value = text; handleStatutoryNoteChange() }
    else if (section === 'section-discretionary-note') { discretionaryNote.value = text; handleDiscretionaryNoteChange() }
    else ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M5-disclosure-listed', '盈余公积附注（上市）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  for (let i = 0; i < dataRows.value.length; i++) {
    for (const field of ['beginBalance', 'increase', 'decrease'] as const) {
      const resp = formData.allResponses.value.get(`M5-disclosure-listed-${i}-${field}`)
      if (resp?.remark) {
        dataRows.value[i][field] = Number(resp.remark) || 0
      }
    }
  }
  const statResp = formData.allResponses.value.get('M5-disclosure-listed-statutory-note')
  if (statResp?.remark) statutoryNote.value = statResp.remark
  const discResp = formData.allResponses.value.get('M5-disclosure-listed-discretionary-note')
  if (discResp?.remark) discretionaryNote.value = discResp.remark
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

onBeforeUnmount(() => { autoSync.cancelPending() })
</script>

<style scoped>
.m5-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
