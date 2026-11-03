<template>
  <el-dialog
    :model-value="state.visible"
    title="有未保存的合并工作区修改"
    width="460px"
    append-to-body
    :close-on-click-modal="false"
    :close-on-press-escape="!state.processing"
    :show-close="!state.processing"
    @close="$emit('decide', 'cancel')"
  >
    <p class="cw-guard-reason">{{ state.reason }}</p>
    <p v-if="state.labels.length" class="cw-guard-targets">
      待处理：{{ state.labels.join('、') }}
    </p>
    <template #footer>
      <el-button :disabled="state.processing" @click="$emit('decide', 'cancel')">取消</el-button>
      <el-button :disabled="state.processing" @click="$emit('decide', 'discard')">放弃修改</el-button>
      <el-button type="primary" :loading="state.processing" @click="$emit('decide', 'save')">
        保存并继续
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import type {
  ConsolTransitionDecision,
  ConsolWorkspaceDecisionState,
} from './composables/useConsolWorkspaceGuard'

defineProps<{ state: ConsolWorkspaceDecisionState }>()
defineEmits<{ decide: [decision: ConsolTransitionDecision] }>()
</script>

<style scoped>
.cw-guard-reason { margin: 0; color: var(--gt-color-text-primary); line-height: 1.6; }
.cw-guard-targets { margin: 10px 0 0; color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-sm); }
</style>
