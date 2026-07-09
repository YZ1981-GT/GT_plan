<template>
  <div class="j3-tab-index">
    <!-- 底稿信息区 -->
    <el-card shadow="never" class="index-header">
      <div class="header-grid">
        <div class="header-item">
          <span class="label">被审计单位：</span>
          <span class="value">{{ clientName }}</span>
        </div>
        <div class="header-item">
          <span class="label">截止日：</span>
          <span class="value">{{ cutoffDate }}</span>
        </div>
        <div class="header-item">
          <span class="label">编制人：</span>
          <span class="value">{{ preparer }}</span>
        </div>
        <div class="header-item">
          <span class="label">编制日期：</span>
          <span class="value">{{ prepareDate }}</span>
        </div>
        <div class="header-item">
          <span class="label">复核人：</span>
          <span class="value">{{ reviewer }}</span>
        </div>
        <div class="header-item">
          <span class="label">复核日期：</span>
          <span class="value">{{ reviewDate }}</span>
        </div>
      </div>
    </el-card>

    <!-- 底稿目录 -->
    <el-card shadow="never" class="index-table">
      <template #header>
        <span style="font-weight: 600">底稿目录</span>
      </template>
      <el-table :data="indexItems" border size="small" style="width: 100%">
        <el-table-column prop="seq" label="序号" width="60" align="center" />
        <el-table-column prop="content" label="内容" min-width="300" />
        <el-table-column prop="indexCode" label="索引号" width="100" align="center">
          <template #default="{ row }">
            <el-link
              type="primary"
              @click="$emit('navigate-sheet', row.sheetName)"
            >
              {{ row.indexCode }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" width="200" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * J3TabIndex — J3 股份支付底稿目录
 *
 * 显示底稿信息头 + 底稿目录（可点击索引号跳转子sheet）。
 */
import { ref } from 'vue'

defineProps<{
  wpId: string
  projectId: string
  isReadonly?: boolean
}>()

defineEmits<{
  'navigate-sheet': [sheetName: string]
}>()

const clientName = ref('')
const cutoffDate = ref('')
const preparer = ref('')
const prepareDate = ref('')
const reviewer = ref('')
const reviewDate = ref('')

const indexItems = ref([
  { seq: 1, content: '股份支付实质性程序表', indexCode: 'J3A', sheetName: '股份支付实质性程序表 J3A', remark: '' },
  { seq: 2, content: '应付职工薪酬-股份支付情况表', indexCode: 'J3-1', sheetName: '股份支付情况表J3-1', remark: '' },
  { seq: 3, content: '应付职工薪酬-股份支付检查表', indexCode: 'J3-2', sheetName: '股份支付检查表J3-2', remark: '' },
])
</script>

<style scoped>
.j3-tab-index {
  padding: 16px;
  max-width: 900px;
}
.index-header {
  margin-bottom: 16px;
}
.header-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}
.header-item .label {
  color: #606266;
  font-size: 13px;
}
.header-item .value {
  font-size: 13px;
  font-weight: 500;
}
.index-table {
  margin-bottom: 16px;
}
</style>
