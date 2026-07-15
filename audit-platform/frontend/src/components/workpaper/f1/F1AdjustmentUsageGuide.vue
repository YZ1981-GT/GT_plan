<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1-3 调整分录汇总 · 使用手册"
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
        title="一句话：逐笔编制 AJE/RJE，借贷须平衡；AJE 改审定、RJE 改列报；勾选后可推 A13。"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>来源：F1-1 试算差异、F1-5 减值/重分类、F1-6 占资、F1-7 异常、F1-2 性质错记等。</li>
          <li>逐笔填说明、类别、科目/报表项目、借贷金额与索引。</li>
          <li>确认借贷合计平衡后再写说明/结论（可用 AI）。</li>
          <li>需进错报汇总的分录勾选「推送至 A13」。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 类别口径</h3>
        <ul>
          <li><b>账项调整（AJE）</b>：影响审定数/损益。</li>
          <li><b>重分类调整（RJE）</b>：一般只改列报位置（如转其他应收）。</li>
          <li>常见：长期无法收回转其他应收并评估坏账；关联方列报；错挂冲回。</li>
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
