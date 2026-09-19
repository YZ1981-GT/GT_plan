<template>
  <div class="g5-installment-sales">
    <div class="section-head">
      <h3 class="sheet-title">G5-6 未实现融资收益测算表（分期销售）</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-6" />
        <GtIndexChip value="wp:G5-2" />
        <GtIndexChip value="wp:G5-4" />
        <G5ImportExportDropdown
          :wp-id="props.wpId"
          sheet="G5-6"
          :disabled="!!props.readonly"
          @imported="onImported"
        />
        <el-tag size="small" type="info">共 {{ sales.groups.value.length }} 个项目</el-tag>
        <GtReviewTrigger section-id="g5-6-installment-sales" />
      </div>
    </div>

    <div class="method-context">
      <p><strong>实际利率法</strong>：本期融资收益(3) = 期初未收本金/摊余成本(1) × 实际利率(4)</p>
      <p>
        未实现初始 = 应收总额 − 公允价值；
        已收本金(2) = 本期收款(5) − 本期收益(3)；
        期末摊余 = 期初摊余 + 收益 − 收款；
        期间连续性：第 N 期期初 = 第 N−1 期期末
      </p>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：检查有融资性质的分期收款销售合同及收入确认条件；按实际利率法测算未实现融资收益摊销，验证各期融资收益与账面一致，并勾稽摊余成本、预计可收回与减值。
    </el-alert>

    <div class="segment-tabs">
      <el-segmented v-model="sales.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions tab-toolbar">
        <el-button size="small" :disabled="!!props.readonly" @click="pullFromG52">
          从 G5-2 带入分期销售
        </el-button>
        <el-button size="small" type="primary" plain @click="sales.addGroup()" :disabled="!!props.readonly">
          + 新增项目
        </el-button>
      </div>
    </div>

    <!-- Tab1: 初始交易要素 -->
    <div v-show="sales.activeTab.value === 'initial'">
      <div v-if="sales.groups.value.length === 0" class="empty-hint">
        暂无项目。可「新增项目」或「从 G5-2 带入分期销售」。
      </div>
      <template v-for="group in sales.groups.value" :key="group.id">
        <div class="group-header">
          <el-input
            v-model="group.projectName"
            size="small"
            class="group-name-input"
            :disabled="!!props.readonly"
            placeholder="项目名称"
          />
          <el-button
            size="small"
            type="primary"
            text
            :disabled="!!props.readonly"
            @click="sales.seedFirstPeriodFromInitial(group)"
          >种子第一期</el-button>
          <el-button size="small" type="danger" text @click="sales.removeGroup(group.id)" :disabled="!!props.readonly">
            删除
          </el-button>
        </div>
        <el-table :data="[group.initial]" border style="width:100%;font-size:13px" class="basic-table">
          <el-table-column label="客户/债务人" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.customer" size="small" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="合同编号" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.contractNo" size="small" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="应收总额" min-width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-model="row.contractTotal"
                size="small"
                :disabled="!!props.readonly"
                @change="onRecalcInitial(group)"
              />
            </template>
          </el-table-column>
          <el-table-column label="公允价值" min-width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-model="row.fairValue"
                size="small"
                :disabled="!!props.readonly"
                @change="onRecalcInitial(group)"
              />
            </template>
          </el-table-column>
          <el-table-column label="未实现收益(初)" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="应收总额−公允价值">{{ fmt(row.unrealizedIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="实际利率(4)" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.effectiveRate"
                size="small"
                :controls="false"
                :precision="6"
                :disabled="!!props.readonly"
                @change="sales.recalcGroup(group)"
              />
            </template>
          </el-table-column>
          <el-table-column label="收款期限" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.collectionTerm" size="small" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>

    <!-- Tab2: 分期摊销（对齐模板列1–5） -->
    <div v-show="sales.activeTab.value === 'amortization'">
      <div v-if="sales.groups.value.length === 0" class="empty-hint">请先在「初始交易要素」新增项目。</div>
      <template v-for="group in sales.groups.value" :key="group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }}</span>
          <span class="group-meta">实际利率 {{ pct(group.initial.effectiveRate) }}</span>
          <el-button size="small" type="primary" text @click="sales.addPeriod(group.id)" :disabled="!!props.readonly">
            + 新增期间
          </el-button>
        </div>
        <el-table
          :data="group.periods"
          border
          stripe
          style="width:100%;font-size:13px"
          :row-class-name="({ row }) => getContinuityClass(group, row)"
        >
          <el-table-column prop="periodNo" label="期次" width="55" align="center" />
          <el-table-column label="收款时间" min-width="110">
            <template #default="{ row }">
              <el-input
                v-model="row.collectionDate"
                size="small"
                placeholder="YYYY-MM-DD"
                :disabled="!!props.readonly"
              />
            </template>
          </el-table-column>
          <el-table-column label="期初应收" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.openingReceivable"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onRecalc(group, row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="期初未实现" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.openingUnrealized"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onRecalc(group, row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="未收本金(1)" min-width="105" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初应收−期初未实现（摊余成本）">{{ fmt(row.openingAmortizedCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期收益(3)" min-width="105" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="(1)×实际利率(4)">{{ fmt(row.periodIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面收益" min-width="100" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-model="row.companyBookIncome"
                size="small"
                :disabled="!!props.readonly"
                @change="onRecalc(group, row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="差异" min-width="85" align="right">
            <template #default="{ row }">
              <span :class="{ 'variance-error': Math.abs(row.variance) > 0.01 }">{{ fmt(row.variance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期收款(5)" min-width="105" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.periodCollection"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onRecalc(group, row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="已收本金(2)" min-width="105" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="(5)−(3)">{{ fmt(row.principalCollected) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末应收" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmt(row.closingReceivable) }}</span></template>
          </el-table-column>
          <el-table-column label="期末未实现" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-cell" title="期初未实现−本期收益">{{ fmt(row.closingUnrealized) }}</span></template>
          </el-table-column>
          <el-table-column label="期末摊余" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-cell" title="期初摊余+收益−收款">{{ fmt(row.closingAmortizedCost) }}</span></template>
          </el-table-column>
          <el-table-column v-if="!props.readonly" label="操作" width="60" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                type="danger"
                link
                :disabled="group.periods.length <= 1"
                @click="sales.removePeriod(group.id, row.id)"
              >删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!sales.validateContinuity(group)" class="continuity-warning">
          ⚠ 期间连续性校验未通过（第 {{ sales.getContinuityErrors(group).join('、') }} 期）
        </div>
      </template>
    </div>

    <!-- Tab3: 期末汇总勾稽 -->
    <div v-show="sales.activeTab.value === 'reconcile'">
      <el-alert type="warning" :closable="false" show-icon class="reconcile-tip">
        汇总对齐致同「有融资性质的销售」模板：未实现滚存、摊余/未收本金、收款与减值。预计可收回填报后将按
        「初始公允 − 预计可收回 − 已收回」估算减值启发值(8)；账面净值 = 摊余期末 − 减值 − 核销。
      </el-alert>

      <template v-for="group in sales.groups.value" :key="'edit-' + group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }} — 账面与减值录入</span>
        </div>
        <el-table :data="[group.initial]" border size="small" class="basic-table">
          <el-table-column label="账面未实现期末" min-width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-model="row.bookClosingUnrealized" size="small" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="账面摊余期末" min-width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-model="row.bookClosingAmortizedCost" size="small" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="预计可收回(6)" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.estimatedRecoverable" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="账面已收回(7)" min-width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-model="row.totalCollectedBook"
                size="small"
                :disabled="!!props.readonly"
                placeholder="默认取摊销收款合计"
              />
            </template>
          </el-table-column>
          <el-table-column label="减值准备期末" min-width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-model="row.impairmentEnding" size="small" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="已核销" min-width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.writtenOffAmount" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
        </el-table>
      </template>

      <div class="reconcile-main-title">期末汇总勾稽（审计测算）</div>
      <el-table
        :data="sales.reconcileRows.value"
        border
        stripe
        size="small"
        style="width:100%;font-size:12px"
        :row-class-name="reconcileRowClass"
        show-summary
        :summary-method="reconcileSummaryMethod"
      >
        <el-table-column prop="projectName" label="项目/客户" min-width="120" fixed>
          <template #default="{ row }">
            <div>{{ row.projectName }}</div>
            <div class="sub-lessee">{{ row.customer || '—' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="contractTotal" label="应收总额" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.contractTotal) }}</span></template>
        </el-table-column>
        <el-table-column prop="fairValue" label="公允价值" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.fairValue) }}</span></template>
        </el-table-column>
        <el-table-column prop="initialUnrealized" label="初始未实现" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.initialUnrealized) }}</span></template>
        </el-table-column>
        <el-table-column prop="unrealizedOpening" label="未实现期初" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.unrealizedOpening) }}</span></template>
        </el-table-column>
        <el-table-column prop="unrealizedAddition" label="本期增加" min-width="90" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期末−期初+本期确认">{{ fmt(row.unrealizedAddition) }}</span></template>
        </el-table-column>
        <el-table-column prop="unrealizedRecognized" label="本期确认收益" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.unrealizedRecognized) }}</span></template>
        </el-table-column>
        <el-table-column prop="unrealizedEnding" label="未实现期末" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.unrealizedEnding) }}</span></template>
        </el-table-column>
        <el-table-column prop="amortizedOpening" label="摊余/未收本金期初" min-width="130" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.amortizedOpening) }}</span></template>
        </el-table-column>
        <el-table-column prop="principalCollectedTotal" label="已收本金合计(2)" min-width="120" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.principalCollectedTotal) }}</span></template>
        </el-table-column>
        <el-table-column prop="amortizedEnding" label="摊余期末" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.amortizedEnding) }}</span></template>
        </el-table-column>
        <el-table-column prop="collectionTotal" label="收款合计(5)" min-width="105" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.collectionTotal) }}</span></template>
        </el-table-column>
        <el-table-column prop="estimatedRecoverable" label="预计可收回(6)" min-width="110" align="right">
          <template #default="{ row }">{{ fmt(row.estimatedRecoverable) }}</template>
        </el-table-column>
        <el-table-column prop="impairmentEnding" label="减值(8)" min-width="90" align="right">
          <template #default="{ row }">{{ fmt(row.impairmentEnding) }}</template>
        </el-table-column>
        <el-table-column prop="carryingAmount" label="账面净值" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="摊余期末−减值−核销">{{ fmt(row.carryingAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookClosingUnrealized" label="账面未实现" min-width="100" align="right">
          <template #default="{ row }">{{ fmt(row.bookClosingUnrealized) }}</template>
        </el-table-column>
        <el-table-column prop="unrealizedVariance" label="未实现差异" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'variance-error': Math.abs(row.unrealizedVariance) > 0.01 }">{{ fmt(row.unrealizedVariance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amortizedVariance" label="摊余差异" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'variance-error': Math.abs(row.amortizedVariance) > 0.01 }">{{ fmt(row.amortizedVariance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="continuityOk" label="连续性" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.continuityOk ? 'success' : 'danger'" size="small">
              {{ row.continuityOk ? 'OK' : '断档' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="totals-bar">
      <span>融资收益合计（审计测算）：<strong>{{ fmt(sales.totalIncome.value) }}</strong></span>
      <span>账面融资收益合计：<strong>{{ fmt(sales.totalBookIncome.value) }}</strong></span>
      <span :class="{ 'variance-error': Math.abs(sales.totalVariance.value) > 0.01 }">
        收益差异合计：<strong>{{ fmt(sales.totalVariance.value) }}</strong>
      </span>
      <span :class="{ 'variance-error': Math.abs(sales.reconcileTotals.value.unrealizedVariance) > 0.01 }">
        未实现期末差异：<strong>{{ fmt(sales.reconcileTotals.value.unrealizedVariance) }}</strong>
      </span>
    </div>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="sales.conclusion.value"
      conclusion-ai-section="sales-amortization-conclusion"
      note-placeholder="填写审计说明：收入确认条件与合同要素、公允价值/实际利率依据、摊销与账面差异、收款困难时未实现及减值处理、与权益法长期应收穿透（如适用）。"
      conclusion-placeholder="A、分期销售未实现融资收益测算正确，与账面一致。B、除下述差异应予调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
      conclusion-hint="按 A/B/C 口径评价实际利率法测算与期末勾稽结果。"
      :related-context="aiContext"
      @update:note="saveAuditNote"
      @update:conclusion="(v: string) => { sales.conclusion.value = v }"
    />

    <details class="prep-hint" open>
      <summary>📋 编制提示（对齐致同模板）</summary>
      <ol>
        <li>
          <strong>合同与收入确认</strong>：获取分期收款销售合同，检查商品控制权转移/收入确认条件是否满足；核对售价、各期收款额与收款期。
        </li>
        <li>
          <strong>初始计量</strong>：未实现融资收益 = 应收总额 − 公允价值；实际利率应使未来收款折现等于公允价值，并与前期一致。
        </li>
        <li>
          <strong>分期摊销（模板列）</strong>：(3)=(1)×(4)；(2)=(5)−(3)；录入账面收益比对差异。可点「种子第一期」用初始要素填首期期初。
        </li>
        <li>
          <strong>特殊情形</strong>：实质构成对联营/合营净投资的长期应收，应与长期股权投资审计协调，关注超额亏损冲减顺序。
        </li>
        <li>
          <strong>收款困难</strong>：若长期应收存在回收风险，检查未实现融资收益与减值准备处理是否恰当（汇总页预计可收回与减值列）。
        </li>
        <li>
          <strong>勾稽</strong>：本表合计应与 G5-2 分期销售行、G5-1 审定及附注未实现披露勾稽；差异考虑调整至 G5-4。
        </li>
      </ol>
      <p class="cas-basis">
        CAS 依据：《企业会计准则第 14 号——收入》《企业会计准则第 22 号——金融工具确认和计量》；
        审计证据充分性参见《中国注册会计师审计准则第 1301 号——审计证据》。
      </p>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, watch, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useG5InstallmentSales } from '../../composables/useG5InstallmentSales'
import type {
  InstallmentSalesGroup,
  InstallmentPeriod,
  InstallmentReconcileRow,
} from '../../composables/useG5InstallmentSales'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const emit = defineEmits<{ imported: [] }>()
const sales = useG5InstallmentSales()

const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const G5_NOTE_KEY = 'G5-6-audit-note'
const G5_CONCLUSION_KEY = 'G5-6-audit-conclusion'

function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
watch(() => sales.conclusion.value, (val) => {
  if (props.readonly) return
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val ?? '' })
})

onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) sales.conclusion.value = c.remark
  const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_6_ROWS))
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (parsed?.groups) sales.loadData(parsed)
      else if (Array.isArray(parsed)) sales.loadData({ groups: parsed })
    } catch { /* ignore */ }
  }
})

watch(
  () => sales.groups.value,
  () => {
    if (props.readonly) return
    const json = JSON.stringify(sales.toJSON())
    g5Notes.debouncedSave(G5_ITEM_IDS.G5_6_ROWS, { remark: json, conclusion: json })
  },
  { deep: true },
)

const tabOptions = [
  { label: '初始交易要素', value: 'initial' },
  { label: '分期摊销', value: 'amortization' },
  { label: '期末汇总勾稽', value: 'reconcile' },
]

function onRecalcInitial(group: InstallmentSalesGroup) {
  sales.recalcInitial(group)
  sales.recalcGroup(group)
}
function onRecalc(group: InstallmentSalesGroup, period: InstallmentPeriod) {
  sales.recalcPeriod(period, group.initial.effectiveRate)
}
async function onImported() {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_6_ROWS))
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (parsed?.groups) sales.loadData(parsed)
      else if (Array.isArray(parsed)) sales.loadData({ groups: parsed })
    } catch { /* ignore */ }
  }
  emit('imported')
}

