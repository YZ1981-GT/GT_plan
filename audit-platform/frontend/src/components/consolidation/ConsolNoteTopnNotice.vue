<template>
  <el-alert
    v-if="notice"
    :type="notice.type"
    :title="notice.title"
    :closable="false"
    show-icon
    class="gt-consol-topn-notice"
    data-testid="consol-note-topn-notice"
  >
    <div v-for="(line, i) in notice.lines" :key="i">{{ line }}</div>
  </el-alert>
</template>

<script setup lang="ts">
/** 合并附注「前 N 名」表的重排说明（近似 / 集团内单位 / 比例分母，spec note-pull-followup-closure R10）。 */
import { computed } from 'vue'
import { consolNoteTopnNotice } from './consolNoteTopn'

const props = defineProps<{ data: unknown }>()
const notice = computed(() => consolNoteTopnNotice(props.data))
</script>

<style scoped>
.gt-consol-topn-notice {
  margin: 4px 0 8px;
}
</style>
