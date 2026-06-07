<!--
  AccountPackageFieldSource.vue — 审定表字段来源面板

  spec workpaper-account-package-d1-d2-pilot Task 4.3
  展示审定表关键字段（期末余额、坏账准备等）的数据来源（哪个 sheet 提供），点击跳转。

  Validates: Requirements 2.4
-->
<template>
  <div class="gt-field-source">
    <h4 class="gt-field-source__title">审定表字段来源</h4>
    <div class="gt-field-source__list">
      <div
        v-for="field in auditSheetFields"
        :key="field.fieldId"
        class="gt-field-source__item"
      >
        <span class="gt-field-source__label">{{ field.label }}</span>
        <span class="gt-field-source__arrow">←</span>
        <span class="gt-field-source__source" @click="handleSourceClick(field.sourceSheet)">
          {{ field.sourceSheet }}
        </span>
        <el-tag size="small" :type="field.tagType" effect="light">
          {{ field.sourceType }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface AuditFieldSource {
  fieldId: string
  label: string
  sourceSheet: string
  sourceType: string
  tagType: '' | 'success' | 'warning' | 'info' | 'danger'
}

const props = defineProps<{
  packageId: string
  primaryWpCode: string
}>()

// D1 审定表关键字段来源（静态配置，真实环境从后端获取）
const D1_FIELDS: AuditFieldSource[] = [
  { fieldId: 'period_end_balance', label: '期末余额', sourceSheet: '应收票据明细表D1-2', sourceType: '明细表汇总', tagType: 'success' },
  { fieldId: 'bad_debt_provision', label: '坏账准备', sourceSheet: '坏账准备明细表D1-4', sourceType: '坏账计算', tagType: 'warning' },
  { fieldId: 'discount_endorsed', label: '贴现/背书', sourceSheet: '应收票据贴现背书明细表D1-8', sourceType: '明细表', tagType: 'info' },
  { fieldId: 'pledged_amount', label: '质押金额', sourceSheet: '应收票据质押检查表D1-12', sourceType: '检查程序', tagType: '' },
]

// D2 审定表关键字段来源
const D2_FIELDS: AuditFieldSource[] = [
  { fieldId: 'period_end_balance', label: '期末余额', sourceSheet: '应收账款明细表D2-2', sourceType: '明细表汇总', tagType: 'success' },
  { fieldId: 'bad_debt_provision', label: '坏账准备', sourceSheet: '坏账准备明细表D2-3', sourceType: '坏账计算', tagType: 'warning' },
  { fieldId: 'ecl_amount', label: '预期信用损失', sourceSheet: '预期信用损失的计量测试D2-10', sourceType: 'ECL 测算', tagType: 'danger' },
  { fieldId: 'adjustment_total', label: '调整合计', sourceSheet: '调整分录汇总表D2-4', sourceType: '调整分录', tagType: 'info' },
]

const auditSheetFields = computed<AuditFieldSource[]>(() => {
  if (props.primaryWpCode === 'D1') return D1_FIELDS
  if (props.primaryWpCode === 'D2') return D2_FIELDS
  return []
})

function handleSourceClick(sheetName: string) {
  // 后续可跳转到对应 sheet
  console.log('[AccountPackageFieldSource] navigate to:', sheetName)
}
</script>

<style scoped>
.gt-field-source {
  margin: 16px 0;
  padding: 16px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.gt-field-source__title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-field-source__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-field-source__item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.gt-field-source__label {
  font-weight: 500;
  min-width: 80px;
}

.gt-field-source__arrow {
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-field-source__source {
  color: var(--gt-color-primary, #4b2d77);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-style: dotted;
}

.gt-field-source__source:hover {
  text-decoration-style: solid;
}
</style>
