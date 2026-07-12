<template>
  <div class="s21-amortization">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        检查数据资产摊销政策的适当性：摊销方法是否匹配经济利益实现方式、使用寿命与残值估计是否合理、摊销起始时点与会计处理是否正确，并核对年/月摊销额计算。
      </div>
    </el-alert>

    <!-- ─── 摊销政策检查 ─── -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>摊销政策检查表 S21-4</span>
        </div>
      </template>

      <el-table
        :data="checkItems"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="checkPoint" label="检查要点" min-width="280" />
        <el-table-column prop="actual" label="实际情况" min-width="250">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.actual"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写实际情况"
            />
            <span v-else>{{ row.actual || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="judgment" label="是否适当" width="120" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.judgment"
              size="small"
              placeholder="选择"
            >
              <el-option label="适当" value="适当" />
              <el-option label="不适当" value="不适当" />
              <el-option label="需进一步了解" value="需进一步了解" />
            </el-select>
            <el-tag
              v-else
              :type="row.judgment === '适当' ? 'success' : row.judgment === '不适当' ? 'danger' : 'warning'"
              size="small"
            >
              {{ row.judgment || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="备注说明"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ─── 摊销计算核对 ─── -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>摊销计算核对</span>
        </div>
      </template>

      <el-form
        :model="amortizationCalc"
        label-width="160px"
        size="small"
        :disabled="isReadonly"
        class="amortization-form"
      >
        <el-form-item label="数据资产原值(元)">
          <el-input-number
            v-model="amortizationCalc.originalCost"
            :controls="false"
            :precision="2"
            class="input-amount"
          />
        </el-form-item>
        <el-form-item label="预计残值(元)">
          <el-input-number
            v-model="amortizationCalc.residualValue"
            :controls="false"
            :precision="2"
            class="input-amount"
          />
        </el-form-item>
        <el-form-item label="摊销年限(年)">
          <el-input-number
            v-model="amortizationCalc.usefulYears"
            :controls="false"
            :precision="0"
            :min="1"
            class="input-amount"
          />
        </el-form-item>
        <el-form-item label="摊销方法">
          <el-select v-model="amortizationCalc.method" placeholder="选择">
            <el-option label="直线法" value="直线法" />
            <el-option label="产量法" value="产量法" />
            <el-option label="加速摊销" value="加速摊销" />
          </el-select>
        </el-form-item>
        <el-divider content-position="left">计算结果（公式单元格，不可手工覆盖）</el-divider>
        <el-form-item label="年摊销额(元)">
          <span class="formula-cell" title="年摊销额 = (原值 - 残值) ÷ 摊销年限">
            {{ fmtAmount(annualAmortization) }}
          </span>
        </el-form-item>
        <el-form-item label="月摊销额(元)">
          <span class="formula-cell" title="月摊销额 = 年摊销额 ÷ 12">
            {{ fmtAmount(monthlyAmortization) }}
          </span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ─── 审计结论 ─── -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写摊销政策检查的审计结论"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>① 检查摊销方法是否符合数据资产的经济利益预期实现方式。</p>
      <p>② 关注摊销年限是否合理（考虑技术更新速度、许可期限、合同约定等）。</p>
      <p>③ 残值估计是否恰当（数据资产通常无残值或残值极低）。</p>
      <p>④ 确认摊销起始时点（达到预定用途之日起）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS21Amortization.vue — 摊销政策检查表 S21-4
 *
 * 功能：
 * - 摊销政策各检查要点逐项核对
 * - 摊销计算核对（直线法公式自动计算年/月摊销额）
 * - 公式单元格只读不可手工覆盖
 * - 审计结论
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.2
 */
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { useSExpertPersist, parseResponseValue } from '../composables/useSExpertPersist'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  /** 主入口透传的持久化快照（已解包纯 Map） */
  allResponses?: Map<string, any>
}>()

// ─── 检查要点 ────────────────────────────────────────────────

interface CheckItem {
  checkPoint: string
  actual: string
  judgment: string
  remark: string
}

const checkItems = ref<CheckItem[]>([
  { checkPoint: '摊销方法是否与数据资产经济利益的预期实现方式相匹配', actual: '', judgment: '', remark: '' },
  { checkPoint: '预计使用寿命的确定是否合理（技术/合同/法律限制）', actual: '', judgment: '', remark: '' },
  { checkPoint: '残值估计是否恰当（通常为零或极低）', actual: '', judgment: '', remark: '' },
  { checkPoint: '摊销起始时点是否正确（达到预定用途之日）', actual: '', judgment: '', remark: '' },
  { checkPoint: '是否定期复核使用寿命和摊销方法（至少年末）', actual: '', judgment: '', remark: '' },
  { checkPoint: '使用寿命或摊销方法变更是否作为会计估计变更处理', actual: '', judgment: '', remark: '' },
  { checkPoint: '摊销金额的会计处理是否正确（管理费用/制造费用等）', actual: '', judgment: '', remark: '' },
])

// ─── 摊销计算核对 ────────────────────────────────────────────

const amortizationCalc = reactive({
  originalCost: 0,
  residualValue: 0,
  usefulYears: 10,
  method: '直线法',
})

/** 年摊销额 = (原值 - 残值) ÷ 摊销年限 */
const annualAmortization = computed(() => {
  const years = amortizationCalc.usefulYears
  if (!years || years <= 0) return 0
  return (amortizationCalc.originalCost - amortizationCalc.residualValue) / years
})

/** 月摊销额 = 年摊销额 ÷ 12 */
const monthlyAmortization = computed(() => {
  return annualAmortization.value / 12
})

// ─── 审计结论 ────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── 持久化接线（load seed + save；hydrating 防回写） ─────────────────────────

const CHECK_ID = 'S21-4-check'
const CALC_ID = 'S21-4-calc'
const CONCLUSION_ID = 'S21-4-conclusion'
const { save } = useSExpertPersist(() => props.allResponses)

let hydrating = false

onMounted(async () => {
  hydrating = true
  const items = parseResponseValue(props.allResponses, CHECK_ID)
  if (Array.isArray(items) && items.length) checkItems.value = items
  const calc = parseResponseValue(props.allResponses, CALC_ID)
  if (calc && typeof calc === 'object') Object.assign(amortizationCalc, calc)
  const conc = parseResponseValue(props.allResponses, CONCLUSION_ID)
  if (typeof conc === 'string') auditConclusion.value = conc
  await nextTick()
  hydrating = false
})

watch(checkItems, () => { if (!hydrating) save(CHECK_ID, checkItems.value) }, { deep: true })
watch(amortizationCalc, () => { if (!hydrating) save(CALC_ID, { ...amortizationCalc }) }, { deep: true })
watch(auditConclusion, () => { if (!hydrating) save(CONCLUSION_ID, auditConclusion.value) })
</script>

<style scoped>
.s21-amortization {
  padding: 12px;
}
.audit-objective {
  margin-bottom: 12px;
}
.audit-objective-text {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.audit-section {
  margin-bottom: 16px;
}
.amortization-form {
  max-width: 600px;
}
.input-amount {
  width: 200px;
}

/* 公式单元格样式 */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 600;
  color: #303133;
  padding: 2px 4px;
}

.audit-conclusion-card {
  margin-top: 16px;
}
.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-hints summary {
  cursor: pointer;
  user-select: none;
}
</style>
