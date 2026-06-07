<!--
  AccountPackageEvidenceCard.vue — 摘要卡片（函证、调整等）

  spec workpaper-account-package-d1-d2-pilot Task 5.3
  函证摘要卡片：展示覆盖率、差异金额、未解决事项。
  数据来自函证模块（placeholder，显示"跳转函证中心"链接）。

  Validates: Requirements 3.2, 4.3
-->
<template>
  <div class="gt-evidence-card" :class="`gt-evidence-card--${type}`">
    <div class="gt-evidence-card__header">
      <span class="gt-evidence-card__icon">{{ cardIcon }}</span>
      <span class="gt-evidence-card__title">{{ cardTitle }}</span>
    </div>
    <div class="gt-evidence-card__body">
      <template v-if="type === 'confirmation_summary'">
        <div class="gt-evidence-card__metric">
          <span class="gt-evidence-card__metric-label">覆盖率</span>
          <span class="gt-evidence-card__metric-value">--</span>
        </div>
        <div class="gt-evidence-card__metric">
          <span class="gt-evidence-card__metric-label">差异金额</span>
          <span class="gt-evidence-card__metric-value">--</span>
        </div>
        <div class="gt-evidence-card__metric">
          <span class="gt-evidence-card__metric-label">未解决事项</span>
          <span class="gt-evidence-card__metric-value">--</span>
        </div>
        <div class="gt-evidence-card__link">
          <a href="#" @click.prevent="navigateToConfirmation">
            跳转函证中心 →
          </a>
        </div>
      </template>
      <template v-else-if="type === 'adjustment_impact'">
        <div class="gt-evidence-card__metric">
          <span class="gt-evidence-card__metric-label">调整分录数</span>
          <span class="gt-evidence-card__metric-value">--</span>
        </div>
        <div class="gt-evidence-card__metric">
          <span class="gt-evidence-card__metric-label">影响金额</span>
          <span class="gt-evidence-card__metric-value">--</span>
        </div>
        <div class="gt-evidence-card__status">
          <span>数据来自调整模块（Placeholder）</span>
        </div>
      </template>
      <template v-else>
        <div class="gt-evidence-card__placeholder">
          暂无数据
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{
  type: string
  packageId: string
  projectId: string
}>()

const router = useRouter()

const CARD_CONFIG: Record<string, { icon: string; title: string }> = {
  confirmation_summary: { icon: '📬', title: '函证摘要' },
  adjustment_impact: { icon: '✏️', title: '调整影响' },
  note_disclosure: { icon: '📝', title: '附注披露' },
}

const cardIcon = computed(() => CARD_CONFIG[props.type]?.icon ?? '📄')
const cardTitle = computed(() => CARD_CONFIG[props.type]?.title ?? props.type)

function navigateToConfirmation() {
  router.push({
    name: 'ConfirmationHub',
    params: { projectId: props.projectId },
  })
}
</script>

<style scoped>
.gt-evidence-card {
  flex: 1;
  min-width: 240px;
  max-width: 360px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}

.gt-evidence-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gt-color-border-purple, #e8e4f0);
}

.gt-evidence-card__icon {
  font-size: 16px;
}

.gt-evidence-card__title {
  font-weight: 600;
  font-size: 14px;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-evidence-card__metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 13px;
}

.gt-evidence-card__metric-label {
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-evidence-card__metric-value {
  font-weight: 500;
  color: var(--gt-color-text-primary, #1d1d1f);
}

.gt-evidence-card__link {
  margin-top: 12px;
  text-align: center;
}

.gt-evidence-card__link a {
  color: var(--gt-color-primary, #4b2d77);
  font-size: 13px;
  text-decoration: none;
}

.gt-evidence-card__link a:hover {
  text-decoration: underline;
}

.gt-evidence-card__status {
  margin-top: 8px;
  font-size: 12px;
  color: var(--gt-color-text-secondary, #6e6e73);
}

.gt-evidence-card__placeholder {
  text-align: center;
  color: var(--gt-color-text-secondary, #6e6e73);
  padding: 12px;
  font-size: 13px;
}
</style>
