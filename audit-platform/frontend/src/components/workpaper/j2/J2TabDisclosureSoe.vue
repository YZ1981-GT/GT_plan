<template>
  <div class="j2-tab-disclosure-soe">
    <h3 class="section-title">长期应付职工薪酬/设定受益计划净资产附注披露信息（国有企业）</h3>

    <div v-for="(section, sIdx) in disclosure.sections.value" :key="sIdx" class="disclosure-section">
      <h4 class="sub-title">{{ section.title }}</h4>
      <el-table :data="section.rows" border stripe style="width: 100%; font-size: 13px">
        <el-table-column prop="label" label="项目" min-width="250" />
        <el-table-column prop="beginAmount" label="期初数" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginAmount" :controls="false" size="small" />
            <span v-else>{{ fmt(row.beginAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.increase !== undefined" v-model="row.increase" :controls="false" size="small" />
            <span v-else>{{ fmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && row.decrease !== undefined" v-model="row.decrease" :controls="false" size="small" />
            <span v-else>{{ fmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="endAmount" label="期末数" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 期初 + 增加 - 减少">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useJ2Disclosure } from '@/composables/workpaper/j2/useJ2Disclosure'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const disclosure = useJ2Disclosure('soe')

function fmt(val: number | undefined): string {
  if (!val) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(() => {
  if (props.htmlData) {
    disclosure.loadFromHtmlData(props.htmlData)
  } else {
    disclosure.initDefault()
  }
})
</script>

<style scoped>
.j2-tab-disclosure-soe { padding: 16px; }
.section-title { font-size: 15px; font-weight: 600; text-align: center; margin-bottom: 16px; }
.disclosure-section { margin-bottom: 20px; }
.sub-title { font-size: 14px; font-weight: 500; margin-bottom: 8px; color: #303133; }
.formula-cell { border-bottom: 1px dashed #409eff; cursor: help; }
</style>
