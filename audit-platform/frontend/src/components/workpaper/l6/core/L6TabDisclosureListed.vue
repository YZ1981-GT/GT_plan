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
        <el-button
          type="primary"
          plain
          size="small"
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          data-testid="l6-disclosure-listed-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（五、48）</el-button>
      </div>
    </div>

    <!-- ═══ 共章节说明（L6 与 L5 共 §五、48，按子表名浅合并） ═══ -->
    <el-alert type="info" :closable="false" show-icon class="shared-section-alert">
      本表同步到附注 <strong>§五、48 长期应付款</strong> 的子表「专项应付款」——
      与 L5 长期应付款共章节（源模板：【长期应付款与专项应付款的合计数披露详见P5-1】），
      两个底稿各推自己的子表，互不覆盖。
    </el-alert>

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
import { computed, inject, onMounted, onUnmounted, onBeforeUnmount, ref } from 'vue'
import { MagicStick, Check, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useL6FormData } from '../../composables/useL6FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'
import { L5_NOTE_SECTION, buildL6SyncPayload } from '../../composables/l5NoteSectionMap'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const router = useRouter()

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

const conclusion = ref('')

function saveConclusion() {
  formData.debouncedSave('L6-disc-listed-conclusion', { remark: conclusion.value || null })
}

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
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  }
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────

const isSyncing = ref(false)

/** 占位提示行不得推送（否则附注多一行占位披露数据） */
const PLACEHOLDER_MARK = '暂无数据'

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const rows = disclosureRows.value
    .filter((r) => String(r.project ?? '').trim() && !r.project.includes(PLACEHOLDER_MARK))
    .map((r) => ({
      label: r.project,
      beginAmount: Number(r.beginBalance) || 0,
      increase: Number(r.increase) || 0,
      decrease: Number(r.decrease) || 0,
      reason: r.reason ?? '',
    }))
  if (rows.length === 0) {
    ElMessage.warning('请先在 L6-2 明细表填写专项应付款数据')
    return
  }
  const payload = buildL6SyncPayload(props.wpId, { variant: 'listed', rows })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success('已同步到附注（五、48 专项应付款）')
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'L6',
      projectId: props.projectId,
      sectionIds: [L5_NOTE_SECTION.listed],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'L6', 'listed')
  if (route) router.push(route)
}

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `l6-disclosure-listed-${section}`,
      prompt: `请基于专项应付款底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => {
    loadDisclosureData()
    // 上游 L6-2 审定数变化 → 本表数据随之变化 → 自动同步（监听实际数据）
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  })
}

onMounted(async () => {
  await formData.loadData()
  loadDisclosureData()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
})

onBeforeUnmount(() => { autoSync.cancelPending() })
</script>

<style scoped>
.l6-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.disclosure-card { margin-bottom: 16px; }
.shared-section-alert { margin-bottom: 12px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.formula-value { color: #409eff; font-weight: 500; }
.sub-header { font-size: 11px; color: #909399; }
.total-row { display: flex; gap: 20px; padding: 10px 16px; margin-top: 8px; background: #f5f7fa; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #606266; }
.auto-pull-notice { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: #ecf5ff; border-radius: 4px; margin-bottom: 12px; font-size: 12px; color: #409eff; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.conclusion-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.l6-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.l6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
