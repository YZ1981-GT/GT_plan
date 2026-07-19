<template>
  <div class="g5-lease-amortization">
    <!-- 表头：对齐 G5-2/G5-4 -->
    <div class="section-head">
      <h3 class="sheet-title">G5-5 未实现融资收益测算表（融资租赁）</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-5" />
        <GtIndexChip value="wp:G5-2" />
        <GtIndexChip value="wp:G5-4" />
        <G5ImportExportDropdown
          :wp-id="props.wpId"
          sheet="G5-5"
          :disabled="!!props.readonly"
          @imported="onImported"
        />
        <el-tag size="small" type="info">共 {{ lease.groups.value.length }} 个项目</el-tag>
        <GtReviewTrigger section-id="g5-5-lease-amortization" />
      </div>
    </div>

    <div class="method-context">
      <p><strong>内含利率法</strong>：本期融资收益 = 期初租赁投资净额 × 内含利率</p>
      <p>
        净投资额 = 应收融资租赁款 − 未实现融资收益；
        毛投资额 ≈ 最低租赁收款额 + 未担保余值 + 初始直接费用；
        期间连续性：第 N 期期初 = 第 N−1 期期末
      </p>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：获取并检查融资租赁合同，核实长期应收款初始确认与后续计量；按内含利率法测算未实现融资收益摊销，验证各期融资收益与账面确认金额的一致性，期末汇总勾稽净投资额与账面净值。
    </el-alert>

    <!-- 区段 Tab + 操作 -->
    <div class="segment-tabs">
      <el-segmented v-model="lease.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions tab-toolbar">
        <el-button size="small" :disabled="!!props.readonly" @click="pullFromG52">
          从 G5-2 带入租赁
        </el-button>
        <el-button size="small" type="primary" plain @click="lease.addGroup()" :disabled="!!props.readonly">
          + 新增租赁项目
        </el-button>
      </div>
    </div>

    <!-- Tab1: 租赁基础信息（对齐模板初始确认列） -->
    <div v-show="lease.activeTab.value === 'basic'">
      <div v-if="lease.groups.value.length === 0" class="empty-hint">
        暂无租赁项目。可「新增租赁项目」或「从 G5-2 带入租赁」。
      </div>
      <template v-for="group in lease.groups.value" :key="group.id">
        <div class="group-header">
          <el-input
            v-model="group.projectName"
            size="small"
            class="group-name-input"
            :disabled="!!props.readonly"
            placeholder="项目名称"
          />
          <el-button size="small" type="danger" text @click="removeGroup(group.id)" :disabled="!!props.readonly">
            删除项目
          </el-button>
        </div>
        <el-table :data="[group.basic]" border style="width: 100%; font-size: 13px" class="basic-table">
          <el-table-column label="承租人" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.lessee" size="small" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="租赁开始日" width="120">
            <template #default="{ row }">
              <el-input v-model="row.leaseStartDate" size="small" placeholder="YYYY-MM-DD" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="租赁到期日" width="120">
            <template #default="{ row }">
              <el-input v-model="row.leaseEndDate" size="small" placeholder="YYYY-MM-DD" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="各期租金" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.rentalInstallments"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onBasicMlpChange(group)"
              />
            </template>
          </el-table-column>
          <el-table-column label="承租人担保余值" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.residualLessee"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onBasicMlpChange(group)"
              />
            </template>
          </el-table-column>
          <el-table-column label="第三方担保余值" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.residualThirdParty"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onBasicMlpChange(group)"
              />
            </template>
          </el-table-column>
          <el-table-column label="最低租赁收款额" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="租金+承租人担保+第三方担保">{{ fmt(row.minimumLeasePayment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="初始直接费用" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.initialDirectCosts" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="未担保余值期末" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.unguaranteedResidual"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onUnguaranteedEndEdit(group)"
              />
            </template>
          </el-table-column>
          <el-table-column label="公允价值" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.fairValue" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="内含利率" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.implicitRate"
                size="small"
                :controls="false"
                :precision="6"
                :disabled="!!props.readonly"
                @change="lease.recalcGroup(group)"
              />
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>

    <!-- Tab2: 分期摊销 -->
    <div v-show="lease.activeTab.value === 'amortization'">
      <div v-if="lease.groups.value.length === 0" class="empty-hint">请先在「租赁基础信息」新增项目。</div>
      <template v-for="group in lease.groups.value" :key="group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }}</span>
          <span class="group-meta">内含利率 {{ pct(group.basic.implicitRate) }}</span>
          <el-button size="small" type="primary" text @click="lease.addPeriod(group.id)" :disabled="!!props.readonly">
            + 新增期间
          </el-button>
        </div>
        <el-table
          :data="group.periods"
          border
          stripe
          style="width: 100%; font-size: 13px"
          :row-class-name="({ row }) => getContinuityClass(group, row)"
        >
          <el-table-column prop="periodNo" label="期次" width="55" align="center" />
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
          <el-table-column label="净投资额" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初应收−期初未实现">{{ fmt(row.openingNetInvestment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期融资收益(测)" min-width="115" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="净投资额×内含利率">{{ fmt(row.periodIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面融资收益" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.companyBookIncome"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="onRecalc(group, row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="差异" min-width="90" align="right">
            <template #default="{ row }">
              <span :class="{ 'variance-error': Math.abs(row.variance) > 0.01 }">{{ fmt(row.variance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期收款额" min-width="100" align="right">
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
          <el-table-column label="期末应收" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初应收−本期收款">{{ fmt(row.closingReceivable) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末未实现" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初未实现−本期收益">{{ fmt(row.closingUnrealized) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末净投资" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末应收−期末未实现">{{ fmt(row.closingNetInvestment) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!props.readonly" label="操作" width="60" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                type="danger"
                link
                :disabled="group.periods.length <= 1"
                @click="lease.removePeriod(group.id, row.id)"
              >删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!lease.validateContinuity(group)" class="continuity-warning">
          ⚠ 期间连续性校验未通过：存在期初值 ≠ 上期期末值（第 {{ lease.getContinuityErrors(group).join('、') }} 期）
        </div>
      </template>
    </div>

    <!-- Tab3: 期末汇总勾稽（对齐 Excel 模板列） -->
    <div v-show="lease.activeTab.value === 'reconcile'">
      <el-alert type="warning" :closable="false" show-icon class="reconcile-tip">
        本表按项目汇总，对应致同模板「未实现融资收益测算表」期末勾稽口径。灰色/虚线列为公式自动计算（来自基础信息 + 分期摊销）；可编辑列用于未担保余值滚存、账面对照、减值与核销。
      </el-alert>

      <!-- 可编辑：未担保滚存 + 账面/减值 -->
      <template v-for="group in lease.groups.value" :key="'edit-' + group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }} — 滚存与账面录入</span>
        </div>
        <el-table :data="[group.basic]" border size="small" class="basic-table">
          <el-table-column label="未担保余值期初" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.unguaranteedOpening"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="lease.syncUnguaranteedEnding(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.unguaranteedIncrease"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="lease.syncUnguaranteedEnding(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-model="row.unguaranteedDecrease"
                size="small"
                :controls="false"
                :disabled="!!props.readonly"
                @change="lease.syncUnguaranteedEnding(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="未担保期末(公式)" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmt(row.unguaranteedResidual) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面未实现期末" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.bookClosingUnrealized" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="账面净投资期末" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.bookClosingNetInvestment" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="预计可收回" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.estimatedRecoverable" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="减值准备期末" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.impairmentEnding" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="已核销" min-width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.writtenOffAmount" size="small" :controls="false" :disabled="!!props.readonly" />
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- 汇总勾稽主表 -->
      <div class="reconcile-main-title">期末汇总勾稽（审计测算）</div>
      <el-table
        :data="reconcileTableData"
        border
        stripe
        size="small"
        style="width: 100%; font-size: 12px"
        :row-class-name="reconcileRowClass"
        show-summary
        :summary-method="reconcileSummaryMethod"
      >
        <el-table-column prop="projectName" label="项目/承租人" min-width="120" fixed>
          <template #default="{ row }">
            <div>{{ row.projectName }}</div>
            <div class="sub-lessee">{{ row.lessee || '—' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="minimumLeasePayment" label="最低租赁收款额" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.minimumLeasePayment) }}</span></template>
        </el-table-column>
        <el-table-column prop="initialDirectCosts" label="初始直接费用" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.initialDirectCosts) }}</span></template>
        </el-table-column>
        <el-table-column prop="unguaranteedEnding" label="未担保余值期末" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.unguaranteedEnding) }}</span></template>
        </el-table-column>
        <el-table-column prop="grossInvestment" label="毛投资额" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="最低租赁收款额+未担保余值+初始直接费用">{{ fmt(row.grossInvestment) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unrealizedOpening" label="未实现期初" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.unrealizedOpening) }}</span></template>
        </el-table-column>
        <el-table-column prop="unrealizedAddition" label="本期增加" min-width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末−期初+本期确认">{{ fmt(row.unrealizedAddition) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unrealizedRecognized" label="本期确认收益" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.unrealizedRecognized) }}</span></template>
        </el-table-column>
        <el-table-column prop="unrealizedEnding" label="未实现期末" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.unrealizedEnding) }}</span></template>
        </el-table-column>
        <el-table-column prop="netOpening" label="净投资期初" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.netOpening) }}</span></template>
        </el-table-column>
        <el-table-column prop="netDecrease" label="净投资本期减少" min-width="120" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期初−期末">{{ fmt(row.netDecrease) }}</span></template>
        </el-table-column>
        <el-table-column prop="netEnding" label="净投资期末" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.netEnding) }}</span></template>
        </el-table-column>
        <el-table-column prop="estimatedRecoverable" label="预计可收回" min-width="100" align="right">
          <template #default="{ row }">{{ fmt(row.estimatedRecoverable) }}</template>
        </el-table-column>
        <el-table-column prop="impairmentEnding" label="减值准备" min-width="90" align="right">
          <template #default="{ row }">{{ fmt(row.impairmentEnding) }}</template>
        </el-table-column>
        <el-table-column prop="writtenOffAmount" label="已核销" min-width="80" align="right">
          <template #default="{ row }">{{ fmt(row.writtenOffAmount) }}</template>
        </el-table-column>
        <el-table-column prop="carryingAmount" label="账面净值" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净投资期末−减值−已核销">{{ fmt(row.carryingAmount) }}</span>
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
        <el-table-column prop="netVariance" label="净投资差异" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'variance-error': Math.abs(row.netVariance) > 0.01 }">{{ fmt(row.netVariance) }}</span>
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

    <!-- 合计条 -->
    <div class="totals-bar">
      <span>融资收益合计（审计测算）：<strong>{{ fmt(lease.totalIncome.value) }}</strong></span>
      <span>账面融资收益合计：<strong>{{ fmt(lease.totalBookIncome.value) }}</strong></span>
      <span :class="{ 'variance-error': Math.abs(lease.totalVariance.value) > 0.01 }">
        收益差异合计：<strong>{{ fmt(lease.totalVariance.value) }}</strong>
      </span>
      <span :class="{ 'variance-error': Math.abs(lease.reconcileTotals.value.unrealizedVariance) > 0.01 }">
        未实现期末差异：<strong>{{ fmt(lease.reconcileTotals.value.unrealizedVariance) }}</strong>
      </span>
    </div>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="lease.conclusion.value"
      conclusion-ai-section="lease-amortization-conclusion"
      note-placeholder="填写审计说明：合同分类与内含利率核对、初始确认（最低租赁收款额/未担保余值/初始直接费用）、分期摊销与账面确认差异、期末净投资与减值勾稽。"
      conclusion-placeholder="A、融资租赁未实现融资收益测算正确，与账面一致。B、除下述差异应予调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
      conclusion-hint="按 A/B/C 口径评价内含利率法测算与期末勾稽结果。"
      :related-context="aiContext"
      @update:note="saveAuditNote"
      @update:conclusion="(v: string) => { lease.conclusion.value = v }"
    />

    <details class="prep-tips" open>
      <summary>📋 编制提示（对齐致同模板）</summary>
      <ol>
        <li>
          <strong>初始确认</strong>：核对租赁合同分类是否为融资租赁；最低租赁收款额 = 各期租金 + 承租人担保余值 + 第三方担保余值；
          毛投资额 ≈ 最低租赁收款额 + 未担保余值 + 初始直接费用；初始净投资应与公允价值（加初始直接费用）勾稽。
        </li>
        <li>
          <strong>内含利率</strong>：验证出租人用于确认融资收益的内含利率是否能使最低租赁收款额及未担保余值的现值等于租赁资产公允价值与初始直接费用之和。
        </li>
        <li>
          <strong>分期摊销</strong>：在「分期摊销」页按期间录入期初应收/未实现与本期收款；系统按净投资×内含利率计算本期收益，并检查期间连续性。
        </li>
        <li>
          <strong>期末汇总</strong>：「期末汇总勾稽」页自动汇总未实现滚存与净投资变动；对比账面未实现/净投资，差异超过重要性水平需追查并考虑调整（汇总至 G5-4）。
        </li>
        <li>
          <strong>列报</strong>：关注一年内到期重分类、减值准备与附注最低租赁收款额披露（与 G5-1 / 附注勾稽）。
        </li>
      </ol>
      <p class="cas-basis">CAS 依据：《企业会计准则第 21 号——租赁》；审计程序执行与证据充分性参见《中国注册会计师审计准则第 1301 号——审计证据》。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, watch, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useG5LeaseAmortization } from '../../composables/useG5LeaseAmortization'
