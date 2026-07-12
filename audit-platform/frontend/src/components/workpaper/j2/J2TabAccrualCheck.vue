<template>
  <div class="j2-tab-accrual-check">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：评估设定受益计划精算假设（折现率、薪酬增长率、死亡率、离职率）的合理性，并依据 ISA 620 评价精算师工作的胜任能力、客观性与充分性，判断计提充分性。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="section-title">长期应付职工薪酬/设定受益计划净资产检查表</h3>
      <span class="chip-wrap"><GtIndexChip value="wp:J2-1" :context-project-id="projectId" /></span>
    </div>

    <!-- 精算假设面板 -->
    <el-card class="assumption-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>精算假设参数</span>
          <el-tag v-if="validation.isValid" type="success" size="small">参数合理</el-tag>
          <el-tag v-else type="warning" size="small">存在异常</el-tag>
        </div>
      </template>
      <el-form label-width="120px" size="small">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="折现率">
              <el-input-number
                v-model="accrualCheck.assumptions.value.discountRate"
                :step="0.005"
                :min="0"
                :max="1"
                :precision="4"
                :controls="true"
                :disabled="isReadonly"
              />
              <span class="unit-hint">（如0.04=4%）</span>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="薪酬增长率">
              <el-input-number
                v-model="accrualCheck.assumptions.value.salaryGrowthRate"
                :step="0.01"
                :min="0"
                :max="1"
                :precision="4"
                :controls="true"
                :disabled="isReadonly"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="死亡率">
              <el-input-number
                v-model="accrualCheck.assumptions.value.mortalityRate"
                :step="0.001"
                :min="0"
                :max="1"
                :precision="4"
                :controls="true"
                :disabled="isReadonly"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="离职率">
              <el-input-number
                v-model="accrualCheck.assumptions.value.turnoverRate"
                :step="0.01"
                :min="0"
                :max="1"
                :precision="4"
                :controls="true"
                :disabled="isReadonly"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <!-- 校验警告 -->
      <div v-if="validation.warnings.length" class="warnings">
        <el-alert
          v-for="(w, i) in validation.warnings"
          :key="i"
          :title="w"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 4px"
        />
      </div>
    </el-card>

    <!-- ISA620 专家利用评估 -->
    <el-card class="isa620-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>ISA620 精算师工作利用评估</span>
          <el-progress :percentage="isa620Completeness.percent" :stroke-width="6" style="width: 120px" />
        </div>
      </template>
      <el-form label-width="130px" size="small">
        <el-form-item label="精算师姓名">
          <el-input v-model="accrualCheck.isa620.value.actuaryName" :disabled="isReadonly" placeholder="如：张精算" />
        </el-form-item>
        <el-form-item label="精算事务所">
          <el-input v-model="accrualCheck.isa620.value.actuaryFirm" :disabled="isReadonly" placeholder="如：XX精算顾问有限公司" />
        </el-form-item>
        <el-form-item label="资质">
          <el-input v-model="accrualCheck.isa620.value.actuaryQualification" :disabled="isReadonly" placeholder="如：中国精算师/FSA/FIA" />
        </el-form-item>
        <el-form-item label="资质已验证">
          <el-switch v-model="accrualCheck.isa620.value.qualificationVerified" :disabled="isReadonly" />
        </el-form-item>
        <el-divider content-position="left">独立性评价</el-divider>
        <el-form-item label="独立性结论">
          <el-radio-group v-model="accrualCheck.isa620.value.independenceConclusion" :disabled="isReadonly">
            <el-radio value="independent">独立</el-radio>
            <el-radio value="not_independent">不独立</el-radio>
            <el-radio value="pending">待评价</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-divider content-position="left">工作范围评价</el-divider>
        <el-form-item label="范围充分性">
          <el-radio-group v-model="accrualCheck.isa620.value.scopeAdequacy" :disabled="isReadonly">
            <el-radio value="adequate">充分</el-radio>
            <el-radio value="inadequate">不充分</el-radio>
            <el-radio value="pending">待评价</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-divider content-position="left">总体结论</el-divider>
        <el-form-item label="利用结论">
          <el-radio-group v-model="accrualCheck.isa620.value.overallConclusion" :disabled="isReadonly">
            <el-radio value="rely">可利用</el-radio>
            <el-radio value="partial_rely">部分利用</el-radio>
            <el-radio value="not_rely">不可利用</el-radio>
            <el-radio value="pending">待定</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="总体说明">
          <el-input
            v-model="accrualCheck.isa620.value.overallNote"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="isReadonly"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 计提结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header><span>计提充分性结论</span></template>
      <el-input
        v-model="accrualCheck.accrualConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="经检查，设定受益计划义务的精算假设合理，计提金额充分/不充分..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，设定受益义务须由精算师采用预期累计福利单位法计量。</p>
        <p>2. 折现率应参考资产负债表日高质量公司债券（或国债）市场收益率，与货币、期限匹配。</p>
        <p>3. 依据 ISA 620，须评价精算师的胜任能力与客观性、工作范围充分性，形成利用结论。</p>
        <p>4. 参数偏离上期或行业基准较大的须查明原因，评估计提是否充分。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useJ2AccrualCheck } from '@/composables/workpaper/j2/useJ2AccrualCheck'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const accrualCheck = useJ2AccrualCheck()
const validation = accrualCheck.validation
const isa620Completeness = accrualCheck.isa620Completeness

onMounted(() => {
  if (props.htmlData) {
    accrualCheck.loadFromHtmlData(props.htmlData)
  }
})
</script>

<style scoped>
.j2-tab-accrual-check { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-size: 15px; font-weight: 600; margin: 0; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.assumption-card, .isa620-card, .conclusion-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.unit-hint { font-size: 11px; color: #909399; margin-left: 8px; }
.warnings { margin-top: 12px; }
</style>
