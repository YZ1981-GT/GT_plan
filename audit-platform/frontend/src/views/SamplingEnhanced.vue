<template>
  <div class="gt-sampling-enhanced gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">抽样程序增强</h2>
    </div>
    <el-tabs v-model="activeTab">
      <!-- 截止性测试 -->
      <el-tab-pane label="截止性测试" name="cutoff">
        <el-form :model="cutoffForm" label-width="100px" style="max-width: 600px">
          <el-form-item label="科目编码"><el-input v-model="cutoffForm.codes" placeholder="多个用逗号分隔，如 6001,6401" /></el-form-item>
          <el-form-item label="年度"><el-input-number v-model="cutoffForm.year" :min="2020" :max="2030" /></el-form-item>
          <el-form-item label="期末前天数"><el-input-number v-model="cutoffForm.days_before" :min="1" :max="30" /></el-form-item>
          <el-form-item label="期末后天数"><el-input-number v-model="cutoffForm.days_after" :min="1" :max="30" /></el-form-item>
          <el-form-item label="金额阈值"><el-input-number v-model="cutoffForm.threshold" :min="0" :step="1000" /></el-form-item>
          <el-form-item><el-button type="primary" @click="runCutoff" :loading="loading">执行</el-button></el-form-item>
        </el-form>
        <el-table v-if="cutoffResult" :data="cutoffResult.entries" stripe size="small" style="margin-top: 16px">
          <el-table-column prop="voucher_date" label="日期" width="100" />
          <el-table-column prop="voucher_no" label="凭证号" width="100" />
          <el-table-column prop="account_code" label="科目" width="100" />
          <el-table-column prop="debit_amount" label="借方" width="120" align="right" />
          <el-table-column prop="credit_amount" label="贷方" width="120" align="right" />
          <el-table-column prop="summary" label="摘要" show-overflow-tooltip />
          <el-table-column label="截止" width="80">
            <template #default="{ row }"><el-tag :type="row.is_before_cutoff ? 'success' : 'danger'" size="small">{{ row.is_before_cutoff ? '期内' : '期后' }}</el-tag></template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <!-- 账龄分析 -->
      <el-tab-pane label="账龄分析" name="aging">
        <el-form :model="agingForm" label-width="100px" style="max-width: 600px">
          <el-form-item label="科目编码"><el-input v-model="agingForm.account_code" placeholder="如 1122" /></el-form-item>
          <el-form-item label="基准日"><el-date-picker v-model="agingForm.base_date" type="date" value-format="YYYY-MM-DD" /></el-form-item>
          <el-form-item label="账龄区间">
            <div v-for="(b, i) in agingForm.brackets" :key="i" style="display:flex;gap:8px;margin-bottom:4px">
              <el-input v-model="b.label" placeholder="标签" style="width:120px" />
              <el-input-number v-model="b.min_days" :min="0" placeholder="起始天" />
              <el-input-number v-model="b.max_days" placeholder="结束天" />
              <el-button text type="danger" @click="agingForm.brackets.splice(i, 1)">删除</el-button>
            </div>
            <el-button size="small" @click="agingForm.brackets.push({ label: '', min_days: 0, max_days: null })">添加区间</el-button>
          </el-form-item>
          <el-form-item><el-button type="primary" @click="runAging" :loading="loading">分析</el-button></el-form-item>
        </el-form>
        <el-table v-if="agingResult" :data="agingResult.details" stripe size="small" style="margin-top: 16px">
          <el-table-column prop="aux_name" label="辅助维度" width="160" />
          <el-table-column prop="total_balance" label="余额合计" width="120" align="right" />
          <el-table-column v-for="b in agingResult.summary" :key="b.label" :label="b.label" align="right">
            <template #default="{ row }">{{ row.brackets?.find((x: any) => x.label === b.label)?.amount ?? '-' }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <!-- 月度明细 -->
      <el-tab-pane label="月度明细" name="monthly">
        <el-form :model="monthlyForm" label-width="100px" style="max-width: 400px" inline>
          <el-form-item label="科目"><el-input v-model="monthlyForm.account_code" /></el-form-item>
          <el-form-item label="年度"><el-input-number v-model="monthlyForm.year" :min="2020" :max="2030" /></el-form-item>
          <el-form-item><el-button type="primary" @click="runMonthly" :loading="loading">查询</el-button></el-form-item>
        </el-form>
        <el-table v-if="monthlyResult" :data="monthlyResult.months" stripe size="small" style="margin-top: 16px">
          <el-table-column prop="period" label="月份" width="80" />
          <el-table-column prop="debit_total" label="借方合计" width="120" align="right" />
          <el-table-column prop="credit_total" label="贷方合计" width="120" align="right" />
          <el-table-column prop="net_change" label="净变动" width="120" align="right" />
          <el-table-column prop="cumulative" label="累计" width="120" align="right" />
          <el-table-column prop="entry_count" label="笔数" width="80" align="right" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { cutoffTest, agingAnalysis, monthlyDetail } from '@/services/phase10Api'
const route = useRoute()
const projectId = ref(route.params.projectId as string || '')
const activeTab = ref('cutoff')
const loading = ref(false)
const cutoffForm = ref({ codes: '6001', year: 2025, days_before: 5, days_after: 5, threshold: 10000 })
const cutoffResult = ref<any>(null)
const agingForm = ref({
  account_code: '1122', base_date: '2025-12-31',
  brackets: [
    { label: '1年以内', min_days: 0, max_days: 365 },
    { label: '1-2年', min_days: 366, max_days: 730 },
    { label: '2-3年', min_days: 731, max_days: 1095 },
    { label: '3年以上', min_days: 1096, max_days: null },
  ],
})
const agingResult = ref<any>(null)
const monthlyForm = ref({ account_code: '6001', year: 2025 })
const monthlyResult = ref<any>(null)
async function runCutoff() {
  loading.value = true
  try {
    cutoffResult.value = await cutoffTest(projectId.value, {
      account_codes: cutoffForm.value.codes.split(',').map(s => s.trim()),
      year: cutoffForm.value.year, days_before: cutoffForm.value.days_before,
      days_after: cutoffForm.value.days_after, amount_threshold: cutoffForm.value.threshold,
    })
  } finally { loading.value = false }
}
async function runAging() {
  loading.value = true
  try {
    agingResult.value = await agingAnalysis(projectId.value, {
      account_code: agingForm.value.account_code, base_date: agingForm.value.base_date,
      aging_brackets: agingForm.value.brackets,
    })
  } finally { loading.value = false }
}
async function runMonthly() {
  loading.value = true
  try { monthlyResult.value = await monthlyDetail(projectId.value, monthlyForm.value) }
  finally { loading.value = false }
}
</script>
<style scoped>
.gt-sampling-enhanced { padding: var(--gt-space-4); }
.gt-page-header { margin-bottom: var(--gt-space-3); }
</style>
