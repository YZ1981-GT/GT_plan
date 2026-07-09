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
        <el-button size="small" @click="handleAI('disclosure-listed')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
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
          <el-button size="small" @click="handleAI('disclosure-note')">
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
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM7FormData } from '../../composables/useM7FormData'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

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

// ─── 从 M7-1 审定数据刷新附注 ───────────────────────────────────────────────
function refreshFromAdjudication(): void {
  // 从 checklist_responses 读取 M7-1 审定数据
  const safetyAudited = parseNum(formData.allResponses.value.get('M7-1-safety-subtotal')?.remark)
  const maintenanceAudited = parseNum(formData.allResponses.value.get('M7-1-maintenance-subtotal')?.remark)
  const otherAudited = parseNum(formData.allResponses.value.get('M7-1-other-subtotal')?.remark)
  const totalAudited = parseNum(formData.allResponses.value.get('M7-1-total-audited')?.remark)

  // 尝试获取更详细的期初/贷方/借方数据
  // 简单展示：审定总额填入期末余额列
  if (totalAudited !== 0 || safetyAudited !== 0) {
    disclosureRows.value[0].endBalance = safetyAudited
    disclosureRows.value[1].endBalance = maintenanceAudited
    disclosureRows.value[2].endBalance = otherAudited
    disclosureRows.value[3].endBalance = totalAudited
    lastRefreshTime.value = new Date().toLocaleTimeString('zh-CN')
  }
}

// ─── 保存 ────────────────────────────────────────────────────────────────────
function handleReasonChange(index: number): void {
  const row = disclosureRows.value[index]
  formData.debouncedSave(`M7-disclosure-listed-row-${index}-reason`, { remark: row.reason || null })
}

function saveDisclosureNote(): void {
  formData.debouncedSave('M7-disclosure-listed-note', { remark: disclosureNote.value || null })
}

// ─── UI handlers ─────────────────────────────────────────────────────────────
function handleAI(_section: string): void { /* AI辅助钩子 */ }
function handleReview(): void { openReviewDialog?.('M7-disclosure-listed', '附注披露-上市公司') }

// ─── EventBus: subscribe 'substantive:adjudicated' → 刷新附注 ────────────────
function onAdjudicated(payload: any): void {
  // 当 M7 审定数变化时刷新附注数据
  if (payload?.wpCode === 'M7' && payload?.accountCode === '4201') {
    // 重新加载数据后刷新
    formData.loadData().then(() => {
      refreshFromAdjudication()
    })
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
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

  // 从审定数据刷新
  refreshFromAdjudication()

  // EventBus subscribe
  eventBus.on('substantive:adjudicated', onAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicated)
})
</script>

<style scoped>
.m7-tab-disclosure-listed { padding: 12px; font-size: 13px; }

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
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }

.disclosure-card { margin-bottom: 16px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; }

:deep(.el-table) { font-size: 13px; }

.m7-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}
.m7-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m7-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m7-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
