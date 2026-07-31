<template>
  <div class="l7-tab-disclosure-soe">
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
        <el-button
          type="primary"
          plain
          size="small"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="l7-disclosure-soe-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（八、57）</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>国有企业附注披露要求：</strong>
        除通用披露外，需按年初余额和期末余额列示其他非流动负债。
        国企格式重点关注国有资本相关融资安排和政府补贴明细。
        数据自动从审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ 附注表：项目 | 年初余额 | 期末余额 ═══ -->
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
        <el-table-column label="年初余额" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.beginBalance"
              :aria-label="`年初余额 ${row.item}`"
              @change="(val: number) => updateRow($index, 'beginBalance', val)"
            />
            <span v-else :class="row.isTotal ? 'total-value' : ''">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="140" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endBalance"
              :aria-label="`期末余额 ${row.item}`"
              @change="(val: number) => updateRow($index, 'endBalance', val)"
            />
            <span v-else :class="row.isTotal ? 'total-value' : ''">{{ fmtAmt(row.endBalance) }}</span>
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
      <p class="order-hint">
        注：本表按源模板列序「年初余额 / 期末余额」录入；推送附注时投影为交付物口径
        「期末余额 / 期初余额」（与上市侧一致）。
      </p>
    </el-card>

    <!-- ═══ 国资专项说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>国资体系专项说明</span>
          <el-button size="small" @click="handleAI('section2')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeSpecialNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="国资体系内融资安排、政府贴息/补贴明细、国有股东相关安排等专项说明..."
        @change="handleSoeNoteChange"
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
    <details class="l7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国企需额外披露国资体系内融资安排</li>
        <li>列报顺序为：项目 | 年初余额 | 期末余额（与上市公司不同）</li>
        <li>数据从审定表和明细表自动拉取，订阅审定事件刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L7TabDisclosureSoe — 附注披露信息（国有企业）
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 4.5
 * Requirements: 4.4-4.5
 *
 * Table: 项目 | 年初余额 | 期末余额 (same data different order from Listed)
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

interface L7SoeRow { item: string; beginBalance: number; endBalance: number }

const ROWS_ITEM_ID = 'L7-disclosure-soe-rows'

/** 源模板 八、57 数据行取模板 seed（待转销项税额 / 合同负债），行名可编辑可增删 */
function defaultRows(): L7SoeRow[] {
  return [
    { item: '待转销项税额', beginBalance: 0, endBalance: 0 },
    { item: '合同负债', beginBalance: 0, endBalance: 0 },
    { item: '', beginBalance: 0, endBalance: 0 },
  ]
}

const disclosureRows = ref<L7SoeRow[]>(defaultRows())

/** 合计行读时派生 */
const displayRows = computed(() => [
  ...disclosureRows.value.map((r) => ({ ...r, isTotal: false })),
  {
    item: '合计',
    beginBalance: disclosureRows.value.reduce((s, r) => s + (Number(r.beginBalance) || 0), 0),
    endBalance: disclosureRows.value.reduce((s, r) => s + (Number(r.endBalance) || 0), 0),
    isTotal: true,
  },
])

const soeSpecialNote = ref('')

// ─── Handlers ────────────────────────────────────────────────────────────────

function persistRows() {
  formData.debouncedSave(ROWS_ITEM_ID, { remark: JSON.stringify(disclosureRows.value) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function updateRow(index: number, field: 'beginBalance' | 'endBalance', val: number) {
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
  disclosureRows.value.push({ item: '', beginBalance: 0, endBalance: 0 })
  persistRows()
}

function removeRow(index: number) {
  if (index >= 0 && index < disclosureRows.value.length) {
    disclosureRows.value.splice(index, 1)
    persistRows()
  }
}

function handleSoeNoteChange() {
  formData.debouncedSave('L7-disclosure-soe-special', { remark: soeSpecialNote.value || null })
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────

const isSyncing = ref(false)

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  // 投影：底稿列序（年初/期末）→ 附注交付物口径（期末/期初）
  const payload = buildL7SyncPayload(props.wpId, {
    variant: 'soe',
    rows: disclosureRows.value
      .filter((r) => String(r.item ?? '').trim())
      .map((r) => ({
        label: r.item,
        endAmount: Number(r.endBalance) || 0,
        priorAmount: Number(r.beginBalance) || 0,
      })),
  })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success('已同步到附注（八、57 其他非流动负债）')
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'L7',
      projectId: props.projectId,
      sectionIds: [L7_NOTE_SECTION.soe],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'L7', 'soe')
  if (route) router.push(route)
}

// ─── Conclusion ──────────────────────────────────────────────────────────────

const conclusion = ref('')

function saveConclusion() {
  formData.debouncedSave('L7-disc-soe-conclusion', { remark: conclusion.value || null })
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l7-disclosure-soe-${section}`,
      prompt: `请基于其他非流动负债底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.('L7-disclosure-soe', '附注披露（国企）') }

/** 只读金额走平台单一真源 */
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
          beginBalance: Number(r?.beginBalance) || 0,
          endBalance: Number(r?.endBalance) || 0,
        }))
        return
      }
    } catch { /* 落到旧格式兼容 */ }
  }
  // 旧格式：逐格 `L7-disclosure-soe-{index}-{field}`（旧默认 5 行 + 第 6 行合计，合计丢弃）
  const legacyDefaults = ['递延收益', '长期保证金/押金', '政府补助（非流动）', '预收款项（非流动）', '其他']
  const rows: L7SoeRow[] = legacyDefaults.map((item) => ({ item, beginBalance: 0, endBalance: 0 }))
  let touched = false
  rows.forEach((row, i) => {
    for (const field of ['beginBalance', 'endBalance'] as const) {
      const raw = formData.allResponses.value.get(`L7-disclosure-soe-${i}-${field}`)?.remark
      if (raw != null && raw !== '') {
        const n = Number(raw)
        if (Number.isFinite(n)) { row[field] = n; touched = true }
      }
    }
  })
  if (touched) disclosureRows.value = rows
  const special = formData.allResponses.value.get('L7-disclosure-soe-special')?.remark
  if (special) soeSpecialNote.value = String(special)
  const savedConclusion = formData.allResponses.value.get('L7-disc-soe-conclusion')?.remark
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
.l7-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.order-hint { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.conclusion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
