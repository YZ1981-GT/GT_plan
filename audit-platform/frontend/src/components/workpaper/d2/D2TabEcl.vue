<script setup lang="ts">
/**
 * D2TabEcl — ECL测算D2-9+D2-10
 * el-tabs: 单项ECL(D2-9) | 计量测试(D2-10)
 * D2-9: 8列 + 合计 + 差异高亮
 * D2-10: 折现法 + 迁徙率矩阵
 */
import { ref, inject, toRef, type Ref } from 'vue'
import { useD2Ecl, type EclSingleRow, type MigrationRateRow, type EclDiscountRow } from '../composables/useD2Ecl'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.debtorName || row?.fromBand || 'unknown'
  openReviewDialog(`D2-ecl-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })
const activeTab = ref('single')

const {
  singleRows,
  singleTotal,
  discountRows,
  migrationMatrix,
  outputLossRates,
  migrationChangeWarning,
  importFromDetail,
  addSingleRow,
  removeSingleRow,
  addDiscountRow,
  removeDiscountRow,
  updateCell,
  updateScenario,
} = useD2Ecl({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

function fmtPct(v: number): string {
  if (v === 0) return '-'
  return (v * 100).toFixed(2) + '%'
}
</script>

<template>
  <div class="d2-tab-ecl">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <!-- D2-9 单项ECL -->
      <el-tab-pane label="单项ECL (D2-9)" name="single">
        <div class="section-actions">
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addSingleRow">添加债务人</el-button>
          <el-button size="small" :disabled="isReadonly" @click="importFromDetail">从D2-2导入单项计提</el-button>
        </div>

        <el-table :data="singleRows" border size="small" style="width: 100%">
          <el-table-column label="债务人" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
              <span v-else>{{ row.debtorName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定余额" width="120" align="right">
            <template #default="{ row }">{{ displayPrefs.fmtAmount(row.auditedBalance) }}</template>
          </el-table-column>
          <el-table-column label="预期损失率" width="100" align="right">
            <template #default="{ row }">{{ fmtPct(row.expectedLossRate) }}</template>
          </el-table-column>
          <el-table-column label="应计提" width="120" align="right">
            <template #default="{ row }">{{ displayPrefs.fmtAmount(row.shouldProvision) }}</template>
          </el-table-column>
          <el-table-column label="实际余额" width="120" align="right">
            <template #default="{ row }">{{ displayPrefs.fmtAmount(row.actualBalance) }}</template>
          </el-table-column>
          <el-table-column label="差异" width="110" align="right">
            <template #default="{ row }">
              <span :style="{ color: row.difference !== 0 ? '#f56c6c' : '' }">{{ displayPrefs.fmtAmount(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计提依据" min-width="100">
            <template #default="{ row }">{{ row.basis || '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="60" v-if="!isReadonly">
            <template #default="{ row }">
              <el-button type="danger" link size="small" @click="removeSingleRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="total-bar">
          <span class="total-label">合计</span>
          <span>审定余额: {{ displayPrefs.fmtAmount(singleTotal.auditedBalance) }}</span>
          <span>应计提: {{ displayPrefs.fmtAmount(singleTotal.shouldProvision) }}</span>
          <span :style="{ color: singleTotal.difference !== 0 ? '#f56c6c' : '' }">
            差异: {{ displayPrefs.fmtAmount(singleTotal.difference) }}
          </span>
        </div>
      </el-tab-pane>

      <!-- D2-10 计量测试 -->
      <el-tab-pane label="计量测试 (D2-10)" name="measurement">
        <!-- 迁徙率变动警告 -->
        <el-alert v-if="migrationChangeWarning" type="warning" :closable="false" class="migration-alert">
          {{ migrationChangeWarning }}
        </el-alert>

        <!-- 折现法区域 -->
        <div class="sub-section">
          <div class="sub-header">
            <span class="sub-title">单项折现法ECL</span>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addDiscountRow">添加债务人</el-button>
          </div>
          <el-collapse v-if="discountRows.length > 0">
            <el-collapse-item v-for="dr in discountRows" :key="dr.rowId" :title="`${dr.debtorName || '未命名'} - 余额${displayPrefs.fmtAmount(dr.balance)}`">
              <div class="scenario-grid">
                <div v-for="(s, idx) in dr.scenarios" :key="idx" class="scenario-item">
                  <span class="scenario-name">{{ s.scenarioName }}</span>
                  <span>概率: {{ (s.probability * 100).toFixed(0) }}%</span>
                  <span>现值: {{ displayPrefs.fmtAmount(s.presentValue) }}</span>
                  <span>加权: {{ displayPrefs.fmtAmount(s.weighted) }}</span>
                </div>
              </div>
              <div class="discount-result">
                预期损失率: <b>{{ fmtPct(dr.expectedLossRate) }}</b>
                <el-button v-if="!isReadonly" type="danger" link size="small" style="margin-left:12px" @click="removeDiscountRow(dr.rowId)">删除</el-button>
              </div>
            </el-collapse-item>
          </el-collapse>
          <el-empty v-else description="暂无折现法ECL数据" :image-size="40" />
        </div>

        <!-- 迁徙率矩阵 -->
        <div class="sub-section">
          <div class="sub-header">
            <span class="sub-title">组合迁徙率矩阵</span>
          </div>
          <el-table :data="migrationMatrix" border size="small" style="width: 100%">
            <el-table-column prop="agingBand" label="账龄段" width="100" />
            <el-table-column label="第1年" width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.year1Rate) }}</template>
            </el-table-column>
            <el-table-column label="第2年" width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.year2Rate) }}</template>
            </el-table-column>
            <el-table-column label="第3年" width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.year3Rate) }}</template>
            </el-table-column>
            <el-table-column label="平均迁徙率" width="100" align="right">
              <template #default="{ row }">{{ fmtPct(row.avgRate) }}</template>
            </el-table-column>
            <el-table-column label="预期损失率" width="110" align="right">
              <template #default="{ row }">
                <span style="font-weight:600">{{ fmtPct(row.expectedLossRate) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.d2-tab-ecl { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.section-actions { margin-bottom: 10px; display: flex; gap: 8px; }
.total-bar {
  display: flex; gap: 24px; padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px; font-weight: 600;
}
.total-label { font-weight: 700; }
.migration-alert { margin-bottom: 12px; }
.sub-section { margin-bottom: 20px; }
.sub-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sub-title { font-weight: 600; font-size: 14px; }
.scenario-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 8px; }
.scenario-item { display: flex; flex-direction: column; gap: 2px; font-size: 12px; padding: 6px; background: #f5f7fa; border-radius: 4px; }
.scenario-name { font-weight: 600; }
.discount-result { font-size: 13px; padding: 6px 0; }
</style>
