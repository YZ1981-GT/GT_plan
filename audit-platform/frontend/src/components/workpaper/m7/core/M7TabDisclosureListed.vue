<template>
  <div class="m7-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag v-if="lastRefreshTime" type="info" size="small" effect="plain">
          上次刷新: {{ lastRefreshTime }}
        </el-tag>
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
          data-testid="m7-disclosure-listed-sync"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
        <el-button size="small" plain @click="jumpToNote">↩ 附注（五、58）</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>附注披露（上市公司）：</strong>
        按照上市公司财报附注格式，披露专项储备期初余额、本期增加（计提）、本期减少（使用）及期末余额。
        审定表（M7-1）数据变化时自动刷新此表，确保附注与审定数一致。
      </div>
    </div>

    <!-- ═══ 附注披露表格 (11×7) ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">专项储备附注披露表</span>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="160" />
        <el-table-column prop="beginBalance" label="期初余额" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.beginBalance) }}</template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.increase) }}</template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.decrease) }}</template>
        </el-table-column>
        <el-table-column prop="endBalance" label="期末余额" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.endBalance) }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="增减原因说明" min-width="200">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              v-model="disclosureRows[$index].reason"
              size="small"
              placeholder="请填写变动原因"
              @change="handleReasonChange($index)"
            />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 披露说明文字区 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">披露说明</span>
          <el-button size="small" :loading="aiLoading === 'disclosure-note'" @click="handleAI('disclosure-note')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="disclosureNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写专项储备附注披露说明..."
        :disabled="isReadonly"
        @change="saveDisclosureNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司附注按CAS格式披露专项储备变动</li>
        <li>数据来源：M7-1审定表（审定数变化时自动推送刷新）</li>
        <li>增加原因=安全生产费计提（贷方），减少原因=使用支出（借方）</li>
        <li>确保期末余额与试算表一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 6.1
 * Requirements: 6.2, 6.3
 *
 * EventBus集成：
 * - subscribe 'substantive:adjudicated' → 自动刷新附注数据（当M7-1审定数变化时）
 * - 组件卸载时 off 清理
 */
import { computed, inject, onMounted, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useM7FormData } from '../../composables/useM7FormData'
import { useNoteAutoFill } from '../../composables/useNoteAutoFill'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { buildMEquitySyncPayload, M_EQUITY_CONFIG } from '../../composables/mEquityChangeNoteSectionMap'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
const router = useRouter()
const isSyncing = ref(false)

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM7FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

// ─── State ───────────────────────────────────────────────────────────────────
const lastRefreshTime = ref('')
const disclosureNote = ref('')

interface DisclosureRow {
  item: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  reason: string
}

const disclosureRows = ref<DisclosureRow[]>([
  { item: '安全生产费', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, reason: '' },
  { item: '维简费', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, reason: '' },
  { item: '其他专项储备', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, reason: '' },
  { item: '合  计', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, reason: '' },
])

// ─── Helpers ─────────────────────────────────────────────────────────────────
function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── 从 M7-1 审定数据刷新附注（P2：统一 useNoteAutoFill SDK）────────────────
// 替换原 brittle 的 wpCode+accountCode 双条件订阅 + 手写 refreshFromAdjudication。
// 经 crossWpEventBridge，任一传输通道的 4201 审定事件都能命中；reload 先拉最新再取数。
const autoFill = useNoteAutoFill({
  allResponses: computed(() => formData.allResponses.value) as any,
  sources: {
    safety: 'M7-1-safety-subtotal',
    maintenance: 'M7-1-maintenance-subtotal',
    other: 'M7-1-other-subtotal',
    total: 'M7-1-total-audited',
  },
  accountCodes: ['4201'],
  reload: () => formData.loadData(),
  onRefresh: (v) => {
    if ((v.total ?? 0) !== 0 || (v.safety ?? 0) !== 0) {
      disclosureRows.value[0].endBalance = v.safety ?? 0
      disclosureRows.value[1].endBalance = v.maintenance ?? 0
      disclosureRows.value[2].endBalance = v.other ?? 0
      disclosureRows.value[3].endBalance = v.total ?? 0
      lastRefreshTime.value = autoFill.lastRefreshAt.value
      autoSync.scheduleAutoSync(syncToDisclosureNotes)
    }
  },
})

// ─── 保存 ────────────────────────────────────────────────────────────────────
function handleReasonChange(index: number): void {
  const row = disclosureRows.value[index]
  formData.debouncedSave(`M7-disclosure-listed-row-${index}-reason`, { remark: row.reason || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function saveDisclosureNote(): void {
  formData.debouncedSave('M7-disclosure-listed-note', { remark: disclosureNote.value || null })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 同步到附注（五、58 专项储备变动表） ─────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  const payload = buildMEquitySyncPayload(props.wpId, {
    cycle: 'M7',
    variant: 'listed',
    rows: disclosureRows.value.map((r) => ({
      label: r.item,
      begin: Number(r.beginBalance) || 0,
      increase: Number(r.increase) || 0,
      decrease: Number(r.decrease) || 0,
      end: Number(r.endBalance) || 0,
    })),
    note: disclosureNote.value?.trim() || undefined,
  })
  if (!payload) {
    ElMessage.warning('当前项目准则不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    await http.post(`/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`, payload)
    ElMessage.success(`已同步到附注（${M_EQUITY_CONFIG.M7.section.listed} 专项储备）`)
    eventBus.emit('disclosure:note-text-updated' as any, {
      wpCode: 'M7',
      projectId: props.projectId,
      sectionIds: [M_EQUITY_CONFIG.M7.section.listed],
    })
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function jumpToNote() {
  const route = buildNoteJumpRoute(props.projectId, 'M7', 'listed')
  if (route) router.push(route)
}

// ─── UI handlers ─────────────────────────────────────────────────────────────
async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const context: Record<string, string> = {
      科目: '4201 专项储备 / 附注披露（上市公司）',
      安全生产费期末: fmtAmount(disclosureRows.value[0]?.endBalance ?? 0),
      维简费期末: fmtAmount(disclosureRows.value[1]?.endBalance ?? 0),
      其他专项储备期末: fmtAmount(disclosureRows.value[2]?.endBalance ?? 0),
      合计期末: fmtAmount(disclosureRows.value[3]?.endBalance ?? 0),
    }
    const text = await generateAiText({ section: `m7-disclosure-listed-${section}`, context, existingContent: disclosureNote.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    disclosureNote.value = text
    saveDisclosureNote()
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}
function handleReview(): void { openReviewDialog?.('M7-disclosure-listed', '附注披露-上市公司') }

// ─── Lifecycle ───────────────────────────────────────────────────────────────
// 审定事件订阅由 useNoteAutoFill 统一处理（含卸载清理），此处仅负责首屏加载与文本/原因恢复。
onMounted(async () => {
  await formData.loadData()

  // 恢复已保存的披露说明
  const noteResp = formData.allResponses.value.get('M7-disclosure-listed-note')
  if (noteResp?.remark) disclosureNote.value = noteResp.remark

  // 恢复行原因
  disclosureRows.value.forEach((row, i) => {
    const resp = formData.allResponses.value.get(`M7-disclosure-listed-row-${i}-reason`)
    if (resp?.remark) row.reason = resp.remark
  })

  // 数据加载后从审定数据取数刷新（SDK 的初始 pull 在 loadData 前，故此处再 pull 一次）
  autoFill.pull()
})

onBeforeUnmount(() => { autoSync.cancelPending() })
</script>

<style scoped>
.m7-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

.disclosure-card { margin-bottom: 16px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

.m7-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m7-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m7-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m7-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
