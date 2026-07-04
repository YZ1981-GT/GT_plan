<template>
  <div class="g1-fv-test">
    <h3 class="sheet-title">G1-6 公允价值测试表</h3>
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="fv.addRow()">新增证券</el-button>
      <span class="stats">
        Level1: {{ fv.stats.level1 }} /
        Level2: {{ fv.stats.level2 }} /
        Level3: {{ fv.stats.level3 }} /
        超阈值: {{ fv.stats.overThreshold }}
      </span>
    </div>

    <div v-for="row in fv.rows" :key="row.id" class="fv-card">
      <div class="fv-header">
        <el-input v-model="row.securityName" placeholder="证券名称" size="small" :disabled="isReadonly"
          @change="fv.updateRow(row.id, { securityName: row.securityName })" />
        <el-input v-model="row.securityCode" placeholder="代码" size="small" :disabled="isReadonly"
          @change="fv.updateRow(row.id, { securityCode: row.securityCode })" />
        <el-input-number v-model="row.quantity" placeholder="数量" size="small" :controls="false" :disabled="isReadonly"
          @change="fv.updateRow(row.id, { quantity: row.quantity })" />
        <el-input-number v-model="row.bookValue" placeholder="账面值" size="small" :controls="false" :disabled="isReadonly"
          @change="fv.updateRow(row.id, { bookValue: row.bookValue })" />
        <el-select v-model="row.fvLevel" size="small" :disabled="isReadonly"
          @change="fv.updateRow(row.id, { fvLevel: row.fvLevel as 1|2|3 })">
          <el-option :value="1" label="Level 1" />
          <el-option :value="2" label="Level 2" />
          <el-option :value="3" label="Level 3" />
        </el-select>
        <el-button v-if="!isReadonly" size="small" type="danger" link @click="fv.removeRow(row.id)">删除</el-button>
      </div>

      <div v-if="row.fvLevel === 1" class="level-block level-1">
        <div class="level-title">Level 1 — 活跃市场报价</div>
        <div class="level-fields">
          <el-date-picker v-model="row.quoteDate" type="date" placeholder="报价日" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" @change="fv.updateRow(row.id, { quoteDate: row.quoteDate })" />
          <el-input v-model="row.quoteSource" placeholder="报价来源" size="small" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { quoteSource: row.quoteSource })" />
          <el-input-number v-model="row.quoteValue" placeholder="报价" size="small" :controls="false" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { quoteValue: row.quoteValue })" />
          <span>市值：{{ row.marketValue.toLocaleString() }}</span>
          <span :class="{ 'diff-warn': Math.abs(row.level1Diff) > 0.01 }">
            差异：{{ row.level1Diff.toLocaleString() }}
          </span>
        </div>
      </div>

      <div v-else-if="row.fvLevel === 2" class="level-block level-2">
        <div class="level-title">Level 2 — 可观察输入</div>
        <div class="level-fields">
          <el-input v-model="row.observableDesc" placeholder="可观察输入描述" size="small" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { observableDesc: row.observableDesc })" />
          <el-input v-model="row.valuationMethod" placeholder="估值方法" size="small" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { valuationMethod: row.valuationMethod })" />
          <el-input-number v-model="row.level2Result" placeholder="估值结果" size="small" :controls="false" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { level2Result: row.level2Result })" />
          <span :class="{ 'diff-warn': Math.abs(row.level2Diff) > 0.01 }">
            差异：{{ row.level2Diff.toLocaleString() }}
          </span>
        </div>
      </div>

      <div v-else class="level-block level-3">
        <div class="level-title">Level 3 — 不可观察输入</div>
        <div class="level-fields">
          <el-input v-model="row.unobservableInput" placeholder="不可观察输入" size="small" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { unobservableInput: row.unobservableInput })" />
          <el-input v-model="row.assumption" placeholder="估值假设" size="small" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { assumption: row.assumption })" />
          <el-input-number v-model="row.level3Result" placeholder="估值结果" size="small" :controls="false" :disabled="isReadonly"
            @change="fv.updateRow(row.id, { level3Result: row.level3Result })" />
          <span :class="{ 'diff-warn': Math.abs(row.level3Diff) > 0.01 }">
            差异：{{ row.level3Diff.toLocaleString() }}
          </span>
        </div>
      </div>

      <el-input v-model="row.remark" placeholder="备注" size="small" :disabled="isReadonly" class="row-remark"
        @change="fv.updateRow(row.id, { remark: row.remark })" />
    </div>

    <div class="audit-conclusion">
      <h4>审计结论</h4>
      <el-input v-model="fv.auditConclusion" type="textarea" :rows="3" :disabled="isReadonly" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useG1FairValueTest } from '../../composables/useG1FairValueTest'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const fv = useG1FairValueTest({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.g1-fv-test { padding: 12px; font-size: 13px; }
.sheet-title { margin: 0 0 12px; font-size: 15px; }
.toolbar { display: flex; gap: 16px; align-items: center; margin-bottom: 12px; }
.stats { color: #606266; font-size: 12px; }
.fv-card { border: 1px solid #ebeef5; border-radius: 4px; padding: 12px; margin-bottom: 12px; }
.fv-header { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.level-block { background: #f5f7fa; padding: 10px; border-radius: 4px; margin-bottom: 8px; }
.level-title { font-weight: 600; margin-bottom: 8px; font-size: 12px; color: #409eff; }
.level-2 .level-title { color: #67c23a; }
.level-3 .level-title { color: #e6a23c; }
.level-fields { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.row-remark { margin-top: 4px; }
.audit-conclusion h4 { margin: 16px 0 6px; font-size: 13px; }
</style>
