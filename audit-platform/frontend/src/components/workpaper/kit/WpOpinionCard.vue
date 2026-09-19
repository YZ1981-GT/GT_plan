<template>
  <el-card class="wp-opinion-card" shadow="never">
    <template #header>
      <div class="wp-opinion-card__header">
        <span class="wp-opinion-card__title">{{ sectionLabel }}</span>
        <div class="wp-opinion-card__actions">
          <el-button
            type="primary"
            plain
            size="small"
            :loading="aiLoading"
            @click="handleAiAssist"
          >
            🤖 AI辅助
          </el-button>
          <el-button
            size="small"
            @click="handleReview"
          >
            💬 复核
          </el-button>
        </div>
      </div>
    </template>

    <el-input
      type="textarea"
      :model-value="modelValue"
      :autosize="{ minRows: 5 }"
      :placeholder="`请输入${sectionLabel}...`"
      @update:model-value="handleInput"
    />
  </el-card>
</template>

<script setup lang="ts">
/**
 * WpOpinionCard - 底稿审计说明/结论卡片
 *
 * 统一渲染 autosize textarea + AI 辅助按钮 + 复核按钮。
 * 通过 inject 获取父级 provide 的 generateAiText 与 openReviewDialog。
 *
 * Feature: platform-global-hardening
 * Requirements: 4.3
 */
import { computed, inject, ref } from 'vue'

const props = defineProps<{
  /** v-model 绑定的文本内容 */
  modelValue: string
  /** 区域标识，如 "conclusion" / "opinion" / "audit-description" */
  section: string
  /** 底稿编码，如 "D2" / "F1" */
  wpCode: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// ─── Inject 父级 provide 的 AI 与复核能力 ──────────────────────────────────────
const generateAiText = inject<(section: string, context: string, existingContent: string) => Promise<string>>(
  'generateAiText',
  async () => ''
)
const openReviewDialog = inject<(sectionId: string) => void>(
  'openReviewDialog',
  () => {}
)

// ─── 状态 ──────────────────────────────────────────────────────────────────────
const aiLoading = ref(false)

// ─── 计算属性 ──────────────────────────────────────────────────────────────────
const sectionLabel = computed(() => {
  const labelMap: Record<string, string> = {
    conclusion: '审计结论',
    opinion: '审计意见',
    'audit-description': '审计说明',
    description: '审计说明',
    summary: '审计摘要',
  }
  return labelMap[props.section] || props.section
})

// ─── 事件处理 ──────────────────────────────────────────────────────────────────
function handleInput(value: string | number) {
  emit('update:modelValue', String(value))
}

async function handleAiAssist() {
  aiLoading.value = true
  try {
    const result = await generateAiText(
      props.section,
      props.modelValue,
      props.modelValue
    )
    if (result) {
      emit('update:modelValue', result)
    }
  } finally {
    aiLoading.value = false
  }
}

function handleReview() {
  openReviewDialog(props.section)
}
</script>

<style scoped>
.wp-opinion-card {
  margin-bottom: 16px;
}

.wp-opinion-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.wp-opinion-card__title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.wp-opinion-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
