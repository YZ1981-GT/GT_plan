<template>
  <el-dialog
    :model-value="visible"
    title="🧮 所得税费用测算（N-F7）"
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
        输入利润总额、法定税率、永久性差异、暂时性差异及递延所得税变动，
        自动计算当期/递延/总所得税费用及有效税率。计算结果可「采纳并写回」当前底稿。
      </template>
    </el-alert>

    <!-- is_llm_stub 指示器 -->
    <el-tag v-if="isLlmStub !== null" :type="isLlmStub ? 'warning' : 'success'" size="small" style="margin-bottom: 12px">
      {{ isLlmStub ? '⚠️ Stub 模式（待 AI 服务接入）' : '✅ AI 服务已启用' }}
    </el-tag>

    <el-form :model="form" label-width="160px" size="small">
      <el-form-item label="利润总额" required>
        <el-input-number
          v-model="form.profit_before_tax"
          :precision="2"
          :step="10000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元</span>
      </el-form-item>

      <el-form-item label="法定税率" required>
        <el-input-number
          v-model="form.statutory_rate"
          :min="0"
          :max="1"
          :step="0.01"
          :precision="4"
          controls-position="right"
          style="width: 200px"
        />
        <span class="gt-form-unit">（如 0.25 = 25%）</span>
      </el-form-item>

      <el-divider content-position="left">永久性差异</el-divider>
      <div v-for="(item, idx) in form.permanent_differences" :key="'perm-' + idx" class="gt-kv-row">
        <el-input v-model="item.key" placeholder="项目名称" style="width: 180px" />
        <el-input-number
          v-model="item.value"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 180px; margin-left: 8px"
        />
        <el-button type="danger" text size="small" style="margin-left: 4px" @click="removePermanent(idx)">✕</el-button>
      </div>
      <el-button type="primary" text size="small" @click="addPermanent">+ 添加永久性差异</el-button>

      <el-divider content-position="left">暂时性差异</el-divider>
      <div v-for="(item, idx) in form.temporary_differences" :key="'temp-' + idx" class="gt-kv-row">
        <el-input v-model="item.key" placeholder="项目名称" style="width: 180px" />
        <el-input-number
          v-model="item.value"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 180px; margin-left: 8px"
        />
        <el-button type="danger" text size="small" style="margin-left: 4px" @click="removeTemporary(idx)">✕</el-button>
      </div>
      <el-button type="primary" text size="small" @click="addTemporary">+ 添加暂时性差异</el-button>

      <el-divider content-position="left">递延所得税变动</el-divider>

      <el-form-item label="递延所得税资产变动">
        <el-input-number
          v-model="form.deferred_tax_asset_change"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（正=增加）</span>
      </el-form-item>

      <el-form-item label="递延所得税负债变动">
        <el-input-number
          v-model="form.deferred_tax_liability_change"
          :precision="2"
          :step="1000"
          controls-position="right"
          style="width: 220px"
        />
        <span class="gt-form-unit">元（正=增加）</span>
      </el-form-item>

      <el-form-item label="写回目标 Sheet">
        <el-input v-model="form.apply_to_sheet" placeholder="Sheet 名称" style="width: 260px" />
      </el-form-item>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider content-position="left">计算结果</el-divider>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="当期所得税">
          <span class="gt-amt">¥ {{ formatAmount(result.current_income_tax) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="递延所得税">
          <span class="gt-amt">¥ {{ formatAmount(result.deferred_income_tax) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="所得税费用合计">
          <span class="gt-amt">¥ {{ formatAmount(result.total_income_tax) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="有效税率">
          <span class="gt-amt">{{ formatRate(result.effective_rate) }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <template v-if="result.reconciliation_items && result.reconciliation_items.length > 0">
        <el-divider content-position="left">税率调节表</el-divider>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item
            v-for="(item, idx) in result.reconciliation_items"
            :key="'recon-' + idx"
            :label="item.label"
          >
            <span class="gt-amt">¥ {{ formatAmount(item.amount) }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="onCalc"
      >
        🚀 计算
      </el-button>
      <el-button
        v-if="result"
        type="success"
        :loading="applying"
        :disabled="!form.apply_to_sheet"
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
  targetSheet?: string
}
const props = withDefaults(defineProps<Props>(), {
  targetSheet: '',
})
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface ReconciliationItem {
  label: string
  amount: string
}

interface IncomeTaxCalcResult {
  current_income_tax: string
  deferred_income_tax: string
  total_income_tax: string
  effective_rate: string
  reconciliation_items: ReconciliationItem[]
  is_llm_stub: boolean
  applied_to_sheet?: string | null
  applied_at?: string | null
}

interface KVPair {
  key: string
  value: number
}

const loading = ref(false)
const applying = ref(false)
const result = ref<IncomeTaxCalcResult | null>(null)
const isLlmStub = ref<boolean | null>(null)

const form = reactive({
  profit_before_tax: 0,
  statutory_rate: 0.25,
  permanent_differences: [] as KVPair[],
  temporary_differences: [] as KVPair[],
  deferred_tax_asset_change: 0,
  deferred_tax_liability_change: 0,
  apply_to_sheet: '',
})

// Initialize apply_to_sheet from targetSheet prop
watch(() => props.targetSheet, (v) => {
  if (v) form.apply_to_sheet = v
}, { immediate: true })

function addPermanent() {
  form.permanent_differences.push({ key: '', value: 0 })
}
function removePermanent(idx: number) {
  form.permanent_differences.splice(idx, 1)
}
function addTemporary() {
  form.temporary_differences.push({ key: '', value: 0 })
}
function removeTemporary(idx: number) {
  form.temporary_differences.splice(idx, 1)
}

function formatAmount(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatRate(s: string | number) {
  const n = Number(s)
  if (!Number.isFinite(n)) return String(s)
  return (n * 100).toFixed(2) + '%'
}

function buildDifferencesMap(pairs: KVPair[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const p of pairs) {
    if (p.key.trim()) map[p.key.trim()] = p.value
  }
  return map
}

function buildRequestBody(applySheet?: string) {
  return {
    profit_before_tax: form.profit_before_tax,
    statutory_rate: form.statutory_rate,
    permanent_differences: buildDifferencesMap(form.permanent_differences),
    temporary_differences: buildDifferencesMap(form.temporary_differences),
    deferred_tax_asset_change: form.deferred_tax_asset_change,
    deferred_tax_liability_change: form.deferred_tax_liability_change,
    apply_to_sheet: applySheet || null,
  }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<IncomeTaxCalcResult>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/n5/income-tax-calc`,
      buildRequestBody(),
    )
    result.value = resp
    isLlmStub.value = resp.is_llm_stub
    ElMessage.success('所得税费用测算完成')
  } catch (e: any) {
    ElMessage.error(e?.message || '所得税费用测算失败')
  } finally {
    loading.value = false
  }
}

async function onApplyToSheet() {
  if (!form.apply_to_sheet) {
    ElMessage.warning('未填写目标 sheet，无法写回')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<IncomeTaxCalcResult>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/n5/income-tax-calc`,
      buildRequestBody(form.apply_to_sheet),
    )
    result.value = resp
    isLlmStub.value = resp.is_llm_stub
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已采纳并写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('计算完成但未写回（applied_to_sheet 为空）')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '采纳写回失败')
  } finally {
    applying.value = false
  }
}

watch(() => props.visible, (v) => {
  if (!v) {
    result.value = null
    isLlmStub.value = null
  }
})
</script>

<style scoped>
.gt-form-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.gt-kv-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
