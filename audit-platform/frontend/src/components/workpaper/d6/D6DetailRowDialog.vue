<template>
<el-dialog
  :model-value="visible"
  :title="isEdit ? '编辑合同资产明细' : '新增合同资产明细'"
  width="680px"
  :close-on-click-modal="false"
  destroy-on-close
  @update:model-value="$emit('update:visible', $event)"
>
  <el-steps :active="activeStep" finish-status="success" simple style="margin-bottom:20px">
    <el-step title="基本信息" />
    <el-step title="期初数据" />
    <el-step title="本期变动" />
    <el-step title="期末调整与分类" />
  </el-steps>

  <!-- Step 0: 基本信息 -->
  <div v-show="activeStep === 0" class="step-content">
    <el-alert type="info" :closable="false" class="step-hint">
      填写合同基础信息：合同名称、类型、客户等。类型决定小计分组。
    </el-alert>
    <el-form label-width="110px" label-position="right">
      <el-form-item label="合同名称" required>
        <el-input v-model="form.contractName" placeholder="输入合同/项目名称" />
      </el-form-item>
      <el-form-item label="合同类型" required>
        <el-select v-model="form.contractType" placeholder="选择类型" style="width:100%">
          <el-option v-for="t in CONTRACT_TYPES" :key="t" :label="t" :value="t" />
        </el-select>
      </el-form-item>
      <el-form-item label="客户名称">
        <el-input v-model="form.customerName" placeholder="输入客户名称" />
      </el-form-item>
      <el-form-item label="公司代码">
        <el-input v-model="form.companyCode" placeholder="输入公司代码（可选）" />
      </el-form-item>
      <el-form-item label="关联关系">
        <el-select v-model="form.relatedPartyType" placeholder="选择关联关系" style="width:100%">
          <el-option v-for="t in RELATED_PARTY_TYPES" :key="t" :label="t" :value="t" />
        </el-select>
      </el-form-item>
    </el-form>
  </div>

  <!-- Step 1: 期初数据 -->
  <div v-show="activeStep === 1" class="step-content">
    <el-alert type="info" :closable="false" class="step-hint">
      录入期初余额。期初审定 = 期初未审 + AJE + RJE（自动计算，灰色显示）。
    </el-alert>
    <el-form label-width="110px" label-position="right">
      <el-form-item label="期初未审">
        <WpAmountInput v-model="form.priorUnadjusted" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="期初AJE">
        <WpAmountInput v-model="form.priorAje" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="期初RJE">
        <WpAmountInput v-model="form.priorRje" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="期初审定">
        <div class="computed-value">{{ fmtAmt(computedPriorAudited) }}</div>
        <div class="formula-hint">= 期初未审 + AJE + RJE</div>
      </el-form-item>
      <el-divider content-position="left">期初账龄分布（可选）</el-divider>
      <div class="aging-grid">
        <el-form-item label="≤1年">
          <el-input-number v-model="form.agePrior1y" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
        <el-form-item label="1~2年">
          <el-input-number v-model="form.agePrior1to2y" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
        <el-form-item label="2~3年">
          <el-input-number v-model="form.agePrior2to3y" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
        <el-form-item label="3年以上">
          <el-input-number v-model="form.agePrior3yAbove" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
      </div>
      <div v-if="priorAgingDiff !== 0" class="aging-warn">
        <el-tag type="warning" size="small">账龄合计与期初审定差异：{{ fmtAmt(priorAgingDiff) }}</el-tag>
      </div>
    </el-form>
  </div>

  <!-- Step 2: 本期变动 -->
  <div v-show="activeStep === 2" class="step-content">
    <el-alert type="info" :closable="false" class="step-hint">
      录入本期借贷方发生额。期末未审 = 期初审定 + 借方 - 贷方（借方科目）。
    </el-alert>
    <el-form label-width="110px" label-position="right">
      <el-form-item label="借方发生">
        <WpAmountInput v-model="form.debitAmount" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="贷方发生">
        <WpAmountInput v-model="form.creditAmount" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="期末未审">
        <div class="computed-value">{{ fmtAmt(computedEndUnadjusted) }}</div>
        <div class="formula-hint">= 期初审定({{ fmtAmt(computedPriorAudited) }}) + 借方 - 贷方</div>
      </el-form-item>
    </el-form>
  </div>

  <!-- Step 3: 期末调整与分类 -->
  <div v-show="activeStep === 3" class="step-content">
    <el-alert type="info" :closable="false" class="step-hint">
      录入期末调整及分类信息。期末审定 = 期末未审 + AJE + RJE。
    </el-alert>
    <el-form label-width="120px" label-position="right">
      <el-form-item label="期末AJE">
        <WpAmountInput v-model="form.endAje" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="期末RJE">
        <WpAmountInput v-model="form.endRje" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="期末审定">
        <div class="computed-value highlight">{{ fmtAmt(computedEndAudited) }}</div>
        <div class="formula-hint">= 期末未审({{ fmtAmt(computedEndUnadjusted) }}) + AJE + RJE</div>
      </el-form-item>
      <el-divider content-position="left">期末账龄分布（可选）</el-divider>
      <div class="aging-grid">
        <el-form-item label="≤1年">
          <el-input-number v-model="form.ageEnd1y" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
        <el-form-item label="1~2年">
          <el-input-number v-model="form.ageEnd1to2y" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
        <el-form-item label="2~3年">
          <el-input-number v-model="form.ageEnd2to3y" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
        <el-form-item label="3年以上">
          <el-input-number v-model="form.ageEnd3yAbove" :controls="false" style="width:100%" placeholder="0" />
        </el-form-item>
      </div>
      <div v-if="endAgingDiff !== 0" class="aging-warn">
        <el-tag type="warning" size="small">账龄合计与期末审定差异：{{ fmtAmt(endAgingDiff) }}</el-tag>
      </div>
      <el-divider content-position="left">收款权与分类</el-divider>
      <el-form-item label="1年内收款权">
        <el-input-number v-model="form.receivableWithin1y" :controls="false" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="1年以上收款权">
        <el-input-number v-model="form.receivableAbove1y" :controls="false" style="width:100%" placeholder="0" />
      </el-form-item>
      <el-form-item label="建设期/质保期">
        <el-select v-model="form.isInConstructionPeriod" style="width:100%" placeholder="选择">
          <el-option v-for="o in CONSTRUCTION_PERIOD_OPTIONS" :key="o" :label="o" :value="o" />
        </el-select>
      </el-form-item>
      <el-form-item label="信用风险组合">
        <el-select v-model="form.creditRiskGroup" style="width:100%" placeholder="选择">
          <el-option v-for="g in CREDIT_RISK_GROUPS" :key="g" :label="g" :value="g" />
        </el-select>
      </el-form-item>
      <el-form-item label="是否函证">
        <el-select v-model="form.isConfirmed" style="width:100%" placeholder="选择">
          <el-option label="是" value="是" />
          <el-option label="否" value="否" />
        </el-select>
      </el-form-item>
      <el-form-item label="期后结转金额">
        <WpAmountInput v-model="form.postPeriodSettlement" style="width:100%" placeholder="0" />
      </el-form-item>
    </el-form>
  </div>

  <template #footer>
    <div class="dialog-footer">
      <el-button v-if="activeStep > 0" @click="activeStep--">上一步</el-button>
      <el-button v-if="activeStep < 3" type="primary" @click="activeStep++">下一步</el-button>
      <el-button v-if="activeStep === 3" type="primary" :disabled="!canSubmit" @click="onSubmit">
        {{ isEdit ? '保存修改' : '确认添加' }}
      </el-button>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
    </div>
  </template>
