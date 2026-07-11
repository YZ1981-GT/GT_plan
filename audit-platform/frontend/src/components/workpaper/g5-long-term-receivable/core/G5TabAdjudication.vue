<template>
  <div class="g5-adjudication">
    <div class="section-head">
      <h3 class="sheet-title">G5-1 审定表</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G5-1" />
        <el-tag size="small" type="info">共 {{ flatRows.length }} 行</el-tag>
        <GtReviewTrigger section-id="g5-1-adjudication" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      核对长期应收款原值、坏账准备、净值及一年内到期非流动资产的期初期末审定数，验证与试算表勾稽一致，分析重大变动原因。
    </el-alert>

    <!-- TB差异提示 -->
    <div v-if="Math.abs(adjudication.variance.value) > 0.01" class="variance-alert">
      <el-alert type="error" :closable="false">
        试算表差异：{{ fmtAmount(adjudication.variance.value) }}（审定数 - 试算表）
      </el-alert>
    </div>

    <!-- 五层分组表格 -->
    <el-table
      :data="flatRows"
      :height="560"
      border
      stripe
      style="width: 100%; font-size: 13px"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="item" label="项目" min-width="160" fixed />
      <el-table-column label="期初" align="center">
        <el-table-column prop="openingUnadjusted" label="未审" min-width="90" align="right" />
        <el-table-column prop="openingAJE" label="AJE" min-width="80" align="right" />
        <el-table-column prop="openingRJE" label="RJE" min-width="80" align="right" />
        <el-table-column label="审定" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="未审+AJE+RJE">{{ fmtAmount(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="期末" align="center">
        <el-table-column prop="closingUnadjusted" label="未审" min-width="90" align="right" />
        <el-table-column prop="closingAJE" label="AJE" min-width="80" align="right" />
        <el-table-column prop="closingRJE" label="RJE" min-width="80" align="right" />
        <el-table-column label="审定" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="未审+AJE+RJE">{{ fmtAmount(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="变动额" min-width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末审定-期初审定">{{ fmtAmount(row.changeAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动率" min-width="80" align="right">
        <template #default="{ row }">
          <span
            :class="{ 'rate-warning': adjudication.needsReason(row) }"
            class="formula-cell"
            title="(期末-期初)/期初"
          >
            {{ row.changeRate !== null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="reasonAnalysis" label="原因分析" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="adjudication.needsReason(row)"
            v-model="row.reasonAnalysis"
            size="small"
            placeholder="必填"
            :disabled="props.readonly"
          />
          <span v-else>{{ row.reasonAnalysis || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>审定数 = 未审数 + AJE + RJE（期初、期末分别计算）</li>
        <li>三、净值 = 一、原值合计 − 二、坏账准备合计</li>
        <li>五、报表列示数 = 净值 − 四、一年内到期非流动资产</li>
        <li>变动率 = (期末审定 − 期初审定) / 期初审定，绝对值超 20% 需填写原因分析（CAS 1301）</li>
        <li>期末报表列示数应与试算表 1531 长期应收款审定余额一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useG5Adjudication } from '../../composables/useG5Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const adjudication = useG5Adjudication({
  wpId: props.wpId,
  projectId: props.projectId,
  htmlData: props.htmlData,
  isReadonly: props.readonly,
})

const flatRows = computed(() => adjudication.allRows.value)

function fmtAmount(v: number | null): string {
  if (v === null || v === undefined) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: any) {
  if (adjudication.needsReason(row) && !row.reasonAnalysis) return 'row-warning'
  return ''
}
</script>

<style scoped>
.g5-adjudication { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.variance-alert { margin-bottom: 8px; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.formula-cell {
  border-bottom: 1px dashed #999;
  cursor: help;
}
.rate-warning {
  color: #e6a23c;
  font-weight: 600;
}
:deep(.row-warning) { background-color: #fdf6ec !important; }
</style>
