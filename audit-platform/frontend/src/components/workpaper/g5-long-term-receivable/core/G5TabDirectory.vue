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

defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const emit = defineEmits<{ jump: [code: string] }>()

const rows = ref([
  { seq: 1, indexCode: 'G5A', name: '长期应收款审计程序表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 2, indexCode: 'G5-1', name: '长期应收款审定表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 3, indexCode: 'G5-2', name: '长期应收款余额明细表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 4, indexCode: 'G5-3', name: '坏账准备明细表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 5, indexCode: 'G5-4', name: '调整分录汇总', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 6, indexCode: 'G5-5', name: '融资租赁测算表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 7, indexCode: 'G5-6', name: '分期销售测算表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 8, indexCode: 'G5-7', name: '保理核查表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 9, indexCode: 'G5-8', name: '会计政策检查', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 10, indexCode: 'G5-9', name: '三阶段划分（暂缓）', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 11, indexCode: 'G5-10', name: '坏账准备测算（暂缓）', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 12, indexCode: 'G5-11', name: '转回核销检查', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
  { seq: 13, indexCode: 'G5-12', name: '凭证检查表', preparer: '', reviewer: '', date: '', pages: '', remark: '' },
])
</script>

<style scoped>
.g5-directory { padding: 12px; font-size: var(--wp-font-size, 13px); }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
</style>
