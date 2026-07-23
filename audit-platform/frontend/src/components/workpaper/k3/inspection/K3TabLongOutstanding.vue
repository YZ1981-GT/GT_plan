<!-- K3TabLongOutstanding.vue — K3-5 长期挂账检查表 | Task 4.4 | Req 5.1-5.4 -->
<template>
  <div class="k3-tab-long-outstanding">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K3-5长期挂账检查表用于评估长期未偿付的其他应付款项目（重点3年以上）。
        核查要点：①挂账原因是否合理 ②是否有偿付计划 ③是否需转营业外收入（CAS 16债务豁免/无法支付）
        ④逐行核查结论（合规/需处理/不适用）。3年以上行自动标记并提示评估转销必要性。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>存在与义务：</b>长期挂账的其他应付款是否仍为真实存在的偿还义务；</li>
        <li><b>计价和分摊：</b>无需支付/无法支付的款项是否应按 CAS16 转入营业外收入，计价恰当；</li>
        <li><b>列报与披露：</b>长期挂账原因及处理已恰当披露。</li>
      </ol>
    </el-alert>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K3-5 长期挂账检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('long-outstanding-eval')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handleImportFromDetail">从K3-2带入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-button size="small" @click="handleReview('K3-5-outstanding')">💬 复核</el-button>
      </div>
    </div>

    <!-- 3年以上提示 -->
    <el-alert
      v-if="over3YCount > 0"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 12px"
    >
      <template #title>
        存在 <b>{{ over3YCount }}</b> 笔3年以上长期挂账，合计 <b>{{ fmtAmt(over3YTotal) }}</b>，请评估是否需转营业外收入
      </template>
    </el-alert>

    <!-- 主表格 -->
    <el-table
      :data="longOutstandingRows"
      border
      size="small"
      :max-height="520"
      class="long-outstanding-table"
      :row-style="tableRowStyle"
    >
      <el-table-column label="往来对象" min-width="130" fixed>
        <template #default="{ row }">
          <span class="counterparty-link" @click="navigateToDetail(row)">
            {{ row.counterparty }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="挂账金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.amount" size="small"
            :controls="false" class="amount-input"
            @change="handleRowChange(row)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="挂账时间" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.outstandingDate" size="small" placeholder="如：2021-03"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.outstandingDate || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="账龄" min-width="90">
        <template #default="{ row }">
          <el-tag :type="agingTagType(row.aging)" size="small">{{ row.aging || '-' }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="形成原因" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.formationReason" size="small" placeholder="形成原因"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.formationReason || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="偿付计划" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.repaymentPlan" size="small" placeholder="偿付计划"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.repaymentPlan || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="未偿还/未结转原因" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.nonPaymentReason" size="small" placeholder="未偿还或未结转的原因"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.nonPaymentReason || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="是否无法支付" min-width="100" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.cannotPay" size="small" @change="handleRowChange(row)">
            <el-option label="是" value="是" /><el-option label="否" value="否" />
          </el-select>
          <el-tag v-else :type="row.cannotPay === '是' ? 'danger' : 'success'" size="small">{{ row.cannotPay || '-' }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="是否诉讼" min-width="90" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.hasLitigation" size="small" @change="handleRowChange(row)">
            <el-option label="是" value="是" /><el-option label="否" value="否" />
          </el-select>
          <el-tag v-else :type="row.hasLitigation === '是' ? 'warning' : 'info'" size="small">{{ row.hasLitigation || '-' }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="审定余额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.auditedBalance" size="small"
            :controls="false" class="amount-input"
            @change="handleRowChange(row)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.auditedBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期后付款" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.postPayment" size="small"
            :controls="false" class="amount-input"
            @change="handleRowChange(row)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.postPayment) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="是否需转营业外收入" min-width="150" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.needTransfer" size="small"
            @change="handleRowChange(row)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="待评估" value="待评估" />
          </el-select>
          <template v-else>
            <el-tag :type="transferTagType(row.needTransfer)" size="small">
              {{ row.needTransfer }}
            </el-tag>
            <el-button v-if="row.needTransfer === '是'" size="small" link type="primary" style="margin-left:4px" @click="navigateToK12(row)" title="跳转K12营业外收入">↗K12</el-button>
          </template>
        </template>
      </el-table-column>

      <el-table-column label="处理结论" min-width="140" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.disposalConclusion" size="small" clearable placeholder="请选择"
            @change="handleRowChange(row)">
            <el-option v-for="opt in K3_DISPOSAL_CONCLUSIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <template v-else>
            <el-tag v-if="row.disposalConclusion" :type="disposalTagType(row.disposalConclusion)" size="small">{{ row.disposalConclusion }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </template>
      </el-table-column>

      <!-- 跨底稿联动提示 -->
      <el-table-column label="联动" width="70" align="center">
        <template #default="{ row }">
          <template v-if="row.disposalConclusion === '应确认收入'"><el-button size="small" link type="primary" @click="emit('navigate-sheet', 'D4')">→D4</el-button></template>
          <template v-else-if="row.disposalConclusion === '应转营业外收入'"><el-button size="small" link type="primary" @click="navigateToK12(row)">→K12</el-button></template>
          <template v-else-if="row.disposalConclusion === '应退回'"><el-button size="small" link type="primary" @click="emit('navigate-sheet', 'F4')">→F4</el-button></template>
          <span v-else>—</span>
        </template>
      </el-table-column>

      <el-table-column label="核查结论" min-width="120" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" clearable placeholder="请选择"
            @change="handleRowChange(row)">
            <el-option label="合规" value="合规" />
            <el-option label="需处理" value="需处理" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <el-tag v-else :type="conclusionTagType(row.conclusion)" size="small">
            {{ row.conclusion || '未判定' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 抽凭列 -->
      <el-table-column label="抽凭" width="60" align="center">
        <template #default="{ row }">
          <el-button size="small" link @click="handleVoucherSampling(row)">📋</el-button>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card shadow="never" style="margin-top:12px; margin-bottom:12px">
      <template #header>
        <div class="section-head" style="margin-bottom:0">
          <span style="font-weight:600">审计说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('long-outstanding-note')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="请填写长期挂账检查审计说明：挂账原因评估、CAS16转销条件判断、偿付计划合理性、跨底稿联动（K12营业外收入/D4收入/F4应付）..."
        @change="persistNote"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>重点关注3年以上挂账（橙色高亮）：评估是否满足CAS 16"确实无法偿付"条件</li>
        <li>转营业外收入条件：债权人放弃/企业注销/诉讼时效届满/双方确认豁免</li>
        <li>核查结论：合规=有合理原因且在偿付计划中；需处理=建议管理层清理/转销/调整</li>
        <li>点击往来对象跳转K3-2明细对应行；行级抽凭引用GtVoucherSamplingEngine</li>
        <li>标记"是"转营业外收入的行将联动K12营业外收入底稿（cross_wp_references CW-K3-006）</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 2241 其他应付款-长期挂账）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :workpaper-id="props.wpId"
        account-code="2241"
        phase="final"
        :year="year"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabLongOutstanding.vue — K3-5 长期挂账检查表
 * Spec: .kiro/specs/k3-other-payables/ | Task: 4.4
 * Requirements: 5.1-5.4
 */
import { computed, inject, onMounted, ref, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK3Checks, type K3LongOutstandingRow, type ComplianceState, K3_DISPOSAL_CONCLUSIONS, type K3DisposalConclusion } from '../../composables/useK3Checks'
import http from '@/utils/http'

const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Year ────────────────────────────────────────────────────────────────────

const year = computed(() => props.year ?? new Date().getFullYear())

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

function saveResponse(itemId: string, payload: any) {
  props.allResponses.set(itemId, { item_id: itemId, ...payload })
  emit('save', itemId, payload)
}

const {
  longOutstandingRows,
  updateLongOutstandingConclusion,
  initLongOutstandingFromDetail,
  saveAll,
} = useK3Checks({ allResponses: allResponsesRef as any, saveResponse })

// ─── 审计说明 ────────────────────────────────────────────────────────────────

const auditNote = ref('')
const ITEM_NOTE = 'K3-5-note'

function loadNote() {
  const item = props.allResponses.get(ITEM_NOTE)
  auditNote.value = item?.remark ?? ''
}

function persistNote() {
  saveResponse(ITEM_NOTE, { remark: auditNote.value })
}

onMounted(() => loadNote())

// ─── 从K3-2带入长期挂账候选 ──────────────────────────────────────────────────

function handleImportFromDetail() {
  const item = props.allResponses.get('K3-2-rows')
  const raw = item?.remark ?? null
  if (!raw) { ElMessage.warning('K3-2明细表无数据，请先编制明细表'); return }
  try {
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows) || rows.length === 0) { ElMessage.warning('K3-2明细表无数据'); return }
    const added = initLongOutstandingFromDetail(rows)
    if (added > 0) {
      persistRows()
      ElMessage.success(`已从K3-2带入 ${added} 笔3年以上长期挂账`)
    } else {
      ElMessage.info('K3-2中无新增3年以上挂账行（已有的不重复带入）')
    }
  } catch { ElMessage.warning('K3-2明细数据解析失败') }
}

// ─── Computed ────────────────────────────────────────────────────────────────

/** 3年以上判定（兼容动态账龄标签：3年以上/3-4年/4-5年/5年以上） */
function isOver3Y(aging: string): boolean {
  if (!aging) return false
  return /3年|4年|5年|3-4|4-5|over3|over5|y3to4|y4to5/.test(aging)
}

const over3YCount = computed(() =>
  longOutstandingRows.value.filter(r => isOver3Y(r.aging)).length
)

const over3YTotal = computed(() =>
  longOutstandingRows.value
    .filter(r => isOver3Y(r.aging))
    .reduce((sum, r) => sum + (r.amount || 0), 0)
)

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  // useK3Checks 的 watch(allResponses, ..., { immediate: true }) 已完成 initFromResponses
})

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入往来对象名称',
      '新增长期挂账行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '往来对象名称' }
    )
    if (!value?.trim()) { ElMessage.warning('名称不能为空'); return }
    longOutstandingRows.value.push({
      rowId: `lo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: longOutstandingRows.value.length + 1,
      counterparty: value.trim(),
      amount: 0,
      outstandingDate: '',
      aging: '',
      formationReason: '',
      repaymentPlan: '',
      needTransfer: '待评估',
      disposalConclusion: undefined,
      conclusion: null,
      voucherRef: '',
      remark: '',
    } as any)
    persistRows()
    ElMessage.success(`已新增：${value.trim()}`)
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowId: string) {
  longOutstandingRows.value = longOutstandingRows.value.filter(r => r.rowId !== rowId)
  longOutstandingRows.value.forEach((r, i) => { r.seqNo = i + 1 })
  persistRows()
}

function handleRowChange(_row: K3LongOutstandingRow) {
  persistRows()
}

function persistRows() {
  saveAll()
}

function navigateToDetail(_row: K3LongOutstandingRow) {
  emit('navigate-sheet', 'K3-2 明细表')
}

/** 联动K12营业外收入底稿（cross_wp_references CW-K3-006） */
function navigateToK12(row: K3LongOutstandingRow) {
  if (row.needTransfer === '是') {
    emit('navigate-sheet', 'K12 营业外收入')
  }
}

// ─── Voucher Sampling (GtVoucherSamplingEngine dialog) ───────────────────────

const showSamplingDialog = ref(false)
const currentSamplingRow = ref<K3LongOutstandingRow | null>(null)

function handleVoucherSampling(row: K3LongOutstandingRow) {
  currentSamplingRow.value = row
  showSamplingDialog.value = true
}

function onSampleFilled(payload: any): void {
  if (currentSamplingRow.value && payload?.voucherNo) {
    currentSamplingRow.value.voucherRef = payload.voucherNo
    persistRows()
  }
  showSamplingDialog.value = false
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function tableRowStyle({ row }: { row: K3LongOutstandingRow }): Record<string, string> {
  if (isOver3Y(row.aging)) return { 'background-color': '#fff7ed' }
  return {}
}

function agingTagType(val: string): 'success' | 'warning' | 'danger' | 'info' {
  if (val?.includes('3年')) return 'danger'
  if (val?.includes('2')) return 'warning'
  return 'info'
}

function transferTagType(val: string): 'success' | 'danger' | 'warning' | 'info' {
  if (val === '是') return 'danger'
  if (val === '否') return 'success'
  return 'warning'
}

function conclusionTagType(val: string | null): 'success' | 'danger' | 'info' | 'warning' {
  if (val === '合规') return 'success'
  if (val === '需处理' || val === '不合规') return 'danger'
  if (val === '不适用') return 'info'
  return 'warning'
}

function disposalTagType(val: string): 'success' | 'danger' | 'warning' | 'info' {
  if (val === '正常挂账') return 'success'
  if (val === '应转营业外收入' || val === '应确认收入') return 'danger'
  if (val === '应退回') return 'warning'
  return 'info' // 待确定
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiGenerate(section: string) {
  http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
    prompt: '请生成其他应付款(2241)长期挂账检查审计说明，包含：长期挂账原因分析、是否满足CAS16转销条件评估、偿付计划合理性、跨底稿联动情况',
    context: JSON.stringify({
      科目: '2241其他应付款',
      方向: '贷方/负债类',
      审计重点: '长期挂账转销评估(CAS16)',
      长期挂账笔数: String(longOutstandingRows.value.length),
      '3年以上笔数': String(over3YCount.value),
      '3年以上合计': String(over3YTotal.value),
      需转营业外收入笔数: String(longOutstandingRows.value.filter(r => r.needTransfer === '是').length),
      无法支付笔数: String(longOutstandingRows.value.filter((r: any) => r.cannotPay === '是').length),
    }),
    existingContent: auditNote.value || '',
    section: 'K3-5-long-outstanding',
  }).then((res: any) => {
    const content = res?.data?.data?.content || res?.data?.content || ''
    if (content) {
      auditNote.value = auditNote.value ? `${auditNote.value}\n${content}` : content
      persistNote()
    }
  }).catch(() => { /* AI不可用静默降级 */ })
}

function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k3-tab-long-outstanding { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context { border-left: 4px solid var(--el-color-warning); background: #fffbeb; padding: 10px 14px; margin-bottom: 16px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.long-outstanding-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.counterparty-link { color: var(--el-color-primary); cursor: pointer; }
.counterparty-link:hover { text-decoration: underline; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
