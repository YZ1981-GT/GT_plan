<script setup lang="ts">
/**
 * D2ReferenceBlock — D2 源模板示例内嵌编制参考（方法论上下文）
 *
 * 铁律「示例内嵌编制参考（非Drawer被动查看）」：源模板示例内容内嵌到编制界面，
 * 用户填写时直接看到参照，可一键套用。样式=琥珀色左边线+浅黄背景。
 *
 * 内容来源：致同「应收账款预期信用损失计提及保理合同分析参考示例.xlsx」
 */
interface RefTable {
  headers: string[]
  rows: string[][]
}
interface RefSection {
  heading: string
  /** 段落文本（每条一行） */
  paragraphs?: string[]
  /** 结构化表格 */
  table?: RefTable
  /** 有序步骤 */
  steps?: { title: string; note: string }[]
}

defineProps<{
  title: string
  source: string
  sections: RefSection[]
  /** 一键套用按钮文案，为空则不显示 */
  applyLabel?: string
  disabled?: boolean
}>()

const emit = defineEmits<{ (e: 'apply'): void }>()
</script>

<template>
  <details class="d2-ref-block">
    <summary>
      <span class="ref-icon">📚</span>
      <span class="ref-title">{{ title }}</span>
      <span class="ref-source">参照：{{ source }}</span>
    </summary>
    <div class="ref-body">
      <div v-if="applyLabel" class="ref-apply">
        <el-button size="small" type="warning" plain :disabled="disabled" @click.stop.prevent="emit('apply')">
          ⚡ {{ applyLabel }}
        </el-button>
        <span class="ref-apply-hint">按源模板示例一键填入，可再手动调整</span>
      </div>

      <section v-for="(sec, si) in sections" :key="'sec-' + si" class="ref-section">
        <h5 class="ref-heading">{{ sec.heading }}</h5>

        <p v-for="(p, pi) in sec.paragraphs || []" :key="'p-' + pi" class="ref-para">{{ p }}</p>

        <ol v-if="sec.steps && sec.steps.length" class="ref-steps">
          <li v-for="(st, sti) in sec.steps" :key="'st-' + sti">
            <span class="step-title">{{ st.title }}</span>
            <span class="step-note">{{ st.note }}</span>
          </li>
        </ol>

        <table v-if="sec.table" class="ref-table">
          <thead>
            <tr><th v-for="(h, hi) in sec.table.headers" :key="'h-' + hi">{{ h }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, ri) in sec.table.rows" :key="'r-' + ri">
              <td v-for="(c, ci) in r" :key="'c-' + ci">{{ c }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </details>
</template>

<style scoped>
.d2-ref-block {
  margin: 12px 0;
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 0 6px 6px 0;
  padding: 8px 14px;
  font-size: var(--wp-font-size, 13px);
  color: #5c4b28;
}
.d2-ref-block summary {
  cursor: pointer;
  font-weight: 600;
  color: #b88230;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ref-icon { font-size: 15px; }
.ref-title { font-size: 14px; }
.ref-source { font-size: 12px; color: #a0864f; font-weight: 400; }
.ref-body { margin-top: 10px; }
.ref-apply { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.ref-apply-hint { font-size: 12px; color: #a0864f; }
.ref-section { margin-bottom: 14px; }
.ref-heading { margin: 6px 0; font-size: var(--wp-font-size, 13px); font-weight: 700; color: #96631b; }
.ref-para { margin: 4px 0; line-height: 1.6; }
.ref-steps { margin: 4px 0 4px 18px; padding: 0; }
.ref-steps li { margin: 4px 0; line-height: 1.55; }
.step-title { font-weight: 600; color: #7a5518; margin-right: 6px; }
.step-note { color: #6b5a34; }
.ref-table { width: 100%; border-collapse: collapse; margin: 6px 0; font-size: 12px; }
.ref-table th, .ref-table td { border: 1px solid #f0d9b5; padding: 5px 8px; text-align: left; vertical-align: top; }
.ref-table th { background: #faecd8; font-weight: 600; color: #96631b; }
</style>
