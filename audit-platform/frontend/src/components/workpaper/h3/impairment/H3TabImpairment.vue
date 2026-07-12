<template>
  <div class="h3-tab-impairment">
    <!-- 仅成本模式提示 -->
    <el-alert title="减值测算（H3-10）— 仅成本模式适用" type="info" :closable="false" show-icon class="mode-alert" />

    <!-- 区域1：减值迹象判断 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>一、减值迹象判断</span>
          <el-button size="small" @click="generateAI('H3-10-signs')">AI</el-button>
        </div>
      </template>
      <el-table :data="impairmentSigns" border size="small" class="audit-table">
        <el-table-column prop="seq" label="序号" width="50" align="center" />
        <el-table-column prop="indicator" label="减值迹象" min-width="200" />
        <el-table-column prop="exists" label="是否存在" width="100" align="center">
          <template #default="{ row, $index }">
            <el-select v-model="row.exists" size="small" :disabled="isReadonly" @change="onSignChange($index, row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="判断依据" min-width="200">
          <template #default="{ row, $index }">
            <el-input v-model="row.evidence" size="small" :disabled="isReadonly" @change="onSignChange($index, row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域2：减值测算表 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>二、减值测算表</span>
          <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-11 可收回金额')">→ H3-11 DCF模型</el-tag>
        </div>
      </template>
      <el-table :data="impairmentCalcRows" border size="small" class="audit-table">
        <el-table-column prop="assetName" label="资产名称" min-width="120" />
        <el-table-column prop="bookValue" label="账面价值" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.bookValue" size="small" :disabled="isReadonly" @change="onCalcChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="recoverableAmount" label="可收回金额" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.recoverableAmount" size="small" :disabled="isReadonly" @change="onCalcChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="减值=MAX(账面-可收回,0)" min-width="140" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-danger': row.impairmentLoss > 0 }">
              {{ fmtNum(row.impairmentLoss) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCalcChange($index, row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-10')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-10')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabImpairment.vue — H3-10 减值测算（仅成本模式）
 * 减值迹象+测算表+GtIndexChip→H3-11
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH3Impairment } from '../../composables/useH3Impairment'
import { useH3FormData } from '../../composables/useH3FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  impairmentSigns, impairmentCalcRows, updateSign, updateCalcRow,
} = useH3Impairment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const auditConclusion = ref(getValue('H3-10-conclusion') ?? '')

function onSignChange(index: number, row: any) { updateSign(index, row) }
function onCalcChange(index: number, row: any) { updateCalcRow(index, row) }

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.mode-alert { margin-bottom: 16px; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.nav-chip { cursor: pointer; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-danger { color: var(--el-color-danger); }
.conclusion-card { margin-top: 16px; }
.action-btns { display: flex; gap: 4px; }
</style>
