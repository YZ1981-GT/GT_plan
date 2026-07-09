<template>
  <div class="j1-tab-nonmonetary">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">非货币性福利检查表（J1-9）</span>
          <el-tag v-if="hasNonCompliant" type="warning" size="small">存在不合规项</el-tag>
        </div>
      </template>

      <el-table :data="rows" border size="small" style="font-size: 13px">
        <el-table-column prop="benefitType" label="福利形式" min-width="120" />
        <el-table-column prop="source" label="实物来源" min-width="120" />
        <el-table-column prop="measureMethod" label="计量方式" width="100" />
        <el-table-column prop="amount" label="金额" width="110" align="right">
          <template #default="{ row }">{{ row.amount?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" width="100" />
        <el-table-column prop="employeeCount" label="受益人数" width="80" align="right" />
        <el-table-column prop="checkResult" label="检查结论" min-width="100" />
        <el-table-column label="合规" width="60" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isCompliant ? 'success' : 'danger'" size="small">
              {{ row.isCompliant ? '✓' : '✗' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="total-summary">非货币性福利合计: {{ totalAmount?.toLocaleString() }} 元</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1NonMonetaryCheck } from '@/composables/workpaper/j1/useJ1NonMonetaryCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, totalAmount, hasNonCompliant, initFromHtmlData } = useJ1NonMonetaryCheck(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-nonmonetary { padding: 16px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.section-title { font-weight: 600; font-size: 15px; }
.total-summary { margin-top: 12px; font-size: 13px; color: #606266; padding: 8px; background: #f5f7fa; border-radius: 4px; }
</style>
