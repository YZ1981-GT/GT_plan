import{j as n,M as t}from"./index-B9ipDK6S.js";import{useMDXComponents as s}from"./index-Dzk-1iMg.js";import"./iframe-DRCZA9bM.js";import"./_commonjsHelpers-CqkleIqs.js";import"./index-8_2S3kac.js";import"./index-DrFu-skq.js";function r(l){const e={blockquote:"blockquote",code:"code",h1:"h1",h2:"h2",h3:"h3",hr:"hr",li:"li",ol:"ol",p:"p",pre:"pre",strong:"strong",ul:"ul",...s(),...l.components};return n.jsxs(n.Fragment,{children:[n.jsx(t,{title:"Docs/组件使用指南"}),`
`,n.jsx(e.h1,{id:"组件使用指南",children:"组件使用指南"}),`
`,n.jsx(e.p,{children:"本文档帮助开发者快速判断在不同场景下应使用哪个组件，以及金额格式化、表格字号等 UI 规范。"}),`
`,n.jsx(e.hr,{}),`
`,n.jsx(e.h2,{id:"1-gteditabletable-vs-原生-el-table",children:"1. GtEditableTable vs 原生 el-table"}),`
`,n.jsx(e.h3,{id:"gteditabletable-适用场景",children:"GtEditableTable 适用场景"}),`
`,n.jsxs(e.ul,{children:[`
`,n.jsxs(e.li,{children:["需要",n.jsx(e.strong,{children:"查看/编辑模式切换"}),"的表格（如审定表、调整分录）"]}),`
`,n.jsxs(e.li,{children:["需要",n.jsx(e.strong,{children:"行选择"}),"（checkbox）+ ",n.jsx(e.strong,{children:"右键菜单"}),"的表格"]}),`
`,n.jsxs(e.li,{children:["需要",n.jsx(e.strong,{children:"单元格级别编辑"}),"（点击 cell 进入编辑态）"]}),`
`,n.jsxs(e.li,{children:["需要内置",n.jsx(e.strong,{children:"分页"}),"（标准分页组件：左侧 page size + 右侧页码导航含 jumper）"]}),`
`,n.jsxs(e.li,{children:["需要",n.jsx(e.strong,{children:"选中行高亮"}),"（14%+ 透明度背景 + 左侧 3px 紫色竖线指示器）"]}),`
`]}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-vue",children:`<GtEditableTable\r
  :columns="columns"\r
  v-model="tableData"\r
  :editable="isEditMode"\r
  :show-selection="true"\r
/>
`})}),`
`,n.jsx(e.h3,{id:"原生-el-table-适用场景",children:"原生 el-table 适用场景"}),`
`,n.jsxs(e.ul,{children:[`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"纯展示"}),"型表格，无编辑需求"]}),`
`,n.jsxs(e.li,{children:["需要",n.jsx(e.strong,{children:"高度自定义列模板"}),"（复杂 slot 嵌套）"]}),`
`,n.jsx(e.li,{children:"表格行为与 GtEditableTable 封装不兼容的特殊场景（如树形表格、合并行列）"}),`
`,n.jsx(e.li,{children:"临时性/一次性展示（弹窗内的简单列表）"}),`
`]}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-vue",children:`<el-table :data="list" :class="\`gt-tb-font-\${fontSize}\`">\r
  <el-table-column prop="name" label="名称" />\r
  <el-table-column prop="amount" label="金额">\r
    <template #default="{ row }">\r
      <span class="gt-amt">{{ formatAmount(row.amount) }}</span>\r
    </template>\r
  </el-table-column>\r
</el-table>
`})}),`
`,n.jsx(e.h3,{id:"决策速查",children:"决策速查"}),`
`,n.jsx(e.p,{children:`| 需求 | 选择 |\r
|------|------|\r
| 查看+编辑切换 | GtEditableTable |\r
| 行选择 + 右键菜单 | GtEditableTable |\r
| 分页 + 选中高亮 | GtEditableTable |\r
| 纯展示 + 简单列 | el-table |\r
| 树形/合并行列 | el-table |\r
| 弹窗内简单列表 | el-table |`}),`
`,n.jsx(e.hr,{}),`
`,n.jsx(e.h2,{id:"2-gtpageheader-vs-白色工具栏",children:"2. GtPageHeader vs 白色工具栏"}),`
`,n.jsx(e.h3,{id:"gtpageheader-适用场景",children:"GtPageHeader 适用场景"}),`
`,n.jsxs(e.ul,{children:[`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"项目级页面"}),"：仪表盘（PartnerProjectDashboard）、项目概览"]}),`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"需要视觉层级"}),"的入口页面：报表视图、试算平衡表顶部"]}),`
`,n.jsxs(e.li,{children:["带",n.jsx(e.strong,{children:"返回按钮"}),'的二级页面（variant="default"）']}),`
`,n.jsxs(e.li,{children:["带",n.jsx(e.strong,{children:"渐变 banner"}),'的仪表盘页面（variant="banner"）']}),`
`]}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-vue",children:`<GtPageHeader title="项目仪表盘" variant="banner" icon="📊" />
`})}),`
`,n.jsx(e.h3,{id:"白色简洁工具栏适用场景",children:"白色简洁工具栏适用场景"}),`
`,n.jsxs(e.ul,{children:[`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"简单 CRUD 列表页"}),"：人员档案、知识库、模板管理"]}),`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"表格上方操作区"}),"：左标题 + 右操作按钮（刷新/导出/保存）"]}),`
`,n.jsx(e.li,{children:"紫色渐变在简单页面显得过重，白色工具栏更轻量"}),`
`]}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-vue",children:`<div class="toolbar">\r
  <span class="toolbar-title">人员档案</span>\r
  <div class="toolbar-actions">\r
    <el-button @click="refresh">刷新</el-button>\r
    <el-button type="primary" @click="add">新增</el-button>\r
  </div>\r
