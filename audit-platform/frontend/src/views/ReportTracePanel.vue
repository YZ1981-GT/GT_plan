<template>
  <div class="gt-trace gt-fade-in">
    <GtPageHeader title="报告复核溯源" :show-back="false">
      <template #actions>
        <el-input v-model="sectionNumber" placeholder="附注章节号（如 五、9）" style="width: 200px" />
        <el-button type="primary" :loading="tracing" @click="onTrace">溯源查询</el-button>
      </template>
    </GtPageHeader>
    <div v-if="traceData" class="gt-trace-result">
      <!-- 取数口径（spec voucher-workflow-linkage-lineage-closure R8.2）：按年度 + 章节对应科目；不取时写明原因 -->
      <el-alert v-if="basisText" type="info" :closable="false" show-icon :title="basisText" data-testid="report-trace-basis" />
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
          <el-table-column prop="unadjusted" label="未审" width="120" align="right" />
          <el-table-column prop="audited" label="审定" width="120" align="right" />
        </el-table>
      </el-card>
      <el-card header="大额交易（金额前 10 笔）" shadow="never" v-if="traceData.top_ledger_entries?.length">
        <el-table :data="traceData.top_ledger_entries" size="small" stripe>
          <el-table-column prop="voucher_no" label="凭证号" width="100" />
          <el-table-column prop="date" label="日期" width="100" />
          <el-table-column prop="account_code" label="科目" width="110" />
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
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { traceSection, findingsSummary } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'
const route = useRoute()
const projectId = ref(route.params.projectId as string || '')
const sectionNumber = ref('')
const traceData = ref<any>(null)
const findings = ref<any>(null)
const tracing = ref(false)
/** 试算表与序时账的取数口径；两段原因相同（如「项目未设置审计年度」）时只写一次 */
const basisText = computed(() => {
  const tb = String(traceData.value?.trial_balance_basis || '')
  const ledger = String(traceData.value?.ledger_basis || '')
  const parts = [...new Set([tb, ledger].filter(Boolean))]
  return parts.length ? `取数口径：${parts.join('；')}` : ''
})
async function onTrace() {
  if (!sectionNumber.value || !projectId.value) return
  traceData.value = null // 查询失败（后端不再吞异常、报错提示）时不留上一个章节的结果
  tracing.value = true
  try {
    traceData.value = await traceSection(projectId.value, sectionNumber.value)
  } catch (err) {
    // 失败原因经统一错误提示说清、页面留着：原先异常冒到全局错误边界，整页换成英文「Request failed…」（浏览器实测发现）
    handleApiError(err, '溯源查询')
  } finally {
    tracing.value = false
  }
}
onMounted(async () => {
  if (!projectId.value) return
  try {
    findings.value = await findingsSummary(projectId.value)
  } catch (err) {
    handleApiError(err, '读取统一发现汇总')
  }
})
</script>
<style scoped>
.gt-trace { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-header-actions { display: flex; gap: var(--gt-space-2); }
.gt-trace-result { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.gt-trace-json { font-size: var(--gt-font-size-xs); max-height: 200px; overflow: auto; background: var(--el-fill-color-light); padding: var(--gt-space-2); border-radius: var(--gt-radius-sm); }
</style>