function pullFromG52() {
  if (props.readonly) return
  const raw = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_2_ROWS))
  if (!raw) {
    ElMessage.warning('未找到 G5-2 数据，请先在余额明细表录入分期销售行')
    return
  }
  try {
    const parsed = JSON.parse(raw)
    const rows = Array.isArray(parsed) ? parsed : (parsed?.rows || [])
    sales.importFromG5BalanceRows(Array.isArray(rows) ? rows : [])
  } catch {
    ElMessage.error('G5-2 数据解析失败')
  }
}

function getContinuityClass(group: InstallmentSalesGroup, row: InstallmentPeriod): string {
  if (row.periodNo <= 1) return ''
  const prev = group.periods[row.periodNo - 2]
  if (!prev) return ''
  if (Math.abs(row.openingReceivable - prev.closingReceivable) > 0.01) return 'row-continuity-error'
  if (Math.abs(row.openingUnrealized - prev.closingUnrealized) > 0.01) return 'row-continuity-error'
  return ''
}

function reconcileRowClass({ row }: { row: InstallmentReconcileRow }) {
  if (!row.continuityOk) return 'row-continuity-error'
  if (Math.abs(row.unrealizedVariance) > 0.01 || Math.abs(row.amortizedVariance) > 0.01) return 'row-variance-warn'
  return ''
}

