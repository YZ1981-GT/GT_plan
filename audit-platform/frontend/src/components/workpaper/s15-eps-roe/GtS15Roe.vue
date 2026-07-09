<template>
  <div class="s15-roe">
    <!-- 本年/上年对比标题 -->
    <div class="period-comparison-header">
      <el-tag type="primary" size="small">本年</el-tag>
      <el-tag type="info" size="small">上年</el-tag>
      <span class="comparison-hint">S15-4 净资产收益率计算 — 本年/上年对比展示</span>
      <span class="data-source-hint">取数来源：</span>
      <GtIndexChip value="审定报表" />
    </div>

    <div class="dual-period-container">
      <!-- ─── 本年 ─── -->
      <el-card shadow="never" class="period-card">
        <template #header>
          <span>本年（当期）</span>
        </template>

        <el-form
          :model="currentYear"
          label-width="220px"
          size="small"
          :disabled="isReadonly"
          class="roe-form"
        >
          <el-form-item label="归母净利润 P (NP)">
            <el-input-number v-model="currentYear.np" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="扣非归母净利润 P_ex">
            <el-input-number v-model="currentYear.npEx" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="期初净资产 E0">
            <el-input-number v-model="currentYear.e0" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="期末净资产 E_end">
            <el-input-number v-model="currentYear.eEnd" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="少数股东权益">
            <el-input-number v-model="currentYear.minorityEquity" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-divider content-position="left">净资产变动项</el-divider>
          <el-form-item label="新增净资产 Ei">
            <el-input-number v-model="currentYear.ei" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="新增起至期末月份 Mi">
            <el-input-number v-model="currentYear.mi" :controls="false" :min="0" :max="12" class="input-amount" />
          </el-form-item>
          <el-form-item label="减少净资产 Ej">
            <el-input-number v-model="currentYear.ej" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="减少起至期末月份 Mj">
            <el-input-number v-model="currentYear.mj" :controls="false" :min="0" :max="12" class="input-amount" />
          </el-form-item>
          <el-form-item label="其他增减 Ek">
            <el-input-number v-model="currentYear.ek" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="其他增减起至期末月份 Mk">
            <el-input-number v-model="currentYear.mk" :controls="false" :min="0" :max="12" class="input-amount" />
          </el-form-item>
          <el-form-item label="报告期月份数 M0">
            <el-input-number v-model="currentYear.m0" :controls="false" :min="1" :max="12" class="input-amount" />
          </el-form-item>

          <el-divider content-position="left">计算结果（公式单元格，不可手工覆盖）</el-divider>
          <!-- 归母净利润 ROE -->
          <el-form-item label="全面摊薄ROE (归母)">
            <span
              class="formula-cell"
              :class="{ unable: currentYearRoe.unable }"
              title="全面摊薄 ROE = P / E（期末净资产-少数股东权益）"
            >
              {{ currentYearRoe.unable ? '不可计算' : fmtPercent(currentYearRoe.fullyDiluted) }}
            </span>
          </el-form-item>
          <el-form-item label="加权平均ROE (归母)">
            <span
              class="formula-cell"
              :class="{ unable: currentYearRoe.unable }"
              title="加权平均 ROE = P / (E0 + NP/2 + Ei×Mi/M0 - Ej×Mj/M0 + Ek×Mk/M0)"
            >
              {{ currentYearRoe.unable ? '不可计算' : fmtPercent(currentYearRoe.weightedAvg) }}
            </span>
          </el-form-item>
          <!-- 扣非净利润 ROE -->
          <el-form-item label="全面摊薄ROE (扣非)">
            <span
              class="formula-cell"
              :class="{ unable: currentYearRoeEx.unable }"
              title="全面摊薄 ROE(扣非) = P_ex / E"
            >
              {{ currentYearRoeEx.unable ? '不可计算' : fmtPercent(currentYearRoeEx.fullyDilutedEx) }}
            </span>
          </el-form-item>
          <el-form-item label="加权平均ROE (扣非)">
            <span
              class="formula-cell"
              :class="{ unable: currentYearRoeEx.unable }"
              title="加权平均 ROE(扣非) = P_ex / 加权平均净资产"
            >
              {{ currentYearRoeEx.unable ? '不可计算' : fmtPercent(currentYearRoeEx.weightedAvgEx) }}
            </span>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- ─── 上年 ─── -->
      <el-card shadow="never" class="period-card">
        <template #header>
          <span>上年（比较期）</span>
        </template>

        <el-form
          :model="priorYear"
          label-width="220px"
          size="small"
          :disabled="isReadonly"
          class="roe-form"
        >
          <el-form-item label="归母净利润 P (NP)">
            <el-input-number v-model="priorYear.np" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="扣非归母净利润 P_ex">
            <el-input-number v-model="priorYear.npEx" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="期初净资产 E0">
            <el-input-number v-model="priorYear.e0" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="期末净资产 E_end">
            <el-input-number v-model="priorYear.eEnd" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="少数股东权益">
            <el-input-number v-model="priorYear.minorityEquity" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-divider content-position="left">净资产变动项</el-divider>
          <el-form-item label="新增净资产 Ei">
            <el-input-number v-model="priorYear.ei" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="新增起至期末月份 Mi">
            <el-input-number v-model="priorYear.mi" :controls="false" :min="0" :max="12" class="input-amount" />
          </el-form-item>
          <el-form-item label="减少净资产 Ej">
            <el-input-number v-model="priorYear.ej" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="减少起至期末月份 Mj">
            <el-input-number v-model="priorYear.mj" :controls="false" :min="0" :max="12" class="input-amount" />
          </el-form-item>
          <el-form-item label="其他增减 Ek">
            <el-input-number v-model="priorYear.ek" :controls="false" :precision="2" class="input-amount" />
          </el-form-item>
          <el-form-item label="其他增减起至期末月份 Mk">
            <el-input-number v-model="priorYear.mk" :controls="false" :min="0" :max="12" class="input-amount" />
          </el-form-item>
          <el-form-item label="报告期月份数 M0">
            <el-input-number v-model="priorYear.m0" :controls="false" :min="1" :max="12" class="input-amount" />
          </el-form-item>

          <el-divider content-position="left">计算结果（公式单元格，不可手工覆盖）</el-divider>
          <el-form-item label="全面摊薄ROE (归母)">
            <span
              class="formula-cell"
              :class="{ unable: priorYearRoe.unable }"
              title="全面摊薄 ROE = P / E"
            >
              {{ priorYearRoe.unable ? '不可计算' : fmtPercent(priorYearRoe.fullyDiluted) }}
            </span>
          </el-form-item>
          <el-form-item label="加权平均ROE (归母)">
            <span
              class="formula-cell"
              :class="{ unable: priorYearRoe.unable }"
              title="加权平均 ROE = P / (E0 + NP/2 + ...)"
            >
              {{ priorYearRoe.unable ? '不可计算' : fmtPercent(priorYearRoe.weightedAvg) }}
            </span>
          </el-form-item>
          <el-form-item label="全面摊薄ROE (扣非)">
            <span
              class="formula-cell"
              :class="{ unable: priorYearRoeEx.unable }"
              title="全面摊薄 ROE(扣非) = P_ex / E"
            >
              {{ priorYearRoeEx.unable ? '不可计算' : fmtPercent(priorYearRoeEx.fullyDilutedEx) }}
            </span>
          </el-form-item>
          <el-form-item label="加权平均ROE (扣非)">
            <span
              class="formula-cell"
              :class="{ unable: priorYearRoeEx.unable }"
              title="加权平均 ROE(扣非) = P_ex / 加权平均净资产"
            >
              {{ priorYearRoeEx.unable ? '不可计算' : fmtPercent(priorYearRoeEx.weightedAvgEx) }}
            </span>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-conclusion" style="margin-top: 16px">
      <template #header>
        <span>审计结论</span>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="请填写净资产收益率审计结论..."
      />
    </el-card>

    <!-- 披露文本区（Req 8.1: 每股收益披露 + AI辅助） -->
    <el-card shadow="never" class="disclosure-card" style="margin-top: 16px">
      <template #header>
        <div class="disclosure-header">
          <span style="font-weight: 600">每股收益与净资产收益率披露</span>
          <el-button
            v-if="!isReadonly"
            size="small"
            :loading="sDisclosure?.aiLoading?.value"
            @click="handleAiDisclosure"
          >AI辅助生成</el-button>
        </div>
      </template>
      <el-input
        v-model="disclosureNoteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="每股收益与净资产收益率披露内容...（可使用AI辅助生成）"
        @input="handleDisclosureInput"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>全面摊薄 ROE = 归母净利润 ÷ 归属公司普通股股东期末净资产 (E = E_end - 少数股东权益)。</p>
      <p>加权平均 ROE = P ÷ (E0 + NP÷2 + Ei×Mi÷M0 - Ej×Mj÷M0 + Ek×Mk÷M0)。</p>
      <p>当期末净资产为零或缺失时，显示"不可计算"（Req 3.5）。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS15Roe.vue — S15-4 净资产收益率计算
 *
 * 功能：
 * - 本年/上年双期对比展示（Req 3.4）
 * - 使用 calcDilutedRoe + calcDilutedRoeEx 纯函数
 * - 全面摊薄 ROE + 加权平均 ROE（归母、扣非共 4 项）
 * - eEnd=0（期末净资产为零/缺失）显示"不可计算"（Req 3.5）
 * - 公式单元格只读不可手工覆盖（Req 2.5）
 *
 * Requirements: 2.5, 3.1, 3.2, 3.4, 3.5
 */
