<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1-7 预付账款检查表 · 使用手册"
    width="760px"
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
        title="一句话：借方看付出是否真、贷方看结转是否真、期后贷方看截止是否妥；用覆盖率证明程序充分。"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>填抽样：测试总体、特定样本、抽样方法/过程；大额、关联方、长账龄优先入样。</li>
          <li>表(1) 本期借方：可用「抽凭回填」或手工添加；逐笔勾凭证 ↔ 付款审批 ↔ 银行回单 ↔ 合同/订单。</li>
          <li>表(2)(3) 本期/期后贷方：抽凭或手工；勾凭证 ↔ 入库/验收 ↔ 采购发票。</li>
          <li>填覆盖率（账面×检查×比例），写说明/结论（可用 AI）。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 三张表各验什么</h3>
        <ul>
          <li><strong>借方</strong>：预付增加是否真实、审批合规、资金流出有据。</li>
          <li><strong>贷方</strong>：预付减少是否对应到货/服务、资产是否该结转。</li>
          <li><strong>期后贷方</strong>：期末余额是否期后及时核销，评估截止；合计与 F1-2 期后结转(Z列)勾稽。</li>
        </ul>
      </section>
      <section class="guide-section">
        <h3>3. 导入导出</h3>
        <p>分别导出/导入 F1-7（借方）、F1-7-credit（贷方）、F1-7-post（期后）；列结构与屏幕一致。</p>
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
.guide-section li, .guide-section p { margin: 4px 0; }
</style>
