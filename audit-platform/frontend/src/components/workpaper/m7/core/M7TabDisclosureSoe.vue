<template>
  <div class="m7-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">附注披露信息（国有企业）</h3>
        <el-tag v-if="lastRefreshTime" type="info" size="small" effect="plain">
          上次刷新: {{ lastRefreshTime }}
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-soe')">
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
        <strong>附注披露（国有企业）：</strong>
        按照国有企业财务报告格式，披露安全生产费等专项储备的计提标准、使用情况及余额变动。
        国有企业需额外披露计提依据（行业标准/政策文件）和使用明细（按费用化/资本化分别列示）。
        审定表（M7-1）数据变化时自动刷新此表，确保附注与审定数一致。
      </div>
    </div>

    <!-- ═══ 附注披露表格 (13×7) ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">专项储备附注披露表（国有企业格式）</span>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="160" />
        <el-table-column prop="beginBalance" label="期初余额" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.beginBalance) }}</template>
        </el-table-column>
        <el-table-column prop="increase" label="本期计提" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.increase) }}</template>
        </el-table-column>
        <el-table-column prop="expenseDecrease" label="费用化使用" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.expenseDecrease) }}</template>
        </el-table-column>
        <el-table-column prop="capitalDecrease" label="资本化使用" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.capitalDecrease) }}</template>
        </el-table-column>
        <el-table-column prop="endBalance" label="期末余额" width="130" align="right">
          <template #default="{ row }">{{ fmtAmount(row.endBalance) }}</template>
        </el-table-column>
        <el-table-column prop="policyBasis" label="计提依据" min-width="180">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              v-model="disclosureRows[$index].policyBasis"
              size="small"
              placeholder="政策/行业标准"
              @change="handlePolicyChange($index)"
            />
            <span v-else>{{ row.policyBasis || '—' }}</span>
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
        placeholder="请填写专项储备附注披露说明（国有企业）..."
        :disabled="isReadonly"
        @change="saveDisclosureNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>国有企业附注需额外披露计提依据（安全生产费管理办法/行业标准）</li>
        <li>使用列区分费用化（直接冲减）和资本化（形成固定资产）</li>
        <li>数据来源：M7-1审定表（审定数变化时自动推送刷新）</li>
        <li>确保期末余额与试算表一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabDisclosureSoe.vue — 附注披露信息（国有企业）
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 6.1
 * Requirements: 6.2, 6.3
 *
 * EventBus集成：
 * - subscribe 'substantive:adjudicated' → 自动刷新附注数据（当M7-1审定数变化时）
 * - 组件卸载时 off 清理
 *
 * 国有企业附注格式特殊：
 * - 使用列需区分费用化/资本化
 * - 需披露计提依据（政策文件/行业标准）
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useM7FormData } from '../../composables/useM7FormData'
import { useNoteAutoFill } from '../../composables/useNoteAutoFill'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM7FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

// ─── State ───────────────────────────────────────────────────────────────────
const lastRefreshTime = ref('')
const disclosureNote = ref('')

interface SoeDisclosureRow {
  item: string
  beginBalance: number
  increase: number
  expenseDecrease: number
  capitalDecrease: number
  endBalance: number
  policyBasis: string
}

const disclosureRows = ref<SoeDisclosureRow[]>([
  { item: '安全生产费', beginBalance: 0, increase: 0, expenseDecrease: 0, capitalDecrease: 0, endBalance: 0, policyBasis: '' },
  { item: '维简费', beginBalance: 0, increase: 0, expenseDecrease: 0, capitalDecrease: 0, endBalance: 0, policyBasis: '' },
  { item: '其他专项储备', beginBalance: 0, increase: 0, expenseDecrease: 0, capitalDecrease: 0, endBalance: 0, policyBasis: '' },
  { item: '合  计', beginBalance: 0, increase: 0, expenseDecrease: 0, capitalDecrease: 0, endBalance: 0, policyBasis: '' },
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
    }
  },
})

// ─── 保存 ────────────────────────────────────────────────────────────────────
function handlePolicyChange(index: number): void {
  const row = disclosureRows.value[index]
  formData.debouncedSave(`M7-disclosure-soe-row-${index}-policy`, { remark: row.policyBasis || null })
}

function saveDisclosureNote(): void {
  formData.debouncedSave('M7-disclosure-soe-note', { remark: disclosureNote.value || null })
}

// ─── UI handlers ─────────────────────────────────────────────────────────────
function handleAI(_section: string): void { /* AI辅助钩子 */ }
function handleReview(): void { openReviewDialog?.('M7-disclosure-soe', '附注披露-国有企业') }

// ─── Lifecycle ───────────────────────────────────────────────────────────────
// 审定事件订阅由 useNoteAutoFill 统一处理（含卸载清理），此处仅负责首屏加载与文本/依据恢复。
onMounted(async () => {
  await formData.loadData()

  // 恢复已保存的披露说明
  const noteResp = formData.allResponses.value.get('M7-disclosure-soe-note')
  if (noteResp?.remark) disclosureNote.value = noteResp.remark

  // 恢复行计提依据
  disclosureRows.value.forEach((row, i) => {
    const resp = formData.allResponses.value.get(`M7-disclosure-soe-row-${i}-policy`)
    if (resp?.remark) row.policyBasis = resp.remark
  })

  // 数据加载后从审定数据取数刷新
  autoFill.pull()
})
</script>

<style scoped>
.m7-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }

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
