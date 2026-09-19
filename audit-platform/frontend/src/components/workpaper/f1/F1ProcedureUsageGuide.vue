<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="F1A 预付账款实质性程序表 · 使用手册"
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
        title="一句话：先勾程序矩阵，再按索引落 F1-1～F1-7；本表是「做了什么」的总控，不是明细替身。"
        class="mb12"
      />
      <section class="guide-section">
        <h3>1. 推荐编制顺序</h3>
        <ol>
          <li>按认定勾选拟执行程序，并在备注注明例外或不执行理由。</li>
          <li>同步编 F1-2 明细 → F1-1 审定；需要时开 F1-3 调整。</li>
          <li>按风险落 F1-4 分析、F1-5 长期、F1-6 关联方、F1-7 抽凭。</li>
          <li>程序表索引号与各底稿页眉/索引保持一致，便于复核跳转。</li>
        </ol>
      </section>
      <section class="guide-section">
        <h3>2. 关注点</h3>
        <ul>
          <li>未执行程序须说明；勿只勾不留痕。</li>
          <li>大额/长账龄/关联方预付须能在 F1-5/6/7 找到对应检查。</li>
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
