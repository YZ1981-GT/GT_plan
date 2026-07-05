<template>
  <div class="c24-summary-sheet">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C24-0 汇总表：记录数据来源信息、测试工具说明，以及各测试项（C24-1~5+本福特）的结论索引与汇总结论。</p>
    </div>

    <!-- 数据来源 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">数据来源</span>
      </div>
      <el-form label-width="100px" size="small" class="c24-form">
        <el-form-item label="应用名称">
          <el-input :model-value="formData.sourceAppName" :disabled="isReadonly" placeholder="如：用友/金蝶/SAP" @input="onFieldChange('sourceAppName', $event)" />
        </el-form-item>
        <el-form-item label="应用版本">
          <el-input :model-value="formData.sourceAppVersion" :disabled="isReadonly" placeholder="应用版本号" @input="onFieldChange('sourceAppVersion', $event)" />
        </el-form-item>
        <el-form-item label="导出时间">
          <el-date-picker :model-value="formData.sourceExportTime" :disabled="isReadonly" type="datetime" placeholder="数据导出时间" @change="onFieldChange('sourceExportTime', $event)" />
        </el-form-item>
        <el-form-item label="原始文件索引">
          <template v-if="formData.sourceFileRef && isReadonly">
            <GtIndexChip :value="formData.sourceFileRef" />
          </template>
          <el-input v-else :model-value="formData.sourceFileRef" :disabled="isReadonly" placeholder="原始导出文件索引号（如 B22A-4-3）" @input="onFieldChange('sourceFileRef', $event)" />
        </el-form-item>
      </el-form>
    </section>

    <!-- 测试工具 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试工具</span>
      </div>
      <el-form label-width="100px" size="small" class="c24-form">
        <el-form-item label="是否利用工具">
          <el-select :model-value="formData.toolUsed" :disabled="isReadonly" placeholder="请选择" @change="onFieldChange('toolUsed', $event)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="formData.toolUsed === '是'" label="工具名称">
          <el-select :model-value="formData.toolName" :disabled="isReadonly" placeholder="请选择工具" @change="onFieldChange('toolName', $event)">
            <el-option label="IDEA" value="IDEA" />
            <el-option label="IAS" value="IAS" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="formData.toolUsed === '是'" label="工具版本">
          <el-input :model-value="formData.toolVersion" :disabled="isReadonly" placeholder="工具版本号" @input="onFieldChange('toolVersion', $event)" />
        </el-form-item>
        <el-form-item v-if="formData.toolUsed === '是'" label="测试时间">
          <el-date-picker :model-value="formData.toolTime" :disabled="isReadonly" type="datetime" placeholder="执行测试时间" @change="onFieldChange('toolTime', $event)" />
        </el-form-item>
      </el-form>
    </section>

    <!-- 测试项结论索引 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试项目结论汇总</span>
      </div>
      <el-table :data="testItems" border size="small" class="c24-table">
        <el-table-column label="测试项" prop="label" min-width="200" />
        <el-table-column label="索引号" width="130">
          <template #default="{ row }">
            <GtIndexChip :value="row.indexRef" />
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="300">
          <template #default="{ row }">
            <span class="formula-cell" :title="`来源：${row.sheetName} 测试结论`">{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 汇总结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">汇总结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-0-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :model-value="formData.conclusion"
        :disabled="isReadonly"
        placeholder="请填写 C24 细节测试汇总结论"
        @input="onFieldChange('conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * C24SummarySheet — C24-0 汇总表
 * 数据来源+测试工具+各测试项结论索引+汇总结论
 */
import { computed, defineAsyncComponent } from 'vue'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

export interface C24SummaryFormData {
  sourceAppName: string
  sourceAppVersion: string
  sourceExportTime: string
  sourceFileRef: string
  toolUsed: string
  toolName: string
  toolVersion: string
  toolTime: string
  conclusion: string
}

const props = defineProps<{
  formData: C24SummaryFormData
  conclusions: Record<string, string>  // key=C24-1~5,benford → conclusion text
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update:field', field: keyof C24SummaryFormData, value: string): void
  (e: 'ai-suggest', fieldId: string): void
}>()

const testItems = computed(() => [
  { key: 'C24-1', sheetName: 'C24-1', indexRef: 'C24-1', label: 'C24-1 借贷方发生额完整性', conclusion: props.conclusions['C24-1'] || '' },
  { key: 'C24-2', sheetName: 'C24-2', indexRef: 'C24-2', label: 'C24-2 分录&余额表对比', conclusion: props.conclusions['C24-2'] || '' },
  { key: 'C24-3', sheetName: 'C24-3', indexRef: 'C24-3', label: 'C24-3 跳号测试', conclusion: props.conclusions['C24-3'] || '' },
  { key: 'C24-4', sheetName: 'C24-4', indexRef: 'C24-4', label: 'C24-4 异常账户测试', conclusion: props.conclusions['C24-4'] || '' },
  { key: 'C24-5', sheetName: 'C24-5', indexRef: 'C24-5', label: 'C24-5 异常分录测试', conclusion: props.conclusions['C24-5'] || '' },
  { key: 'benford', sheetName: '本福特', indexRef: 'C24', label: '本福特定律测试', conclusion: props.conclusions['benford'] || '' },
])

function onFieldChange(field: keyof C24SummaryFormData, value: any) {
  emit('update:field', field, value ?? '')
}
</script>

<style scoped>
.c24-summary-sheet { font-size: 13px; }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: 13px; color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-form { max-width: 600px; }
.c24-table { font-size: 13px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
</style>
