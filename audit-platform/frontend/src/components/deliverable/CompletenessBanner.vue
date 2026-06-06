<template>
  <el-alert
    v-if="loaded"
    :type="result?.passed ? 'success' : 'warning'"
    show-icon
    :closable="false"
    class="completeness-banner"
  >
    <template #title>
      <div class="completeness-banner__row">
        <span v-if="result?.passed">三件套完整性检查通过</span>
        <span v-else>
          交付物完整性未通过
          <template v-if="result?.warnings?.length">
            — {{ result.warnings.join('；') }}
          </template>
        </span>
        <el-button
          v-if="!result?.passed"
          size="small"
          type="primary"
          text
          @click="refresh"
        >
          重新检查
        </el-button>
      </div>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { fetchCompleteness, type CompletenessResult } from '@/services/deliverableApi'

const props = defineProps<{
  projectId: string
  year: number
}>()

const result = ref<CompletenessResult | null>(null)
const loaded = ref(false)

async function refresh() {
  try {
    result.value = await fetchCompleteness(props.projectId, props.year)
  } catch {
    result.value = null
  } finally {
    loaded.value = true
  }
}

watch(
  () => [props.projectId, props.year],
  () => refresh(),
)

onMounted(refresh)

defineExpose({ refresh })
</script>

<style scoped>
.completeness-banner {
  margin-bottom: 12px;
}
.completeness-banner__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
</style>
