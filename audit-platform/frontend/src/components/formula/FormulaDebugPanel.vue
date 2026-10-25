<!--
  公式调试/模拟器面板（spec: formula-management-deep-optimization · R3）。
  输入公式 → 点击调试运行 → 展示逐步 trace + 错误高亮。
  嵌入 FormulaEditDialog 底部。
-->
<template>
  <div class="gt-fd-panel">
    <div class="gt-fd-header">
      <span class="gt-fd-title">▶ 调试运行</span>
      <el-button size="small" type="primary" :loading="running" @click="onRun" :disabled="!formula?.trim()">
        {{ running ? '运行中...' : '▶ 调试运行' }}
      </el-button>
      <el-button v-if="result" size="small" @click="result = null">清除结果</el-button>
    </div>

    <!-- 输入区（可外部传入或手动输入） -->
    <div v-if="showInput" class="gt-fd-input">
      <el-input v-model="localFormula" type="textarea" :rows="2" placeholder="输入公式，如 TB(&quot;1001&quot;, &quot;未审数&quot;) + ROW(&quot;1&quot;)" />
    </div>

    <!-- 结果区 -->
    <div v-if="result" class="gt-fd-result">
      <!-- 计算结果 -->
      <div class="gt-fd-value-bar" :class="{ 'gt-fd-ok': result.ok, 'gt-fd-error': !result.ok }">
        <span class="gt-fd-value-label">结果：</span>
        <span v-if="result.ok" class="gt-fd-value">{{ result.value ?? '—' }}</span>
        <span v-else class="gt-fd-value gt-fd-error-text">{{ result.state === 'blocked' ? '⛔ 公式被拦截' : '❌ 执行失败' }}</span>
        <el-tag :type="result.ok ? 'success' : 'danger'" size="small" style="margin-left: 8px;">
          {{ result.state }}
        </el-tag>
      </div>

      <!-- 错误信息 -->
      <div v-if="result.errors?.length" class="gt-fd-errors">
        <div v-for="(err, i) in result.errors" :key="i" class="gt-fd-error-item">
          <span style="color: var(--gt-color-danger);">⚠</span> {{ err }}
        </div>
      </div>

      <!-- 警告信息 -->
      <div v-if="result.warnings?.length" class="gt-fd-warnings">
        <div v-for="(w, i) in result.warnings" :key="i" class="gt-fd-warn-item">
          <span style="color: var(--gt-color-wheat);">💡</span> {{ w }}
        </div>
      </div>

      <!-- Trace 树形展示 -->
      <div v-if="result.trace?.length" class="gt-fd-trace">
        <div class="gt-fd-trace-title">求值轨迹（{{ result.trace.length }} 步）</div>
        <div class="gt-fd-trace-list">
          <div v-for="(step, i) in result.trace" :key="i" class="gt-fd-trace-step" :class="{ 'gt-fd-trace-error': isErrorStep(step) }">
            <span class="gt-fd-trace-idx">{{ i + 1 }}.</span>
            <code class="gt-fd-trace-text">{{ step }}</code>
          </div>
        </div>
      </div>

      <!-- 上下文摘要 -->
      <div v-if="result.context_summary" class="gt-fd-ctx">
        <span class="gt-fd-ctx-title">加载的数据：</span>
        <el-tag v-if="result.context_summary.tb_accounts" size="small" type="info" effect="plain">
          试算表 {{ result.context_summary.tb_accounts }} 科目
        </el-tag>
        <el-tag v-if="result.context_summary.report_rows" size="small" type="info" effect="plain">
          报表 {{ result.context_summary.report_rows }} 行
        </el-tag>
        <el-tag v-if="result.context_summary.note_sections" size="small" type="info" effect="plain">
          附注 {{ result.context_summary.note_sections }} 节
        </el-tag>
        <el-tag v-if="result.context_summary.wp_codes" size="small" type="info" effect="plain">
          底稿 {{ result.context_summary.wp_codes }} 个
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { formulaDebug } from '@/services/apiPaths/formula'
import { formulaErrorText } from '@/composables/formula/useFormulaSettings'

const props = defineProps<{
  /** 外部传入的公式文本（来自 FormulaEditDialog 的编辑区） */
  formula?: string
  projectId?: string
  year?: number
  scope?: string
  /** 是否显示内置输入框（嵌入 FormulaEditDialog 时 = false，独立使用时 = true） */
  showInput?: boolean
}>()

const emit = defineEmits<{
  ran: [result: any]
}>()

const localFormula = ref('')
const running = ref(false)
const result = ref<any>(null)

// 外部 formula 变化时同步
watch(() => props.formula, (v) => {
  if (v !== undefined) localFormula.value = v
}, { immediate: true })

const formula = computed(() => props.formula ?? localFormula.value)

async function onRun() {
  const f = formula.value?.trim()
  if (!f || !props.projectId || !props.year) return

  running.value = true
  result.value = null
  try {
    // 错误由本面板自己显示：请求带 _silent，免得全局拦截器先弹一次
    const data = await api.post(formulaDebug.run(), {
      formula: f,
      project_id: props.projectId,
      year: props.year,
      scope: props.scope || 'report',
    }, { _silent: true } as any)
    result.value = data
    emit('ran', data)
  } catch (e: any) {
    // 原先写 handleApiError(e, { silent: true }) || '请求失败'：它的第二参是上下文文案、返回 void ⇒
    // 弹一条「[object Object]：…」提示，面板里永远只剩「请求失败」，真实原因丢了（spec formula-fetch-followup 7.2）
    result.value = {
      ok: false,
      state: 'error',
      errors: [formulaErrorText(e, '调试运行失败')],
      trace: [],
    }
  } finally {
    running.value = false
  }
}

function isErrorStep(step: string) {
  return step.includes('错误') || step.includes('Error') || step.includes('失败')
}
</script>

<style scoped>
.gt-fd-panel { border: 1px solid var(--gt-color-border-light); border-radius: 6px; padding: 10px; background: var(--gt-bg-overlay); }
.gt-fd-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.gt-fd-title { font-weight: 600; font-size: var(--gt-font-size-sm); }
.gt-fd-input { margin-bottom: 8px; }
.gt-fd-value-bar { display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; }
.gt-fd-ok { background: var(--gt-bg-success-light, #f0f9eb); }
.gt-fd-error { background: var(--gt-bg-danger-light, #fef0f0); }
.gt-fd-value-label { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.gt-fd-value { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.gt-fd-error-text { color: var(--gt-color-danger); }
.gt-fd-errors, .gt-fd-warnings { margin-bottom: 6px; }
.gt-fd-error-item, .gt-fd-warn-item { font-size: var(--gt-font-size-xs); padding: 2px 0; }
.gt-fd-trace { margin-top: 6px; }
.gt-fd-trace-title { font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-text-secondary); margin-bottom: 4px; }
.gt-fd-trace-list { max-height: 200px; overflow-y: auto; }
.gt-fd-trace-step { font-size: var(--gt-font-size-xs); padding: 2px 4px; border-left: 2px solid var(--gt-color-border-light); margin-bottom: 1px; display: flex; gap: 4px; }
.gt-fd-trace-idx { color: var(--gt-color-text-placeholder); min-width: 24px; }
.gt-fd-trace-text { word-break: break-all; }
.gt-fd-trace-error { border-left-color: var(--gt-color-danger); background: var(--gt-bg-danger-light, #fef0f0); }
.gt-fd-ctx { display: flex; align-items: center; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.gt-fd-ctx-title { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
