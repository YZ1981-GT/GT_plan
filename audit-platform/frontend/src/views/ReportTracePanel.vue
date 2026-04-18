<template>
  <div class="gt-trace gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">报告复核溯源</h2>
      <div class="gt-header-actions">
        <el-input v-model="sectionNumber" placeholder="附注章节号（如 五、9）" style="width: 200px" />
        <el-button type="primary" @click="onTrace">溯源查询</el-button>
      </div>
    </div>
    <div v-if="traceData" class="gt-trace-result">
      <el-card header="附注数据" shadow="never" v-if="traceData.note_data">
        <pre class="gt-trace-json">{{ JSON.stringify(traceData.note_data, null, 2) }}</pre>
      </el-card>
      <el-card header="底稿审定数" shadow="never" v-if="traceData.workpaper_data">
        <pre class="gt-trace-json">{{ JSON.stringify(traceData.workpaper_data, null, 2) }}</pre>
      </el-card>
      <el-card header="试算表数据" shadow="never" v-if="traceData.trial_balance_data">
        <el-table :data="traceData.trial_balance_data" size="small" stripe>
          <el-table-column prop="account_code" label="科目编码" width="120" />
          <el-table-column prop="account_name" label="科目名称" />
          <el-table-column prop="opening" label="期初" width="120" align="right" />
          <el-table-column prop="audited" label="审定" width="120" align="right" />
        </el-table>
      </el-card>
      <el-card header="大额交易 Top10" shadow="never" v-if="traceData.top_ledger_entries?.length">
        <el-table :data="traceData.top_ledger_entries" size="small" stripe>
          <el-table-column prop="voucher_no" label="凭证号" width="100" />
          <el-table-column prop="date" label="日期" width="100" />
          <el-table-column prop="debit" label="借方" width="120" align="right" />
          <el-table-column prop="credit" label="贷方" width="120" align="right" />
          <el-table-column prop="summary" label="摘要" show-overflow-tooltip />
        </el-table>
      </el-card>
    </div>
    <div class="gt-findings-summary" v-if="findings">
      <el-divider />
      <h3>统一 Findings 视图</h3>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="LLM 发现">{{ findings.llm_findings }}</el-descriptions-item>
        <el-descriptions-item label="人工发现">{{ findings.manual_findings }}</el-descriptions-item>
        <el-descriptions-item label="合计">{{ findings.total }}</el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { traceSection, findingsSummary } from '@/services/phase10Api'
const route = useRoute()
const projectId = ref(route.params.projectId as string || '')
const sectionNumber = ref('')
const traceData = ref<any>(null)
const findings = ref<any>(null)
async function onTrace() {
  if (!sectionNumber.value || !projectId.value) return
  traceData.value = await traceSection(projectId.value, sectionNumber.value)
}
onMounted(async () => {
  if (projectId.value) findings.value = await findingsSummary(projectId.value)
})
</script>
<style scoped>
.gt-trace { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-header-actions { display: flex; gap: var(--gt-space-2); }
.gt-trace-result { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.gt-trace-json { font-size: 12px; max-height: 200px; overflow: auto; background: var(--el-fill-color-light); padding: var(--gt-space-2); border-radius: var(--gt-radius-sm); }
</style>