import type {
  LeaseAmortizationGroup,
  LeaseAmortizationPeriod,
  LeaseReconcileRow,
} from '../../composables/useG5LeaseAmortization'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const lease = useG5LeaseAmortization()

const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const G5_NOTE_KEY = 'G5-5-audit-note'
const G5_CONCLUSION_KEY = 'G5-5-audit-conclusion'

function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
watch(() => lease.conclusion.value, (val) => {
  if (props.readonly) return
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val ?? '' })
})

onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) lease.conclusion.value = c.remark
  const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_5_ROWS))
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (parsed?.groups) lease.loadData(parsed)
      else if (Array.isArray(parsed) && parsed.some((r: any) => r?.basic || r?.periods)) {
        lease.loadData({ groups: parsed })
      } else if (Array.isArray(parsed)) {
        // 旧扁平 IE 行：按项目名归并（后端现已写 nested；此路径兼容历史）
        lease.loadData({ groups: parsed })
      }
    } catch { /* ignore */ }
  }
})

watch(
  () => lease.groups.value,
  () => {
    if (props.readonly) return
    const json = JSON.stringify(lease.toJSON())
    g5Notes.debouncedSave(G5_ITEM_IDS.G5_5_ROWS, { remark: json, conclusion: json })
  },
  { deep: true },
)

