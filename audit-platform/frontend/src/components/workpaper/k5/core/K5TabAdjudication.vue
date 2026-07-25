<template>
  <div class="k5-tab-adjudication">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性（负债重点）：</b>所有应当确认的预计负债均已记录，不存在未确认的现时义务（或有事项）；</li>
        <li><b>存在与义务：</b>已记录的预计负债是资产负债表日存在的、很可能导致经济利益流出的现时义务；</li>
        <li><b>计价和分摊：</b>预计负债金额为履行现时义务所需支出的最佳估计数，计量恰当；</li>
        <li><b>列报与披露：</b>预计负债及或有事项已按 CAS13 恰当列报披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K5-1 预计负债审定表</h3>
      <div class="header-actions">
        <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon> 带入调整
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="prefillFromTbSubAccounts">
          📊 从TB预填未审
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="syncFromSpecialSheets">
          📥 从专项表带入
        </el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI审计说明
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '预计负债检查表K5-7')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-refs">
      <span class="cross-refs-label">关联底稿：</span>
      <GtIndexChip value="wp:K5-2" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K5-4" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K5-5" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K5-6" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K5-7" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>预计负债（2701）为<strong>贷方/负债类</strong>科目。期末 = 期初 + 本期计提（增加） − 本期转销/冲回（减少）。按产品质保、诉讼、亏损合同、重组、弃置等类型分行，审定数 = 未审 + AJE + RJE。</p>
    </div>

    <!-- ═══ TB勾稽指示器 ═══ -->
    <div v-if="!tbReconciliation.isMatch" class="reconciliation-alert">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          TB勾稽不平：审定合计 {{ fmtNum(subtotalRow.audited) }} vs TB审定(2701) {{ fmtNum(tbData.audited2701) }}，差异 {{ fmtNum(tbReconciliation.diff) }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ K5-2明细勾稽 ═══ -->
    <div v-if="detailCrossCheckDiff !== 0" class="detail-cross-check">
      <el-alert :type="Math.abs(detailCrossCheckDiff) > 0.01 ? 'warning' : 'success'" :closable="false" show-icon>
        <template #title>
          K5-1审定合计 {{ fmtNum(subtotalRow.audited) }} vs K5-2明细期末合计 {{ fmtNum(detailEndTotal) }}
          <span v-if="Math.abs(detailCrossCheckDiff) > 0.01" style="color:#e6a23c;font-weight:600">  差异 {{ fmtNum(detailCrossCheckDiff) }}</span>
          <span v-else style="color:#67c23a">  ✓ 一致</span>
        </template>
      </el-alert>
    </div>

    <!-- ═══ 审定表主表 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="adjRowClass"
      max-height="480"
    >
      <el-table-column prop="label" label="项目" width="130" fixed />
      <el-table-column label="期初" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.begin) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.begin" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'begin', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="计提(增加)" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.provision) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.provision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'provision', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="转销(减少)" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.release) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.release" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'release', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：期初 + 计提 − 转销" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.end) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="未审" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.unadjusted) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.unadjusted" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'unadj', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.aje) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.aje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => handleCellChange(row.rowKey, 'aje', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.rje) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.rje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => handleCellChange(row.rowKey, 'rje', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="审定数" width="120" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：未审 + AJE + RJE" placement="top">
            <span class="formula-cell formula-underline" :class="{ 'diff-highlight': row.rowKey === 'diff' && Math.abs(row.audited) > 0.01 }">
              {{ fmtNum(row.audited) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <template v-if="row.rowKey !== 'subtotal' && row.rowKey !== 'diff'">
            <el-input v-model="row.remark" :disabled="isReadonly" size="small" placeholder="备注" @blur="handleCellChange(row.rowKey, 'remark', row.remark)" />
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="tb-writeback-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="handleTbWriteback">
        回写试算表(2701)
      </el-button>
      <span v-if="tbReconciliation.isMatch" class="match-indicator">
        <el-icon color="#67c23a"><CircleCheckFilled /></el-icon> 勾稽平衡
      </span>
      <span v-else class="mismatch-indicator">
        <el-icon color="#f56c6c"><WarningFilled /></el-icon> 差异 {{ fmtNum(tbReconciliation.diff) }}
      </span>
    </div>

    <!-- ═══ 报表数核对 ═══ -->
    <div class="report-reconciliation">
      <el-table :data="reportReconciliationRows" border size="small" style="max-width:600px" :show-header="true">
        <el-table-column prop="label" label="核对项目" width="200" />
        <el-table-column label="金额" width="140" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'diff-highlight': row.isDiff && Math.abs(row.amount) > 0.01 }">{{ fmtNum(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isOk" type="success" size="small">✓</el-tag>
            <el-tag v-else-if="row.isDiff" type="danger" size="small">差异</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header compact">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写审计说明、审计程序执行情况、结论..."
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>负债类科目(2701)：期末 = 期初 + 计提(增加) − 转销/冲回(减少)</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>三角勾稽：审定合计应等于各类型行审定数之和</li>
        <li>各专项检查表期末应与对应类型行审定数一致</li>
        <li>「带入调整」：按科目2701拉取调整分录，逐笔选目标类型行累加到 AJE/RJE，带入后自动联动披露/附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="2701 预计负债"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabAdjudication.vue — K5-1 预计负债审定表
 * 负债类108公式+按类型分行+三角勾稽+TB回写
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.2
 * Requirements: 2.1-2.8
 */
import { computed, toRef } from 'vue'
import { MagicStick, CircleCheckFilled, WarningFilled, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK5Adjudication } from '../../composables/useK5Adjudication'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import type { K5TbData } from '../../composables/useK5FormData'
import type { Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: K5TbData
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Composable wiring ───────────────────────────────────────────────────────

const tbDataRef = computed(() => props.tbData)

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  rows,
  subtotalRow,
  diffRow,
  auditConclusion,
  tbReconciliation,
  saveAll,
  publishAdjudicated,
} = useK5Adjudication({
  allResponses: allResponsesRef,
  tbData: tbDataRef as Ref<K5TbData>,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

// ─── 从集中登记带入调整（2701 预计负债，负债贷方） ────────────────────────────
const { adjPull, visible: bringInVisible, rowOptions: bringInRowOptions, open: openBringInAdjustment, apply: onBringInApply } = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '2701',
  direction: 'credit', // 负债贷方：净发生额 = 贷 − 借
  subjectCode: '2701',
  wpCode: 'K5',
  subjectLabel: '预计负债(2701)',
  rows: computed(() => rows.value.map(r => ({ rowKey: r.rowKey, name: r.label, aje: r.aje, rje: r.rje }))),
  updateCell: (rowKey: string, field: any, value: number) => handleCellChange(rowKey, field, value),
  totalAudited: () => subtotalRow.value.audited,
})

// ─── 表格数据（类型行 + 合计 + 差异） ───────────────────────────────────────

const tableData = computed(() => [...rows.value, subtotalRow.value, diffRow.value])

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: string, value: any) {
  emit('save', `K5-1-${rowKey}-${field}`, { remark: String(value ?? '') })
}

function handleTbWriteback() {
  emit('save', 'K5-1-audited-total', { remark: String(subtotalRow.value.audited) })
  // 发布审定数事件通知附注/A13/下游
  publishAdjudicated()
  ElMessage.success('已回写TB(2701)并发布审定数')
}

function handleSaveConclusion() { saveAll() }

function handleAiGenerate() {
  emit('save', 'K5-1-ai-trigger', { remark: 'generate' })
}

// ─── K5-2明细勾稽 ────────────────────────────────────────────────────────────

const detailEndTotal = computed(() => {
  const item = props.allResponses.get('K5-2-detail-end-total')
  return Number(item?.remark ?? 0) || 0
})

const detailCrossCheckDiff = computed(() => {
  if (!detailEndTotal.value && !subtotalRow.value.audited) return 0
  return subtotalRow.value.audited - detailEndTotal.value
})

// ─── 从专项检查表带入 ────────────────────────────────────────────────────────

const ROW_LABELS = ['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '其他']
const CROSS_SHEET_KEYS: Record<string, string> = {
  '产品质量保证': 'K5-4-warranty-end-total',
  '未决诉讼': 'K5-6-litigation-loss-total',
  '弃置义务': 'K5-5-decommission-end-total',
}

async function syncFromSpecialSheets(): Promise<void> {
  const updates: Array<{ label: string; rowKey: string; value: number }> = []

  for (let i = 0; i < ROW_LABELS.length; i++) {
    const label = ROW_LABELS[i]
    const crossKey = CROSS_SHEET_KEYS[label]
    if (!crossKey) continue
    const item = props.allResponses.get(crossKey)
    const val = Number(item?.remark ?? 0) || 0
    if (val > 0) {
      updates.push({ label, rowKey: `r${i}`, value: val })
    }
  }

  if (updates.length === 0) {
    ElMessage.warning('专项检查表(K5-4/K5-5/K5-6)暂无数据')
    return
  }

  try {
    await ElMessageBox.confirm(
      `从专项检查表带入以下审定数（填入"未审"列，仅填空值不覆盖）：\n${updates.map(u => `• ${u.label}：${u.value.toLocaleString()} 元`).join('\n')}`,
      '从专项表带入',
      { confirmButtonText: '带入', cancelButtonText: '取消', type: 'info' }
    )

    let filled = 0
    for (const u of updates) {
      const existingItem = props.allResponses.get(`K5-1-${u.rowKey}-unadj`)
      const existingVal = Number(existingItem?.remark ?? 0) || 0
      if (!existingVal) {
        emit('save', `K5-1-${u.rowKey}-unadj`, { remark: String(u.value) })
        filled++
      }
    }

    if (filled > 0) {
      ElMessage.success(`已带入 ${filled} 行未审数`)
    } else {
      ElMessage.info('所有行已有数据，未覆盖')
    }
  } catch { /* 用户取消 */ }
}

// ─── 从TB 2701子科目预填未审数 ───────────────────────────────────────────────

/**
 * 从 tb_balance 查询 2701 子科目，按科目名称关键词映射到审定表类型行。
 * 映射规则：质量/保修/保证→产品质量保证 | 诉讼/仲裁/赔偿→未决诉讼 |
 *           亏损/合同→亏损合同 | 重组/搬迁→重组义务 | 弃置/复垦/环保→弃置义务 | 其余→其他
 */
const TB_TYPE_KEYWORDS: Array<{ keywords: string[]; typeIndex: number }> = [
  { keywords: ['质量', '保修', '保证', '三包'], typeIndex: 0 },
  { keywords: ['诉讼', '仲裁', '赔偿', '官司'], typeIndex: 1 },
  { keywords: ['亏损', '合同'], typeIndex: 2 },
  { keywords: ['重组', '搬迁', '裁员'], typeIndex: 3 },
  { keywords: ['弃置', '复垦', '环保', '退役'], typeIndex: 4 },
]

function classifySubAccount(name: string): number {
  const lower = name.toLowerCase()
  for (const rule of TB_TYPE_KEYWORDS) {
    if (rule.keywords.some(kw => lower.includes(kw))) return rule.typeIndex
  }
  return 5 // 其他
}

async function prefillFromTbSubAccounts(): Promise<void> {
  try {
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '2701' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    if (list.length === 0) {
      ElMessage.warning('未查到2701子科目数据')
      return
    }

    // 按类型归集
    const grouped: Record<number, number> = {}
    const details: string[] = []
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (!code.startsWith('2701')) continue
      const name = String(item.account_name ?? item.standard_account_name ?? code)
      const amt = Math.abs(Number(item.unadjusted_amount ?? item.closing_balance ?? 0))
      if (amt <= 0) continue
      const typeIdx = classifySubAccount(name)
      grouped[typeIdx] = (grouped[typeIdx] || 0) + amt
      details.push(`${name}: ${amt.toLocaleString()}`)
    }

    if (Object.keys(grouped).length === 0) {
      ElMessage.warning('2701子科目余额全部为0')
      return
    }

    const preview = Object.entries(grouped)
      .map(([idx, amt]) => `• ${ROW_LABELS[Number(idx)]}：${Number(amt).toLocaleString()} 元`)
      .join('\n')

    await ElMessageBox.confirm(
      `从TB(2701)子科目预填未审数（仅填空值不覆盖）：\n${preview}\n\n明细（${details.length}个子科目）：\n${details.slice(0, 8).join('\n')}${details.length > 8 ? '\n...' : ''}`,
      '从TB预填未审数',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }
    )

    let filled = 0
    for (const [idx, amt] of Object.entries(grouped)) {
      const rowKey = `r${idx}`
      const existingItem = props.allResponses.get(`K5-1-${rowKey}-unadj`)
      const existingVal = Number(existingItem?.remark ?? 0) || 0
      if (!existingVal && Number(amt) > 0) {
        emit('save', `K5-1-${rowKey}-unadj`, { remark: String(amt) })
        filled++
      }
    }

    if (filled > 0) {
      ElMessage.success(`已从TB预填 ${filled} 行未审数`)
    } else {
      ElMessage.info('所有行已有未审数，未覆盖')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.toString() !== 'cancel') {
      ElMessage.warning('从TB预填失败')
    }
  }
}