</div>
`})}),`
`,n.jsx(e.h3,{id:"决策速查-1",children:"决策速查"}),`
`,n.jsx(e.p,{children:`| 页面类型 | 选择 |\r
|----------|------|\r
| 项目仪表盘 / 概览 | GtPageHeader (banner) |\r
| 报表 / 试算表顶部 | GtPageHeader (default) |\r
| 人员档案 / 知识库 | 白色工具栏 |\r
| 底稿列表 / 模板管理 | 白色工具栏 |\r
| 弹窗内工具区 | 白色工具栏 |`}),`
`,n.jsxs(e.blockquote,{children:[`
`,n.jsxs(e.p,{children:[n.jsx(e.strong,{children:"原则"}),"：GtPageHeader 只用于需要视觉层级的项目级/仪表盘页面。简单 CRUD 页面用白色工具栏，避免紫色大块喧宾夺主。"]}),`
`]}),`
`,n.jsx(e.hr,{}),`
`,n.jsx(e.h2,{id:"3-金额格式化规范",children:"3. 金额格式化规范"}),`
`,n.jsxs(e.p,{children:["所有表格中的金额列必须使用 ",n.jsx(e.code,{children:".gt-amt"})," class，确保数字对齐和可读性。"]}),`
`,n.jsx(e.h3,{id:"样式规范",children:"样式规范"}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-css",children:`.gt-amt {\r
  font-family: 'Arial Narrow', Arial, sans-serif;\r
  font-variant-numeric: tabular-nums;\r
  white-space: nowrap;\r
}
`})}),`
`,n.jsx(e.h3,{id:"效果说明",children:"效果说明"}),`
`,n.jsxs(e.p,{children:[`| 属性 | 作用 |\r
|------|------|\r
| `,n.jsx(e.code,{children:"font-family: Arial Narrow"}),` | 等宽数字字体，列内数字自然对齐 |\r
| `,n.jsx(e.code,{children:"font-variant-numeric: tabular-nums"}),` | 强制等宽数字（每位数字占相同宽度） |\r
| `,n.jsx(e.code,{children:"white-space: nowrap"})," | 禁止金额换行，避免千分位被截断 |"]}),`
`,n.jsx(e.h3,{id:"使用方式",children:"使用方式"}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-vue",children:`<!-- 在 el-table 列模板中 -->\r
<el-table-column prop="amount" label="期末余额" align="right">\r
  <template #default="{ row }">\r
    <span class="gt-amt">{{ formatAmount(row.amount) }}</span>\r
  </template>\r
