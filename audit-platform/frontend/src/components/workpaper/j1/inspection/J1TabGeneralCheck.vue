<template>
  <div class="j1-tab-general">
    <el-card shadow="never">
      <template #header><span class="section-title">检查表（J1-8）— 贷方检查+借方检查+期后支付</span></template>

      <!-- 贷方检查区 -->
      <h4 class="block-title">贷方检查（计提/增加）</h4>
      <el-table :data="creditRows" border size="small" style="font-size: 13px" max-height="300">
        <el-table-column prop="voucherNo" label="凭证号" width="100" />
        <el-table-column prop="date" label="日期" width="100" />
        <el-table-column prop="subject" label="摘要" min-width="150" />
        <el-table-column prop="amount" label="金额" width="110" align="right" />
        <el-table-column prop="counterAccount" label="对方科目" width="120" />
        <el-table-column prop="checkResult" label="检查结果" width="100" />
        <el-table-column label="📎" width="50" align="center">
          <template #default="{ row }">{{ row.hasAttachment ? '📎' : '' }}</template>
        </el-table-column>
      </el-table>
      <div class="block-total">贷方合计: {{ creditTotal?.toLocaleString() }}</div>

      <!-- 借方检查区 -->
      <h4 class="block-title">借方检查（发放/减少）</h4>
      <el-table :data="debitRows" border size="small" style="font-size: 13px" max-height="300">
        <el-table-column prop="voucherNo" label="凭证号" width="100" />
        <el-table-column prop="date" label="日期" width="100" />
        <el-table-column prop="subject" label="摘要" min-width="150" />
        <el-table-column prop="amount" label="金额" width="110" align="right" />
        <el-table-column prop="counterAccount" label="对方科目" width="120" />
        <el-table-column prop="checkResult" label="检查结果" width="100" />
        <el-table-column label="📎" width="50" align="center">
          <template #default="{ row }">{{ row.hasAttachment ? '📎' : '' }}</template>
        </el-table-column>
      </el-table>
      <div class="block-total">借方合计: {{ debitTotal?.toLocaleString() }}</div>

      <!-- 期后支付 -->
      <h4 class="block-title">期后支付检查</h4>
      <el-table :data="postPeriodRows" border size="small" style="font-size: 13px" max-height="200">
        <el-table-column prop="voucherNo" label="凭证号" width="100" />
        <el-table-column prop="date" label="日期" width="100" />
        <el-table-column prop="subject" label="摘要" min-width="150" />
        <el-table-column prop="amount" label="金额" width="110" align="right" />
        <el-table-column prop="checkResult" label="检查结果" min-width="100" />
      </el-table>
      <div class="block-total">期后支付合计: {{ postPeriodTotal?.toLocaleString() }}</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1GeneralCheck } from '@/composables/workpaper/j1/useJ1GeneralCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { creditRows, debitRows, postPeriodRows, creditTotal, debitTotal, postPeriodTotal, initFromHtmlData } = useJ1GeneralCheck(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-general { padding: 16px; }
.section-title { font-weight: 600; font-size: 15px; }
.block-title { margin: 16px 0 8px; color: #303133; font-size: 14px; border-left: 3px solid #409eff; padding-left: 8px; }
.block-total { margin: 8px 0 16px; font-size: 13px; color: #606266; padding: 4px 8px; background: #f5f7fa; border-radius: 4px; }
</style>
