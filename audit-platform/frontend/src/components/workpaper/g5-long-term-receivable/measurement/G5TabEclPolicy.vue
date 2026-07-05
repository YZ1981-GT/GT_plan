<template>
  <div class="g5-ecl-policy">
    <h3 class="sheet-title">G5-8 会计政策检查</h3>

    <el-card shadow="never" class="section-card">
      <template #header><div class="section-header"><span>（一）基本政策</span><el-button size="small" type="primary" text>AI</el-button></div></template>
      <el-table :data="policy.section1.value" border size="small" style="font-size:13px">
        <el-table-column prop="checkItem" label="检查项" min-width="140" />
        <el-table-column prop="requirement" label="要求" min-width="120" />
        <el-table-column label="企业政策" min-width="120">
          <template #default="{ row }"><el-input v-model="row.companyPolicy" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="合规性" width="100">
          <template #default="{ row }">
            <el-select v-model="row.compliance" size="small" :disabled="props.readonly">
              <el-option label="合规" value="合规" /><el-option label="不合规" value="不合规" /><el-option label="待核实" value="待核实" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="120">
          <template #default="{ row }"><el-input v-model="row.explanation" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <span>（二）ECL 参数</span>
          <div><el-button size="small" type="primary" text>AI</el-button>
          <el-button size="small" plain @click="policy.addSection2Row()" :disabled="props.readonly">+ 新增</el-button></div>
        </div>
      </template>
      <el-table :data="policy.section2.value" border size="small" style="font-size:13px">
        <el-table-column label="检查项" min-width="140">
          <template #default="{ row }"><el-input v-model="row.checkItem" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="要求" min-width="120">
          <template #default="{ row }"><el-input v-model="row.requirement" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="企业政策" min-width="120">
          <template #default="{ row }"><el-input v-model="row.companyPolicy" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
        <el-table-column label="合规性" width="100">
          <template #default="{ row }">
            <el-select v-model="row.compliance" size="small" :disabled="props.readonly">
              <el-option label="合规" value="合规" /><el-option label="不合规" value="不合规" /><el-option label="待核实" value="待核实" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="120">
          <template #default="{ row }"><el-input v-model="row.explanation" size="small" :disabled="props.readonly" /></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><div class="section-header"><span>综合结论</span><el-button size="small" type="primary" text>AI</el-button></div></template>
      <el-input v-model="policy.conclusion.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="props.readonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useG5EclPolicy } from '../../composables/useG5EclPolicy'
const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const policy = useG5EclPolicy()
</script>

<style scoped>
.g5-ecl-policy { font-size: 13px; padding: 4px; }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
.section-card { margin-bottom: 12px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
</style>