function reconcileSummaryMethod(param: { columns: Array<{ property?: string }> }) {
  const t = sales.reconcileTotals.value as Record<string, number>
  return param.columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const key = col.property
    if (!key || key === 'continuityOk' || key === 'projectName') return ''
    const v = t[key]
    return typeof v === 'number' ? fmt(v) : ''
  })
}

const aiContext = computed(() => ({
  projectCount: sales.groups.value.length,
  totalIncome: sales.totalIncome.value,
  totalBookIncome: sales.totalBookIncome.value,
  totalVariance: sales.totalVariance.value,
  unrealizedEndingVariance: sales.reconcileTotals.value.unrealizedVariance,
  amortizedEndingVariance: sales.reconcileTotals.value.amortizedVariance,
}))

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function pct(rate: number): string {
  if (!rate) return '—'
  return `${(rate * 100).toFixed(4)}%`
}
</script>

<style scoped>
.g5-installment-sales { font-size: var(--wp-font-size, 13px); }
.section-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.method-context {
  margin-bottom: 12px; padding: 8px 12px;
  border-left: 3px solid #e6a23c; background: #fdf6ec;
  border-radius: 0 4px 4px 0; font-size: 12px; color: #865c0a; line-height: 1.6;
}
.method-context p { margin: 0 0 4px; }
.method-context p:last-child { margin-bottom: 0; }
.audit-objective { margin-bottom: 12px; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.tab-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.group-header {
  display: flex; align-items: center; gap: 8px;
  margin: 12px 0 4px; padding: 6px 12px;
  background: #f0f9eb; border-left: 3px solid #67c23a; border-radius: 0 4px 4px 0;
}
.group-title { font-weight: 600; }
.group-meta { font-size: 12px; color: #909399; }
.group-name-input { max-width: 280px; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.variance-error { color: #f56c6c; font-weight: 600; }
.continuity-warning { color: #e6a23c; font-size: 12px; margin: 4px 0 8px 12px; }
.totals-bar {
  margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px;
  font-size: 12px; display: flex; flex-wrap: wrap; gap: 16px;
}
.prep-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ol { margin: 8px 0 0; padding-left: 20px; line-height: 1.85; }
.cas-basis { margin: 8px 0 0; color: #909399; font-size: 11px; }
:deep(.row-continuity-error) { background-color: #fef0f0 !important; }
:deep(.row-variance-warn) { background-color: #fdf6ec !important; }
.basic-table { margin-bottom: 4px; }
.empty-hint { padding: 24px; text-align: center; color: #909399; font-size: 13px; }
.reconcile-tip { margin-bottom: 10px; }
.reconcile-main-title { margin: 14px 0 6px; font-size: 13px; font-weight: 600; color: #303133; }
.sub-lessee { font-size: 11px; color: #909399; }
</style>
