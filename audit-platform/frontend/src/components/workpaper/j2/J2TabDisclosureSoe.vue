<template>
  <div class="j2-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证设定受益计划附注披露（国有企业口径）各项目期初余额、本期增减、期末余额的完整性与准确性，确保与审定表、明细表勾稽一致。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="section-title">长期应付职工薪酬/设定受益计划净资产附注披露信息（国有企业）</h3>
      <span class="chip-wrap"><GtIndexChip value="wp:J2-1" :context-project-id="projectId" /></span>
    </div>

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
        <el-table-column prop="endAmount" label="期末数" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="= 期初 + 增加 - 减少">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》及国有企业披露要求，按项目列示期初余额、本期增加、本期减少、期末余额。</p>
        <p>2. 灰色底纹"期末数"列为自动计算列（期初+增加-减少），不可手动编辑。</p>
        <p>3. 设定受益计划相关的精算损益、计划资产变动须单独说明。</p>
        <p>4. 附注金额应与审定表（J2-1）、明细表（J2-2）勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useJ2Disclosure } from '@/composables/workpaper/j2/useJ2Disclosure'
import GtIndexChip from '../GtIndexChip.vue'

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
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-size: 15px; font-weight: 600; margin: 0; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.disclosure-section { margin-bottom: 20px; }
.sub-title { font-size: 14px; font-weight: 500; margin-bottom: 8px; color: #303133; }
.formula-cell { border-bottom: 1px dashed #409eff; cursor: help; }
</style>
