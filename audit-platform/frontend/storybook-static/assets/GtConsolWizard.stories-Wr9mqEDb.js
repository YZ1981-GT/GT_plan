import{D as z,F as G}from"./index-BITwLRGo.js";/* empty css             */import{k as W,v as p,p as q,q as A,u as c,F as D,I as E,l as F}from"./vue.esm-bundler-RyamH92g.js";import{_ as V}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const B={class:"gt-consol-wizard"},g=W({__name:"GtConsolWizard",props:{activeStep:{default:0},steps:{default:()=>[{title:"合并范围",description:"配置子公司",tabName:"structure"},{title:"导入数据",description:"子公司余额表",tabName:"worksheets"},{title:"合并试算",description:"汇总重算",tabName:"worksheets"},{title:"抵消分录",description:"编制抵消",tabName:"worksheets"},{title:"合并报表",description:"生成报表",tabName:"worksheets"},{title:"合并附注",description:"编制附注",tabName:"worksheets"}]},completedSteps:{default:()=>[]}},emits:["step-click"],setup(o,{emit:b}){const t=o,h=b;function N(e){return t.completedSteps[e]?"success":e===t.activeStep?"process":e<t.activeStep?"finish":"wait"}function w(e){h("step-click",e,t.steps[e])}return(e,M)=>{const C=G,y=z;return c(),p("div",B,[q(y,{active:o.activeStep,"finish-status":"success","align-center":"",size:"small"},{default:A(()=>[(c(!0),p(D,null,E(o.steps,(n,i)=>(c(),F(C,{key:i,title:n.title,description:n.description,icon:n.icon,status:N(i),onClick:P=>w(i),style:{cursor:"pointer"}},null,8,["title","description","icon","status","onClick"]))),128))]),_:1},8,["active"])])}}}),I=V(g,[["__scopeId","data-v-83b3205f"]]);g.__docgenInfo={exportName:"default",displayName:"GtConsolWizard",description:"",tags:{},props:[{name:"activeStep",description:"当前激活步骤（0-based）",required:!1,type:{name:"number"},defaultValue:{func:!1,value:"0"}},{name:"steps",description:"步骤定义",required:!1,type:{name:"Array",elements:[{name:"WizardStep"}]},defaultValue:{func:!1,value:`() => [\r
  { title: '合并范围', description: '配置子公司', tabName: 'structure' },\r
  { title: '导入数据', description: '子公司余额表', tabName: 'worksheets' },\r
  { title: '合并试算', description: '汇总重算', tabName: 'worksheets' },\r
  { title: '抵消分录', description: '编制抵消', tabName: 'worksheets' },\r
  { title: '合并报表', description: '生成报表', tabName: 'worksheets' },\r
  { title: '合并附注', description: '编制附注', tabName: 'worksheets' },\r
]`}},{name:"completedSteps",description:"各步骤完成状态",required:!1,type:{name:"Array",elements:[{name:"boolean"}]},defaultValue:{func:!1,value:"() => []"}}],events:[{name:"step-click",type:{names:["number"]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/GtConsolWizard.vue"]};const j={title:"Common/GtConsolWizard",component:I,tags:["autodocs"]},s={args:{activeStep:0}},r={args:{activeStep:3,completedSteps:[!0,!0,!0,!1,!1,!1]}},a={args:{activeStep:5,completedSteps:[!0,!0,!0,!0,!0,!0]}};var l,u,m;s.parameters={...s.parameters,docs:{...(l=s.parameters)==null?void 0:l.docs,source:{originalSource:`{
  args: {
    activeStep: 0
  }
}`,...(m=(u=s.parameters)==null?void 0:u.docs)==null?void 0:m.source}}};var d,f,S;r.parameters={...r.parameters,docs:{...(d=r.parameters)==null?void 0:d.docs,source:{originalSource:`{
  args: {
    activeStep: 3,
    completedSteps: [true, true, true, false, false, false]
  }
}`,...(S=(f=r.parameters)==null?void 0:f.docs)==null?void 0:S.source}}};var v,k,_;a.parameters={...a.parameters,docs:{...(v=a.parameters)==null?void 0:v.docs,source:{originalSource:`{
  args: {
    activeStep: 5,
    completedSteps: [true, true, true, true, true, true]
  }
}`,...(_=(k=a.parameters)==null?void 0:k.docs)==null?void 0:_.source}}};const H=["Default","MidProgress","AllCompleted"];export{a as AllCompleted,s as Default,r as MidProgress,H as __namedExportsOrder,j as default};
