<!--
  WorkpaperStandardHeader — 致同标准底稿表头

  统一渲染：致同事务所 / 底稿名 / 客户名称+编制人+日期+索引号 / 会计期间+复核人+日期+页次
  表头区域只读（用户不可编辑）。

  Foundation Kit Requirements: 3.2
-->
<template>
  <table class="wp-std-header">
    <tbody>
      <tr>
        <td class="wp-std-header__firm" colspan="4">致同会计师事务所（特殊普通合伙）</td>
      </tr>
      <tr>
        <td class="wp-std-header__wpname" colspan="4">{{ header.wpName || '' }}</td>
      </tr>
      <tr>
        <td class="wp-std-header__label">客户名称</td>
        <td class="wp-std-header__value">{{ header.entityName || '' }}</td>
        <td class="wp-std-header__label">索引号</td>
        <td class="wp-std-header__value">{{ header.indexNo || '' }}</td>
      </tr>
      <tr>
        <td class="wp-std-header__label">编制人</td>
        <td class="wp-std-header__value">{{ header.preparer || '' }}</td>
        <td class="wp-std-header__label">编制日期</td>
        <td class="wp-std-header__value">{{ header.preparedDate || '' }}</td>
      </tr>
      <tr>
        <td class="wp-std-header__label">复核人</td>
        <td class="wp-std-header__value">{{ header.reviewer || '' }}</td>
        <td class="wp-std-header__label">复核日期</td>
        <td class="wp-std-header__value">{{ header.reviewedDate || '' }}</td>
      </tr>
      <tr>
        <td class="wp-std-header__label">会计期间</td>
        <td class="wp-std-header__value" colspan="3">{{ header.period || '' }}</td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
import type { StandardHeader } from './WorkpaperHtmlTable.vue'

defineProps<{
  header: StandardHeader
}>()
</script>

<style scoped>
.wp-std-header {
  --gt-purple: var(--gt-color-primary, #4b2d77);
  --gt-purple-light: var(--gt-color-primary-bg, #f4f0fa);
  --gt-purple-border: var(--gt-color-primary-lighter, #d8b8ee);
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 8px;
  font-size: var(--wp-font-size, 13px);
}

.wp-std-header td {
  border: 1px solid var(--gt-purple-border);
  padding: 4px 8px;
}

.wp-std-header__firm {
  text-align: center;
  font-weight: 700;
  color: var(--gt-purple);
  background: var(--gt-purple-light);
  font-size: 14px;
}

.wp-std-header__wpname {
  text-align: center;
  font-weight: 600;
  font-size: 14px;
}

.wp-std-header__label {
  background: var(--gt-purple-light);
  color: var(--gt-purple);
  font-weight: 600;
  width: 90px;
  white-space: nowrap;
}

.wp-std-header__value {
  min-width: 120px;
}
</style>
