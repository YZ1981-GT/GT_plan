<template>
  <div class="gt-proc-panel">
    <!-- 顶部进度条（三色） -->
    <div class="gt-proc-panel-header">
      <h4>{{ procedureSheetName || '审计程序总控台' }}</h4>
      <div class="gt-proc-panel-stats">
        <el-tag size="small" type="success">已批准 {{ summary.approved }}/{{ summary.total }}</el-tag>
        <el-tag size="small" type="warning">已复核 {{ summary.reviewed }}/{{ summary.total }}</el-tag>
        <el-tag size="small" type="info">已填写 {{ summary.filled }}/{{ summary.total }}</el-tag>
      </div>
    </div>

    <div class="gt-proc-panel-progress">
      <el-progress
        :percentage="approvedRate"
        :stroke-width="10"
        :format="() => `批准 ${approvedRate}%`"
        status="success"
      />
      <el-progress
        :percentage="reviewedRate"
        :stroke-width="6"
        :format="() => `复核 ${reviewedRate}%`"
        :color="'#e6a23c'"
        :show-text="false"
      />
      <el-progress
        :percentage="filledRate"
        :stroke-width="4"
        :format="() => `填写 ${filledRate}%`"
        :color="'#909399'"
        :show-text="false"
      />
    </div>

    <!-- 程序行表格 -->
    <el-table :data="procedureStatus.rows.value" size="small" stripe height="320">
      <el-table-column label="行号" prop="row" width="60" />
      <el-table-column label="程序" prop="description" min-width="200" show-overflow-tooltip />
      <el-table-column label="程序分类" width="200">
        <template #default="{ row }">
          <!-- E1 Sprint 2 Task 2.39: el-checkbox-group（常规★/备选/IPO 应对） -->
          <el-checkbox-group
            :model-value="rowCategoryArray(row)"
            size="small"
            @change="(v: (string | number | boolean)[]) => onRowCategoryChange(row, v.map(String))"
          >
            <el-checkbox value="常规★">常规★</el-checkbox>
            <el-checkbox value="备选">备选</el-checkbox>
            <el-checkbox value="IPO 应对">IPO 应对</el-checkbox>
          </el-checkbox-group>
        </template>
      </el-table-column>
      <el-table-column label="认定" width="180">
        <template #default="{ row }">
          <el-tag
            v-for="a in row.assertions || []"
            :key="a"
            size="small"
            class="gt-proc-panel-assertion-tag"
            type="info"
            effect="plain"
          >{{ a }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="底稿索引号" width="160">
        <template #default="{ row }">
          <el-link
            v-for="ref in row.workpaper_refs || []"
            :key="ref"
            type="primary"
            :underline="false"
            class="gt-proc-panel-wp-link"
            @click="onWpRefClick(ref)"
          >{{ ref }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTagType(row.status)">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'pending'"
            size="small"
            type="primary"
            text
            @click="markStatus(row, 'filled')"
          >标记填写</el-button>
          <el-button
            v-if="row.status === 'filled'"
            size="small"
            type="warning"
            text
            @click="markStatus(row, 'reviewed')"
          >标记复核</el-button>
          <el-button
            v-if="row.status === 'reviewed'"
            size="small"
            type="success"
            text
            @click="markStatus(row, 'approved')"
          >标记批准</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="procedureStatus.rows.value.length === 0" class="gt-proc-panel-empty">
      暂无程序数据，请先在总控台 sheet 中录入
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ProcedureControlPanel — 通用程序总控台（Sprint 2 Task 2.6 + 2.14 + 2.39）
 *
 * 通用方案，可推广到 D-N 全部 89 个底稿（D2A/F2A/H1A 等）。
 *
 * Props:
 *   wpCode: 底稿编码（如 'E1' / 'D2'）
 *   procedureSheetName: 程序表 sheet 名（如 '货币资金实质性程序表E1A'）
 *   projectId, wpId
 */
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useProcedureStatus, type ProcedureRow, type ProcedureRowStatus } from '@/composables/useProcedureStatus'
import { eventBus } from '@/utils/eventBus'

interface Props {
  projectId: string
  wpId: string
  wpCode: string
  procedureSheetName?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'category-change': [row: string, categories: string[]]
  'wp-ref-click': [ref: string]
}>()

// sheet_key 命名约定：'e1a' / 'd2a' / 'f2a'... 取 wp_code 小写 + 'a'
const sheetKey = computed(() => `${props.wpCode.toLowerCase()}a`)

const procedureStatus = useProcedureStatus(props.projectId, props.wpId, sheetKey.value)

const summary = computed(() => procedureStatus.summary.value)
const filledRate = computed(() => procedureStatus.filledRate.value)
const reviewedRate = computed(() => procedureStatus.reviewedRate.value)
const approvedRate = computed(() => procedureStatus.approvedRate.value)

function statusTagType(s: string): 'info' | 'warning' | 'success' | 'danger' {
  switch (s) {
    case 'pending':
      return 'info'
    case 'filled':
      return 'warning'
    case 'reviewed':
      return 'warning'
    case 'approved':
      return 'success'
    default:
      return 'info'
  }
}

function statusLabel(s: string): string {
  return {
    pending: '未开始',
    filled: '已填写',
    reviewed: '已复核',
    approved: '已批准',
    not_applicable: '不适用',
  }[s] || s
}

function rowCategoryArray(row: ProcedureRow): string[] {
  const cat = row.category
  if (!cat) return []
  return cat.split(',').map((s) => s.trim()).filter(Boolean)
}

function onRowCategoryChange(row: ProcedureRow, value: string[]) {
  procedureStatus.markStatus(row.row, row.status, { category: value.join(',') })
  emit('category-change', row.row, value)
  eventBus.emit('procedure-status:changed', {
    projectId: props.projectId,
    wpId: props.wpId,
    sheetKey: sheetKey.value,
    row: row.row,
    status: row.status,
  })
}

async function markStatus(row: ProcedureRow, next: ProcedureRowStatus) {
  await procedureStatus.markStatus(row.row, next)
  ElMessage.success(`程序 ${row.row} 已标记为 ${statusLabel(next)}`)
  eventBus.emit('procedure-status:changed', {
    projectId: props.projectId,
    wpId: props.wpId,
    sheetKey: sheetKey.value,
    row: row.row,
    status: next,
  })
}

function onWpRefClick(ref: string) {
  emit('wp-ref-click', ref)
}
</script>

<style scoped>
.gt-proc-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-proc-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gt-proc-panel-header h4 {
  margin: 0;
  font-size: 14px;
  color: var(--gt-color-primary, #4b2d77);
}
.gt-proc-panel-stats {
  display: flex;
  gap: 6px;
}
.gt-proc-panel-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  background: var(--gt-color-bg-page, #f8f7fc);
  border-radius: 4px;
}
.gt-proc-panel-empty {
  text-align: center;
  padding: 30px;
  color: var(--gt-color-text-tertiary, #909399);
  font-size: 13px;
}
.gt-proc-panel-assertion-tag {
  margin-right: 2px;
}
.gt-proc-panel-wp-link {
  margin-right: 6px;
  font-size: 12px;
}
</style>
