import{k as x,l as q,q as B,a as I,u as P,z as w,G as E,E as m,A as O,c as T}from"./vue.esm-bundler-RyamH92g.js";import{u as z}from"./displayPrefs-DvHz_78L.js";import{_ as W}from"./CommentTooltip-BAHN-4hk.js";import{_ as j}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./pinia-C5bunAeq.js";import"./formatters-DqKoiXDY.js";import"./index-BITwLRGo.js";import"./_commonjsHelpers-CqkleIqs.js";/* empty css             *//* empty css                  */import"./el-tooltip-l0sNRNKZ.js";const F=Symbol("amountDivisor"),N=x({__name:"GtAmountCell",props:{value:{},clickable:{type:Boolean,default:!1},comment:{default:void 0},priorValue:{default:void 0}},emits:["click"],setup(e,{emit:D}){const o=e,G=D,s=z();I(F,1);const u=T(()=>o.value);function h(){o.clickable&&G("click",o.value)}return(M,R)=>(P(),q(W,{comment:e.comment},{default:B(()=>[w("span",{class:E(["gt-amount-cell",[m(s).amountClass(u.value,e.priorValue),{"gt-amount-cell--clickable":e.clickable}]]),style:{"white-space":"nowrap"},onClick:h},O(m(s).fmt(u.value)),3)]),_:1},8,["comment"]))}}),K=j(N,[["__scopeId","data-v-125918e4"]]);N.__docgenInfo={exportName:"default",displayName:"GtAmountCell",description:"",tags:{},props:[{name:"value",description:"金额值（number | string | null）",required:!0,type:{name:"union",elements:[{name:"number"},{name:"string"},{name:"null"},{name:"undefined"}]}},{name:"clickable",description:"是否可点击（穿透查询等）",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"comment",description:"批注对象（传入则包裹 CommentTooltip，null/undefined 时直接渲染）",required:!1,type:{name:"union",elements:[{name:"CellComment"},{name:"null"}]},defaultValue:{func:!1,value:"undefined"}},{name:"priorValue",description:"上期金额（用于变动高亮对比）",required:!1,type:{name:"union",elements:[{name:"number"},{name:"string"},{name:"null"}]},defaultValue:{func:!1,value:"undefined"}}],events:[{name:"click",type:{names:["union"],elements:[{name:"number"},{name:"string"},{name:"null"},{name:"undefined"}]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/GtAmountCell.vue"]};const ne={title:"Common/GtAmountCell",component:K,tags:["autodocs"]},a={args:{value:123456789e-2}},n={args:{value:-5e5}},r={args:{value:987654321e-2,clickable:!0}},t={args:{value:15e5,priorValue:12e5,clickable:!0}},l={args:{value:null}};var c,i,p;a.parameters={...a.parameters,docs:{...(c=a.parameters)==null?void 0:c.docs,source:{originalSource:`{
  args: {
    value: 1234567.89
  }
}`,...(p=(i=a.parameters)==null?void 0:i.docs)==null?void 0:p.source}}};var d,f,g;n.parameters={...n.parameters,docs:{...(d=n.parameters)==null?void 0:d.docs,source:{originalSource:`{
  args: {
    value: -500000
  }
}`,...(g=(f=n.parameters)==null?void 0:f.docs)==null?void 0:g.source}}};var v,k,b;r.parameters={...r.parameters,docs:{...(v=r.parameters)==null?void 0:v.docs,source:{originalSource:`{
  args: {
    value: 9876543.21,
    clickable: true
  }
}`,...(b=(k=r.parameters)==null?void 0:k.docs)==null?void 0:b.source}}};var C,_,V;t.parameters={...t.parameters,docs:{...(C=t.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    value: 1500000,
    priorValue: 1200000,
    clickable: true
  }
}`,...(V=(_=t.parameters)==null?void 0:_.docs)==null?void 0:V.source}}};var y,A,S;l.parameters={...l.parameters,docs:{...(y=l.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    value: null
  }
}`,...(S=(A=l.parameters)==null?void 0:A.docs)==null?void 0:S.source}}};const re=["Default","NegativeAmount","Clickable","WithPriorValue","NullValue"];export{r as Clickable,a as Default,n as NegativeAmount,l as NullValue,t as WithPriorValue,re as __namedExportsOrder,ne as default};
