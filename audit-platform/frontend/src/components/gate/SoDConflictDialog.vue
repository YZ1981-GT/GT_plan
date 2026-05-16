<template>
  <el-dialog
    v-model="visible"
    title="职责分离冲突"
    width="480px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    append-to-body
    class="sod-conflict-dialog"
  >
    <div class="sod-content">
      <el-icon class="sod-icon" :size="48"><WarningFilled /></el-icon>
      <div class="sod-detail">
        <p class="sod-type">{{ conflictType }}</p>
        <p class="sod-policy">策略代码：{{ policyCode }}</p>
        <p class="sod-suggestion">
          建议操作：请联系合伙人指定替补人员，或更换当前操作角色。
        </p>
      </div>
    </div>
    <div class="sod-trace" v-if="traceId">
      <span>trace_id: </span>
      <el-button type="primary" link size="small" @click="copyTrace">
        {{ traceId }}
      </el-button>
    </div>
    <template #footer>
      <el-button type="primary" @click="handleClose">我知道了</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue: boolean
  conflictType: string
  policyCode: string
  traceId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()

const visible = ref(props.modelValue)

watch(() => props.modelValue, (v) => { visible.value = v })
watch(visible, (v) => { emit('update:modelValue', v) })

function handleClose() {
  visible.value = false
}

async function copyTrace() {
  try {
    await navigator.clipboard.writeText(props.traceId)
    ElMessage.success('trace_id 已复制')
  } catch {
    ElMessage.warning('复制失败')
  }
}
</script>

<style scoped>
.sod-content {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.sod-icon {
  color: var(--el-color-danger, #f56c6c);
  flex-shrink: 0;
}
.sod-detail {
  flex: 1;
}
.sod-type {
  font-size: var(--gt-font-size-base);
  font-weight: 600;
  margin-bottom: 8px;
}
.sod-policy {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary, #999);
  margin-bottom: 8px;
}
.sod-suggestion {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary, #333);
}
.sod-trace {
  margin-top: 12px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary, #999);
}
</style>