// ─── 报表数核对（审定合计 vs TB vs 明细）─────────────────────────────────────

const reportReconciliationRows = computed(() => {
  const audited = subtotalRow.value.audited
  const tbAudited = props.tbData.audited2701
  const detailTotal = detailEndTotal.value
  const tbDiff = audited - tbAudited
  const detailDiff = detailTotal ? (audited - detailTotal) : 0

  return [
    { label: 'K5-1 审定合计', amount: audited, isOk: true, isDiff: false },
    { label: 'TB(2701) 审定数', amount: tbAudited, isOk: Math.abs(tbDiff) < 0.01, isDiff: Math.abs(tbDiff) > 0.01 },
    { label: 'K5-2 明细期末合计', amount: detailTotal || 0, isOk: !detailTotal || Math.abs(detailDiff) < 0.01, isDiff: detailTotal > 0 && Math.abs(detailDiff) > 0.01 },
    { label: '审定 vs TB 差异', amount: tbDiff, isOk: Math.abs(tbDiff) < 0.01, isDiff: Math.abs(tbDiff) > 0.01 },
    { label: '审定 vs 明细差异', amount: detailDiff, isOk: !detailTotal || Math.abs(detailDiff) < 0.01, isDiff: detailTotal > 0 && Math.abs(detailDiff) > 0.01 },
  ]
})

