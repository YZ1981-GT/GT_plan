<template>
  <div class="j1-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：验证应付职工薪酬附注披露（国有企业口径）各项目期初余额、本期增减、期末余额的完整性与准确性，确保与审定表、明细表勾稽一致。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">应付职工薪酬附注披露信息（国有企业）</span>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        </div>
      </template>
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
        <el-table-column label="期末余额" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少(负债贷方)">{{ row.endBalance?.toLocaleString() }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9 及国有企业财务披露要求，按项目列示期初余额、本期增加（计提）、本期减少（发放）、期末余额。</p>
        <p>2. 灰色底纹"期末余额"列为自动计算列（期初+增加-减少，负债贷方口径），不可手动编辑。</p>
        <p>3. 附注披露金额应与审定表（J1-1）期末审定数、明细表（J1-2）勾稽一致。</p>
        <p>4. 工资、社保、住房公积金等分项须与分配情况检查表（J1-7）保持一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useJ1Disclosure } from '@/composables/workpaper/j1/useJ1Disclosure'
import GtIndexChip from '../../GtIndexChip.vue'

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
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.subtotal-row { background-color: #f5f7fa !important; font-weight: 600; }
</style>
