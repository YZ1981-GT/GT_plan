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

    <template v-if="mode === 'HTML'">
      <h3 class="section-title">长期应付职工薪酬/设定受益计划净资产审定表</h3>

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
          <el-table-column prop="beginAudited" label="审定数" width="110" align="right">
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
          <el-table-column prop="endAudited" label="审定数" width="110" align="right">
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
  </div>
</template>

<script setup lang="ts">
/**
 * J2TabAdjudication — J2-1 审定表（三区块 + 67公式 + 精算假设面板）
 */
import { ref, computed, onMounted } from 'vue'
import { useJ2Adjudication } from '@/composables/workpaper/j2/useJ2Adjudication'
import { useJ2DualMode } from '@/composables/workpaper/j2/useJ2DualMode'

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

function handleExport(cmd: string) {
  // placeholder — will wire to useJ2ImportExport
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