import { reactive, computed, ref, inject, defineAsyncComponent } from 'vue'
import { calcDilutedRoe, calcDilutedRoeEx, type RoeInput } from '../composables/useS15FormulaEngine'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 披露联动（inject from parent GtS15EpsRoe） ──────────────────────────────

const sDisclosure = inject<{
  disclosureText: { value: string }
  aiLoading: { value: boolean }
  onDisclosureTextChange: (text: string, section?: string) => void
  generateDisclosureWithAi: (section?: string, context?: Record<string, unknown>) => Promise<string | null>
} | null>('sEstimateDisclosure', null)

const disclosureNoteText = ref('')

function handleDisclosureInput(val: string | Event) {
  const text = typeof val === 'string' ? val : (val?.target as HTMLTextAreaElement)?.value || ''
  disclosureNoteText.value = text
  sDisclosure?.onDisclosureTextChange(text, 'S15-4-roe-disclosure')
}

async function handleAiDisclosure() {
  const result = await sDisclosure?.generateDisclosureWithAi('S15-4-roe-disclosure', {
    currentYearRoe: currentYearRoe.value,
    currentYearRoeEx: currentYearRoeEx.value,
    priorYearRoe: priorYearRoe.value,
    priorYearRoeEx: priorYearRoeEx.value,
  })
  if (result) {
    disclosureNoteText.value = result
  }
}
// ─── 本年输入 ────────────────────────────────────────────────

