<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1-5 账龄1年以上大额预付检查 · 使用手册"
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
        title="一句话：对本金挂账超 1 年的大户逐笔问清原因、出路与是否减值/重分类，结论回撑 F1-1。"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>从 F1-2 导入账龄&gt;1 年户（或手工添加）。</li>
          <li>核期末余额、选枚举账龄（与 F1-1 口径一致），写清业务说明与未结转原因。</li>
          <li>填计划供货/退款、是否诉讼、是否转其他应收；需要时计提坏账（审定余额自动=期末−坏账）。</li>
          <li>填期后供货或退款、支持性证据索引；写审计说明与结论（可用 AI，可二次编辑）。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 关键字段逻辑</h3>
        <ul>
          <li><b>审定余额</b>：期末余额 − 坏账准备（灰底自动算）。</li>
          <li><b>是否转入其他应收</b>：若性质已变，通常需在 F1-3 做重分类。</li>
          <li><b>期后供货或退款</b>：截止日后已消化部分，可与 F1-7 勾稽。</li>
        </ul>
      </section>
      <section class="guide-section">
        <h3>3. 导入导出</h3>
        <ul>
          <li>导入导出为全量 13 列 Excel，与本表一致。</li>
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
