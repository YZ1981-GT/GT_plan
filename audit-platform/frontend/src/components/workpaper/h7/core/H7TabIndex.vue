<template>
  <div class="h7-tab-index">
    <!-- E1 标准加法式增强：目录卡 + 结论看板 + 本循环 grid -->
    <GtCycleDirExtras
      wp-code="H7"
      cycle-letter="H"
      :wp-id="props.wpId"
      :project-id="props.projectId"
      :all-responses="props.allResponses"
      :sheets="dirSheets"
      @navigate="onDirNavigate"
      @open-handbook="openHandbook"
    />
    <H7PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

    <!-- 行业标识 + 计量模式 -->
    <div class="h7-index-header">
      <el-tag type="success" size="small">
        {{ industryLabel }}
      </el-tag>
      <el-tag :type="measurementModel === 'cost' ? 'primary' : 'warning'" size="small">
        {{ measurementModel === 'cost' ? '成本模式' : '公允价值模式' }}
      </el-tag>
      <el-tag type="info" size="small">共 {{ visibleCount }} 张底稿</el-tag>
    </div>

    <!-- 底稿目录表 -->
    <el-table :data="sheetList" stripe border size="small" class="h7-index-table" style="margin-top: 12px">
      <el-table-column prop="code" label="编号" width="80" />
      <el-table-column prop="name" label="底稿名称" min-width="200">
        <template #default="{ row }">
          <el-link type="primary" @click="emit('navigate-sheet', row.sheetName)">
            {{ row.name }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column prop="mode" label="模式" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.mode === 'cost'" size="small" type="info">成本</el-tag>
          <el-tag v-else-if="row.mode === 'fair'" size="small" type="warning">公允</el-tag>
          <el-tag v-else size="small">共用</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="120">
        <template #default="{ row }">
          <el-progress
            :percentage="row.progress"
            :stroke-width="6"
            :show-text="false"
            :color="row.progress === 100 ? '#67c23a' : '#409eff'"
          />
        </template>
      </el-table-column>
      <el-table-column prop="visible" label="可见" width="60" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.visible" color="#67c23a"><Check /></el-icon>
          <el-icon v-else color="#c0c4cc"><Close /></el-icon>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabIndex.vue — H7 生产性生物资产底稿目录
 *
 * 26行sheet列表 + 进度条 + 行业标识 + 计量模式指示
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 4.1
 * Requirements: 1.2
 */
import { computed, ref, defineAsyncComponent } from 'vue'
import { Check, Close } from '@element-plus/icons-vue'
import { useH7MeasurementModel, type MeasurementModelType } from '../../composables/useH7MeasurementModel'

const GtCycleDirExtras = defineAsyncComponent(() => import('../../GtCycleDirExtras.vue'))
const H7PreparationHandbookDialog = defineAsyncComponent(() => import('../H7PreparationHandbookDialog.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel?: MeasurementModelType
  industry?: string
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
}>()

// ─── E1 标准加法式增强：目录卡 + 结论看板 + 本循环 grid（GtCycleDirExtras） ───
const dirSheets = computed(() => {
  const seen = new Set<string>()
  const out: { code: string; navValue: string; name: string }[] = []
  for (const s of ALL_SHEETS) {
    if (seen.has(s.code)) continue
    seen.add(s.code)
    out.push({ code: s.code, navValue: s.sheetName, name: s.name })
  }
  return out
})
function onDirNavigate(navValue: string) {
  emit('navigate-sheet', navValue)
}
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

const industryLabel = computed(() => {
  const map: Record<string, string> = {
    agriculture: '农业',
    forestry: '林业',
    livestock: '畜牧业',
    fishery: '渔业',
  }
  return map[props.industry || ''] || '农林牧渔'
})

// Sheet 定义
interface SheetDef {
  code: string
  name: string
  sheetName: string
  mode: 'cost' | 'fair' | 'shared'
}

const ALL_SHEETS: SheetDef[] = [
  { code: 'H7A', name: '生物资产实质性程序表', sheetName: 'H7A 程序表', mode: 'shared' },
  { code: 'H7-1', name: '审定表（成本模式）', sheetName: 'H7-1 审定表', mode: 'cost' },
  { code: 'H7-1', name: '审定表（公允价值模式）', sheetName: 'H7-1 审定表', mode: 'fair' },
  { code: 'H7-2', name: '明细表（成本模式）', sheetName: 'H7-2 明细表', mode: 'cost' },
  { code: 'H7-2', name: '明细表（公允价值模式）', sheetName: 'H7-2 明细表', mode: 'fair' },
  { code: 'H7-3', name: '调整分录汇总', sheetName: 'H7-3 调整分录', mode: 'shared' },
  { code: 'H7-4', name: '会计政策估计检查表', sheetName: 'H7-4 政策检查', mode: 'shared' },
  { code: 'H7-5', name: '分析表', sheetName: 'H7-5 分析表', mode: 'shared' },
  { code: 'H7-6', name: '增加检查表（成本模式）', sheetName: 'H7-6 增加检查', mode: 'cost' },
  { code: 'H7-6', name: '增加检查表（公允价值模式）', sheetName: 'H7-6 增加检查', mode: 'fair' },
  { code: 'H7-7', name: '减少检查表（成本模式）', sheetName: 'H7-7 减少检查', mode: 'cost' },
  { code: 'H7-7', name: '减少检查表（公允价值模式）', sheetName: 'H7-7 减少检查', mode: 'fair' },
  { code: 'H7-8', name: '监盘计划', sheetName: 'H7-8 监盘计划', mode: 'shared' },
  { code: 'H7-9', name: '盘点检查表', sheetName: 'H7-9 盘点检查', mode: 'shared' },
  { code: 'H7-10', name: '监盘小结', sheetName: 'H7-10 监盘小结', mode: 'shared' },
  { code: 'H7-11', name: '折旧测算表', sheetName: 'H7-11 折旧测算', mode: 'cost' },
  { code: 'H7-12', name: '折旧分配分析表', sheetName: 'H7-12 折旧分配', mode: 'cost' },
  { code: 'H7-13', name: '公允价值复核表', sheetName: 'H7-13 公允价值复核', mode: 'fair' },
  { code: 'H7-14', name: '互转审核表', sheetName: 'H7-14 互转审核', mode: 'shared' },
  { code: 'H7-15', name: '减值测算表', sheetName: 'H7-15 减值测算', mode: 'cost' },
  { code: 'H7-16', name: '可收回金额测试表', sheetName: 'H7-16 可收回金额', mode: 'cost' },
  { code: 'H7-17', name: '关联交易检查表', sheetName: 'H7-17 关联交易', mode: 'shared' },
]

const sheetList = computed(() => {
  const model = props.measurementModel || 'cost'
  return ALL_SHEETS.map((s) => {
    const visible = s.mode === 'shared' || s.mode === model
    return {
      ...s,
      visible,
      progress: 0, // TODO: calculate from allResponses
    }
  })
})

const visibleCount = computed(() => sheetList.value.filter((s) => s.visible).length)
</script>

<style scoped>
.h7-tab-index {
  padding: 16px;
}
.h7-index-header {
  display: flex;
  gap: 8px;
  align-items: center;
}
.h7-index-table :deep(.el-table__cell) {
  font-size: var(--wp-font-size, 13px);
}
</style>