async function onImported() {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_5_ROWS))
  if (saved) {
    try {
      const parsed = JSON.parse(saved)
      if (parsed?.groups) lease.loadData(parsed)
      else if (Array.isArray(parsed)) lease.loadData({ groups: parsed })
    } catch { /* ignore */ }
  }
  emit('imported')
}

function pullFromG52() {
  if (props.readonly) return
  const raw = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_2_ROWS))
  if (!raw) {
    ElMessage.warning('未找到 G5-2 数据，请先在余额明细表录入融资租赁行')
    return
  }
  try {
    const parsed = JSON.parse(raw)
    const rows = Array.isArray(parsed) ? parsed : (parsed?.rows || parsed?.groups || [])
    lease.importFromG5BalanceRows(Array.isArray(rows) ? rows : [])
  } catch {
    ElMessage.error('G5-2 数据解析失败')
  }
}

const tabOptions = [
  { label: '租赁基础信息', value: 'basic' },
  { label: '分期摊销', value: 'amortization' },
  { label: '期末汇总勾稽', value: 'reconcile' },
]

function onBasicMlpChange(group: LeaseAmortizationGroup) {
  lease.syncMinimumLeasePayment(group.basic)
}

function onUnguaranteedEndEdit(group: LeaseAmortizationGroup) {
  // 直接改期末时，同步写入期初（无滚存明细时）
  const b = group.basic
  if (!b.unguaranteedIncrease && !b.unguaranteedDecrease) {
    b.unguaranteedOpening = b.unguaranteedResidual
  }
}

