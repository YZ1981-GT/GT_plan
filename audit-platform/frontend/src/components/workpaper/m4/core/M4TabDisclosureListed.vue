<template>
  <div class="m4-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" :loading="aiLoading === 'disclosure-listed'" @click="handleAI('disclosure-listed')">
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
          data-testid="m4-disclosure-listed-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（五、55）</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司资本公积附注披露（16×15）：</strong>
        按项目（资本溢价/其他资本公积）列示期初余额、本期增加、本期减少、期末余额。
        数据自动从M4-2明细表/M4-1审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
        资本溢价来源：出资超面值/股本溢价。
        其他资本公积来源：股份支付权益结算(J3)、外币折算差异(M2)、权益法调整等。
      </div>
    </div>

    <!-- ═══ Section 1: 资本公积变动明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>资本公积变动明细</span>
          <el-button size="small" :loading="aiLoading === 'section-detail'" @click="handleAI('section-detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="项目" min-width="180" fixed>
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

    <!-- ═══ Section 2: 资本溢价变动说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>资本溢价变动说明</span>
          <el-button size="small" :loading="aiLoading === 'section-premium-note'" @click="handleAI('section-premium-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="premiumNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明资本溢价的增加原因（如增资、合并溢价）和减少原因（如转增资本）..."
        @change="handlePremiumNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 其他资本公积变动说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>其他资本公积变动说明</span>
          <el-button size="small" :loading="aiLoading === 'section-other-note'" @click="handleAI('section-other-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="otherNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明其他资本公积变动原因（股份支付权益结算、外币折算差异、权益法调整等）..."
        @change="handleOtherNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从M4-1审定表和M4-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司需按资本溢价、其他资本公积分项列示变动</li>
        <li>期末 = 期初 + 本期增加 - 本期减少（权益类贷方）</li>
        <li>格式：16行×15列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M4TabDisclosureListed — 附注披露信息（上市公司）16×15
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 4.5
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - 表格: 项目 | 期初 | 本期增加 | 本期减少 | 期末
 * - 行: 资本溢价 | 其他资本公积 | 合计
 * - Auto-calculated from M4-2 data (subscribe 'substantive:adjudicated')
 * - Static layout matching xlsx structure
 * - AI辅助 per section
 */
import { computed, inject, onMounted, onUnmounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useM4FormData } from '../../composables/useM4FormData'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { calcEquityEndBalance } from '../../composables/useM4FormulaEngine'
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
  { item: '资本溢价（股本溢价）', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
  { item: '其他资本公积', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
])

const premiumNote = ref('')
const otherNote = ref('')

// ─── 合计行 + 计算 ──────────────────────────────────────────────────────────

const disclosureRows = computed<DisclosureRow[]>(() => {
  const rows: DisclosureRow[] = dataRows.value.map(r => ({
    ...r,
    // 期末=期初+增加-减少（权益类贷方：增加=贷方，减少=借方）
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
    formData.debouncedSave(`M4-disclosure-listed-${index}-${field}`, { remark: String(val) })
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  }
}

// ─── 同步到附注（五、55 资本公积变动表） ─────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildMEquitySyncPayload(props.wpId, {
    cycle: 'M4',
    variant: 'listed',
    rows: dataRows.value.map((r) => ({
      label: r.item,
      begin: Number(r.beginBalance) || 0,
      increase: Number(r.increase) || 0,
      decrease: Number(r.decrease) || 0,
    })),
    note: [premiumNote.value, otherNote.value].filter(Boolean).join('\n') || undefined,
  })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success(`已同步到附注（${M_EQUITY_CONFIG.M4.section.listed} 资本公积）`)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'M4',
      projectId: props.projectId,
      sectionIds: [M_EQUITY_CONFIG.M4.section.listed],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'M4', 'listed')
  if (route) router.push(route)
}

function getRowClassName({ row }: { row: DisclosureRow; rowIndex: number }): string {
  return row._isTotal ? 'total-row' : ''
}

function handlePremiumNoteChange() {
  formData.debouncedSave('M4-disclosure-listed-premium-note', { remark: premiumNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function handleOtherNoteChange() {
  formData.debouncedSave('M4-disclosure-listed-other-note', { remark: otherNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const totalRow = disclosureRows.value.find(r => r._isTotal)
    const context: Record<string, string> = {
      科目: '4002 资本公积（权益类贷方）',
      披露口径: '上市公司',
      期末余额合计: fmtAmount(totalRow?.endBalance ?? 0),
      本期增加合计: fmtAmount(totalRow?.increase ?? 0),
      本期减少合计: fmtAmount(totalRow?.decrease ?? 0),
    }
    // section-detail 为表格（无 textarea）→ 建议弹窗
    if (section === 'section-detail') {
      const text = await generateAiText({ section: `m4-disclosure-listed-${section}`, context })
      if (!text) {
        ElMessage.warning('AI 未生成内容，请稍后重试')
        return
      }
      ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
      return
    }
    // 其余 section 回填对应 textarea（'section-other-note' → 其他；其余 → 资本溢价）
    const targetOther = section === 'section-other-note'
    const existing = targetOther ? otherNote.value : premiumNote.value
    const text = await generateAiText({ section: `m4-disclosure-listed-${section}`, context, existingContent: existing })
    if (!text) {
      ElMessage.warning('AI 未生成内容，请稍后重试')
      return
    }
    if (targetOther) {
      otherNote.value = text
      handleOtherNoteChange()
    } else {
      premiumNote.value = text
      handlePremiumNoteChange()
    }
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = ''
  }
}

function handleReview() {
  openReviewDialog?.('M4-disclosure-listed', '附注披露（上市）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  for (let i = 0; i < dataRows.value.length; i++) {
    for (const field of ['beginBalance', 'increase', 'decrease'] as const) {
      const resp = formData.allResponses.value.get(`M4-disclosure-listed-${i}-${field}`)
      if (resp?.remark) {
        dataRows.value[i][field] = Number(resp.remark) || 0
      }
    }
  }
  const premResp = formData.allResponses.value.get('M4-disclosure-listed-premium-note')
  if (premResp?.remark) premiumNote.value = premResp.remark
  const otherResp = formData.allResponses.value.get('M4-disclosure-listed-other-note')
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

onBeforeUnmount(() => { autoSync.cancelPending() })
</script>

<style scoped>
.m4-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.m4-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
