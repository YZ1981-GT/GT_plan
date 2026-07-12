<template>
  <div class="h8-tab-impairment">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS8资产减值：使用权资产应当在资产负债表日评估是否存在减值迹象，存在减值迹象的应进行减值测试。可收回金额=max(公允价值-处置费用, 未来现金流量现值)。减值一经确认不得转回。</p>
    </div>

    <!-- 索引 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-10" />
    </div>

    <!-- 减值摘要卡片 -->
    <el-card shadow="never" class="summary-card">
      <template #header>
        <div class="section-title">
          <span>减值测算摘要（H8-10，35行32列15公式）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'impairment')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'impairment')">复核</el-button>
          </div>
        </div>
      </template>
      <el-form :inline="true" size="small" label-position="left" :disabled="isReadonly">
        <el-form-item label="使用权资产账面价值">
          <el-input-number v-model="impairParams.bookValue" :controls="false"
            @change="handleParamChange('bookValue', impairParams.bookValue)" />
        </el-form-item>
        <el-form-item label="可收回金额">
          <el-input-number v-model="impairParams.recoverableAmount" :controls="false"
            @change="handleParamChange('recoverableAmount', impairParams.recoverableAmount)" />
        </el-form-item>
        <el-form-item label="减值迹象">
          <el-select v-model="impairParams.impairmentSign" @change="handleParamChange('impairmentSign', impairParams.impairmentSign)">
            <el-option label="无减值迹象" value="无" />
            <el-option label="市场利率上升" value="市场利率上升" />
            <el-option label="经营环境恶化" value="经营环境恶化" />
            <el-option label="资产使用变化" value="资产使用变化" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
      </el-form>

      <!-- 减值结果 -->
      <div class="impair-result" v-if="impairParams.bookValue > 0">
        <div class="result-row">
          <div class="result-item">
            <span class="result-label">账面价值</span>
            <span class="result-value">{{ fmtAmt(impairParams.bookValue) }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">可收回金额</span>
            <span class="result-value">{{ fmtAmt(impairParams.recoverableAmount) }}</span>
          </div>
          <div class="result-item">
            <span class="result-label">应计提减值</span>
            <span class="result-value" :class="impairmentLoss > 0 ? 'loss-value' : ''">
              {{ impairmentLoss > 0 ? fmtAmt(impairmentLoss) : '无需计提' }}
            </span>
          </div>
        </div>
        <div v-if="impairmentLoss > 0" class="impair-warning">
          <el-alert type="warning" :closable="false" show-icon>
            <template #title>
              应计提减值准备 {{ fmtAmt(impairmentLoss) }} 元（账面价值 > 可收回金额）
            </template>
          </el-alert>
        </div>
      </div>
    </el-card>

    <!-- OO渲染区域 -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>减值测算明细（35行32列15公式）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'减值测算表H8-10'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
        <div v-else class="oo-fallback">
          <el-empty description="OnlyOffice未加载">
            <template #image><span style="font-size:40px">📉</span></template>
          </el-empty>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>减值迹象评估：市场利率上升/经营环境恶化/资产物理损毁/使用方式变化</li>
        <li>可收回金额 = max(公允价值-处置费用, 未来现金流量现值)</li>
        <li>当账面价值 > 可收回金额时，应计提减值</li>
        <li>使用权资产减值一经确认，不得转回（CAS8规定）</li>
        <li>减值后需切换H8-8至"含减值"版本重新计算折旧</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabImpairment.vue — H8-10 减值测算表（OO渲染+减值摘要）
 * 35行32列15公式
 * Spec: Task 4.7 | Requirements: 7.1-7.2
 */
import { ref, reactive, computed, toRef, defineAsyncComponent } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() =>
  import('../../GtOnlyOfficeSheet.vue').catch(() => ({ template: '<div>OO不可用</div>' })),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const showOO = ref(true)

const impairParams = reactive({
  bookValue: 0,
  recoverableAmount: 0,
  impairmentSign: '无' as string,
})

// 从allResponses恢复
const stored = props.allResponses.get('H8-10-params')
if (stored) {
  try {
    const parsed = JSON.parse(stored.remark ?? stored.conclusion ?? '{}')
    Object.assign(impairParams, parsed)
  } catch { /* ignore */ }
}

const impairmentLoss = computed(() => {
  if (impairParams.bookValue <= 0 || impairParams.recoverableAmount <= 0) return 0
  const diff = impairParams.bookValue - impairParams.recoverableAmount
  return diff > 0 ? diff : 0
})

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleParamChange(field: string, value: any) {
  emit('save', 'H8-10-params', JSON.stringify(impairParams))
}
</script>

<style scoped>
.h8-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.summary-card { margin-bottom: 16px; }
.impair-result { margin-top: 12px; }
.result-row { display: flex; gap: 32px; flex-wrap: wrap; margin-bottom: 12px; }
.result-item { display: flex; flex-direction: column; gap: 4px; }
.result-label { font-size: 12px; color: var(--el-text-color-secondary); }
.result-value { font-size: 16px; font-weight: 700; color: var(--el-color-primary); }
.loss-value { color: #f56c6c; }
.impair-warning { margin-top: 8px; }

.oo-card { margin-bottom: 16px; }
.oo-placeholder { min-height: 400px; }
.oo-fallback { padding: 40px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
