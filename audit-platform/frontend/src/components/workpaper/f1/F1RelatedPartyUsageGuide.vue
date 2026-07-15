<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1-6 关联方及交易检查 · 使用手册"
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
        title="一句话：从明细筛出关联方预付，核余额与商业实质，防占资漏披露；坏账后得账面价值。"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>从 F1-2 导入关联方户（或手工添加），对照关联方名录补漏识。</li>
          <li>选关联关系（模板清单枚举）、填期初/借贷；期末=期初+借方−贷方（自动）。</li>
          <li>选账龄（F1-1 枚举）、款项性质，填期后到货与索引。</li>
          <li>需要时计提坏账；账面价值=期末−坏账（自动）。写说明/结论（可用 AI）。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 关注点</h3>
        <ul>
          <li>大额长期关联预付：是否变相资金占用。</li>
          <li>披露：与附注关联方余额/交易是否一致。</li>
          <li>若性质已变或需减值，推 F1-3 调整。</li>
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
