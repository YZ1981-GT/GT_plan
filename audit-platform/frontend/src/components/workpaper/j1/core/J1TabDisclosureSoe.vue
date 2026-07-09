<template>
  <div class="j1-tab-disclosure-soe">
    <el-card shadow="never">
      <template #header><span class="section-title">应付职工薪酬附注披露信息（国有企业）</span></template>
      <el-table :data="rows" border size="small" style="font-size: 13px"
        :row-class-name="({ row }) => row.isSubtotal ? 'subtotal-row' : ''">
        <el-table-column prop="label" label="项  目" min-width="180" />
        <el-table-column label="期初余额" width="120" align="right">
          <template #default="{ row }">{{ row.beginBalance?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="本期增加" width="120" align="right">
          <template #default="{ row }">{{ row.increase?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="本期减少" width="120" align="right">
          <template #default="{ row }">{{ row.decrease?.toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="期末余额" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少(负债贷方)">{{ row.endBalance?.toLocaleString() }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1Disclosure } from '@/composables/workpaper/j1/useJ1Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

const htmlDataRef = ref(props.htmlData || {})
const modeRef = ref<'listed' | 'soe'>('soe')
const { rows, initFromHtmlData } = useJ1Disclosure(htmlDataRef, modeRef)

onMounted(() => { if (props.htmlData) initFromHtmlData(props.htmlData) })
</script>

<style scoped>
.j1-tab-disclosure-soe { padding: 16px; }
.section-title { font-weight: 600; font-size: 15px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.subtotal-row { background-color: #f5f7fa !important; font-weight: 600; }
</style>
