<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1 函证程序 · 使用手册"
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
        title="一句话：从 F1-2 筛拟发函对象 → 标记发函(Y) → 在 F0-1 汇总发函/回函；未回函用 F0-5 替代。函证中心为可选寄件台账。"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>完成 F1-2 明细与期末审定余额。</li>
          <li>在本页按余额排序查看拟发函清单，勾选后「标记已发函」写回 F1-2「发函(Y)」列。</li>
          <li>打开 <b>F0-1</b> 创建/维护函证汇总（confirm_index、发函、回函）。</li>
          <li>在 F0-1 <b>保存</b>后，已发函对象会自动回写 F1-2「发函(Y)」列。</li>
          <li>未回函或无法函证对象：在 <b>F0-5</b>「从 F0-1 带入」执行替代程序。</li>
          <li>（可选）用项目「函证中心」登记寄出物流；推进状态也会回写明细发函标记。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 关注点</h3>
        <ul>
          <li>大额、长账龄、关联方预付优先函证；与 F1-5/F1-6 交叉核对。</li>
          <li>「标记已发函」只更新 F1-2 标识；法定函证证据在 F0 系列底稿。</li>
          <li>覆盖率 = 已标记发函户期末审定合计 / 有余额户期末审定合计。</li>
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
