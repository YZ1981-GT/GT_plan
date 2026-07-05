<template>
  <div class="c24-balance-integrity">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C24-1 完整性测试 — 借贷方发生额：验证导入分录的借方发生额合计=贷方发生额合计（允许浮点误差 0.01 元）。</p>
    </div>

    <!-- 计算结果 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">借贷平衡完整性</span>
        <span class="unit-label">单位：元</span>
      </div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="借方发生额合计">
          <span class="formula-cell" title="来源：calcBalanceIntegrity.debitTotal">{{ fmtAmount(result.debitTotal) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="贷方发生额合计">
          <span class="formula-cell" title="来源：calcBalanceIntegrity.creditTotal">{{ fmtAmount(result.creditTotal) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="差额">
          <span class="formula-cell" :class="{ 'text-danger': !result.balanced }" title="来源：|debitTotal - creditTotal|">
            {{ fmtAmountWithZero(Math.abs(result.debitTotal - result.creditTotal)) }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="是否一致">
          <el-tag :type="result.balanced ? 'success' : 'danger'" size="small">
            {{ result.balanced ? '一致' : '不一致' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="!result.balanced && (result.debitTotal > 0 || result.creditTotal > 0)"
        type="error"
        :closable="false"
        style="margin-top: 12px;"
        show-icon
      >
        借方发生额合计与贷方发生额合计不一致，差额为 {{ fmtAmountWithZero(Math.abs(result.debitTotal - result.creditTotal)) }} 元，请核实数据完整性。
      </el-alert>

      <el-alert
        v-if="result.debitTotal === 0 && result.creditTotal === 0"
        type="info"
        :closable="false"
        style="margin-top: 12px;"
        show-icon
      >
        尚未导入分录数据，请先在程序表或汇总表中导入会计分录。
      </el-alert>
    </section>

    <!-- 测试结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-1-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="请填写借贷方发生额完整性测试结论"
        @input="$emit('update:conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import type { BalanceIntegrityResult } from '@/composables/useC24AnalyticsEngine'
import { fmtAmount, fmtAmountWithZero } from '@/utils/formatters'

defineProps<{
  result: BalanceIntegrityResult
  conclusion: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'update:conclusion', val: string): void
  (e: 'ai-suggest', fieldId: string): void
}>()
</script>

<style scoped>
.c24-balance-integrity { font-size: 13px; }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: 13px; color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
.text-danger { color: #f56c6c !important; }
.unit-label { font-size: 12px; color: #909399; font-weight: normal; }
</style>
