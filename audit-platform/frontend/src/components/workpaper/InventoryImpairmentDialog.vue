<template>
  <el-dialog
    :model-value="visible"
    title="🤖 存货跌价准备 AI 分析（F-F12）"
    width="780px"
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
        基于成本与可变现净值孰低法，结合库龄分析，AI 给出每个产品的跌价计提建议。
        当前 LLM 接入为 stub 实现，分析结果作为辅助参考，最终金额需审计师确认。
        <strong>「采纳并写回」会把分析结果写入当前底稿 parsed_data，便于后续溯源。</strong>
      </template>
    </el-alert>

    <el-form :model="form" label-width="120px" size="small">
      <el-form-item label="计提方法">
        <el-radio-group v-model="form.method">
          <el-radio value="lower_of_cost_or_nrv">成本与 NRV 孰低</el-radio>
          <el-radio value="aging_based">库龄法</el-radio>
          <el-radio value="specific_id">个别认定</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="重要性水平">
        <el-input-number
          v-model="form.materiality_threshold"
          :min="0"
          :step="10000"
          controls-position="right"
          style="width: 200px"
        />
        <span style="margin-left: 8px; color: var(--el-text-color-secondary)">元</span>
      </el-form-item>
    </el-form>

    <el-divider>产品级输入</el-divider>

    <el-table :data="form.products" size="small" border style="margin-bottom: 12px">
      <el-table-column label="#" type="index" width="50" />
      <el-table-column label="产品名称" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.product_name" size="small" placeholder="请输入产品" />
        </template>
      </el-table-column>
      <el-table-column label="账面成本" width="140">
        <template #default="{ row }">
          <el-input-number v-model="row.cost" :min="0" :step="100" controls-position="right" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="可变现净值" width="140">
        <template #default="{ row }">
          <el-input-number v-model="row.nrv" :min="0" :step="100" controls-position="right" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="库龄(月)" width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.aging_months" :min="0" :max="120" controls-position="right" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="数量" width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.qty" :min="0" controls-position="right" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="" width="60">
        <template #default="{ $index }">
          <el-button size="small" link type="danger" @click="removeRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-button size="small" plain @click="addRow">+ 添加产品行</el-button>

    <el-divider v-if="result">分析结果</el-divider>

    <div v-if="result" class="impairment-result">
      <el-alert
        :title="result.summary"
        type="success"
        show-icon
        :closable="false"
        style="margin-bottom: 12px"
      />
      <el-table :data="result.suggestions" size="small" border>
        <el-table-column label="产品" prop="product_name" min-width="160" />
        <el-table-column label="账面成本" prop="book_cost" width="120" />
        <el-table-column label="可变现净值" prop="nrv" width="120" />
        <el-table-column label="建议计提" prop="suggested_provision" width="130" />
        <el-table-column label="风险" width="90">
          <template #default="{ row }">
            <el-tag
              :type="row.risk_level === 'high' ? 'danger' : row.risk_level === 'medium' ? 'warning' : 'success'"
              size="small"
            >
              {{ riskLabel(row.risk_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明" prop="rationale" min-width="280" show-overflow-tooltip />
      </el-table>
      <div class="total-line">
        建议合计计提：
        <span class="amt">¥ {{ formatAmount(result.total_suggested_provision) }}</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button type="primary" :loading="loading" :disabled="form.products.length === 0" @click="onAnalyze">
        🚀 AI 分析
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
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

interface Props {
  visible: boolean
  projectId: string
  wpId: string
  /** 当前活动 sheet 名（用于「采纳并写回」按钮，把结果落到该 sheet 的 parsed_data） */
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface ProductRow {
  product_name: string
  cost: number
  nrv: number
  aging_months: number
  qty: number
}

interface ImpairmentSuggestion {
  product_name: string
  book_cost: string
  nrv: string
  suggested_provision: string
  rationale: string
  risk_level: 'high' | 'medium' | 'low'
}

interface ImpairmentResponse {
  method: string
  total_products: number
  suggestions: ImpairmentSuggestion[]
  summary: string
  total_suggested_provision: string
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<ImpairmentResponse | null>(null)

const form = reactive({
  method: 'lower_of_cost_or_nrv',
  materiality_threshold: 50000,
  products: [
    { product_name: '', cost: 0, nrv: 0, aging_months: 0, qty: 0 },
  ] as ProductRow[],
})

function addRow() {
  form.products.push({ product_name: '', cost: 0, nrv: 0, aging_months: 0, qty: 0 })
}
function removeRow(idx: number) {
  if (form.products.length <= 1) {
    form.products.splice(idx, 1)
    addRow()
    return
  }
  form.products.splice(idx, 1)
}

function riskLabel(r: string) {
  return { high: '高', medium: '中', low: '低' }[r] || r
}

function formatAmount(s: string) {
  const n = Number(s)
  if (!Number.isFinite(n)) return s
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onAnalyze() {
  // 过滤空行
  const valid = form.products.filter((p) => p.product_name && (p.cost > 0 || p.nrv > 0))
  if (valid.length === 0) {
    ElMessage.warning('请至少填入一个产品的成本或可变现净值')
    return
  }
  loading.value = true
  try {
    const resp = await api.post<ImpairmentResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/f2/impairment-analysis`,
      {
        products: valid,
        method: form.method,
        materiality_threshold: form.materiality_threshold,
      },
    )
    result.value = resp
    if (resp?.is_llm_stub) {
      ElMessage.success('AI 分析完成（stub 模式）')
    } else {
      ElMessage.success('AI 分析完成')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'AI 分析失败')
  } finally {
    loading.value = false
  }
}

// 重置 result 在弹窗关闭时
watch(() => props.visible, (v) => {
  if (!v) result.value = null
})

async function onApplyToSheet() {
  // P0-3 写回联动：把已分析结果写回当前底稿 parsed_data.impairment_analyses[targetSheet]
  if (!props.targetSheet) {
    ElMessage.warning('未识别到当前 sheet，无法写回')
    return
  }
  const valid = form.products.filter((p) => p.product_name && (p.cost > 0 || p.nrv > 0))
  if (valid.length === 0) {
    ElMessage.warning('请先 AI 分析后再写回')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<ImpairmentResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/f2/impairment-analysis`,
      {
        products: valid,
        method: form.method,
        materiality_threshold: form.materiality_threshold,
        apply_to_sheet: props.targetSheet,
      },
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
</script>

<style scoped>
.impairment-result {
  margin-top: 8px;
}
.total-line {
  margin-top: 12px;
  text-align: right;
  font-size: 14px;
}
.total-line .amt {
  color: var(--el-color-warning);
  font-weight: 600;
  font-size: 16px;
  margin-left: 6px;
}
</style>
