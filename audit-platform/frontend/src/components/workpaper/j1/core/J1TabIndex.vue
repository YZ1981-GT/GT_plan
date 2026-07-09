<template>
  <div class="j1-tab-index">
    <el-card shadow="never">
      <template #header>
        <span class="section-title">底稿目录</span>
      </template>
      <el-table :data="indexRows" border stripe size="small" style="font-size: 13px">
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="content" label="内容" min-width="280" />
        <el-table-column prop="indexCode" label="索引号" width="100" align="center" />
        <el-table-column prop="remark" label="备注" width="120" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * J1TabIndex — 底稿目录
 * 列出J1系列全部底稿编码及索引
 */
const indexRows = [
  { seq: 1, content: '应付职工薪酬实质性程序表', indexCode: 'J1A', remark: '' },
  { seq: 2, content: '应付职工薪酬审定表', indexCode: 'J1-1', remark: '' },
  { seq: 3, content: '应付职工薪酬附注披露表（上市公司）', indexCode: '无需打印', remark: '' },
  { seq: 4, content: '应付职工薪酬附注披露表（国有企业）', indexCode: '无需打印', remark: '' },
  { seq: 5, content: '应付职工薪酬明细表', indexCode: 'J1-2', remark: '' },
  { seq: 6, content: '调整分录汇总表', indexCode: 'J1-3', remark: '' },
  { seq: 7, content: '月度分析表', indexCode: 'J1-4', remark: '' },
  { seq: 8, content: '与同行业对比分析表', indexCode: 'J1-5', remark: '' },
  { seq: 9, content: '计提情况检查表', indexCode: 'J1-6', remark: '' },
  { seq: 10, content: '分配情况检查表', indexCode: 'J1-7', remark: '' },
  { seq: 11, content: '检查表', indexCode: 'J1-8', remark: '' },
  { seq: 12, content: '非货币性福利检查表', indexCode: 'J1-9', remark: '' },
  { seq: 13, content: '辞退福利检查表', indexCode: 'J1-10', remark: '' },
]
</script>

<style scoped>
.j1-tab-index { padding: 16px; }
.section-title { font-weight: 600; font-size: 15px; }
</style>
