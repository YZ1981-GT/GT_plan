<script setup lang="ts">
/**
 * GtDiscontinuedOperations — 终止经营利润计算组件 (A5-4)
 *
 * 公式链：C=A-B, E=C-D, I=G-H, J=E+F+I
 * 持续经营净利润 + 终止经营净利润 = 净利润合计
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

const props = defineProps<{ wpId: string; projectId?: string; htmlData?: any; readonly?: boolean }>()
const emit = defineEmits<{ (e: 'save'): void }>()

const inputs = ref({
  A: 0, // 持续经营收入
  B: 0, // 持续经营费用
  D: 0, // 持续经营所得税
  F: 0, // 其他综合收益
  G: 0, // 终止经营收益
  H: 0, // 终止经营损失
})

const C = computed(() => inputs.value.A - inputs.value.B)
const E = computed(() => C.value - inputs.value.D)
const I_val = computed(() => inputs.value.G - inputs.value.H)
const J = computed(() => E.value + inputs.value.F + I_val.value)

const formulaRows = computed(() => [
  { code: 'A', label: '持续经营收入', value: inputs.value.A, editable: true, formula: '' },
  { code: 'B', label: '持续经营费用', value: inputs.value.B, editable: true, formula: '' },
  { code: 'C', label: '持续经营税前利润', value: C.value, editable: false, formula: 'C = A - B' },
  { code: 'D', label: '持续经营所得税', value: inputs.value.D, editable: true, formula: '' },
  { code: 'E', label: '持续经营净利润', value: E.value, editable: false, formula: 'E = C - D' },
  { code: 'F', label: '其他综合收益', value: inputs.value.F, editable: true, formula: '' },
  { code: 'G', label: '终止经营收益', value: inputs.value.G, editable: true, formula: '' },
  { code: 'H', label: '终止经营损失', value: inputs.value.H, editable: true, formula: '' },
  { code: 'I', label: '终止经营净利润', value: I_val.value, editable: false, formula: 'I = G - H' },
  { code: 'J', label: '净利润合计', value: J.value, editable: false, formula: 'J = E + F + I' },
])

function onInput(code: string, val: number) {
  if (code in inputs.value) {
    (inputs.value as any)[code] = val || 0
    scheduleSave()
  }
}

// ─── 保存 ───
const saving = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null
function scheduleSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(doSave, 2000)
}
async function doSave() {
  if (saving.value) return
  saving.value = true
  try {
    await api.put(`/api/workpapers/${props.wpId}/parsed-data`, {
      discontinued_operations: {
        inputs: inputs.value,
        results: { C: C.value, E: E.value, I: I_val.value, J: J.value },
      },
    })
    emit('save')
  } catch { ElMessage.error('保存失败') }
  finally { saving.value = false }
}

async function loadData() {
  if (!props.wpId) return
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/render-config`)
    const parsed = data?.sheets?.[0]?.html_data?.discontinued_operations || data?.fill_results?.discontinued_operations
    if (parsed?.inputs) Object.assign(inputs.value, parsed.inputs)
  } catch { /* 降级 */ }
}

onMounted(loadData)
onBeforeUnmount(() => { if (saveTimer) { clearTimeout(saveTimer); doSave() } })
</script>

<template>
  <div class="gt-discontinued-ops">
    <h4>持续经营利润和终止经营净利润计算表</h4>
    <el-table :data="formulaRows" border size="small" class="gt-compact-table">
      <el-table-column label="代号" width="60" align="center">
        <template #default="{ row }">
          <strong class="gt-do-code">{{ row.code }}</strong>
        </template>
      </el-table-column>
      <el-table-column label="项目" prop="label" width="180" />
      <el-table-column label="金额（万元）" min-width="180">
        <template #default="{ row }">
          <el-input-number
            v-if="row.editable"
            :model-value="row.value"
            @update:model-value="(v: number) => onInput(row.code, v)"
            :disabled="readonly"
            size="small"
            :controls="false"
            style="width: 100%"
          />
          <strong v-else class="gt-do-computed">{{ row.value.toLocaleString() }}</strong>
        </template>
      </el-table-column>
      <el-table-column label="公式" width="120">
        <template #default="{ row }">
          <code v-if="row.formula" class="gt-do-formula">{{ row.formula }}</code>
        </template>
      </el-table-column>
    </el-table>

    <!-- 结论摘要 -->
    <div class="gt-do-summary">
      <div class="gt-do-summary-row">
        <span>持续经营净利润</span>
        <strong :class="{ 'gt-do-negative': E < 0 }">{{ E.toLocaleString() }} 万元</strong>
      </div>
      <div class="gt-do-summary-row">
        <span>终止经营净利润</span>
        <strong :class="{ 'gt-do-negative': I_val < 0 }">{{ I_val.toLocaleString() }} 万元</strong>
      </div>
      <div class="gt-do-summary-row gt-do-total">
        <span>净利润合计</span>
        <strong :class="{ 'gt-do-negative': J < 0 }">{{ J.toLocaleString() }} 万元</strong>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gt-discontinued-ops { padding: 12px; }
.gt-discontinued-ops h4 { margin: 0 0 12px; font-size: 14px; color: var(--gt-primary, #4b2d77); }
.gt-do-code { color: var(--gt-primary, #4b2d77); }
.gt-do-computed { color: var(--gt-primary, #4b2d77); }
.gt-do-formula { font-size: 11px; color: #999; }
.gt-do-summary { margin-top: 16px; background: #fafafa; border: 1px solid #eee; border-radius: 6px; padding: 12px 16px; }
.gt-do-summary-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.gt-do-total { border-top: 1px solid #ddd; padding-top: 8px; margin-top: 4px; }
.gt-do-total strong { font-size: 15px; }
.gt-do-negative { color: #e6323e; }
</style>
