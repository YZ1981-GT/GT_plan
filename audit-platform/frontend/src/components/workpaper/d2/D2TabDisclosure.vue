<script setup lang="ts">
/**
 * D2TabDisclosure — 附注披露4版本
 * 顶部el-segmented: 上市公司|国企 + 二级: D2-1版|账龄版
 * 动态表, 跨sheet自动取数蓝色背景, 不一致警告
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD2Disclosure, type DisclosureVersion } from '../composables/useD2Disclosure'
import GtReviewDot from '../GtReviewDot.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.rowId || 'unknown'
  openReviewDialog(`D2-disclosure-${rowKey}-${field}`)
}


const {
  activeVersion,
  sections,
  crossSheetRefs,
  inconsistencyWarnings,
  switchVersion,
  updateCell,
  addRow,
  removeRow,
} = useD2Disclosure({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// 一级切换: 上市公司 vs 国企
const companyType = computed({
  get: () => activeVersion.value.startsWith('listed') ? 'listed' : 'soe',
  set: (v) => {
    const suffix = activeVersion.value.includes('aging') ? 'aging' : 'd2-1'
    switchVersion(`${v}-${suffix}` as DisclosureVersion)
  },
})

// 二级切换: D2-1版 vs 账龄版
const tableType = computed({
  get: () => activeVersion.value.includes('aging') ? 'aging' : 'd2-1',
  set: (v) => {
    const prefix = activeVersion.value.startsWith('listed') ? 'listed' : 'soe'
    switchVersion(`${prefix}-${v}` as DisclosureVersion)
  },
})
</script>

<template>
  <div class="d2-tab-disclosure">
    <div class="tab-toolbar">
      <div class="toolbar-left" />
    </div>

    <!-- 版本切换 -->
    <div class="version-switcher">
      <el-segmented v-model="companyType" :options="[
        { label: '上市公司', value: 'listed' },
        { label: '国企', value: 'soe' },
      ]" size="small" />
      <el-segmented v-model="tableType" :options="[
        { label: 'D2-1版', value: 'd2-1' },
        { label: '账龄版', value: 'aging' },
      ]" size="small" style="margin-left: 12px" />
    </div>

    <!-- 不一致警告 -->
    <el-alert
      v-for="(warning, idx) in inconsistencyWarnings"
      :key="idx"
      type="warning"
      :closable="false"
      class="inconsistency-alert"
    >
      <el-tooltip :content="warning" placement="top">
        <span>{{ warning }}</span>
      </el-tooltip>
    </el-alert>

    <!-- 各区块渲染 -->
    <el-card
      v-for="section in sections"
      :key="section.sectionId"
      class="section-card"
      shadow="hover"
    >
      <template #header>
        <div class="section-header">
          <span class="section-title">{{ section.title }}</span>
          <el-button v-if="!isReadonly" size="small" type="primary" link @click="addRow(section.sectionId)">+ 添加行</el-button>
        </div>
      </template>

      <el-table :data="[...section.rows, section.totalRow]" border size="small" style="width: 100%">
        <el-table-column label="项目" min-width="140">
          <template #default="{ row }">
            <el-input v-if="row.isEditable && !isReadonly" :model-value="row.label" size="small" @change="(v: string) => updateCell(section.sectionId, row.rowId, 'label', v)" />
            <span v-else :style="{ fontWeight: !row.isEditable ? '600' : 'normal' }">{{ row.label || '-' }}</span>
            <GtReviewDot v-if="row.rowId" row-prefix="D2-disclosure" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }">
            <el-tooltip v-if="!row.isEditable && crossSheetRefs.adjTotal > 0" content="跨sheet自动取数" placement="top">
              <span class="cross-sheet-cell">{{ displayPrefs.fmtAmount(row.amount) }}</span>
            </el-tooltip>
            <span v-else>{{ displayPrefs.fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="80" align="right">
          <template #default="{ row }">{{ row.ratio === 0 ? '-' : row.ratio.toFixed(1) + '%' }}</template>
        </el-table-column>
        <el-table-column label="坏账准备" width="120" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.badDebt) }}</template>
        </el-table-column>
        <el-table-column label="账面价值" width="120" align="right">
          <template #default="{ row }">
            <span style="font-weight:600">{{ displayPrefs.fmtAmount(row.netAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="80">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button v-if="row.isEditable" type="danger" link size="small" @click="removeRow(section.sectionId, row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.d2-tab-disclosure { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.version-switcher { margin-bottom: 12px; display: flex; align-items: center; }
.inconsistency-alert { margin-bottom: 8px; }
.section-card { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.section-title { font-weight: 600; font-size: 14px; }
.cross-sheet-cell { background-color: #e6f7ff; padding: 2px 4px; border-radius: 2px; }
</style>
