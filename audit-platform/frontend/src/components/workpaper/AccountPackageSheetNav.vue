<!--
  AccountPackageSheetNav.vue — sheet_type 分组导航

  spec workpaper-account-package-d1-d2-pilot Task 4.2 / 5.2
  Validates: Requirements 2.2
-->
<template>
  <div class="gt-sheet-nav">
    <h4 class="gt-sheet-nav__title">工作表导航</h4>
    <div class="gt-sheet-nav__groups">
      <div
        v-for="group in groups"
        :key="group.type"
        class="gt-sheet-nav__group"
      >
        <div class="gt-sheet-nav__group-header">
          <span class="gt-sheet-nav__group-icon">{{ group.icon }}</span>
          <span class="gt-sheet-nav__group-label">{{ group.label }}</span>
          <el-badge :value="group.sheets.length" :max="99" type="info" />
        </div>
        <div class="gt-sheet-nav__group-sheets">
          <div
            v-for="sheet in group.sheets"
            :key="sheet.sheet_name"
            class="gt-sheet-nav__sheet"
            :class="{ 'gt-sheet-nav__sheet--active': activeSheet === sheet.sheet_name }"
            @click="$emit('select', sheet.sheet_name)"
          >
            <span class="gt-sheet-nav__sheet-name">{{ sheet.sheet_name }}</span>
            <el-tag
              v-if="sheet.schema_ref"
              size="small"
              effect="plain"
              class="gt-sheet-nav__schema-tag"
            >
              schema
            </el-tag>
          </div>
        </div>
      </div>
      <div v-if="groups.length === 0" class="gt-sheet-nav__empty">
        暂无工作表
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SheetTypeGroup } from '@/composables/useAccountPackage'

defineProps<{
  groups: SheetTypeGroup[]
  activeSheet: string
}>()

defineEmits<{
  select: [sheetName: string]
}>()
</script>

<style scoped>
.gt-sheet-nav {
  margin: 16px 0;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  padding: 16px;
}

.gt-sheet-nav__title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-sheet-nav__groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.gt-sheet-nav__group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--gt-color-text-primary, #1d1d1f);
  margin-bottom: 6px;
}

.gt-sheet-nav__group-icon {
  font-size: 14px;
}

.gt-sheet-nav__group-sheets {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 20px;
}

.gt-sheet-nav__sheet {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.2s;
}

.gt-sheet-nav__sheet:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.gt-sheet-nav__sheet--active {
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-left: 3px solid var(--gt-color-primary, #4b2d77);
}

.gt-sheet-nav__sheet-name {
  flex: 1;
}

.gt-sheet-nav__schema-tag {
  font-size: 11px;
}

.gt-sheet-nav__empty {
  text-align: center;
  color: var(--gt-color-text-secondary, #6e6e73);
  padding: 16px;
  font-size: 13px;
}
</style>
