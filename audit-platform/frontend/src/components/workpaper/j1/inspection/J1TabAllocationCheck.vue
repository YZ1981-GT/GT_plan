<template>
  <div class="j1-tab-allocation">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">分配情况检查表（J1-7）</span>
          <el-tag v-if="hasImbalance" type="danger" size="small">分配不平衡</el-tag>
          <el-tag v-else type="success" size="small">分配闭合✓</el-tag>
        </div>
      </template>

      <el-table :data="rows" border size="small" style="font-size: 13px" max-height="500">
        <el-table-column prop="category" label="薪酬项目" min-width="120" fixed />
        <el-table-column prop="adminExpense" label="管理费用(→K9)" width="110" align="right" />
        <el-table-column prop="sellingExpense" label="销售费用(→K8)" width="110" align="right" />
        <el-table-column prop="productionCost" label="生产成本" width="100" align="right" />
        <el-table-column prop="manufacturing" label="制造费用" width="100" align="right" />
        <el-table-column prop="researchExpense" label="研发费用" width="100" align="right" />
        <el-table-column prop="construction" label="在建工程" width="100" align="right" />
        <el-table-column prop="otherExpense" label="其他" width="90" align="right" />
        <el-table-column label="行合计" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="行合计=Σ各科目">{{ row.rowTotal?.toLocaleString() }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditIncrease" label="贷方增加" width="110" align="right" />
        <el-table-column label="差额" width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'text-danger': !row.isBalanced }">{{ row.difference?.toFixed(2) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- K8/K9联动摘要 -->
      <div class="linkage-summary">
        <el-tag effect="plain">→ K9管理费用薪酬: {{ totalAdmin?.toLocaleString() }}</el-tag>
        <el-tag effect="plain" type="warning">→ K8销售费用薪酬: {{ totalSelling?.toLocaleString() }}</el-tag>
        <el-tag effect="plain" type="info">研发费用薪酬: {{ totalResearch?.toLocaleString() }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1AllocationCheck } from '@/composables/workpaper/j1/useJ1AllocationCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const { rows, totalAdmin, totalSelling, totalResearch, hasImbalance, initFromHtmlData } = useJ1AllocationCheck(htmlDataRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-allocation { padding: 16px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.section-title { font-weight: 600; font-size: 15px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.text-danger { color: #f56c6c; font-weight: 600; }
.linkage-summary { margin-top: 12px; display: flex; gap: 12px; flex-wrap: wrap; }
</style>