</el-dialog>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, computed, watch, reactive } from 'vue'
import {
  CONTRACT_TYPES,
  RELATED_PARTY_TYPES,
  CREDIT_RISK_GROUPS,
  CONSTRUCTION_PERIOD_OPTIONS,
  type DetailRow,
} from '../composables/useD6Detail'

const props = defineProps<{
  visible: boolean
  editRow?: DetailRow | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'confirm', data: Partial<DetailRow>): void
}>()

const isEdit = computed(() => !!props.editRow)
const activeStep = ref(0)

const form = reactive({
  contractName: '',
  contractType: '' as string,
  customerName: '',
  companyCode: '',
  relatedPartyType: '' as string,
  priorUnadjusted: 0,
  priorAje: 0,
  priorRje: 0,
  agePrior1y: 0,
  agePrior1to2y: 0,
  agePrior2to3y: 0,
  agePrior3yAbove: 0,
  debitAmount: 0,
  creditAmount: 0,
  endAje: 0,
  endRje: 0,
  ageEnd1y: 0,
  ageEnd1to2y: 0,
  ageEnd2to3y: 0,
  ageEnd3yAbove: 0,
  receivableWithin1y: 0,
  receivableAbove1y: 0,
  isInConstructionPeriod: '' as string,
  creditRiskGroup: '' as string,
  isConfirmed: '' as string,
  postPeriodSettlement: 0,
})

