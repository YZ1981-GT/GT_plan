<template>
  <div class="h85-sync-bar">
    <el-alert
      v-if="mismatch"
      type="warning"
      :closable="false"
      show-icon
      class="mismatch-alert"
      :title="`与 H8-5 不一致：合同 ${mismatch.contractNo} 有效期 ${mismatch.h85Months} 月，本表 ${mismatch.h86Months} 月`"
    >
      <template #default>
        <div class="mismatch-actions">
          <el-button
            size="small"
            type="warning"
            :disabled="isReadonly"
            @click="$emit('pull', mismatch.contractNo)"
          >
            按 H8-5 覆盖
          </el-button>
          <el-button size="small" link type="primary" @click="$emit('navigate', 'H8-5')">
            打开 H8-5
          </el-button>
        </div>
      </template>
    </el-alert>

    <div class="sync-row">
      <el-tag v-if="sourceContract" size="small" type="success" effect="plain">
        来源 H8-5 · {{ sourceContract }}
        <template v-if="syncedFrom">（已同步）</template>
      </el-tag>
      <el-tag v-else-if="options.length === 0" size="small" type="info" effect="plain">
        H8-5 暂无可用租赁期
      </el-tag>
      <el-select
        v-if="options.length > 1"
        v-model="picked"
        size="small"
        placeholder="选择合同"
        style="width: 180px"
        :disabled="isReadonly"
      >
        <el-option
          v-for="o in options"
          :key="o.recordId"
          :label="`${o.contractNo}（${o.months}月）`"
          :value="o.contractNo"
        />
      </el-select>
      <el-button
        size="small"
        type="primary"
        plain
        :disabled="isReadonly || options.length === 0"
        @click="$emit('pull', picked || undefined)"
      >
        从 H8-5 带入租赁期
      </el-button>
      <el-button size="small" link type="primary" @click="$emit('navigate', 'H8-5')">
        ← H8-5
      </el-button>
      <el-button
        v-if="leaseTermMonths > 0 && leaseTermMonths <= 12"
        size="small"
        link
        type="warning"
        @click="$emit('navigate', 'H8-13')"
      >
        短期？H8-13
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { H85TermOption } from '../../composables/useH8Measurement'

const props = defineProps<{
  options: H85TermOption[]
  mismatch: { contractNo: string; h85Months: number; h86Months: number } | null
  sourceContract?: string
  syncedFrom?: string
  leaseTermMonths: number
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'pull', contractNo?: string): void
  (e: 'navigate', sheet: string): void
}>()

const picked = ref('')
watch(
  () => [props.sourceContract, props.options] as const,
  () => {
    if (props.sourceContract) {
      picked.value = props.sourceContract
      return
    }
    if (props.options.length === 1) picked.value = props.options[0].contractNo
  },
  { immediate: true, deep: true },
)
</script>

<style scoped>
.h85-sync-bar { margin-bottom: 12px; }
.mismatch-alert { margin-bottom: 10px; }
.mismatch-actions { margin-top: 6px; display: flex; gap: 8px; flex-wrap: wrap; }
.sync-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
</style>
