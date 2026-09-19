<template>
  <div class="g5-directory">
    <h3 class="sheet-title">底稿目录</h3>
    <el-table :data="rows" border stripe style="width:100%;font-size:13px">
      <el-table-column prop="seq" label="序号" width="55" align="center" />
      <el-table-column prop="indexCode" label="索引号" width="90">
        <template #default="{ row }">
          <GtIndexChip v-if="row.indexCode" :label="row.indexCode" @click="emit('jump', row.indexCode)" />
          <span v-else>{{ row.indexCode }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="底稿名称" min-width="200" />
      <el-table-column prop="preparer" label="编制人" width="90" />
      <el-table-column prop="reviewer" label="复核人" width="90" />
      <el-table-column prop="date" label="日期" width="110" />
      <el-table-column prop="pages" label="页数" width="70" align="center" />
      <el-table-column prop="remark" label="备注" min-width="100" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { G5_DIRECTORY_ROWS } from '../../composables/g5SheetLabels'

defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const emit = defineEmits<{ jump: [code: string] }>()

const rows = ref(
  G5_DIRECTORY_ROWS.map((r) => ({
    ...r,
    preparer: '',
    reviewer: '',
    date: '',
    pages: '',
    remark: '',
  })),
)
</script>

<style scoped>
.g5-directory { padding: 12px; font-size: var(--wp-font-size, 13px); }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
</style>
