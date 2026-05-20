<template>
  <el-dialog
    :model-value="visible"
    title="🧾 K11 资产减值损失跨循环汇总（K-F8）"
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
        系统自动汇总 4 类来源底稿的减值数据：H1-14 固定资产 / I3 商誉 / G14 信用 / F2 存货跌价。
        汇总类规则时机铁律：来源底稿未保存时不阻断，列入"未提供数据"清单。
      </template>
    </el-alert>

    <el-form :model="form" label-width="120px" size="small">
      <el-form-item label="年度">
        <el-input-number
          v-model="form.year"
          :min="2000"
          :max="2100"
          :step="1"
          controls-position="right"
          style="width: 200px"
        />
      </el-form-item>
    </el-form>

    <!-- 计算结果 -->
    <template v-if="result">
      <el-divider>汇总结果</el-divider>

      <el-descriptions :column="2" size="small" border style="margin-bottom: 12px">
        <el-descriptions-item label="资产减值合计" :span="2">
          <span class="total-amount">¥ {{ formatAmount(result.total_impairment) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="来源命中">
          {{ result.sources_found.length }}/4 个底稿
        </el-descriptions-item>
        <el-descriptions-item label="LLM Stub">
          {{ result.is_llm_stub ? '是（待接入）' : '否' }}
        </el-descriptions-item>
        <el-descriptions-item label="简要分析" :span="2">
          {{ result.summary }}
        </el-descriptions-item>
      </el-descriptions>

      <el-table
        :data="result.impairment_by_type"
        size="small"
        border
        max-height="240"
        empty-text="暂无来源数据"
      >
        <el-table-column label="资产类型" prop="asset_type" min-width="140" />
        <el-table-column label="减值金额" width="180" align="right">
          <template #default="{ row }">
            <span class="gt-amt">¥ {{ formatAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源底稿" prop="source_wp" width="120" />
        <el-table-column label="来源 sheet" prop="source_sheet" min-width="180" />
      </el-table>

      <div v-if="result.sources_missing.length" class="missing-block">
        <el-divider>未提供数据的来源</el-divider>
        <ul class="missing-list">
          <li v-for="(m, i) in result.sources_missing" :key="i">⚠ {{ m }}</li>
        </ul>
      </div>
    </template>

    <template #footer>
      <el-button @click="emit('update:visible', false)">关闭</el-button>
      <el-button
        type="primary"
        :loading="loading"
        @click="onCalc"
      >🔍 汇总查询</el-button>
      <el-button
        v-if="result"
        type="success"
        :loading="applying"
        :disabled="!targetSheet"
        @click="onApplyToSheet"
      >✅ 采纳并写回</el-button>
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
  /** 当前激活的 sheet 名（用于写回 parsed_data.impairment_summary[sheet]） */
  targetSheet?: string
}

const props = withDefaults(defineProps<Props>(), { targetSheet: '' })

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'applied', sheet: string): void
}>()

interface ImpairmentByType {
  asset_type: string
  amount: number
  source_wp: string
  source_sheet: string | null
}

interface SummaryResponse {
  impairment_by_type: ImpairmentByType[]
  total_impairment: number
  sources_found: string[]
  sources_missing: string[]
  summary: string
  is_llm_stub: boolean
  applied_to_sheet?: string | null
}

const loading = ref(false)
const applying = ref(false)
const result = ref<SummaryResponse | null>(null)

const form = reactive({
  year: new Date().getFullYear(),
})

function formatAmount(n: number | undefined) {
  if (n === undefined || n === null) return '0.00'
  if (!Number.isFinite(n)) return String(n)
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function buildBody(applySheet?: string) {
  return {
    year: form.year,
    apply_to_sheet: applySheet || null,
  }
}

async function onCalc() {
  loading.value = true
  try {
    const resp = await api.post<SummaryResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/k11/impairment-summary`,
      buildBody(),
    )
    result.value = resp
    ElMessage.success(
      `汇总完成：合计 ¥${formatAmount(resp.total_impairment)}，来源 ${resp.sources_found.length}/4`,
    )
  } catch (e: any) {
    ElMessage.error(e?.message || '汇总查询失败')
  } finally {
    loading.value = false
  }
}

async function onApplyToSheet() {
  if (!props.targetSheet) {
    ElMessage.warning('未识别到当前 sheet')
    return
  }
  applying.value = true
  try {
    const resp = await api.post<SummaryResponse>(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/k11/impairment-summary`,
      buildBody(props.targetSheet),
    )
    result.value = resp
    if (resp?.applied_to_sheet) {
      ElMessage.success(`已写回 ${resp.applied_to_sheet}`)
      emit('applied', resp.applied_to_sheet)
    } else {
      ElMessage.warning('计算完成但未写回')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '写回失败')
  } finally {
    applying.value = false
  }
}

watch(
  () => props.visible,
  (v) => {
    if (!v) result.value = null
  },
)
</script>

<style scoped>
.total-amount {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-color-danger);
  font-family: 'Arial Narrow', sans-serif;
}
.missing-block {
  margin-top: 12px;
}
.missing-list {
  margin: 0;
  padding-left: 20px;
  color: var(--el-color-warning-dark-2);
  font-size: 13px;
  line-height: 1.8;
}
.missing-list li {
  margin-bottom: 4px;
}
</style>