function onRecalc(group: LeaseAmortizationGroup, period: LeaseAmortizationPeriod) {
  lease.recalcPeriod(period, group.basic.implicitRate)
}

function removeGroup(groupId: string) {
  lease.removeGroup(groupId)
}

function getContinuityClass(group: LeaseAmortizationGroup, row: LeaseAmortizationPeriod): string {
  if (row.periodNo <= 1) return ''
  const prev = group.periods[row.periodNo - 2]
  if (!prev) return ''
  if (Math.abs(row.openingReceivable - prev.closingReceivable) > 0.01) return 'row-continuity-error'
  if (Math.abs(row.openingUnrealized - prev.closingUnrealized) > 0.01) return 'row-continuity-error'
  return ''
}

const reconcileTableData = computed(() => lease.reconcileRows.value)

function reconcileRowClass({ row }: { row: LeaseReconcileRow }) {
  if (!row.continuityOk) return 'row-continuity-error'
  if (Math.abs(row.unrealizedVariance) > 0.01 || Math.abs(row.netVariance) > 0.01) return 'row-variance-warn'
  return ''
}

function reconcileSummaryMethod(param: { columns: Array<{ property?: string }> }) {
  const t = lease.reconcileTotals.value as Record<string, number>
  return param.columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const key = col.property
    if (!key || key === 'continuityOk' || key === 'projectName') return ''
    const v = t[key]
    return typeof v === 'number' ? fmt(v) : ''
  })
}

