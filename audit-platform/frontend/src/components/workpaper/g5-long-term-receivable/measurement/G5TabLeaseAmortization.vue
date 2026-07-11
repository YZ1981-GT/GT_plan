<template>
  <div class="g5-lease-amortization">
    <!-- 方法论上下文 -->
    <div class="method-context">
      <p><strong>内含利率法</strong>：融资收益 = 期初净投资额 × 内含利率</p>
      <p>净投资额 = 应收融资租赁款 - 未实现融资收益；期间连续性：第N期期初 = 第N-1期期末</p>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      对融资租赁形成的长期应收款按内含利率法测算未实现融资收益的分期摊销，验证各期融资收益与账面确认金额的一致性。
    </el-alert>

    <!-- 区段Tab + 操作按钮 -->
    <div class="segment-tabs">
      <el-segmented v-model="lease.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions">
        <GtIndexChip value="wp:G5-5" />
        <el-button size="small" type="primary" plain @click="lease.addGroup()" :disabled="props.readonly">
          + 新增租赁项目
        </el-button>
      </div>
    </div>

    <!-- Tab1: 租赁基础信息 -->
    <div v-show="lease.activeTab.value === 'basic'">
      <template v-for="group in lease.groups.value" :key="group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }}</span>
          <el-button size="small" type="danger" text @click="removeGroup(group.id)" :disabled="props.readonly">
            删除项目
          </el-button>
        </div>
        <el-table :data="[group.basic]" border style="width: 100%; font-size: 13px" class="basic-table">
          <el-table-column label="承租人" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.lessee" size="small" :disabled="props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="租赁开始日" width="120">
            <template #default="{ row }">
              <el-input v-model="row.leaseStartDate" size="small" placeholder="YYYY-MM-DD" :disabled="props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="租赁到期日" width="120">
            <template #default="{ row }">
              <el-input v-model="row.leaseEndDate" size="small" placeholder="YYYY-MM-DD" :disabled="props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="最低租赁收款额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.minimumLeasePayment" size="small" :controls="false" :disabled="props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="未担保余值" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.unguaranteedResidual" size="small" :controls="false" :disabled="props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="租赁资产公允价值" min-width="130" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.fairValue" size="small" :controls="false" :disabled="props.readonly" />
            </template>
          </el-table-column>
          <el-table-column label="内含利率" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.implicitRate" size="small" :controls="false" :precision="6" :disabled="props.readonly" />
            </template>
          </el-table-column>
        </el-table>
      </template>
    </div>

    <!-- Tab2: 摊销计算 -->
    <div v-show="lease.activeTab.value === 'amortization'">
      <template v-for="group in lease.groups.value" :key="group.id">
        <div class="group-header">
          <span class="group-title">{{ group.projectName }}</span>
          <el-button size="small" type="primary" text @click="lease.addPeriod(group.id)" :disabled="props.readonly">
            + 新增期间
          </el-button>
        </div>
        <el-table
          :data="group.periods"
          border stripe
          style="width: 100%; font-size: 13px"
          :row-class-name="({ row }) => getContinuityClass(group, row)"
        >
          <el-table-column prop="periodNo" label="期次" width="55" align="center" />
          <el-table-column label="期初应收" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.openingReceivable" size="small" :controls="false" :disabled="props.readonly"
                @change="onRecalc(group, row)" />
            </template>
          </el-table-column>
          <el-table-column label="期初未实现" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.openingUnrealized" size="small" :controls="false" :disabled="props.readonly"
                @change="onRecalc(group, row)" />
            </template>
          </el-table-column>
          <el-table-column label="净投资额" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初应收-期初未实现">{{ fmt(row.openingNetInvestment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期融资收益" min-width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="净投资额×内含利率">{{ fmt(row.periodIncome) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期收款额" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.periodCollection" size="small" :controls="false" :disabled="props.readonly"
                @change="onRecalc(group, row)" />
            </template>
          </el-table-column>
          <el-table-column label="期末应收" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初应收-本期收款">{{ fmt(row.closingReceivable) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末未实现" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初未实现-本期收益">{{ fmt(row.closingUnrealized) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末净投资" min-width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末应收-期末未实现">{{ fmt(row.closingNetInvestment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" min-width="90" align="right">
            <template #default="{ row }">
              <span :class="{ 'variance-error': Math.abs(row.variance) > 0.01 }">{{ fmt(row.variance) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="!lease.validateContinuity(group)" class="continuity-warning">
          ⚠ 期间连续性校验未通过：存在期初值≠上期期末值
        </div>
      </template>
    </div>

    <!-- 融资收益合计 -->
    <div class="totals-bar">
      融资收益合计（审计测算）：{{ fmt(lease.totalIncome.value) }}
    </div>

    <!-- 审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" text class="ai-btn">AI 辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="lease.conclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入审计结论..."
        :disabled="props.readonly"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-tips">
      <summary>编制提示</summary>
      <ol>
        <li>逐项录入租赁合同的基础信息（Tab1），确认内含利率准确</li>
        <li>按期间逐期添加摊销数据（Tab2），系统自动计算公式列</li>
        <li>核对期间连续性（第N期期初=第N-1期期末）</li>
        <li>比较审计测算融资收益与企业账面值，分析差异原因</li>
        <li>差异超过重要性水平的以红色标记，需进一步追查</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import { useG5LeaseAmortization } from '../../composables/useG5LeaseAmortization'
import type { LeaseAmortizationGroup, LeaseAmortizationPeriod } from '../../composables/useG5LeaseAmortization'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const lease = useG5LeaseAmortization()

const tabOptions = [
  { label: '租赁基础信息', value: 'basic' },
  { label: '摊销计算', value: 'amortization' },
]

function onRecalc(group: LeaseAmortizationGroup, period: LeaseAmortizationPeriod) {
  lease.recalcPeriod(period, group.basic.implicitRate)
}

function removeGroup(groupId: string) {
  const idx = lease.groups.value.findIndex(g => g.id === groupId)
  if (idx >= 0) lease.groups.value.splice(idx, 1)
}

function getContinuityClass(group: LeaseAmortizationGroup, row: LeaseAmortizationPeriod): string {
  if (row.periodNo <= 1) return ''
  const prev = group.periods[row.periodNo - 2]
  if (!prev) return ''
  if (Math.abs(row.openingReceivable - prev.closingReceivable) > 0.01) return 'row-continuity-error'
  if (Math.abs(row.openingUnrealized - prev.closingUnrealized) > 0.01) return 'row-continuity-error'
  return ''
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g5-lease-amortization { font-size: 13px; }
.method-context {
  margin-bottom: 12px; padding: 8px 12px;
  border-left: 3px solid #e6a23c; background: #fdf6ec;
  border-radius: 0 4px 4px 0; font-size: 12px; color: #865c0a; line-height: 1.6;
}
.method-context p { margin: 0 0 4px; }
.method-context p:last-child { margin-bottom: 0; }
.audit-objective { margin-bottom: 12px; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.tab-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.group-header {
  display: flex; align-items: center; gap: 8px;
  margin: 12px 0 4px; padding: 6px 12px;
  background: #f0f9eb; border-left: 3px solid #67c23a; border-radius: 0 4px 4px 0;
}
.group-title { font-weight: 600; font-size: 13px; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.variance-error { color: #f56c6c; font-weight: 600; }
.continuity-warning { color: #e6a23c; font-size: 12px; margin: 4px 0 8px 12px; }
.totals-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
.conclusion-card { margin-top: 12px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.ai-btn { float: right; }
.prep-tips { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-tips summary { cursor: pointer; font-weight: 500; }
.prep-tips ol { margin: 4px 0 0; padding-left: 20px; line-height: 1.8; }
:deep(.row-continuity-error) { background-color: #fef0f0 !important; }
.basic-table { margin-bottom: 4px; }
</style>
