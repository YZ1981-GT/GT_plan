<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1-1 预付账款审定表 · 使用手册"
    width="720px"
    top="6vh"
    destroy-on-close
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="guide-body">
      <el-alert
        type="success"
        :closable="false"
        show-icon
        title="一句话：按性质+按账龄双维审定；浅蓝来自 F1-2，灰底审定=未审+AJE+RJE；两维合计与试算须一致。"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>先填全 F1-2（性质、账龄、期末），本表聚合自动更新。</li>
          <li>账龄口径（3年段/5年段/自定义）与 F1-2/4/5/6 保持一致。</li>
          <li>核对：性质合计=账龄合计；账龄审定合计=试算 1123。</li>
          <li>差异走 F1-3；超1年大额推 F1-5；说明/结论可用 AI 后人工改。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 勾稽关系</h3>
        <ul>
          <li>F1-2 期末审定合计 ≈ 本表「按性质」期末未审合计。</li>
          <li>F1-3 AJE/RJE 进审定列；变动率&gt;30% 须写原因。</li>
          <li>审定结果供附注、函证引用。</li>
        </ul>
      </section>
    </div>
    <template #footer>
      <el-button type="primary" @click="close">知道了</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.guide-body { max-height: min(68vh, 640px); overflow-y: auto; font-size: 13px; line-height: 1.65; color: #303133; }
.mb12 { margin-bottom: 12px; }
.guide-section { margin-bottom: 16px; }
.guide-section h3 { margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #1d39c4; border-left: 3px solid #409eff; padding-left: 8px; }
.guide-section ol, .guide-section ul { margin: 0; padding-left: 1.35em; }
.guide-section li { margin: 4px 0; }
</style>
