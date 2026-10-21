<!-- 推送覆盖率卡片（从 FormulaManagerDialog 提取；spec formula-settings-wiring-closure T11）。 -->
<template>
  <div v-if="coverage" class="gt-fm-coverage-section" style="margin-bottom: 12px; padding: 12px; background: var(--gt-bg-page, #fafafa); border-radius: 6px;">
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
      <span style="font-size: 13px; font-weight: 600;">📤 推送覆盖率</span>
      <span :style="{ fontSize: '18px', fontWeight: 700, color: coverage.percentage >= 80 ? 'var(--gt-color-success)' : 'var(--gt-color-warning)' }">
        {{ coverage.percentage }}%
      </span>
      <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
        （{{ coverage.total_registered }} / {{ coverage.total_codes }} 个底稿编码已接入）
      </span>
    </div>
    <el-progress :percentage="coverage.percentage" :stroke-width="8" :status="coverage.percentage >= 95 ? 'success' : ''" style="margin-bottom: 8px;" />
    <div style="display: flex; flex-wrap: wrap; gap: 6px;">
      <div v-for="cy in coverage.cycles" :key="cy.cycle"
        style="display: flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 6px; border-radius: 4px;"
        :style="{ background: cy.not_needed ? '#f5f5f5' : cy.percentage >= 100 ? '#f6ffed' : '#fffbe6' }">
        <span style="font-weight: 600; min-width: 14px;">{{ cy.cycle }}</span>
        <template v-if="cy.not_needed">
          <span style="color: var(--gt-color-text-tertiary);">不需推送</span>
          <el-tooltip :content="cy.reason" placement="top">
            <span style="cursor: help;">ℹ️</span>
          </el-tooltip>
        </template>
        <template v-else>
          <span :style="{ color: cy.percentage >= 100 ? 'var(--gt-color-success)' : 'var(--gt-color-warning)' }">
            {{ cy.connected }}/{{ cy.total }}
          </span>
          <el-tooltip v-if="cy.missing?.length" :content="`缺口：${cy.missing.join('、')}`" placement="top">
            <span style="cursor: help; color: var(--gt-color-warning);">⚠</span>
          </el-tooltip>
        </template>
      </div>
    </div>
    <div v-if="coverage.excluded?.length" style="margin-top: 6px; font-size: 11px; color: var(--gt-color-text-tertiary);">
      不适用：{{ coverage.excluded.join('、') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '@/services/apiProxy'

const props = defineProps<{ show: boolean }>()

const coverage = ref<any>(null)

watch(() => props.show, async (v) => {
  if (v && !coverage.value) {
    try { coverage.value = await api.get('/api/formula-push/coverage') as any } catch { /* 不阻断 */ }
  }
}, { immediate: true })
</script>
