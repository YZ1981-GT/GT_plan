<template>
  <el-alert
    v-if="entry"
    class="gt-wp-background-merge"
    :type="entry.status === 'merging' ? 'info' : 'warning'"
    :closable="false"
    show-icon
    role="status"
    aria-live="polite"
  >
    <template #title>
      {{ entry.status === 'merging' ? '正在合并在线编辑的改动' : '在线编辑的改动没有合并进表单' }}
    </template>
    <div class="gt-wp-background-merge__body">
      <span>{{ entry.message }}</span>
      <span v-if="entry.status === 'failed'" class="gt-wp-background-merge__actions">
        <el-button v-if="entry.canRetry" size="small" type="primary" :loading="busy" @click="run('retry')">
          重试回写
        </el-button>
        <el-button size="small" :loading="busy" @click="run('refresh')">刷新状态</el-button>
        <el-button size="small" :disabled="busy" @click="run('dismiss')">关闭提示</el-button>
      </span>
    </div>
  </el-alert>
</template>

<script setup lang="ts">
/**
 * 后台合并横幅（spec oo-return-to-form-dead-end-and-save-speed R4.2）。
 *
 * 数据只来自 `backgroundMergeRegistry`（按 wpId）；动作是桥登记进来的三个回调。合并中只有说明，
 * 失败后给出口：重试回写（服务端重新合并同一份已耐久文件）/ 刷新状态 / 关闭提示。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { backgroundMergeOf } from './backgroundMergeRegistry'

const props = defineProps<{ wpId: string }>()
const entry = computed(() => backgroundMergeOf(props.wpId))
const busy = ref(false)

async function run(action: 'retry' | 'refresh' | 'dismiss'): Promise<void> {
  const current = entry.value
  if (!current || busy.value) return
  busy.value = true
  try {
    await current[action]()
  } catch (error) {
    const message = error instanceof Error && /[\u4e00-\u9fff]/.test(error.message) ? error.message : ''
    ElMessage.error(message || '操作没有成功，请稍后再试')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.gt-wp-background-merge {
  margin-bottom: 8px;
}

.gt-wp-background-merge__body {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.gt-wp-background-merge__actions {
  display: inline-flex;
  gap: 6px;
}
</style>
