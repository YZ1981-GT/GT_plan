<template>
  <div class="f2-inspect">
    <header class="ic-hero">
      <div>
        <div class="ic-kicker">{{ sc.sheetCode }} · 委托加工物资</div>
        <h2 class="ic-title">{{ sc.title }}</h2>
        <p class="ic-sub">从余额倒轧 → 供应商加工规模 → 发出/收回材料流，核查委托加工真实、完整与计价。</p>
      </div>
      <div class="ic-actions">
        <GtIndexChip value="wp:F2-35" :context-project-id="projectId" />
        <GtIndexChip value="wp:F2-7" :context-project-id="projectId" />
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-35"
          :disabled="isReadonly"
          review-section="F2-35-conclusion"
        />
        <el-tag v-if="sc.unrecoveredCount.value" size="small" type="danger">
          未全额收回 {{ sc.unrecoveredCount.value }}
        </el-tag>
        <el-tag v-if="valuationCount" size="small" type="warning">
          计价差异 {{ valuationCount }}
        </el-tag>
        <el-tag v-if="feeCross.status === 'mismatch'" size="small" type="warning">
          加工费勾稽差
        </el-tag>
        <el-tag v-if="f27Recon.status === 'mismatch'" size="small" type="danger">
          ≠F2-7
        </el-tag>
      </div>
    </header>

    <details class="ic-guide guidance-details">
      <summary>编制提示</summary>
      <ol>
        <li>获取委外明细，检查合同、发料凭证、加工费结算凭证；必要时向加工方函证加工费与期末结存。</li>
        <li>表一核对期初期末倒轧；表二关注主要供应商加工规模与结算单据；表三跟踪发出未收回风险。</li>
        <li>表一/二/三加工费合计应勾稽；期末余额应与 F2-7 委托加工物资明细表核对（可手工填对照数）。</li>
      </ol>
    </details>

    <el-alert
      v-if="feeCross.status === 'mismatch' || f27Recon.status === 'mismatch'"
      type="warning"
      :closable="false"
      show-icon
      class="ic-cross-alert"
      :title="crossAlertTitle"
    />

    <section class="ic-card">
      <header class="ic-card-head"><h3>一、审计目标</h3></header>
      <ul class="ic-list">
        <li>资产负债表中记录的存货是存在的，并计入了正确的会计科目</li>
        <li>所有应记录的存货均已记录，且相关信息已得到恰当披露</li>
        <li>被审计单位拥有或控制资产负债表中记录的存货</li>
        <li>存货以恰当金额列示，相关调整已记录，相关信息已得到恰当披露</li>
      </ul>
    </section>

    <section class="ic-card">
      <header class="ic-card-head"><h3>二、样本选取标准与规模</h3></header>
      <div class="ic-meta-grid">
        <div class="ic-field"><label>被审计单位</label>
          <el-input :model-value="sc.meta.value.entityName" :disabled="isReadonly" @update:model-value="(v: string) => sc.updateMeta({ entityName: v })" />
        </div>
        <div class="ic-field"><label>截止日</label>
          <el-input :model-value="sc.meta.value.cutoffDate" :disabled="isReadonly" @update:model-value="(v: string) => sc.updateMeta({ cutoffDate: v })" />
        </div>
        <div class="ic-field"><label>F2-7 期末对照</label>
          <el-input-number
            :model-value="f27ClosingRef"
            :controls="false"
            :disabled="isReadonly"
            class="compact-num"
            style="width:100%"
            @change="(v?: number) => onF27ClosingChange(v ?? 0)"
          />
        </div>
        <div class="ic-field span2"><label>样本说明</label>
          <el-input :model-value="sc.meta.value.sampleNote" type="textarea" :rows="2" :disabled="isReadonly" @update:model-value="(v: string) => sc.updateMeta({ sampleNote: v })" />
        </div>
      </div>
    </section>

    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>三、审计过程</h3>
          <p>1. 取得委外明细并检查合同/发料/加工费结算；2. 必要时向加工方函证；3. 填写下方三表</p>
        </div>
      </header>
      <div class="ic-meta-grid" style="padding-top: 0">
        <div class="ic-field span2"><label>过程补充</label>
          <el-input :model-value="sc.meta.value.processNote" type="textarea" :rows="2" :disabled="isReadonly" @update:model-value="(v: string) => sc.updateMeta({ processNote: v })" />
        </div>
      </div>
    </section>

    <!-- 表一 -->
    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>（一）委托加工物资基本情况</h3>
          <p>期末＝期初＋本期增加－本期减少 · 合计期末 {{ sc.closingTotal.value.toLocaleString() }}</p>
        </div>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addBasic()">+ 行</el-button>
      </header>
      <div class="ic-table-wrap">
        <el-table :data="sc.basicRows.value" border size="small">
          <el-table-column prop="seq" label="序号" width="50" />
          <el-table-column label="年度" width="90">
            <template #default="{ row }">
              <el-input :model-value="row.year" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateBasic(row.id, { year: v })" />
            </template>
          </el-table-column>
          <el-table-column label="期初余额" width="110">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.opening" size="small" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateBasic(row.id, { opening: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="110">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.increase" size="small" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateBasic(row.id, { increase: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="110">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.decrease" size="small" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateBasic(row.id, { decrease: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="110">
            <template #default="{ row }"><span class="formula">{{ row.closing.toLocaleString() }}</span></template>
          </el-table-column>
          <el-table-column label="其中加工费发生" width="120">
            <template #default="{ row }">
              <el-input-number :model-value="row.processingFee" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateBasic(row.id, { processingFee: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column width="44">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="sc.removeBasic(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- 表二 -->
    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>（二）主要委外供应商情况 1</h3>
          <p>加工入库与加工费 · 加工费合计 {{ sc.feeTotal.value.toLocaleString() }}</p>
        </div>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addSupplier1()">+ 行</el-button>
      </header>
      <div class="ic-table-wrap">
        <el-table :data="sc.supplier1Rows.value" border size="small" max-height="320">
          <el-table-column prop="seq" label="序号" width="50" />
          <el-table-column label="年度" width="80">
            <template #default="{ row }">
              <el-input :model-value="row.year" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier1(row.id, { year: v })" />
            </template>
          </el-table-column>
          <el-table-column label="供应商名称" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="row.supplier" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier1(row.id, { supplier: v })" />
            </template>
          </el-table-column>
          <el-table-column label="主要加工工序" min-width="110">
            <template #default="{ row }">
              <el-input :model-value="row.processStep" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier1(row.id, { processStep: v })" />
            </template>
          </el-table-column>
          <el-table-column label="入库数量" width="90">
            <template #default="{ row }">
              <el-input-number :model-value="row.inboundQty" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateSupplier1(row.id, { inboundQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="入库金额" width="100">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.inboundAmount" size="small" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateSupplier1(row.id, { inboundAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="加工费金额" width="100">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.feeAmount" size="small" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateSupplier1(row.id, { feeAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="加工费结算单据" min-width="110">
            <template #default="{ row }">
              <el-input :model-value="row.settlementDocs" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier1(row.id, { settlementDocs: v })" />
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" width="96">
            <template #default="{ row }">
              <el-input :model-value="row.voucherNo" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier1(row.id, { voucherNo: v })" />
            </template>
          </el-table-column>
          <el-table-column width="44">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="sc.removeSupplier1(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- 表三 -->
    <section class="ic-card">
      <header class="ic-card-head">
        <div>
          <h3>（三）主要委外供应商情况 2</h3>
          <p>发出/收回材料成本 · 未收回须说明原因并评估是否函证</p>
        </div>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sc.addSupplier2()">+ 行</el-button>
      </header>
      <div class="ic-table-wrap">
        <el-table
          :data="sc.supplier2Rows.value"
          border
          size="small"
          max-height="360"
          :row-class-name="supplier2RowClassName"
        >
          <el-table-column prop="seq" label="序号" width="50" />
          <el-table-column label="加工单位名称" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="row.processor" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier2(row.id, { processor: v })" />
            </template>
          </el-table-column>
          <el-table-column label="合同或协议号" width="120">
            <template #default="{ row }">
              <el-input :model-value="row.contractNo" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier2(row.id, { contractNo: v })" />
            </template>
          </el-table-column>
          <el-table-column label="发出时间" width="110">
            <template #default="{ row }">
              <el-input :model-value="row.issueDate" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier2(row.id, { issueDate: v })" />
            </template>
          </el-table-column>
          <el-table-column label="发出材料成本" width="110">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.issueCost" size="small" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateSupplier2(row.id, { issueCost: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="加工费" width="96">
            <template #default="{ row }">
              <el-input-number :model-value="row.fee" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateSupplier2(row.id, { fee: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="收回材料成本" width="110">
            <template #default="{ row }">
              <WpAmountInput :model-value="row.recoverCost" size="small" :disabled="isReadonly" class="compact-num" @change="(v?: number) => sc.updateSupplier2(row.id, { recoverCost: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="应收回(发出+加工费)" width="120">
            <template #default="{ row }">
              <span class="formula">{{ recoverCheck(row).expected.toLocaleString() }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计价勾稽" width="150">
            <template #default="{ row }">
              <el-tooltip :content="recoverCheck(row).detail" placement="top" :show-after="200">
                <span :class="'recover-st recover-' + recoverCheck(row).status">
                  {{ RECOVER_ICON[recoverCheck(row).status] }}
                  {{ recoverCheck(row).status === 'ok' ? '一致'
                    : recoverCheck(row).status === 'unrecovered' ? '未全额收回'
                    : recoverCheck(row).status === 'valuation' ? '计价差异' : '待填' }}
                </span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="未收回原因及是否需函证" min-width="160">
            <template #default="{ row }">
              <el-input :model-value="row.unrecoveredNote" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier2(row.id, { unrecoveredNote: v })" />
            </template>
          </el-table-column>
          <el-table-column label="索引号" width="80">
            <template #default="{ row }">
              <el-input :model-value="row.indexRef" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier2(row.id, { indexRef: v })" />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="90">
            <template #default="{ row }">
              <el-input :model-value="row.remark" size="small" :disabled="isReadonly" @change="(v: string) => sc.updateSupplier2(row.id, { remark: v })" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="72" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openVoucher(row)">核对</el-button>
            </template>
          </el-table-column>
          <el-table-column width="44">
            <template #default="{ row }">
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="sc.removeSupplier2(row.id)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <F2SubcontractVoucherDialog
      v-model="voucherVisible"
      :row="voucherRow"
      :wp-id="wpId"
      :readonly="isReadonly"
      @save="handleSaveVoucher"
    />

    <section class="ic-card">
      <header class="ic-card-head">
        <h3>四、审计说明</h3>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="genNote">🤖 AI辅助说明</el-button>
        </el-tooltip>
      </header>
      <el-input v-model="sc.auditNote.value" class="ic-note" type="textarea" :rows="3" :disabled="isReadonly" placeholder="概述核查程序、函证情况、未收回风险与处理…" />
    </section>

    <section class="ic-card conclusion-card">
      <header class="ic-card-head">
        <h3>五、审计结论</h3>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="genConclusion">🤖 AI辅助结论</el-button>
        </el-tooltip>
      </header>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="A / B / C 结论模板"
        @change="saveAuditConclusion"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, onMounted, toRef, type Ref } from 'vue'
import { useF2SubcontractSheet } from '../../composables/useF2SubcontractCheck'
import { useF2ValuationAiGenerate } from '../../composables/useF2ValuationAiGenerate'
import {
  evaluateSubcontractRecover,
  evaluateSubcontractFeeCross,
  reconcileSubcontractWithF27,
  type SubcontractSupplier2Row,
} from '../../composables/useF2InspectionCheckFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2SubcontractVoucherDialog from './F2SubcontractVoucherDialog.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sc = useF2SubcontractSheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 表三计价勾稽（收回 ≈ 发出 + 加工费）─────────────────────────────────────
function recoverCheck(row: SubcontractSupplier2Row) {
  return evaluateSubcontractRecover(row)
}
const valuationCount = computed(
  () => sc.supplier2Rows.value.filter((r) => recoverCheck(r).status === 'valuation').length,
)
const RECOVER_ICON: Record<string, string> = { ok: '✓', unrecovered: '!', valuation: '✗', pending: '…' }

function supplier2RowClassName({ row }: { row: SubcontractSupplier2Row }): string {
  const s = recoverCheck(row).status
  return s === 'unrecovered' ? 'error-row' : s === 'valuation' ? 'warn-row' : ''
}

const voucherVisible = ref(false)
const voucherRow = ref<SubcontractSupplier2Row | null>(null)
function openVoucher(row: SubcontractSupplier2Row) {
  voucherRow.value = row
  voucherVisible.value = true
}
function handleSaveVoucher(patch: Partial<SubcontractSupplier2Row> & { id: string }) {
  const { id, ...rest } = patch
  sc.updateSupplier2(id, rest)
  voucherVisible.value = false
}

// ─── 表间加工费 + F2-7 期末勾稽 ─────────────────────────────────────────────
const feeCross = computed(() =>
  evaluateSubcontractFeeCross(sc.basicRows.value, sc.supplier1Rows.value, sc.supplier2Rows.value),
)

function parseF27ClosingFromResponses(): number | null {
  const raw = props.allResponses.get('F2-7-rows')?.remark
  if (!raw) return null
  try {
    const rows = JSON.parse(raw)
    if (!Array.isArray(rows) || !rows.length) return null
    return rows.reduce((s: number, r: Record<string, unknown>) => {
      const v = Number(r.processingCost ?? r.closingAmt ?? 0) || 0
      return s + v
    }, 0)
  } catch {
    return null
  }
}

const f27ClosingRef = computed(() => {
  const fromMeta = Number(sc.meta.value.f27ClosingRef)
  if (!Number.isNaN(fromMeta) && sc.meta.value.f27ClosingRef !== undefined && sc.meta.value.f27ClosingRef !== '') {
    return fromMeta
  }
  return parseF27ClosingFromResponses() ?? 0
})

function onF27ClosingChange(v: number) {
  sc.updateMeta({ f27ClosingRef: String(v) })
}

const f27Recon = computed(() =>
  reconcileSubcontractWithF27(
    sc.closingTotal.value,
    sc.meta.value.f27ClosingRef !== undefined && sc.meta.value.f27ClosingRef !== ''
      ? Number(sc.meta.value.f27ClosingRef)
      : parseF27ClosingFromResponses(),
  ),
)

const crossAlertTitle = computed(() => {
  const parts: string[] = []
  if (feeCross.value.status === 'mismatch') parts.push(`加工费：${feeCross.value.detail}`)
  if (f27Recon.value.status === 'mismatch') parts.push(`F2-7：${f27Recon.value.detail}`)
  return parts.join('；')
})

// ─── AI 辅助（与 D4/F2-33 gold 标准一致）─────────────────────────────────────
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)
const aiTip = computed(() => (aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用'))
function aiCtx(): Record<string, unknown> {
  return {
    sheet: 'F2-35',
    unrecoveredCount: sc.unrecoveredCount.value,
    valuationCount: valuationCount.value,
    feeTotal: sc.feeTotal.value,
    closingTotal: sc.closingTotal.value,
    feeCross: feeCross.value,
    f27Recon: f27Recon.value,
  }
}
async function genNote(): Promise<void> {
  const t = await generateAndConfirm('inspection-audit-note', sc.auditNote.value, aiCtx(), 'AI 生成 · 委托加工核查说明')
  if (t) sc.auditNote.value = t
}
async function genConclusion(): Promise<void> {
  const t = await generateAndConfirm('inspection-conclusion', auditConclusion.value, aiCtx(), 'AI 生成 · 委托加工核查结论')
  if (t) saveAuditConclusion(t)
}

const CONCLUSION_KEY = 'F2-35-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<style scoped src="./f2InspectSheetStyles.css"></style>
<style scoped>
.formula {
  text-decoration: underline dotted #909399;
  cursor: help;
}
.ic-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
:deep(.warn-row) td { background: #fdf6ec; }
.recover-st { font-size: 12px; white-space: nowrap; }
.recover-ok { color: var(--el-color-success); }
.recover-unrecovered { color: var(--el-color-danger); font-weight: 600; }
.recover-valuation { color: var(--el-color-warning); font-weight: 600; }
.recover-pending { color: var(--el-text-color-placeholder); }
.ic-cross-alert { margin: 0 0 12px; }
</style>
