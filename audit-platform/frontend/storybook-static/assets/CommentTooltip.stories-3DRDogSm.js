import{_ as r}from"./CommentTooltip-BAHN-4hk.js";import"./index-BITwLRGo.js";import"./vue.esm-bundler-RyamH92g.js";import"./_commonjsHelpers-CqkleIqs.js";/* empty css             *//* empty css                  */import"./el-tooltip-l0sNRNKZ.js";const f={title:"Common/CommentTooltip",component:r,tags:["autodocs"],decorators:[()=>({template:'<div style="padding: 60px;"><story /></div>'})]},o={args:{comment:{id:"1",project_id:"p1",year:2025,module:"tb",sheet_key:"sheet1",row_idx:4,col_idx:1,row_name:"银行存款",col_name:"期末余额",comment:"此金额需要复核确认",comment_type:"comment",status:"pending",created_at:"2025-06-01T10:30:00Z"}},render:e=>({components:{CommentTooltip:r},setup:()=>({args:e}),template:'<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#f0f0f0;border-radius:4px">¥5,000,000</span></CommentTooltip>'})},t={args:{comment:{id:"2",project_id:"p1",year:2025,module:"tb",sheet_key:"sheet1",row_idx:9,col_idx:2,row_name:"应收账款",col_name:"期末余额",comment:"已复核，金额正确",comment_type:"review",status:"reviewed",created_at:"2025-06-02T14:00:00Z"}},render:e=>({components:{CommentTooltip:r},setup:()=>({args:e}),template:'<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#e8f5e9;border-radius:4px">¥1,200,000</span></CommentTooltip>'})},m={args:{comment:null},render:e=>({components:{CommentTooltip:r},setup:()=>({args:e}),template:'<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#f0f0f0;border-radius:4px">¥800,000</span></CommentTooltip>'})};var a,n,p;o.parameters={...o.parameters,docs:{...(a=o.parameters)==null?void 0:a.docs,source:{originalSource:`{
  args: {
    comment: {
      id: '1',
      project_id: 'p1',
      year: 2025,
      module: 'tb',
      sheet_key: 'sheet1',
      row_idx: 4,
      col_idx: 1,
      row_name: '银行存款',
      col_name: '期末余额',
      comment: '此金额需要复核确认',
      comment_type: 'comment',
      status: 'pending',
      created_at: '2025-06-01T10:30:00Z'
    }
  },
  render: args => ({
    components: {
      CommentTooltip
    },
    setup: () => ({
      args
    }),
    template: '<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#f0f0f0;border-radius:4px">¥5,000,000</span></CommentTooltip>'
  })
}`,...(p=(n=o.parameters)==null?void 0:n.docs)==null?void 0:p.source}}};var s,d,i;t.parameters={...t.parameters,docs:{...(s=t.parameters)==null?void 0:s.docs,source:{originalSource:`{
  args: {
    comment: {
      id: '2',
      project_id: 'p1',
      year: 2025,
      module: 'tb',
      sheet_key: 'sheet1',
      row_idx: 9,
      col_idx: 2,
      row_name: '应收账款',
      col_name: '期末余额',
      comment: '已复核，金额正确',
      comment_type: 'review',
      status: 'reviewed',
      created_at: '2025-06-02T14:00:00Z'
    }
  },
  render: args => ({
    components: {
      CommentTooltip
    },
    setup: () => ({
      args
    }),
    template: '<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#e8f5e9;border-radius:4px">¥1,200,000</span></CommentTooltip>'
  })
}`,...(i=(d=t.parameters)==null?void 0:d.docs)==null?void 0:i.source}}};var c,l,u;m.parameters={...m.parameters,docs:{...(c=m.parameters)==null?void 0:c.docs,source:{originalSource:`{
  args: {
    comment: null
  },
  render: args => ({
    components: {
      CommentTooltip
    },
    setup: () => ({
      args
    }),
    template: '<CommentTooltip v-bind="args"><span style="padding:4px 8px;background:#f0f0f0;border-radius:4px">¥800,000</span></CommentTooltip>'
  })
}`,...(u=(l=m.parameters)==null?void 0:l.docs)==null?void 0:u.source}}};const v=["Default","ReviewComment","NoComment"];export{o as Default,m as NoComment,t as ReviewComment,v as __namedExportsOrder,f as default};
