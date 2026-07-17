<template>
  <details class="f2-example-ref" :open="defaultOpen">
    <summary>
      <span class="ref-icon">📚</span>
      <span class="ref-title">编制参考示例 — 合同履约成本测试</span>
      <span class="ref-tag">只读参照</span>
    </summary>
    <div class="ref-body">
      <p class="ref-intro">
        源模板示例（ABC 公司）：先判断资本化，再对资本化项目做摊销测试。
        亦可切换底稿标签「合同履约成本测试（示例）」查看完整版。
      </p>
      <F2ContractCostTestExample compact />
    </div>
  </details>
</template>

<script setup lang="ts">
import F2ContractCostTestExample from './F2ContractCostTestExample.vue'

withDefaults(
  defineProps<{
    defaultOpen?: boolean
  }>(),
  { defaultOpen: false },
)
</script>

<style scoped>
.f2-example-ref {
  margin-bottom: 14px;
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 0 6px 6px 0;
  padding: 8px 12px;
}
.f2-example-ref summary {
  cursor: pointer;
  font-weight: 600;
  color: #b88230;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  list-style: none;
}
.f2-example-ref summary::-webkit-details-marker { display: none; }
.ref-icon { font-size: 15px; }
.ref-title { font-size: 14px; }
.ref-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: #faecd8;
  color: #a0864f;
  font-weight: 500;
}
.ref-body { margin-top: 10px; }
.ref-intro {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.6;
  color: #7a5518;
}
</style>
