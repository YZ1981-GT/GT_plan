<template>
  <el-dialog append-to-body v-model="visible" title="质量自检结果" width="700px" @close="$emit('close')">
    <template v-if="result">
      <!-- 汇总 -->
      <div class="qc-header">
        <el-tag :type="result.passed ? 'success' : 'danger'" size="large">
          {{ result.passed ? '✓ 自检通过' : '✗ 存在问题' }}
        </el-tag>
        <span class="qc-time" v-if="result.check_timestamp">
          检查时间: {{ result.check_timestamp.slice(0, 19) }}
        </span>
      </div>

      <!-- 阻断级 -->
      <div v-if="blockingFindings.length" class="finding-group">
        <div class="group-header blocking">
          <span class="group-icon">🚫</span>
          阻断 ({{ blockingFindings.length }})
        </div>
        <div v-for="f in blockingFindings" :key="f.rule_id + f.message" class="finding-item blocking">
          <div class="finding-main">
            <el-tag type="danger" size="small">{{ f.rule_id }}</el-tag>
            <span class="finding-msg">{{ f.message }}</span>
          </div>
          <div class="finding-detail" v-if="f.cell_reference || f.expected_value">
            <span v-if="f.cell_reference" class="cell-ref" @click="$emit('cell-click', f.cell_reference)">
              📍 {{ f.cell_reference }}
            </span>
            <span v-if="f.expected_value">期望: {{ f.expected_value }}</span>
            <span v-if="f.actual_value">实际: {{ f.actual_value }}</span>
          </div>
        </div>
      </div>

      <!-- 警告级 -->
      <div v-if="warningFindings.length" class="finding-group">
        <div class="group-header warning">
          <span class="group-icon">⚠️</span>
          警告 ({{ warningFindings.length }})
        </div>
        <div v-for="f in warningFindings" :key="f.rule_id + f.message" class="finding-item warning">
          <div class="finding-main">
            <el-tag type="warning" size="small">{{ f.rule_id }}</el-tag>
            <span class="finding-msg">{{ f.message }}</span>
          </div>
          <div class="finding-detail" v-if="f.cell_reference || f.expected_value">
            <span v-if="f.cell_reference" class="cell-ref" @click="$emit('cell-click', f.cell_reference)">
              📍 {{ f.cell_reference }}
            </span>
            <span v-if="f.expected_value">期望: {{ f.expected_value }}</span>
            <span v-if="f.actual_value">实际: {{ f.actual_value }}</span>
          </div>
        </div>
      </div>

      <!-- 提示级 -->
      <div v-if="infoFindings.length" class="finding-group">
        <div class="group-header info">
          <span class="group-icon">ℹ️</span>
          提示 ({{ infoFindings.length }})
        </div>
        <div v-for="f in infoFindings" :key="f.rule_id + f.message" class="finding-item info">
          <div class="finding-main">
            <el-tag type="info" size="small">{{ f.rule_id }}</el-tag>
            <span class="finding-msg">{{ f.message }}</span>
          </div>
        </div>
      </div>

      <el-empty v-if="!result.findings?.length" description="无检查发现" :image-size="60" />
    </template>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        type="success"
        :disabled="hasBlocking"
        @click="$emit('submit-review')"
      >
        提交复核
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { QCResult, QCFinding } from '@/services/workpaperApi'

const props = defineProps<{ modelValue: boolean; result: QCResult | null }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'close'): void
  (e: 'cell-click', ref: string): void
  (e: 'submit-review'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const findings = computed<QCFinding[]>(() => props.result?.findings || [])
const blockingFindings = computed(() => findings.value.filter(f => f.severity === 'blocking'))
const warningFindings = computed(() => findings.value.filter(f => f.severity === 'warning'))
const infoFindings = computed(() => findings.value.filter(f => f.severity === 'info'))
const hasBlocking = computed(() => blockingFindings.value.length > 0)
</script>

<style scoped>
.qc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.qc-time { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.finding-group { margin-bottom: 16px; }
.group-header {
  font-weight: 600; font-size: var(--gt-font-size-sm); padding: 6px 10px;
  border-radius: var(--gt-radius-sm); margin-bottom: 8px;
}
.group-header.blocking { background: var(--gt-bg-danger); color: var(--gt-color-coral); }
.group-header.warning { background: var(--gt-bg-warning); color: var(--gt-color-wheat); }
.group-header.info { background: var(--gt-color-bg); color: var(--gt-color-info); }
.finding-item {
  padding: 8px 12px; border-left: 3px solid; margin-bottom: 4px;
  border-radius: 0 var(--gt-radius-sm) var(--gt-radius-sm) 0;
  background: var(--gt-color-bg);
}
.finding-item.blocking { border-color: #f56c6c; }
.finding-item.warning { border-color: #e6a23c; }
.finding-item.info { border-color: #c0c4cc; }
.finding-main { display: flex; align-items: center; gap: 8px; }
.finding-msg { font-size: var(--gt-font-size-sm); }
.finding-detail { margin-top: 4px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); display: flex; gap: 12px; }
.cell-ref { cursor: pointer; color: var(--gt-color-teal); }
.cell-ref:hover { text-decoration: underline; }
</style>
