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
        <el-button
          type="primary"
          plain
          size="small"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="l7-disclosure-listed-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（五、52）</el-button>
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
      <el-table :data="displayRows" border size="small" style="width: 100%">
        <el-table-column label="项目" min-width="200">
          <template #default="{ row, $index }">
            <span v-if="row.isTotal" class="total-value">{{ row.item }}</span>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.item"
              size="small"
              placeholder="按实际项目性质填列"
              @input="(val: string) => updateRowLabel($index, val)"
            />
            <span v-else>{{ row.item }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endAmount"
              :aria-label="`期末数 ${row.item}`"
              @change="(val: number) => updateRow($index, 'endAmount', val)"
            />
            <span v-else :class="row.isTotal ? 'total-value' : ''">{{ fmtAmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末数" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.priorYearEnd"
              :aria-label="`上年年末数 ${row.item}`"
              @change="(val: number) => updateRow($index, 'priorYearEnd', val)"
            />
            <span v-else :class="row.isTotal ? 'total-value' : ''">{{ fmtAmt(row.priorYearEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row, $index }">
            <el-button
              v-if="!row.isTotal"
              link
              type="danger"
              size="small"
              @click="removeRow($index)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!isReadonly" class="table-actions">
        <el-button size="small" @click="addRow">+ 添加行</el-button>
      </div>
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
import { computed, inject, onMounted, onUnmounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { fmtAmount } from '@/utils/formatters'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useL7FormData } from '../../composables/useL7FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { L7_NOTE_SECTION, buildL7SyncPayload } from '../../composables/l7NoteSectionMap'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const router = useRouter()

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useL7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

interface L7Row { item: string; endAmount: number; priorYearEnd: number }

/** 持久化键（整表 JSON；旧版是逐格 `L7-disclosure-listed-{i}-{field}`，见 restore 兼容） */
const ROWS_ITEM_ID = 'L7-disclosure-listed-rows'

/**
 * 源模板 五、52 是**空行骨架**（r7~r11 五个空行，无固定行名）→ 默认给 5 个
 * 常见项目名作示例、行名可编辑可增删，避免把示例名当披露内容写死。
 */
function defaultRows(): L7Row[] {
  return [
    { item: '递延收益', endAmount: 0, priorYearEnd: 0 },
    { item: '长期保证金/押金', endAmount: 0, priorYearEnd: 0 },
    { item: '政府补助（非流动）', endAmount: 0, priorYearEnd: 0 },
    { item: '预收款项（非流动）', endAmount: 0, priorYearEnd: 0 },
    { item: '其他', endAmount: 0, priorYearEnd: 0 },
  ]
}

const disclosureRows = ref<L7Row[]>(defaultRows())

/** 合计行**读时派生**（禁持久化派生值） */
const displayRows = computed(() => [
  ...disclosureRows.value.map((r) => ({ ...r, isTotal: false })),
  {
    item: '合计',
    endAmount: disclosureRows.value.reduce((s, r) => s + (Number(r.endAmount) || 0), 0),
    priorYearEnd: disclosureRows.value.reduce((s, r) => s + (Number(r.priorYearEnd) || 0), 0),
    isTotal: true,
  },
])

// ─── Handlers ────────────────────────────────────────────────────────────────

function persistRows() {
  formData.debouncedSave(ROWS_ITEM_ID, { remark: JSON.stringify(disclosureRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function updateRow(index: number, field: 'endAmount' | 'priorYearEnd', val: number) {
  if (index >= 0 && index < disclosureRows.value.length) {
    disclosureRows.value[index][field] = val
    persistRows()
  }
}

function updateRowLabel(index: number, val: string) {
  if (index >= 0 && index < disclosureRows.value.length) {
    disclosureRows.value[index].item = val
    persistRows()
  }
}

function addRow() {
  disclosureRows.value.push({ item: '', endAmount: 0, priorYearEnd: 0 })
  persistRows()
}

function removeRow(index: number) {
  if (index >= 0 && index < disclosureRows.value.length) {
    disclosureRows.value.splice(index, 1)
    persistRows()
  }
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────

const isSyncing = ref(false)

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildL7SyncPayload(props.wpId, {
    variant: 'listed',
    rows: disclosureRows.value
      .filter((r) => String(r.item ?? '').trim())
      .map((r) => ({
        label: r.item,
        endAmount: Number(r.endAmount) || 0,
        priorAmount: Number(r.priorYearEnd) || 0,
      })),
  })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success('已同步到附注（五、52 其他非流动负债）')
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'L7',
      projectId: props.projectId,
      sectionIds: [L7_NOTE_SECTION.listed],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'L7', 'listed')
  if (route) router.push(route)
}

// ─── Conclusion ──────────────────────────────────────────────────────────────

const conclusion = ref('')

function saveConclusion() {
  formData.debouncedSave('L7-disc-listed-conclusion', { remark: conclusion.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l7-disclosure-listed-${section}`,
      prompt: `请基于其他非流动负债底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.('L7-disclosure-listed', '附注披露（上市）') }

/** 只读金额走平台单一真源（千分符 + 2 位小数 + 「元」偏好） */
const fmtAmt = (val: number) => fmtAmount(val)

// ─── 反序列化（含旧版逐格 key 兼容） ────────────────────────────────────────

function restoreRows() {
  const packed = formData.allResponses.value.get(ROWS_ITEM_ID)?.remark
  if (packed) {
    try {
      const parsed = JSON.parse(packed)
      if (Array.isArray(parsed) && parsed.length) {
        disclosureRows.value = parsed.map((r: any) => ({
          item: String(r?.item ?? ''),
          endAmount: Number(r?.endAmount) || 0,
          priorYearEnd: Number(r?.priorYearEnd) || 0,
        }))
        return
      }
    } catch { /* 落到旧格式兼容 */ }
  }
  // 旧格式：逐格 `L7-disclosure-listed-{index}-{field}`（含被当数据行的第 6 行合计，丢弃）
  const rows = defaultRows()
  let touched = false
  rows.forEach((row, i) => {
    for (const field of ['endAmount', 'priorYearEnd'] as const) {
      const raw = formData.allResponses.value.get(`L7-disclosure-listed-${i}-${field}`)?.remark
      if (raw != null && raw !== '') {
        const n = Number(raw)
        if (Number.isFinite(n)) { row[field] = n; touched = true }
      }
    }
  })
  if (touched) disclosureRows.value = rows
  const savedConclusion = formData.allResponses.value.get('L7-disc-listed-conclusion')?.remark
  if (savedConclusion) conclusion.value = String(savedConclusion)
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => restoreRows())
}

onMounted(async () => {
  await formData.loadData()
  restoreRows()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onBeforeUnmount(() => { autoSync.cancelPending() })
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
.table-actions { margin-top: 8px; }
.total-value { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.conclusion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
