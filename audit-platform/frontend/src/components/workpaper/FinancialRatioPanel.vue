<!--
  FinancialRatioPanel — 财务比率分析面板

  显示 9 个核心比率，异常项高亮，支持未审/已审切换。
  Requirements: 5.2, 5.4
-->
<template>
  <div class="ratio-panel">
    <div class="ratio-panel__toolbar">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="audited">已审</el-radio-button>
        <el-radio-button value="unadjusted">未审</el-radio-button>
      </el-radio-group>
    </div>

    <el-table :data="ratios" border class="gt-compact-table">
      <el-table-column prop="name" label="指标" min-width="160" />
      <el-table-column label="数值" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'ratio-panel__abnormal': row.abnormal }">
            {{ row.value != null ? row.value : '—' }}{{ row.value != null ? row.unit : '' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注" width="120" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  projectId: string
  year: number
}>()

const mode = ref('audited')
const ratios = ref<any[]>([])

async function loadRatios() {
  try {
    ratios.value = await api.get(
      `/api/workpapers/${props.projectId}/${props.year}/financial-ratios`,
      { params: { mode: mode.value } },
    ) as any[]
  } catch { ratios.value = [] }
}

watch(mode, loadRatios)
onMounted(loadRatios)

defineExpose({ loadRatios })
</script>

<style scoped>
.ratio-panel__toolbar {
  margin-bottom: 8px;
}
.ratio-panel__abnormal {
  color: #f56c6c;
  font-weight: 700;
}
</style>
