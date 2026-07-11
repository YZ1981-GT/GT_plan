<template>
  <div class="g1-fv-test">
    <div class="section-head">
      <h3 class="sheet-title">G1-6 公允价值测试表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">新增证券</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-6-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证交易性金融资产公允价值计量的合理性，核实公允价值层级（Level 1/2/3）划分恰当、估值方法与关键输入合理，确认公允价值变动损益准确、完整。"
      class="objective-alert"
    />

    <div class="toolbar">
      <span class="stats">
        Level1: {{ stats.level1 }} /
        Level2: {{ stats.level2 }} /
        Level3: {{ stats.level3 }} /
        超阈值: {{ stats.overThreshold }}
      </span>
    </div>

    <div v-for="row in rows" :key="row.id" class="fv-card">
      <div class="fv-header">
        <el-input v-model="row.securityName" placeholder="证券名称" size="small" :disabled="isReadonly"
          @change="updateRow(row.id, { securityName: row.securityName })" />
        <el-input v-model="row.securityCode" placeholder="代码" size="small" :disabled="isReadonly"
          @change="updateRow(row.id, { securityCode: row.securityCode })" />
        <el-input-number v-model="row.quantity" placeholder="数量" size="small" :controls="false" :disabled="isReadonly"
          @change="updateRow(row.id, { quantity: row.quantity })" />
        <el-input-number v-model="row.bookValue" placeholder="账面值" size="small" :controls="false" :disabled="isReadonly"
          @change="updateRow(row.id, { bookValue: row.bookValue })" />
        <el-select v-model="row.fvLevel" size="small" :disabled="isReadonly"
          @change="updateRow(row.id, { fvLevel: row.fvLevel as 1|2|3 })">
          <el-option :value="1" label="Level 1" />
          <el-option :value="2" label="Level 2" />
          <el-option :value="3" label="Level 3" />
        </el-select>
        <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeRow(row.id)">删除</el-button>
      </div>

      <div v-if="row.fvLevel === 1" class="level-block level-1">
        <div class="level-title">Level 1 — 活跃市场报价</div>
        <div class="level-fields">
          <el-date-picker v-model="row.quoteDate" type="date" placeholder="报价日" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" @change="updateRow(row.id, { quoteDate: row.quoteDate })" />
          <el-input v-model="row.quoteSource" placeholder="报价来源" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { quoteSource: row.quoteSource })" />
          <el-input-number v-model="row.quoteValue" placeholder="报价" size="small" :controls="false" :disabled="isReadonly"
            @change="updateRow(row.id, { quoteValue: row.quoteValue })" />
          <span class="formula-cell" title="市值 = 数量 × 报价">市值：{{ row.marketValue.toLocaleString() }}</span>
          <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.level1Diff) > 0.01 }" title="差异 = 市值 - 账面值">
            差异：{{ row.level1Diff.toLocaleString() }}
          </span>
        </div>
      </div>

      <div v-else-if="row.fvLevel === 2" class="level-block level-2">
        <div class="level-title">Level 2 — 可观察输入</div>
        <div class="level-fields">
          <el-input v-model="row.observableDesc" placeholder="可观察输入描述" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { observableDesc: row.observableDesc })" />
          <el-input v-model="row.valuationMethod" placeholder="估值方法" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { valuationMethod: row.valuationMethod })" />
          <el-input-number v-model="row.level2Result" placeholder="估值结果" size="small" :controls="false" :disabled="isReadonly"
            @change="updateRow(row.id, { level2Result: row.level2Result })" />
          <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.level2Diff) > 0.01 }" title="差异 = 估值结果 - 账面值">
            差异：{{ row.level2Diff.toLocaleString() }}
          </span>
        </div>
      </div>

      <div v-else class="level-block level-3">
        <div class="level-title">Level 3 — 不可观察输入</div>
        <div class="level-fields">
          <el-input v-model="row.unobservableInput" placeholder="不可观察输入" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { unobservableInput: row.unobservableInput })" />
          <el-input v-model="row.assumption" placeholder="估值假设" size="small" :disabled="isReadonly"
            @change="updateRow(row.id, { assumption: row.assumption })" />
          <el-input-number v-model="row.level3Result" placeholder="估值结果" size="small" :controls="false" :disabled="isReadonly"
            @change="updateRow(row.id, { level3Result: row.level3Result })" />
          <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.level3Diff) > 0.01 }" title="差异 = 估值结果 - 账面值">
            差异：{{ row.level3Diff.toLocaleString() }}
          </span>
        </div>
      </div>

      <el-input v-model="row.remark" placeholder="备注" size="small" :disabled="isReadonly" class="row-remark"
        @change="updateRow(row.id, { remark: row.remark })" />
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="对公允价值计量层级划分与估值合理性的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>Level 1 采用活跃市场报价，市值 = 数量 × 报价，与账面值差异应说明原因。</li>
        <li>Level 2 采用可观察输入估值，需披露估值方法及可观察输入描述。</li>
        <li>Level 3 采用不可观察输入估值，需说明关键假设及敏感性分析。</li>
        <li>差异绝对值超过阈值（0.01）自动橙色高亮，应在审计结论中说明。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { toRef, inject } from 'vue'
import { useG1FairValueTest } from '../../composables/useG1FairValueTest'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// 解构到顶层：composable 返回的 ref/computed 只有作为顶层绑定才自动解包。
// 嵌套访问（fv.rows / fv.stats.level1 / fv.auditConclusion）不解包 →
// v-for 遍历 Ref（空列表）、stats.x 读为 undefined、v-model 绑定到 ref 对象。
const { rows, auditConclusion, stats, updateRow, addRow, removeRow } = useG1FairValueTest({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.g1-fv-test { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.toolbar { display: flex; gap: 16px; align-items: center; margin-bottom: 12px; }
.stats { color: #606266; font-size: 12px; }
.fv-card { border: 1px solid #ebeef5; border-radius: 4px; padding: 12px; margin-bottom: 12px; }
.fv-header { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.level-block { background: #f5f7fa; padding: 10px; border-radius: 4px; margin-bottom: 8px; }
.level-title { font-weight: 600; margin-bottom: 8px; font-size: 12px; color: #409eff; }
.level-2 .level-title { color: #67c23a; }
.level-3 .level-title { color: #e6a23c; }
.level-fields { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.row-remark { margin-top: 4px; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
