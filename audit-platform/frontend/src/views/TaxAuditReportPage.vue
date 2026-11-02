<!--
  TaxAuditReportPage — 税审报告（鉴证报告组）：企业所得税年度纳税申报审核报告正文。

  版式移植自参考实现 CITAR `src/screens/part4/ReportScreens.tsx` 的 ReportBodyScreen：
  按文书版式渲染而非表格 —— 固定措辞照原文，报告编号 / 公司名称 / 日期三处做成下划线空档。

  数据口径：
  - 审核年度、公司名称默认值取自项目信息（GET /api/projects/{id}）。
  - 三个空档只存在页内，离开即丢（参考实现同此；落库要新建表与后端路由，另行处理）。
  - 25 行摘录金额来自纳税申报表主表 A100000，而纳税申报表页面尚未实现
    ⇒ 金额列**留空**（只有税率一行是原表固定值 25%），可切换显示来源地址。
    🔴 不填 0：填个零会让人以为已经取过数了。

  导出 / 保存保持禁用：没有落库也就没有可保存的内容；放个能点的按钮再弹「开发中」是假入口。
-->
<template>
  <div class="gt-tar">
    <GtPageHeader title="报告正文" :show-back="false">
      <template #prefix>
        <span class="gt-tar__badge">{{ SECTION_NO }}</span>
      </template>
      <span class="gt-tar__status">摘录金额待申报表实现后取数</span>
    </GtPageHeader>

    <div class="gt-tar__toolbar">
      <el-tooltip v-for="btn in DISABLED_BUTTONS" :key="btn.key" :content="DISABLED_REASON" placement="bottom">
        <!-- 禁用的 el-button 不触发 hover ⇒ tooltip 挂在外层 span 上 -->
        <span>
          <el-button size="small" disabled :data-testid="`tar-${btn.key}`">{{ btn.label }}</el-button>
        </span>
      </el-tooltip>
      <el-button
        size="small"
        :type="showSources ? 'primary' : 'default'"
        data-testid="tar-toggle-sources"
        @click="showSources = !showSources"
      >{{ showSources ? '隐藏取数来源' : '显示取数来源' }}</el-button>
    </div>

    <section class="gt-tar__panel">
      <article class="gt-tar-doc" data-testid="tar-doc">
        <template v-for="(block, index) in REPORT_BODY_BLOCKS" :key="`${block.kind}-${block.excelRow}-${index}`">
          <h2 v-if="block.kind === 'title'" class="gt-tar-doc__title">{{ block.text }}</h2>

          <div
            v-else-if="block.kind === 'field'"
            class="gt-tar-doc__field"
            :class="{ 'gt-tar-doc__field--right': block.variable === 'reportNo' }"
          >
            <span class="gt-tar-doc__field-label">{{ block.label }}</span>
            <input
              v-model="fields[block.variable]"
              class="gt-tar-doc__input"
              @input="onFieldInput(block.variable)"
              :aria-label="block.label"
              :data-testid="`tar-field-${block.variable}`"
            />
          </div>

          <p v-else-if="block.kind === 'paragraph'" class="gt-tar-doc__para">
            {{ fillYear(block.text, auditYear) }}
          </p>

          <table v-else-if="block.kind === 'summary-table'" class="gt-tar-summary" data-testid="tar-summary">
            <thead>
              <tr>
                <th class="gt-tar-summary__seq">序号</th>
                <th>项　　　目</th>
                <th class="gt-tar-summary__amount">金　额</th>
                <th v-if="showSources" class="gt-tar-summary__source">取数来源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in REPORT_SUMMARY_LINES" :key="line.seq">
                <td class="gt-tar-summary__seq">{{ line.seq }}</td>
                <td>{{ line.label }}</td>
                <td class="gt-tar-summary__amount">{{ line.fixedText ?? '' }}</td>
                <td v-if="showSources" class="gt-tar-summary__source">{{ line.source ?? '固定值' }}</td>
              </tr>
            </tbody>
          </table>

          <p v-else-if="block.kind === 'note'" class="gt-tar-doc__note">{{ block.text }}</p>
          <p v-else-if="block.kind === 'signature'" class="gt-tar-doc__signature">{{ block.text }}</p>
          <p v-else-if="block.kind === 'footer'" class="gt-tar-doc__footer">{{ block.text }}</p>

          <div v-else-if="block.kind === 'attachments'" class="gt-tar-doc__attachments">
            <p class="gt-tar-doc__attachments-title">{{ block.title }}</p>
            <p v-for="item in block.items" :key="item" class="gt-tar-doc__attachments-item">{{ item }}</p>
          </div>

          <div v-else class="gt-tar-doc__spacer" />
        </template>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import { api } from '@/services/apiProxy'
import { projects as P_proj } from '@/services/apiPaths'
import {
  REPORT_BODY_BLOCKS,
  REPORT_SUMMARY_LINES,
  fillYear,
  type BodyFieldVariable,
} from '@/constants/taxAuditReportTemplate'

defineOptions({ name: 'TaxAuditReportPage' })

/** 章节编号（参考实现口径「4.1.1 报告正文」） */
const SECTION_NO = '4.1.1'

const DISABLED_BUTTONS = [
  { key: 'export', label: '导出' },
  { key: 'save', label: '保存' },
] as const
const DISABLED_REASON = '正文暂不落库，导出与保存本期未开放'

const route = useRoute()

/** 来源地址开关。核对取数口径时才需要看，默认收起（同参考实现） */
const showSources = ref(false)