</el-table-column>\r
\r
<!-- 在 GtEditableTable 列定义中 -->\r
const columns = [\r
  { prop: 'balance', label: '余额', width: 150, align: 'right', className: 'gt-amt' },\r
]
`})}),`
`,n.jsx(e.h3,{id:"注意事项",children:"注意事项"}),`
`,n.jsxs(e.ul,{children:[`
`,n.jsxs(e.li,{children:["科目编号列也应使用 ",n.jsx(e.code,{children:".gt-amt"}),"（等宽对齐）"]}),`
`,n.jsxs(e.li,{children:["金额列统一右对齐（",n.jsx(e.code,{children:"align: 'right'"}),"）"]}),`
`,n.jsx(e.li,{children:"列宽要足够大，不折行不省略号截断"}),`
`]}),`
`,n.jsx(e.hr,{}),`
`,n.jsx(e.h2,{id:"4-表格字号规范",children:"4. 表格字号规范"}),`
`,n.jsxs(e.p,{children:["Element Plus 的 el-table 内部 DOM 层级深，",n.jsx(e.code,{children:':style="{ fontSize }"'})," 无法穿透生效。必须使用",n.jsxs(e.strong,{children:["动态 class + ",n.jsx(e.code,{children:":deep()"})," + ",n.jsx(e.code,{children:"!important"})]})," 方案。"]}),`
`,n.jsx(e.h3,{id:"正确方案",children:"正确方案"}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-vue",children:`<template>\r
  <el-table :data="data" :class="\`gt-tb-font-\${fontSize}\`">\r
    <!-- columns -->\r
  </el-table>\r
</template>\r
\r
<script setup>\r
const fontSize = ref('sm') // 'xs' | 'sm' | 'md' | 'lg'\r
<\/script>\r
\r
<style scoped>\r
:deep(.gt-tb-font-xs) th .cell,\r
:deep(.gt-tb-font-xs) td .cell {\r
  font-size: 11px !important;\r
}\r
\r
:deep(.gt-tb-font-sm) th .cell,\r
:deep(.gt-tb-font-sm) td .cell {\r
  font-size: 12px !important;\r
}\r
\r
:deep(.gt-tb-font-md) th .cell,\r
:deep(.gt-tb-font-md) td .cell {\r
  font-size: 13px !important;\r
}\r
\r
:deep(.gt-tb-font-lg) th .cell,\r
:deep(.gt-tb-font-lg) td .cell {\r
  font-size: 14px !important;\r
}\r
</style>
`})}),`
`,n.jsx(e.h3,{id:"错误方式不生效",children:"错误方式（不生效）"}),`
`,n.jsx(e.pre,{children:n.jsx(e.code,{className:"language-vue",children:`<!-- ❌ :style 无法穿透 el-table 内部 DOM -->\r
<el-table :data="data" :style="{ fontSize: '12px' }">
`})}),`
`,n.jsx(e.h3,{id:"字号选择建议",children:"字号选择建议"}),`
`,n.jsxs(e.p,{children:[`| 场景 | 推荐字号 |\r
|------|---------|\r
| 数据密集型表格（试算表/明细账） | `,n.jsx(e.code,{children:"sm"}),` (12px) |\r
| 常规列表（底稿列表/人员档案） | `,n.jsx(e.code,{children:"md"}),` (13px) |\r
| 大屏展示 / 演示模式 | `,n.jsx(e.code,{children:"lg"}),` (14px) |\r
| 紧凑模式（弹窗内表格） | `,n.jsx(e.code,{children:"xs"})," (11px) |"]}),`
`,n.jsx(e.hr,{}),`
`,n.jsx(e.h2,{id:"5-通用组件选择原则",children:"5. 通用组件选择原则"}),`
`,n.jsxs(e.ol,{children:[`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"优先复用 common 组件"}),"：在 ",n.jsx(e.code,{children:"src/components/common/"})," 中查找是否已有满足需求的组件"]}),`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"不引入 AG Grid"}),"：包体积大且与 Univer 重叠，所有表格统一用 el-table 或 GtEditableTable"]}),`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"底稿编辑器用 Univer"}),"：底稿内容编辑继续使用 Univer Core Preset"]}),`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"弹窗优先 el-dialog"}),"：除追溯类轻量信息用 el-popover，其余交互统一用 el-dialog"]}),`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"图表用 vue-echarts"}),"：已全局引入，不要引入其他图表库"]}),`
`,n.jsxs(e.li,{children:[n.jsx(e.strong,{children:"表格分页用标准分页组件"}),'：左侧 page size 选择器 + 右侧页码导航含 jumper，不用"加载更多"模式']}),`
`]})]})}function x(l={}){const{wrapper:e}={...s(),...l.components};return e?n.jsx(e,{...l,children:n.jsx(r,{...l})}):r(l)}export{x as default};