// ─── Row class（差异行+勾稽不平红色高亮） ────────────────────────────────────

function adjRowClass({ row }: { row: any }): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row'
  if (row.rowKey === 'diff') return Math.abs(row.audited) > 0.01 ? 'diff-row-error' : 'diff-row'
  return ''
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.section-header.compact { margin-bottom: 0; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.cross-refs { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 12px; flex-wrap: wrap; }
.cross-refs-label { color: #909399; }
.detail-cross-check { margin-bottom: 12px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.reconciliation-alert { margin-bottom: 12px; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.diff-highlight { color: #f56c6c; font-weight: 600; }
.tb-writeback-bar { display: flex; align-items: center; gap: 12px; margin: 12px 0; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.match-indicator, .mismatch-indicator { display: flex; align-items: center; gap: 4px; font-size: var(--wp-font-size, 13px); }
.match-indicator { color: #67c23a; }
.mismatch-indicator { color: #f56c6c; }
.conclusion-card { margin-top: 16px; }
.report-reconciliation { margin: 12px 0; }
.report-reconciliation :deep(.el-table) { font-size: 12px; }
:deep(.subtotal-row) { background-color: #f0f9eb !important; font-weight: 600; }
:deep(.diff-row) { background-color: #f5f7fa !important; }
:deep(.diff-row-error) { background-color: #fef0f0 !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