/** 审核年度：取不到时为 null，段落里留全角空格占位（见 fillYear） */
const auditYear = ref<number | null>(null)

/** 三个空档。只存在页内，离开即丢 */
const fields = reactive<Record<BodyFieldVariable, string>>({
  reportNo: '',
  companyName: '',
  reportDate: '',
})

/**
 * 用户是否已在本项目里手动改过公司名称。改过就不再用项目信息覆盖（接口晚到时会冲掉输入）。
 *
 * 🔴 由输入框的 @input 置位，**不能**用 watch(fields.companyName) 判断：
 *    watch 是异步 flush 的，回调跑的时候程序自己刚写进去的值也会被当成「用户改过」。
 */
const companyNameTouched = ref(false)
function onFieldInput(variable: BodyFieldVariable) {
  if (variable === 'companyName') companyNameTouched.value = true
}

/** 防乱序：快速切项目时，只认最后一次请求的结果 */
let loadSeq = 0

async function loadProject(pid: string) {
  const mine = ++loadSeq
  // 换项目 = 换一份报告：空档与手改标记全部清空，不把上个项目的编号带过来
  fields.reportNo = ''
  fields.companyName = ''
  fields.reportDate = ''
  companyNameTouched.value = false
  auditYear.value = null
  if (!pid) return
  try {
    // 🔴 _dedupe:false —— 布局层的 ProjectEntryBar / projectStore 同时在取同一 URL，
    //    utils/http 的 GET 去重会取消先发的那一个（ProjectEntryBar 已实测踩过）。
    const d = await api.get(P_proj.detail(pid), { _dedupe: false } as any) as any
    if (mine !== loadSeq) return
    auditYear.value = d?.audit_year ?? null
    if (!companyNameTouched.value) fields.companyName = d?.client_name || d?.name || ''
  } catch {
    // 取不到项目信息不阻断正文展示：年度留占位、公司名称留空待手填
  }
}

watch(() => route.params.projectId as string, pid => loadProject(pid), { immediate: true })
</script>

<style scoped>
.gt-tar { max-width: 1180px; }

/* 标题前的章节编号徽标（半透明白底，落在紫色渐变横幅上） */
.gt-tar__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.18);
  color: var(--gt-color-text-inverse, #fff);
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.gt-tar__status {
  margin-left: auto;
  font-size: var(--gt-font-size-xs);
  opacity: 0.85;
  white-space: nowrap;
}

.gt-tar__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--gt-space-3);
}

.gt-tar__panel {
  padding: 20px 22px 24px;
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: var(--gt-radius-lg, 10px);
  min-height: 320px;
}

/* 文书视图：按 A4 比例给最大宽度，正文读起来才像一份报告而非网页 */
.gt-tar-doc {
  max-width: 760px;
  margin: 0 auto;
  padding: 10px 0 30px;
  font-size: 14px;
  line-height: 1.9;
  color: #2f2f45;
}

.gt-tar-doc__title {
  margin: 10px 0 24px;
  text-align: center;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 2px;
}

.gt-tar-doc__field {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 13px;
}
.gt-tar-doc__field--right { justify-content: flex-end; }
.gt-tar-doc__field-label {
  color: #6b6b76;
  white-space: nowrap;
}

/* 空档做成下划线输入框，照纸质文书的样子 */
.gt-tar-doc__input {
  min-width: 200px;
  padding: 2px 4px;
  border: none;
  border-bottom: 1px solid #c9c9d4;
  background: none;
  font: inherit;
  font-size: 13px;
  color: #2f2f45;
  outline: none;
}
.gt-tar-doc__input:focus {
  border-bottom-color: var(--gt-color-primary, #4b2d77);
  background: #faf6fe;
}

/* 正文段落：首行缩进两字，照中文公文惯例 */
.gt-tar-doc__para {
  margin: 0 0 14px;
  text-indent: 2em;
  text-align: justify;
}

.gt-tar-doc__note {
  margin: 10px 0 0;
  font-size: 12px;
  color: #6b6b76;
  text-indent: 0;
}
.gt-tar-doc__signature {
  margin: 0 0 18px;
  font-size: 13px;
  white-space: pre;
}
.gt-tar-doc__footer {
  margin: 0 0 4px;
  font-size: 13px;
}
.gt-tar-doc__spacer { height: 18px; }

.gt-tar-doc__attachments {
  margin-top: 22px;
  font-size: 13px;
}
.gt-tar-doc__attachments-title { margin: 0 0 6px; }
.gt-tar-doc__attachments-item {
  margin: 0 0 3px;
  padding-left: 2em;
  color: #4a4a58;
}

/* 25 行数据摘录表，嵌在正文中间 */
.gt-tar-summary {
  width: 100%;
  margin: 16px 0 10px;
  border-collapse: collapse;
  font-size: 13px;
  line-height: 1.5;
}
.gt-tar-summary th {
  background: #f1e7fb;
  color: #4c1273;
  font-weight: 700;
  padding: 8px 10px;
  border: 1px solid #d9c4ee;
}
.gt-tar-summary td {
  padding: 6px 10px;
  border: 1px solid #ebebf0;
}
.gt-tar-summary__seq {
  width: 50px;
  text-align: center;
}
.gt-tar-summary__amount {
  width: 150px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
/* 来源地址列：等宽字体便于核对单元格编号 */
.gt-tar-summary__source {
  width: 130px;
  font-size: 12px;
  color: #8a6aa8;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: nowrap;
}
</style>
