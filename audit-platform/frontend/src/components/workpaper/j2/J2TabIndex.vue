<template>
  <div class="j2-tab-index">
    <h3 class="index-title">长期应付职工薪酬-设定受益计划净资产 底稿目录</h3>
    <el-table :data="indexItems" border stripe style="width: 100%">
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="content" label="内容" min-width="300" />
      <el-table-column prop="indexCode" label="索引号" width="120" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="row.indexCode" :value="row.indexCode" />
          <span v-else class="no-print">无需打印</span>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注" width="150" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * J2TabIndex — J2 底稿目录
 */
import { computed } from 'vue'
// @ts-ignore - GtIndexChip 全局注册
const GtIndexChip = resolveComponent('GtIndexChip')

const props = defineProps<{
  wpId: string
  projectId: string
}>()

const indexItems = computed(() => [
  { seq: '', content: '长期应付职工薪酬实质性程序表', indexCode: 'J2A', note: '' },
  { seq: '1', content: '长期应付职工薪酬-设定受益计划净资产审定表', indexCode: 'J2-1', note: '' },
  { seq: '2', content: '长期应付职工薪酬-设定受益计划净资产附注披露信息（上市公司）', indexCode: '', note: '无需打印' },
  { seq: '3', content: '长期应付职工薪酬-设定受益计划净资产附注披露信息（国有企业）', indexCode: '', note: '无需打印' },
  { seq: '4', content: '长期应付职工薪酬-设定受益计划净资产明细表', indexCode: 'J2-2', note: '' },
  { seq: '5', content: '调整分录汇总表', indexCode: 'J2-3', note: '' },
  { seq: '6', content: '计提情况检查表', indexCode: 'J2-4', note: '' },
])

import { resolveComponent } from 'vue'
</script>

<style scoped>
.j2-tab-index {
  padding: 16px;
}
.index-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  text-align: center;
}
.no-print {
  color: #909399;
  font-size: 12px;
}
</style>
