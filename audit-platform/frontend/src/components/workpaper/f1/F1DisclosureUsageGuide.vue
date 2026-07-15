<script setup lang="ts">
const props = defineProps<{ modelValue: boolean; variant?: 'listed' | 'soe' }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
const isListed = () => (props.variant || 'listed') === 'listed'
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="isListed() ? 'F1 附注（上市）· 使用手册' : 'F1 附注（国企）· 使用手册'"
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
        :title="isListed()
          ? '一句话：按账龄披露 + 超1年重要预付原因 + 前五名；数字与 F1-1 账龄审定勾稽。'
          : '一句话：按账龄列示（含坏账）+ 超1年大额原因 + 前五名；口径与 F1-1/F1-5 一致。'"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>先完成 F1-1 审定（账龄口径与明细一致）。</li>
          <li>点「从 F1-1 带入账龄」填 (1)；核对比例。</li>
          <li>「从 F1-2 带入超1年 / 前五名」补 (2)(3)，再手工填原因与坏账。</li>
          <li>核对附注表述勿与关联方、坏账披露冲突。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 勾稽</h3>
        <ul>
          <li>账龄合计应与 F1-1「按账龄」审定合计一致。</li>
          <li>超1年户可与 F1-5 / F1-2 交叉检查。</li>
          <li>5年段/自定义口径：前3段按年段带入，3年以上并入最后一档。</li>
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