// Reset form when dialog opens / editRow changes
watch(
  () => props.visible,
  (val) => {
    if (!val) return
    activeStep.value = 0
    if (props.editRow) {
      Object.assign(form, {
        contractName: props.editRow.contractName,
        contractType: props.editRow.contractType,
        customerName: props.editRow.customerName,
        companyCode: props.editRow.companyCode,
        relatedPartyType: props.editRow.relatedPartyType,
        priorUnadjusted: props.editRow.priorUnadjusted,
        priorAje: props.editRow.priorAje,
        priorRje: props.editRow.priorRje,
        agePrior1y: props.editRow.agePrior1y,
        agePrior1to2y: props.editRow.agePrior1to2y,
        agePrior2to3y: props.editRow.agePrior2to3y,
        agePrior3yAbove: props.editRow.agePrior3yAbove,
        debitAmount: props.editRow.debitAmount,
        creditAmount: props.editRow.creditAmount,
        endAje: props.editRow.endAje,
        endRje: props.editRow.endRje,
        ageEnd1y: props.editRow.ageEnd1y,
        ageEnd1to2y: props.editRow.ageEnd1to2y,
        ageEnd2to3y: props.editRow.ageEnd2to3y,
        ageEnd3yAbove: props.editRow.ageEnd3yAbove,
        receivableWithin1y: props.editRow.receivableWithin1y,
        receivableAbove1y: props.editRow.receivableAbove1y,
        isInConstructionPeriod: props.editRow.isInConstructionPeriod,
        creditRiskGroup: props.editRow.creditRiskGroup,
        isConfirmed: props.editRow.isConfirmed,
        postPeriodSettlement: props.editRow.postPeriodSettlement,
      })
    } else {
      Object.assign(form, {
        contractName: '', contractType: '', customerName: '', companyCode: '',
        relatedPartyType: '', priorUnadjusted: 0, priorAje: 0, priorRje: 0,
        agePrior1y: 0, agePrior1to2y: 0, agePrior2to3y: 0, agePrior3yAbove: 0,
        debitAmount: 0, creditAmount: 0, endAje: 0, endRje: 0,
        ageEnd1y: 0, ageEnd1to2y: 0, ageEnd2to3y: 0, ageEnd3yAbove: 0,
        receivableWithin1y: 0, receivableAbove1y: 0,
        isInConstructionPeriod: '', creditRiskGroup: '', isConfirmed: '',
        postPeriodSettlement: 0,
      })
    }
  },
)

// ─── Computed fields (live preview) ────────────────────────────────────────
const computedPriorAudited = computed(() => (form.priorUnadjusted || 0) + (form.priorAje || 0) + (form.priorRje || 0))
const computedEndUnadjusted = computed(() => computedPriorAudited.value + (form.debitAmount || 0) - (form.creditAmount || 0))
const computedEndAudited = computed(() => computedEndUnadjusted.value + (form.endAje || 0) + (form.endRje || 0))

// Aging validation
const priorAgingSum = computed(() => (form.agePrior1y || 0) + (form.agePrior1to2y || 0) + (form.agePrior2to3y || 0) + (form.agePrior3yAbove || 0))
const endAgingSum = computed(() => (form.ageEnd1y || 0) + (form.ageEnd1to2y || 0) + (form.ageEnd2to3y || 0) + (form.ageEnd3yAbove || 0))
const priorAgingDiff = computed(() => priorAgingSum.value > 0 ? priorAgingSum.value - computedPriorAudited.value : 0)
const endAgingDiff = computed(() => endAgingSum.value > 0 ? endAgingSum.value - computedEndAudited.value : 0)

const canSubmit = computed(() => !!form.contractName.trim())

function onSubmit() {
  emit('confirm', { ...form })
  emit('update:visible', false)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.step-content { min-height: 280px; }
.step-hint { margin-bottom: 16px; }
.computed-value {
  font-size: 16px; font-weight: 600; color: #303133;
  background: #f5f7fa; padding: 4px 10px; border-radius: 4px;
  display: inline-block;
}
.computed-value.highlight { color: #409eff; background: #ecf5ff; }
.formula-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.aging-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px;
}
.aging-warn { margin-top: 4px; margin-bottom: 8px; }
.dialog-footer { display: flex; justify-content: flex-end; gap: 8px; }
</style>
