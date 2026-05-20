<template>
  <el-dialog
    :model-value="visible"
    title="🧮 AI 辅助商誉减值分析（I-F4 DCF + Gordon Growth + CAS 8 分摊）"
    width="820px"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="emit('update:visible', $event)"
  >
    <el-alert
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #default>
        基于 DCF（折现现金流）+ Gordon growth 永续增长模型，测算 CGU 可收回金额；
        总账面（商誉 + 其他资产）大于可收回金额时计提减值，
        减值优先冲减商誉，剩余按比例分摊到 CGU 其他资产（CAS 8 / IFRS 36）。
        当前 LLM 接入为 stub 实现，DCF + 分摊公式正确。
        <strong>「采纳并写回」会把分析结果写入当前底稿 parsed_data，便于后续溯源。</strong>
      </template>
    </el-alert>

    <el-form :model="form" label-width="160px" size="small">
      <el-form-item label="资产组 ID（CGU）" required>
        <el-input
          v-model="form.cgu_id"
          placeholder="如 CGU-G-001"
          style="width: 220px"
        />
      </el-form-item>

      <el-form-item label="商誉账面价值" required>
        <el-input-number
          v-model="form.goodwill_book_value"
          :min="0.01"
          :max="999999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="CGU 其他资产账面价值">
        <el-input-number
          v-model="form.other_assets_book_value"
          :min="0"
          :max="999999999999"
          :step="10000"
          :precision="2"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（不含商誉）</span>
      </el-form-item>

      <el-form-item label="折现率 r" required>
        <el-input-number
          v-model="form.discount_rate"
          :min="0.001"
          :max="0.999"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
        <span class="gt-form-unit">（0~1，如 0.10 = 10%）</span>
      </el-form-item>

      <el-form-item label="终值永续增长率 g">
        <el-input-number
          v-model="form.terminal_growth_rate"
          :min="0"
          :max="0.999"
          :step="0.005"
          :precision="4"
          controls-position="right"
          style="width: 160px"
        />
        <span class="gt-form-unit">（0~r，0 = 不计终值）</span>
      </el-form-item>
    </el-form>

    <el-divider>5 年现金流预测</el-divider>

    <el-table :data="cashFlowRows" size="small" border style="margin-bottom: 12px">
      <el-table-column label="年份" width="80" align="center">
        <template #default="{ $index }">第 {{ $index + 1 }} 年</template>
      </el-table-column>
      <el-table-column label="预测现金流（元）" min-width="200">
        <template #default="{ $index }">
          <el-input-number
            v-model="form.cash_flows[$index]"
            :min="0"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 200px"
          />
        </template>
      </el-table-column>
      <el-table-column label="" width="60">
        <template #default="{ $index }">
          <el-button
            v-if="form.cash_flows.length > 1"
            size="small"
            link
            type="danger"
            @click="removeCashFlowYear($index)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-button v-if="form.cash_flows.length < 10" size="small" plain @click="addCashFlowYear">
      + 添加年份
    </el-button>

    <el-divider>CGU 内资产清单（CAS 8 / IFRS 36 完整版分摊，可选）</el-divider>

    <el-alert
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 8px"
    >
      <template #default>
        填写 CGU 内可分摊资产清单后，剩余减值（商誉冲完后）将按账面价值比例分摊到各资产，
        并满足"每项 post-impairment ≥ max(资产可收回金额, 0)"下限保护；
        留空则只返回汇总冲减额（向后兼容）。
      </template>
    </el-alert>

    <el-table :data="form.cgu_assets" size="small" border style="margin-bottom: 8px">
      <el-table-column label="#" width="50" align="center" type="index" />
      <el-table-column label="资产名称" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.name" placeholder="如 专利权 A" />
        </template>
      </el-table-column>
      <el-table-column label="账面价值（元）" min-width="180">
        <template #default="{ row }">
          <el-input-number
            v-model="row.book_value"
            :min="0"
            :step="10000"
            :precision="2"
            controls-position="right"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column label="可收回金额（元，可选）" min-width="200">
        <template #default="{ row }">
          <el-input-number
            v-model="row.recoverable_amount"
            :min="0"
            :step="10000"
            :precision="2"
            controls-position="right"
            placeholder="留空 = 无下限"
            style="width: 100%"
          />
        </template>
      </el-table-column>
      <el-table-column label="" width="70">
        <template #default="{ $index }">
          <el-button size="small" link type="danger" @click="removeAsset($index)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-button size="small" plain @click="addAsset">
      + 添加资产
    </el-button>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>分析结果</el-divider>
      <div class="impairment-result">
        <el-alert
          :title="result.summary"
          :type="result.is_impaired ? 'warning' : 'success'"
          show-icon
          :closable="false"
          style="margin-bottom: 12px"
        />

        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="资产组">{{ result.cgu_id }}</el-descriptions-item>
          <el-descriptions-item label="商誉账面价值">¥ {{ formatAmount(result.goodwill_book_value) }}</el-descriptions-item>
          <el-descriptions-item label="其他资产账面价值">¥ {{ formatAmount(result.other_assets_book_value) }}</el-descriptions-item>
          <el-descriptions-item label="总账面价值">¥ {{ formatAmount(result.total_book_value) }}</el-descriptions-item>
          <el-descriptions-item label="未来现金流现值">¥ {{ formatAmount(result.present_value_of_cash_flows) }}</el-descriptions-item>
          <el-descriptions-item label="可收回金额">
            <span class="amt-highlight">¥ {{ formatAmount(result.recoverable_amount) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="减值损失（合计）">
            <span :class="result.is_impaired ? 'amt-danger' : 'amt-safe'">
              ¥ {{ formatAmount(result.impairment_loss) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="商誉冲减">
            <span :class="Number(result.goodwill_writedown) > 0 ? 'amt-danger' : 'amt-safe'">
              ¥ {{ formatAmount(result.goodwill_writedown) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="其他资产冲减" :span="2">
            <span :class="Number(result.other_assets_writedown) > 0 ? 'amt-danger' : 'amt-safe'">
              ¥ {{ formatAmount(result.other_assets_writedown) }}
            </span>
            <span class="gt-form-unit" style="margin-left: 8px">
              （前端可按各资产账面比例细化拆分）
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <el-table
          :data="result.dcf_details"
          size="small"
          border
          style="margin-top: 12px"
        >
          <el-table-column label="年份" prop="year" width="200" align="center" />
          <el-table-column label="现金流" width="160" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.cash_flow) }}</template>
          </el-table-column>
          <el-table-column label="折现因子" prop="discount_factor" width="120" align="right" />
          <el-table-column label="现值" width="160" align="right">
            <template #default="{ row }">¥ {{ formatAmount(row.present_value) }}</template>
          </el-table-column>
        </el-table>

        <template v-if="result.asset_allocations && result.asset_allocations.length">
          <el-divider>CGU 内资产分摊明细（CAS 8 / IFRS 36 完整版）</el-divider>
          <el-table
            :data="result.asset_allocations"
            size="small"
            border
            style="margin-top: 8px"
          >
            <el-table-column label="资产名称" prop="name" min-width="160" />
            <el-table-column label="账面价值" min-width="140" align="right">
              <template #default="{ row }">¥ {{ formatAmount(row.book_value) }}</template>
            </el-table-column>
            <el-table-column label="可收回金额" min-width="140" align="right">
              <template #default="{ row }">
                <span v-if="row.recoverable_amount !== null">¥ {{ formatAmount(row.recoverable_amount) }}</span>
                <span v-else style="color: var(--el-text-color-secondary)">—</span>
              </template>
            </el-table-column>
            <el-table-column label="分摊减值" min-width="140" align="right">
              <template #default="{ row }">
                <span :class="Number(row.allocated_impairment) > 0 ? 'amt-danger' : 'amt-safe'">
                  ¥ {{ formatAmount(row.allocated_impairment) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="分摊后账面" min-width="140" align="right">
              <template #default="{ row }">
                <span class="amt-highlight">¥ {{ formatAmount(row.post_impairment_book_value) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!isFormValid"
        @click="onAnalyze"
      >
        🚀 计算分析
      </el-button>
      <el-button
        v-if="result"
        type="success"
        :loading="applying"
        :disabled="!targetSheet"
        @click="onApplyToSheet"
      >
        ✅ 采纳并写回
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  /** 当前活动 sheet 名（用于「采纳并写回」按钮） */
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface DcfDetail {
  year: string | number
  cash_flow: string
  discount_factor: string
  present_value: string
}

interface AssetAllocation {
  name: string
  book_value: string
  recoverable_amount: string | null
  allocated_impairment: string
  post_impairment_book_value: string
}

interface CguAssetRow {
  name: string
  book_value: number
  recoverable_amount: number | null
}

interface GoodwillImpairmentResponse {
  cgu_id: string
  goodwill_book_value: string
  other_assets_book_value: string
  total_book_value: string
  present_value_of_cash_flows: string
  recoverable_amount: string
  impairment_loss: string
  goodwill_writedown: string
  other_assets_writedown: string
  is_impaired: boolean
  dcf_details: DcfDetail[]
  asset_allocations: AssetAllocation[]
  summary: string
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<GoodwillImpairmentResponse | null>(null)

const form = reactive({
  cgu_id: 'CGU-G-001',
  goodwill_book_value: 1000000,
  other_assets_book_value: 3000000,
  discount_rate: 0.10,
  terminal_growth_rate: 0.03,
  cash_flows: [500000, 520000, 540000, 560000, 580000] as number[],
  cgu_assets: [] as CguAssetRow[],
})

const cashFlowRows = computed(() => form.cash_flows.map((_, i) => ({ index: i })))

function addCashFlowYear() {
  if (form.cash_flows.length < 10) {
    const last = form.cash_flows[form.cash_flows.length - 1] || 0
    form.cash_flows.push(last)
  }
}

function removeCashFlowYear(idx: number) {
  if (form.cash_flows.length > 1) {
    form.cash_flows.splice(idx, 1)
  }
}

function addAsset() {
  form.cgu_assets.push({
    name: '',
    book_value: 0,
    recoverable_amount: null,
  })
}

function removeAsset(idx: number) {
  form.cgu_assets.splice(idx, 1)
}

const isFormValid = computed(() => {
  if (!form.cgu_id) return false
  if (form.goodwill_book_value <= 0) return false
  if (form.other_assets_book_value < 0) return false
  if (form.discount_rate <= 0 || form.discount_rate >= 1) return false
  // r > g 是 Gordon growth 收敛条件
  if (form.terminal_growth_rate >= form.discount_rate) return false
  if (form.cash_flows.length === 0) return false
  return form.cash_flows.some((cf) => cf > 0)
})

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function buildRequestBody(applySheet?: string) {
  const body: Record<string, any> = {
    cgu_id: form.cgu_id,
    goodwill_book_value: form.goodwill_book_value,
    other_assets_book_value: form.other_assets_book_value,
    cash_flows: form.cash_flows.filter((cf) => cf >= 0),
    discount_rate: form.discount_rate,
    terminal_growth_rate: form.terminal_growth_rate,
  }
  // 仅在用户填写了至少 1 项资产时附带 cgu_assets（向后兼容）
  const validAssets = form.cgu_assets
    .filter((a) => a.name && a.book_value >= 0)
    .map((a) => ({
      name: a.name,
      book_value: a.book_value,
      recoverable_amount: a.recoverable_amount ?? null,
    }))
  if (validAssets.length > 0) {
    body.cgu_assets = validAssets
  }
  if (applySheet) {
    body.apply_to_sheet = applySheet
  }
  return body
}

async function onAnalyze() {
  loading.value = true
  try {
    const resp = await api.post<GoodwillImpairmentResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/i3/goodwill-impairment`,
      buildRequestBody(),
    )
    result.value = resp
    if (resp?.is_impaired) {
      ElMessage.warning(`分析完成：需计提减值 ¥${formatAmount(resp.impairment_loss)}`)
    } else {
      ElMessage.success('分析完成：无需计提减值')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '商誉减值分析失败')
  } finally {
    loading.value = false
  }
}

async function onApplyToSheet() {
  if (!props.targetSheet) {
    ElMessage.warning('未识别到当前 sheet，无法写回')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<GoodwillImpairmentResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/i3/goodwill-impairment`,
      buildRequestBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已采纳并写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('分析完成但未写回（applied_to_sheet 为空）')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '采纳写回失败')
  } finally {
    applying.value = false
  }
}

// 重置 result 在弹窗关闭时
watch(() => props.visible, (v) => {
  if (!v) result.value = null
})
</script>

<style scoped>
.gt-form-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.impairment-result {
  margin-top: 8px;
}
.amt-highlight {
  color: var(--el-color-primary);
  font-weight: 600;
}
.amt-danger {
  color: var(--el-color-danger);
  font-weight: 600;
}
.amt-safe {
  color: var(--el-color-success);
  font-weight: 600;
}
</style>
