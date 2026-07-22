<template>
  <div class="h10-dir" data-testid="h10-directory">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="guide-alert"
      title="建议顺序：H10A 程序 → H10-2 明细 → H10-1「从明细带入」审定 → H10-3 调整 → H10-4 检查 → 附注披露（上市/国企）。6115 不含投房/金融工具/长投。"
    />

    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <div class="index-header">
      <h4 class="index-title">底稿架构</h4>
      <span class="index-hint">点击卡片跳转对应 sheet</span>
      <GtReviewTrigger section-id="H10-index-directory" />
    </div>
    <GtBArchitectureTree
      :active-sheet="''"
      :html-data="archHtmlData"
      @navigate="handleNavigate"
    />

    <el-card shadow="never" class="trace-card">
      <template #header>来源追溯链状态（H1/H2/H5~H8/I1 + H6；DR/NM）</template>
      <el-table :data="sourceTrace" border size="small" style="font-size:12px">
        <el-table-column label="来源底稿" prop="label" min-width="180" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'done' ? 'success' : row.status === 'pending' ? 'warning' : 'info'">
              {{ row.status === 'done' ? '已链接' : row.status === 'pending' ? '待确认' : '未编制' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>H6 清理结转经 EventBus 汇入明细；H10-1 可点「勾稽 H6」跨底稿拉数。试运行若属日常活动，关注 D4/营业收入列报（解释第15号），避免与 6115 双计。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H10TabDirectory — 对齐 H1/J1 GtBArchitectureTree 四阶段泳道
 */
import { computed, inject } from 'vue'
import GtBArchitectureTree from '../../GtBArchitectureTree.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import {
  resolveH10SheetLabel,
  isH10SheetComplete,
  getH10SourceTraceStatus,
} from '../../composables/h10SheetLabels'

const props = defineProps<{
  allResponses: Map<string, any>
  availableSheets?: Array<{ sheet_name?: string }>
}>()

interface NavRow {
  content: string
  index_ref: string
  component_type: string
  progressKeys: string[]
  code: string
}

const NAV_ROWS: NavRow[] = [
  { content: '资产处置损益实质性程序表H10A', index_ref: 'H10A', component_type: 'a-program-console', progressKeys: ['H10-proc-', 'H10A-'], code: 'H10A' },
  { content: '审定表H10-1', index_ref: 'H10-1', component_type: 'd-form-table', progressKeys: ['H10-adj-rows', 'H10-adj-tb'], code: 'H10-1' },
  { content: '明细表H10-2', index_ref: 'H10-2', component_type: 'd-form-table', progressKeys: ['H10-detail-rows'], code: 'H10-2' },
  { content: '调整分录汇总H10-3', index_ref: 'H10-3', component_type: 'd-form-table', progressKeys: ['H10-adjustment-rows'], code: 'H10-3' },
  { content: '检查表H10-4', index_ref: 'H10-4', component_type: 'd-form-table', progressKeys: ['H10-check-rows'], code: 'H10-4' },
  { content: '附注披露信息（上市公司）', index_ref: '附注上市', component_type: 'c-note-table', progressKeys: ['H10-disclosure-listed'], code: '附注上市' },
  { content: '附注披露信息（国有企业）', index_ref: '附注国企', component_type: 'c-note-table', progressKeys: ['H10-disclosure-soe'], code: '附注国企' },
]

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function keyMatches(mapKey: string, pk: string): boolean {
  if (mapKey === pk) return true
  if (pk.endsWith('-')) return mapKey.startsWith(pk)
  return mapKey.startsWith(`${pk}-`) || mapKey.startsWith(`${pk}_`)
}

function rowStatus(row: NavRow): string {
  if (isH10SheetComplete(row.code, props.allResponses)) return 'completed'
  if (row.progressKeys.length === 0) return ''
  const map = props.allResponses
  if (!map || map.size === 0) return 'pending'
  const keys = [...map.keys()]
  const hasData = row.progressKeys.some(
    (pk) => map.has(pk) || keys.some((k) => keyMatches(k, pk)),
  )
  return hasData ? 'completed' : 'pending'
}

const archHtmlData = computed(() => ({
  navigation_rows: NAV_ROWS.map((r, i) => ({
    seq: i + 1,
    content: r.content,
    sheet_name: resolveH10SheetLabel(r.code, props.availableSheets) || r.content,
    index_ref: r.index_ref,
    component_type: r.component_type,
    status: rowStatus(r),
  })),
}))

const applicableCount = computed(() => NAV_ROWS.length)
const completedCount = computed(() => NAV_ROWS.filter((r) => rowStatus(r) === 'completed').length)
const progressPercent = computed(() =>
  applicableCount.value === 0 ? 0 : Math.round((completedCount.value / applicableCount.value) * 100),
)
const sourceTrace = computed(() => getH10SourceTraceStatus(props.allResponses))

function handleNavigate(sheetName: string) {
  if (jumpToSection && sheetName) jumpToSection(sheetName)
}
</script>

<style scoped>
.h10-dir { font-size: var(--wp-font-size, 13px); padding: 4px 0; }
.guide-alert { margin-bottom: 12px; }
.progress-bar-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}
.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
  color: #606266;
}
.progress-text { font-weight: 600; color: #303133; }
.index-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.index-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.index-hint { font-size: 12px; color: #909399; }
.trace-card { margin-top: 16px; }
.methodology-hint { margin-top: 12px; font-size: 12px; color: #606266; }
</style>