const currentYear = reactive<RoeInput>({
  np: 0,
  npEx: 0,
  e0: 0,
  eEnd: 0,
  minorityEquity: 0,
  ei: 0,
  mi: 0,
  ej: 0,
  mj: 0,
  ek: 0,
  mk: 0,
  m0: 12,
})

// ─── 上年输入 ────────────────────────────────────────────────

const priorYear = reactive<RoeInput>({
  np: 0,
  npEx: 0,
  e0: 0,
  eEnd: 0,
  minorityEquity: 0,
  ei: 0,
  mi: 0,
  ej: 0,
  mj: 0,
  ek: 0,
  mk: 0,
  m0: 12,
})

// ─── 实时计算（公式单元格不可覆盖） ─────────────────────────

const currentYearRoe = computed(() => calcDilutedRoe(currentYear))
const currentYearRoeEx = computed(() => calcDilutedRoeEx(currentYear))
const priorYearRoe = computed(() => calcDilutedRoe(priorYear))
const priorYearRoeEx = computed(() => calcDilutedRoeEx(priorYear))

// ─── 审计结论 ────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── 格式化 ──────────────────────────────────────────────────

function fmtPercent(val: number): string {
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.s15-roe {
  padding: 12px;
}
.period-comparison-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.comparison-hint {
  font-size: 13px;
  color: #606266;
}
.data-source-hint {
  font-size: 12px;
  color: #909399;
  margin-left: auto;
  white-space: nowrap;
}
.dual-period-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.period-card {
  font-size: 13px;
}
.input-amount {
  width: 180px;
}
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 600;
  color: #303133;
  padding: 2px 4px;
}
.formula-cell.unable {
  color: #f56c6c;
  font-style: italic;
}
.roe-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
.audit-conclusion :deep(.el-textarea__inner) {
  font-size: 13px;
}
.disclosure-card :deep(.el-textarea__inner) {
  font-size: 13px;
}
.disclosure-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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
