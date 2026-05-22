import{E as n,q as v}from"./index-BITwLRGo.js";/* empty css             */import{k as B,v as F,l as O,B as q,u as c}from"./vue.esm-bundler-RyamH92g.js";import"./_commonjsHelpers-CqkleIqs.js";const N={class:"operation-feedback"},w=B({__name:"OperationFeedback",props:{showProgress:{type:Boolean,default:!1},progress:{default:0},progressStatus:{default:""}},setup(t,{expose:_}){function k(e){n({title:"操作成功",message:e,type:"success",duration:3e3})}function E(e){n({title:"操作失败",message:e,type:"error",duration:5e3})}function x(e){n({title:"处理中",message:e,type:"info",duration:2e3})}return _({notifySuccess:k,notifyError:E,notifyProgress:x}),(e,V)=>{const b=v;return c(),F("div",N,[t.showProgress?(c(),O(b,{key:0,percentage:t.progress,status:t.progressStatus,"stroke-width":4},null,8,["percentage","status"])):q("",!0)])}}});w.__docgenInfo={exportName:"default",displayName:"OperationFeedback",description:"",tags:{},expose:[{name:"notifySuccess"},{name:"notifyError"},{name:"notifyProgress"}],props:[{name:"showProgress",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"progress",required:!1,type:{name:"number"},defaultValue:{func:!1,value:"0"}},{name:"progressStatus",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/OperationFeedback.vue"]};const T={title:"Common/OperationFeedback",component:w,tags:["autodocs"]},s={args:{showProgress:!1,progress:0}},r={args:{showProgress:!0,progress:45,progressStatus:""}},o={args:{showProgress:!0,progress:100,progressStatus:"success"}},a={args:{showProgress:!0,progress:70,progressStatus:"exception"}};var u,p,g;s.parameters={...s.parameters,docs:{...(u=s.parameters)==null?void 0:u.docs,source:{originalSource:`{
  args: {
    showProgress: false,
    progress: 0
  }
}`,...(g=(p=s.parameters)==null?void 0:p.docs)==null?void 0:g.source}}};var i,l,m;r.parameters={...r.parameters,docs:{...(i=r.parameters)==null?void 0:i.docs,source:{originalSource:`{
  args: {
    showProgress: true,
    progress: 45,
    progressStatus: ''
  }
}`,...(m=(l=r.parameters)==null?void 0:l.docs)==null?void 0:m.source}}};var d,f,S;o.parameters={...o.parameters,docs:{...(d=o.parameters)==null?void 0:d.docs,source:{originalSource:`{
  args: {
    showProgress: true,
    progress: 100,
    progressStatus: 'success'
  }
}`,...(S=(f=o.parameters)==null?void 0:f.docs)==null?void 0:S.source}}};var P,y,h;a.parameters={...a.parameters,docs:{...(P=a.parameters)==null?void 0:P.docs,source:{originalSource:`{
  args: {
    showProgress: true,
    progress: 70,
    progressStatus: 'exception'
  }
}`,...(h=(y=a.parameters)==null?void 0:y.docs)==null?void 0:h.source}}};const j=["Default","InProgress","Success","Error"];export{s as Default,a as Error,r as InProgress,o as Success,j as __namedExportsOrder,T as default};
