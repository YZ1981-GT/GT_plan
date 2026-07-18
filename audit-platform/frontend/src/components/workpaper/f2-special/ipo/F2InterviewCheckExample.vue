<template>
  <div class="f2-interview-example" :class="{ compact }">
    <header v-if="!compact" class="example-header">
      <div>
        <h3>访谈记录与核对（示例）</h3>
        <span class="code">只读参照 · XYZ 公司走访示例，说明访谈记录如何编制、询问与交叉核对</span>
      </div>
      <el-tag type="warning" size="small">示例底稿 · 不需编制</el-tag>
    </header>

    <el-alert type="info" :closable="false" class="how-to">
      <template #title>编制思路：走访前先查（工商/地图）→ 访谈中问（交易与合同条款）→ 现场看（经营场所印证）→ 当场证（盖章函证）→ 穿透比（关联方关系）→ 最后下走访结论。红字为编制指引，正文为 XYZ 公司示例写法。</template>
    </el-alert>

    <section
      v-for="section in sections"
      :key="section.title"
      class="example-section"
    >
      <div class="section-head">
        <span class="section-title">{{ section.title }}</span>
        <span class="section-tag">随需填写</span>
      </div>
      <p class="guide-text">【{{ section.guide }}】</p>
      <template v-if="section.title.startsWith('三、')">
        <table class="contract-table">
          <thead>
            <tr>
              <th class="col-item">项目</th>
              <th>询问所得信息</th>
              <th class="col-check">来自发行人合同条款</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in contractRows" :key="row.item">
              <td class="col-item">{{ row.item }}</td>
              <td class="inquiry">{{ row.inquiry || '——' }}</td>
              <td class="col-check">{{ row.crossCheck || '——' }}</td>
            </tr>
          </tbody>
        </table>
      </template>
      <p
        v-for="(paragraph, index) in section.paragraphs"
        :key="index"
        class="example-paragraph"
      >{{ paragraph }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import {
  INTERVIEW_EXAMPLE_CONTRACT_ROWS,
  INTERVIEW_EXAMPLE_SECTIONS,
} from './f2InterviewCheckExampleData'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })

const sections = INTERVIEW_EXAMPLE_SECTIONS
const contractRows = INTERVIEW_EXAMPLE_CONTRACT_ROWS
</script>

<style scoped>
.f2-interview-example{padding:14px 18px;font-size:var(--wp-font-size, 13px);background:linear-gradient(180deg,#faf8fc 0,#fff 130px)}
.f2-interview-example.compact{padding:0;background:none}
.example-header{display: flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
.example-header h3{margin:0;color:#35204f}
.code{font-size:12px;color:#8c7b9d}
.how-to{margin-bottom:12px}
.example-section{margin-bottom:14px;border:1px solid #ded3e8;border-radius:6px;overflow:hidden}
.section-head{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#f0e9f6;color:#3f2465;font-weight:700}
.section-tag{font-size:11px;font-weight:400;color:#8c7b9d}
.guide-text{margin:8px 12px;color:#c45656;line-height:1.7}
.example-paragraph{margin:6px 12px;color:#303133;line-height:1.75;text-indent:2em}
.contract-table{width:calc(100% - 24px);margin:6px 12px 10px;border-collapse:collapse;font-size:12px}
.contract-table th,.contract-table td{border:1px solid #d8cce3;padding:5px 8px;vertical-align:top;text-align:left;line-height:1.6}
.contract-table thead th{background:#4b2d77;color:#fff;font-weight:600}
.col-item{width:150px;background:#f5f0f8;color:#4b2d77;font-weight:600}
.col-check{width:190px;color:#67a23a}
.inquiry{color:#303133}
</style>
