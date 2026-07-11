<template>
  <div class="j2-tab-disclosure-listed">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证设定受益计划附注披露（上市公司口径）的完整性与准确性，包括计划性质、精算假设、义务与计划资产调节表、金额期初期末数，满足 CAS 30 与 CAS 9 披露要求。
      </template>
    </el-alert>

    <div class="title-row">
      <h3 class="section-title">长期应付职工薪酬/设定受益计划净资产附注披露信息（上市公司）</h3>
      <span class="chip-wrap"><GtIndexChip value="wp:J2-1" :context-project-id="projectId" /></span>
    </div>

    <div v-for="(section, sIdx) in disclosure.sections.value" :key="sIdx" class="disclosure-section">
      <h4 class="sub-title">{{ section.title }}</h4>
      <el-table :data="section.rows" border stripe style="width: 100%; font-size: 13px">
        <el-table-column prop="label" label="项目" min-width="250" />
        <el-table-column prop="endAmount" label="期末数" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.endAmount" :controls="false" size="small" />
            <span v-else>{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginAmount" label="期初数" width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginAmount" :controls="false" size="small" />
            <span v-else>{{ fmt(row.beginAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》及 CAS 30，上市公司须披露设定受益计划性质、风险及关键精算假设。</p>
        <p>2. 应列示设定受益义务现值、计划资产公允价值的期初至期末调节表。</p>
        <p>3. 披露折现率、薪酬增长率等关键假设的敏感性分析。</p>
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

const disclosure = useJ2Disclosure('listed')

function fmt(val: number): string {
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
.j2-tab-disclosure-listed { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-size: 15px; font-weight: 600; margin: 0; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.disclosure-section { margin-bottom: 20px; }
.sub-title { font-size: 14px; font-weight: 500; margin-bottom: 8px; color: #303133; }
</style>
