<template>
  <div class="j2-tab-detail">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：核对设定受益义务（DBO）各项目期初、服务成本、利息费用、精算损益、已支付等变动的完整性，验证期末净负债 = DBO期末 - 计划资产公允价值的准确性。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="section-title">长期应付职工薪酬/设定受益计划净资产明细表</h3>
      <span class="chip-wrap"><GtIndexChip value="wp:J2-1" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ detailItems.length }} 行</el-tag>
    </div>

    <!-- 引导区 -->
    <div class="guide-area">
      <div class="guide-step"><span class="step-num">①</span> 录入各类福利的期初余额和本期变动</div>
      <div class="guide-step"><span class="step-num">②</span> 系统自动计算期末余额和净负债</div>
    </div>

    <!-- 明细表 -->
    <el-table :data="detailItems" border stripe style="width: 100%; font-size: 13px">
      <el-table-column prop="label" label="项目" width="180" fixed />
      <el-table-column prop="beginBalance" label="期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small" @change="recalc(row)" />
          <span v-else>{{ fmt(row.beginBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期增加" align="center">
        <el-table-column prop="serviceCost" label="服务成本" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.serviceCost" :controls="false" size="small" @change="recalc(row)" />
            <span v-else>{{ fmt(row.serviceCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="interestCost" label="利息费用" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.interestCost" :controls="false" size="small" @change="recalc(row)" />
            <span v-else>{{ fmt(row.interestCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actuarialLoss" label="精算损失" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.actuarialLoss" :controls="false" size="small" @change="recalc(row)" />
            <span v-else>{{ fmt(row.actuarialLoss) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="本期减少" align="center">
        <el-table-column prop="benefitsPaid" label="已支付" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.benefitsPaid" :controls="false" size="small" @change="recalc(row)" />
            <span v-else>{{ fmt(row.benefitsPaid) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="actuarialGain" label="精算利得" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.actuarialGain" :controls="false" size="small" @change="recalc(row)" />
            <span v-else>{{ fmt(row.actuarialGain) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column prop="endBalance" label="期末余额" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= 期初 + 增加 - 减少">{{ fmt(row.endBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="planAssetFV" label="计划资产FV" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.planAssetFV" :controls="false" size="small" @change="recalc(row)" />
          <span v-else>{{ fmt(row.planAssetFV) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="netLiability" label="净负债" width="120" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="= DBO期末 - 计划资产FV">{{ fmt(row.netLiability) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="totals-bar">
      <span>合计期初：{{ fmt(detail.totalBeginBalance.value) }}</span>
      <span>合计期末：{{ fmt(detail.totalEndBalance.value) }}</span>
      <span>合计净负债：{{ fmt(detail.totalNetLiability.value) }}</span>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，设定受益计划义务变动含当期服务成本、利息费用、精算损益、已支付福利。</p>
        <p>2. 灰色底纹"期末余额""净负债"列为自动计算列（期末=期初+增加-减少；净负债=DBO期末-计划资产FV），不可手动编辑。</p>
        <p>3. 精算损益按 CAS 9 计入其他综合收益（M9），不得重分类至损益。</p>
        <p>4. 明细表期末净负债应与审定表（J2-1）审定数勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useJ2Detail } from '@/composables/workpaper/j2/useJ2Detail'
import type { DetailItem } from '@/composables/workpaper/j2/useJ2Detail'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const detail = useJ2Detail()
const detailItems = detail.items

function recalc(row: DetailItem) {
  detail.recalcItem(row)
}

function fmt(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => {
  if (props.htmlData) {
    detail.loadFromHtmlData(props.htmlData)
  } else {
    detail.items.value = detail.createDefaultItems()
  }
})
</script>

<style scoped>
.j2-tab-detail { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-size: 15px; font-weight: 600; margin: 0; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.guide-area { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; padding: 12px; background: linear-gradient(135deg, #ecf5ff 0%, #f0f9ff 100%); border-radius: 8px; }
.guide-step { font-size: 13px; color: #303133; }
.step-num { display: inline-block; width: 20px; height: 20px; line-height: 20px; text-align: center; background: #409eff; color: #fff; border-radius: 50%; font-size: 11px; margin-right: 6px; }
.formula-cell { border-bottom: 1px dashed #409eff; cursor: help; }
.totals-bar { margin-top: 12px; display: flex; gap: 24px; font-size: 13px; font-weight: 500; color: #303133; }
</style>
