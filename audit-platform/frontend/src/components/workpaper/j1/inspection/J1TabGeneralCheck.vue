<template>
  <div class="j1-tab-general">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：抽查应付职工薪酬贷方（计提/增加）、借方（发放/减少）及期后支付凭证，核验金额、对方科目与业务实质相符，验证发生、完整性及截止认定。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">检查表（J1-8）— 贷方检查+借方检查+期后支付</span>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">贷方 {{ creditRows.length }} · 借方 {{ debitRows.length }} · 期后 {{ postPeriodRows.length }} 笔</el-tag>
        </div>
      </template>

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

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》及审计准则截止测试要求，检查计提与发放凭证的真实性与期间归属。</p>
        <p>2. 贷方检查对应计提/增加业务，借方检查对应发放/减少业务，二者应与明细表变动勾稽。</p>
        <p>3. 期后支付检查用于验证资产负债表日应付未付薪酬的完整性（是否存在漏提）。</p>
        <p>4. 📎 列标记存在附件凭证，异常凭证须在检查结果栏说明。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1GeneralCheck } from '@/composables/workpaper/j1/useJ1GeneralCheck'
import GtIndexChip from '../../GtIndexChip.vue'

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
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.block-title { margin: 16px 0 8px; color: #303133; font-size: 14px; border-left: 3px solid #409eff; padding-left: 8px; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.block-total { margin: 8px 0 16px; font-size: var(--wp-font-size, 13px); color: #606266; padding: 4px 8px; background: #f5f7fa; border-radius: 4px; }
</style>