const aiContext = computed(() => ({
  projectCount: lease.groups.value.length,
  totalIncome: lease.totalIncome.value,
  totalBookIncome: lease.totalBookIncome.value,
  totalVariance: lease.totalVariance.value,
  unrealizedEndingVariance: lease.reconcileTotals.value.unrealizedVariance,
  netEndingVariance: lease.reconcileTotals.value.netVariance,
}))

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pct(rate: number): string {
  if (!rate) return '—'
  return `${(rate * 100).toFixed(4)}%`
}
</script>

<style scoped>
.g5-lease-amortization { font-size: var(--wp-font-size, 13px); }
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
.group-title { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.group-meta { font-size: 12px; color: #909399; }
.group-name-input { max-width: 280px; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.variance-error { color: #f56c6c; font-weight: 600; }
.continuity-warning { color: #e6a23c; font-size: 12px; margin: 4px 0 8px 12px; }
.totals-bar {
  margin-top: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px;
  font-size: 12px; display: flex; flex-wrap: wrap; gap: 16px;
}
.prep-tips { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-tips summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-tips ol { margin: 8px 0 0; padding-left: 20px; line-height: 1.85; }
.cas-basis { margin: 8px 0 0; color: #909399; font-size: 11px; }
:deep(.row-continuity-error) { background-color: #fef0f0 !important; }
:deep(.row-variance-warn) { background-color: #fdf6ec !important; }
.basic-table { margin-bottom: 4px; }
.empty-hint { padding: 24px; text-align: center; color: #909399; font-size: 13px; }
.reconcile-tip { margin-bottom: 10px; }
.reconcile-main-title {
  margin: 14px 0 6px; font-size: 13px; font-weight: 600; color: #303133;
}
.sub-lessee { font-size: 11px; color: #909399; }
</style>
