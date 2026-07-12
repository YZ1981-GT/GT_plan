<template>
  <div class="j2-tab-adjudication">
    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="mode" :options="['HTML', 'OnlyOffice']" size="small" />
      <div class="action-bar">
        <el-dropdown trigger="click" @command="handleExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：确认设定受益计划净负债/净资产、其他长期职工福利及辞退福利的期初、期末审定数的准确性，分析变动合理性，形成审定结论并回写试算平衡表（科目 2221）。
      </template>
    </el-alert>

    <template v-if="mode === 'HTML'">
      <div class="title-row">
        <h3 class="section-title">长期应付职工薪酬/设定受益计划净资产审定表</h3>
        <span class="chip-wrap"><GtIndexChip value="wp:J2-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ tableData.length }} 行</el-tag>
      </div>

      <!-- 审定表主表 -->
      <el-table :data="tableData" border stripe style="width: 100%; font-size: 13px">
        <el-table-column prop="label" label="项目名称" width="200" fixed />
        <!-- 期初 -->
        <el-table-column label="期初数" align="center">
          <el-table-column prop="beginUnadj" label="未审数" width="110" align="right">
            <template #default="{ row }">{{ fmtAmount(row.beginUnadj) }}</template>
          </el-table-column>
          <el-table-column prop="beginAje" label="账项调整" width="110" align="right">
            <template #default="{ row, $index }">
              <el-input-number
                v-if="!isReadonly && !row._isTotal"
                v-model="row.beginAje"
                :controls="false"
                size="small"
                @change="onRecalc"
              />
              <span v-else>{{ fmtAmount(row.beginAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="beginAudited" label="审定数" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula-cell" title="= 未审数 + 账项调整">{{ fmtAmount(row.beginAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 期末 -->
        <el-table-column label="期末数" align="center">
          <el-table-column prop="endUnadj" label="未审数" width="110" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endUnadj) }}</template>
          </el-table-column>
          <el-table-column prop="endAje" label="账项调整" width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly && !row._isTotal"
                v-model="row.endAje"
                :controls="false"
                size="small"
                @change="onRecalc"
              />
              <span v-else>{{ fmtAmount(row.endAje) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="endAudited" label="审定数" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <span class="formula-cell" title="= 未审数 + 账项调整">{{ fmtAmount(row.endAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 变动分析 -->
        <el-table-column label="本期未审vs上期审定" align="center">
          <el-table-column prop="changeAmountUnadj" label="变动额" width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.changeAmountUnadj) }}</template>
          </el-table-column>
          <el-table-column prop="changeRateUnadj" label="变动率" width="80" align="right">
            <template #default="{ row }">{{ fmtPercent(row.changeRateUnadj) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期审定vs上期审定" align="center">
          <el-table-column prop="changeAmountAudited" label="变动额" width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.changeAmountAudited) }}</template>
          </el-table-column>
          <el-table-column prop="changeRateAudited" label="变动率" width="80" align="right">
            <template #default="{ row }">{{ fmtPercent(row.changeRateAudited) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="reasonAnalysis" label="原因分析" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly && !row._isTotal"
              v-model="row.reasonAnalysis"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
            />
            <span v-else>{{ row.reasonAnalysis }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 审计结论 -->
      <el-card class="conclusion-card" shadow="never">
        <template #header>
          <span>审计结论</span>
        </template>
        <el-input
          v-model="conclusion"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="长期应付职工薪酬-设定受益计划审定结论..."
          :disabled="isReadonly"
        />
      </el-card>
    </template>

    <!-- OO降级模式 -->
    <div v-else class="oo-placeholder">
      <el-empty description="OnlyOffice 模式加载中..." />
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 依据 CAS 9《职工薪酬》，设定受益计划净负债 = 设定受益义务现值（DBO）- 计划资产公允价值。</p>
        <p>2. 灰色底纹"审定数"列为自动计算列（未审数+账项调整），不可手动编辑。</p>
        <p>3. 一年内到期的长期应付职工薪酬须重分类列示（withinOneYear 行）。</p>
        <p>4. 审定期末余额回写试算平衡表科目 2221，并与明细表（J2-2）、计提检查表（J2-4）勾稽一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * J2TabAdjudication — J2-1 审定表（三区块 + 67公式 + 精算假设面板）
 */
import { ref, computed, onMounted } from 'vue'
import { useJ2Adjudication } from '@/composables/workpaper/j2/useJ2Adjudication'
import { useJ2DualMode } from '@/composables/workpaper/j2/useJ2DualMode'
import { useJ2ImportExport } from '@/composables/workpaper/j2/useJ2ImportExport'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  save: []
}>()

const { mode } = useJ2DualMode()
const adjudication = useJ2Adjudication({ wpId: props.wpId, projectId: props.projectId })

const conclusion = ref('')

// 表格数据（含合计行）
const tableData = computed(() => {
  const rows = [
    { ...adjudication.definedBenefitRow.value, _isTotal: false },
    { ...adjudication.otherLongTermRow.value, _isTotal: false },
    { ...adjudication.terminationRow.value, _isTotal: false },
    { ...adjudication.totalRow.value, _isTotal: true },
    { ...adjudication.withinOneYearRow.value, _isTotal: false },
  ]
  return rows
})

function onRecalc() {
  adjudication.recalcAll()
}

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (val === 0) return '-'
  return (val * 100).toFixed(2) + '%'
}

const { exportTemplate, exportData, importData } = useJ2ImportExport({
  wpId: props.wpId,
  projectId: props.projectId,
})

function handleExport(cmd: string) {
  if (cmd === 'template') {
    exportTemplate()
  } else if (cmd === 'data') {
    exportData()
  } else if (cmd === 'import') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importData(file)
    }
    input.click()
  }
}

onMounted(() => {
  if (props.htmlData) {
    adjudication.loadFromHtmlData(props.htmlData)
  }
})
</script>

<style scoped>
.j2-tab-adjudication {
  padding: 16px;
}
.audit-objective { margin-bottom: 12px; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.mode-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.action-bar {
  display: flex;
  gap: 8px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  text-align: center;
  margin-bottom: 12px;
}
.formula-cell {
  border-bottom: 1px dashed #409eff;
  cursor: help;
}
.conclusion-card {
  margin-top: 16px;
}
.oo-placeholder {
  min-height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
