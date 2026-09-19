<template>
  <div class="l8-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L8 附注披露（国有企业）</h3>
        <el-tag type="info" size="small">从L8-1/L8-2自动取数</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure')">
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
          data-testid="l8-disclosure-soe-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（八、68）</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业附注披露（财务费用）：</strong>
        国企报表附注按财政部企业财务通则要求披露，结构与上市公司类似但增加国资监管专项内容。
        需额外披露：①资金占用费②关联方借款利息③政策性贷款利息优惠。
        数据从L8-1审定表自动取得。
      </div>
    </div>

    <!-- ═══ 附注表格（3列：项目/本期发生额/上期发生额，源模板 12 行） ═══ -->
    <el-table :data="displayRows" border size="small" style="width: 100%">
      <el-table-column prop="label" label="项目" min-width="220">
        <template #default="{ row }">
          <span :class="{ 'formula-value': row.derived, 'total-value': row.key === 'total' }">
            {{ row.label }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="本期发生额" width="180" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!row.derived && !isReadonly"
            :model-value="row.current"
            :aria-label="`本期发生额 ${row.label}`"
            @change="(val: number) => updateInput('current', row.key, val)"
          />
          <span
            v-else
            :class="{ 'formula-value': row.derived, 'total-value': row.key === 'total' }"
            :title="row.derived ? L8_DERIVE_HINT[row.key] : undefined"
          >{{ fmtAmt(row.current) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期发生额" width="180" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="!row.derived && !isReadonly"
            :model-value="row.prior"
            :aria-label="`上期发生额 ${row.label}`"
            @change="(val: number) => updateInput('prior', row.key, val)"
          />
          <span
            v-else
            :class="{ 'formula-value': row.derived, 'total-value': row.key === 'total' }"
            :title="row.derived ? L8_DERIVE_HINT[row.key] : undefined"
          >{{ fmtAmt(row.prior) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 国企专项分析（源模板无此表 → 不进附注） ═══ -->
    <el-card shadow="never" class="soe-extra-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">
            国企专项披露事项
            <el-tag size="small" type="info" effect="plain">底稿分析 · 不进附注</el-tag>
          </span>
          <el-button size="small" @click="handleAI('soeExtra')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <p class="scope-hint">
        源模板「附注披露信息（国企）」无此区块（行集与上市侧完全相同的 12 行）→
        本区块仅作底稿审计分析留痕，不推送附注，避免自造披露内容。
      </p>
      <el-input
        v-model="soeExtraNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="国资监管专项内容（如：资金占用费/关联方借款/政策性贷款优惠）..."
        :disabled="isReadonly"
        @change="saveSoeExtra"
      />
    </el-card>

    <!-- ═══ 附注文本说明 ═══ -->
    <el-card shadow="never" class="note-text-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">附注文本说明</span>
          <el-button size="small" @click="handleAI('noteText')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="附注文本补充说明..."
        :disabled="isReadonly"
        @change="saveNoteText"
      />
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
    <details class="l8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注与上市公司结构类似，增加国资监管专项内容</li>
        <li>需关注：资金占用费（非金融机构利息）/关联方借款利息/政策性贷款利息优惠</li>
        <li>数据自动从L8-1审定表取得（EventBus联动）</li>
        <li>合计行自动计算</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L8TabDisclosureSoe — L8 附注披露（国有企业）
 *
 * Requirements: 7.5
 * - 3列结构：项目/本期金额/上期金额（同上市版）
 * - 增加国企专项披露事项区
 * - 从L8-1/L8-2自动取数（EventBus联动）
 */
import { computed, inject, onMounted, onUnmounted, onBeforeUnmount, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { fmtAmount } from '@/utils/formatters'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useL8FormData } from '../../composables/useL8FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'
import {
  L8_NOTE_SECTION,
  buildL8DisplayRows,
  buildL8SyncPayload,
  createEmptyL8Period,
  type L8InputKey,
  type L8PeriodValues,
} from '../../composables/l8NoteSectionMap'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const router = useRouter()

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useL8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 附注行数据（源 xlsx 八、68 r7~r18 共 12 行，与上市侧完全相同） ──────────
//
// 🔴 原组件自造 10 行（含「其中：金融机构借款利息」等源模板没有的行）→ 已按源模板统一。
//    国资专项内容移到下方「不进附注」区块。
const DATA_ITEM_ID = 'L8-disclosure-soe-data'

const current = ref<L8PeriodValues>(createEmptyL8Period())
const prior = ref<L8PeriodValues>(createEmptyL8Period())

const displayRows = computed(() => buildL8DisplayRows(current.value, prior.value))

const L8_DERIVE_HINT: Record<string, string> = {
  interestExpense: '利息费用 = 利息费用总额 − 利息资本化',
  interestNet: '利息净支出 = 利息费用 − 利息收入',
  exchangeNet: '汇兑净损失 = 汇兑损失 − 汇兑收益 − 汇兑损益资本化',
  total: '合计 = 利息净支出 + 承兑汇票贴息 + 汇兑净损失 + 手续费及其他',
}

function updateInput(period: 'current' | 'prior', key: L8InputKey, value: number) {
  const target = period === 'current' ? current : prior
  target.value = { ...target.value, [key]: value }
  _triggerSave()
}

// ─── State ───────────────────────────────────────────────────────────────────

const noteText = ref('')
const soeExtraNote = ref('')
const isSyncing = ref(false)

// ─── Handlers ────────────────────────────────────────────────────────────────

function _triggerSave() {
  formData.debouncedSave(DATA_ITEM_ID, {
    remark: JSON.stringify({ current: current.value, prior: prior.value }),
  })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function saveNoteText() {
  formData.debouncedSave('L8-disclosure-soe-note', { remark: noteText.value || null })
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildL8SyncPayload(props.wpId, {
    variant: 'soe',
    current: current.value,
    prior: prior.value,
  })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success('已同步到附注（八、68 财务费用）')
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'L8',
      projectId: props.projectId,
      sectionIds: [L8_NOTE_SECTION.soe],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'L8', 'soe')
  if (route) router.push(route)
}

function saveSoeExtra() {
  formData.debouncedSave('L8-disclosure-soe-extra', { remark: soeExtraNote.value || null })
}

// ─── Conclusion ──────────────────────────────────────────────────────────────

const conclusion = ref('')

function saveConclusion() {
  formData.debouncedSave('L8-disc-soe-conclusion', { remark: conclusion.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l8-disclosure-soe-${section}`,
      prompt: `请基于财务费用底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.('L8-disclosure-soe', '附注(国企)') }

// ─── Format ──────────────────────────────────────────────────────────────────

/** 只读金额走平台单一真源 */
const fmtAmt = (val: number) => fmtAmount(val)

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjudicated() {
  formData.loadData().then(() => _restoreData())
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreData()
  eventBus.on('substantive:adjudicated' as any, handleAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
})

onBeforeUnmount(() => { autoSync.cancelPending() })

/**
 * 反序列化。新格式 `{current,prior}`；旧格式是 10 行自造数组，按行名映射到
 * 源模板录入键（「其中：金融机构借款利息」等源模板没有的行丢弃）。
 */
const LEGACY_LABEL_TO_KEY: Record<string, L8InputKey> = {
  '利息费用': 'interestTotal',
  '减：利息资本化金额': 'interestCapitalized',
  '减：利息资本化': 'interestCapitalized',
  '减：利息收入': 'interestIncome',
  '汇兑损益（净损失以"+"号列示）': 'exchangeLoss',
  '手续费': 'feeAndOther',
}

function _restoreData() {
  const data = formData.allResponses.value.get(DATA_ITEM_ID)
  if (data?.remark) {
    try {
      const parsed = JSON.parse(data.remark)
      if (parsed && !Array.isArray(parsed) && (parsed.current || parsed.prior)) {
        current.value = { ...createEmptyL8Period(), ...(parsed.current || {}) }
        prior.value = { ...createEmptyL8Period(), ...(parsed.prior || {}) }
      } else if (Array.isArray(parsed)) {
        const c = createEmptyL8Period()
        const p = createEmptyL8Period()
        for (const r of parsed) {
          const key = LEGACY_LABEL_TO_KEY[String(r?.item ?? '')]
          if (!key) continue
          c[key] = Number(r?.currentAmount) || 0
          p[key] = Number(r?.priorAmount) || 0
        }
        current.value = c
        prior.value = p
      }
    } catch { /* ignore */ }
  }
  const nt = formData.allResponses.value.get('L8-disclosure-soe-note')
  if (nt?.remark) noteText.value = String(nt.remark)
  const extra = formData.allResponses.value.get('L8-disclosure-soe-extra')
  if (extra?.remark) soeExtraNote.value = String(extra.remark)
  const conc = formData.allResponses.value.get('L8-disc-soe-conclusion')
  if (conc?.remark) conclusion.value = String(conc.remark)
}
</script>

<style scoped>
.l8-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.formula-value { color: #409eff; font-weight: 500; border-bottom: 1px dashed var(--el-border-color); }
.scope-hint { margin: 0 0 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.total-value { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.soe-extra-card { margin-top: 16px; }
.note-text-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 16px; }
.l8-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l8-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l8-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
