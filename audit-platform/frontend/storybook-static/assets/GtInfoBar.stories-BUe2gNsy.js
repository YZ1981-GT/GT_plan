import{n as J,o as K}from"./index-BITwLRGo.js";/* empty css             *//* empty css                     *//* empty css                  *//* empty css               *//* empty css                  */import{r as f,c as B,k as M,v as i,F as m,z as s,p as L,q as N,B as g,A as Y,I as h,D as Q,u as l,l as j}from"./vue.esm-bundler-RyamH92g.js";import{d as X}from"./pinia-C5bunAeq.js";import{h as Z,p as ee}from"./auth-CjxQtL2d.js";import{api as ae}from"./apiProxy-DePeTMgn.js";import{e as te}from"./eventBus-CGRXT3Tn.js";import{u as ne}from"./displayPrefs-DvHz_78L.js";import{u as se}from"./dict-f6tOPmPh.js";import{_ as le}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";import"./iframe-DRCZA9bM.js";import"./formatters-DqKoiXDY.js";async function R(t){const{data:n}=await Z.get(ee.detail(t));return n}async function oe(t){const n=await R(t),u=Number(n==null?void 0:n.audit_year);return Number.isFinite(u)&&u>2e3?u:null}const D=new Date().getFullYear(),re=X("project",()=>{const t=f(""),n=f(D-1),u=f("soe"),b=f(""),p=f(null),v=f([]),q=B(()=>{const e=D;return[e-2,e-1,e,e+1]});async function c(e){const r=e.params.projectId;if(!r){t.value="",b.value="",p.value=null;return}const d=r!==t.value;t.value=r;const k=Number(e.query.year);if(Number.isFinite(k)&&k>2e3)n.value=k;else if(d)try{const o=await oe(r);o&&(p.value=o,n.value=o)}catch{}if(d)try{const o=await R(r);if(b.value=(o==null?void 0:o.client_name)||(o==null?void 0:o.name)||"",o!=null&&o.audit_year){const I=Number(o.audit_year);Number.isFinite(I)&&I>2e3&&(p.value=I)}}catch{}}function a(e){const r=n.value;n.value=e,r!==e&&t.value&&te.emit("year:changed",{projectId:t.value,year:e})}function y(e){u.value=e}async function _(){if(!(v.value.length>0))try{const e=await ae.get("/api/projects",{params:{page_size:200},validateStatus:d=>d<600}),r=(e==null?void 0:e.items)??e??[];v.value=(Array.isArray(r)?r:[]).map(d=>({id:d.id,name:d.client_name||d.name||d.id}))}catch{}}return{projectId:t,year:n,standard:u,clientName:b,auditYear:p,projectOptions:v,yearOptions:q,syncFromRoute:c,changeYear:a,changeStandard:y,loadProjectOptions:_}}),ie={class:"gt-info-bar"},ue={class:"gt-info-bar__item"},ce={class:"gt-info-bar__item"},de={class:"gt-info-bar__item"},me={class:"gt-info-bar__item"},pe={class:"gt-info-bar__badge"},fe={class:"gt-info-bar__item"},ge={key:0,class:"gt-info-bar__label"},be={class:"gt-info-bar__badge"},ve={key:0,class:"gt-info-bar__sep"},H=M({__name:"GtInfoBar",props:{showUnit:{type:Boolean,default:!1},showYear:{type:Boolean,default:!1},showTemplate:{type:Boolean,default:!1},showScope:{type:Boolean,default:!1},scopeLabel:{default:""},unitValue:{default:""},yearValue:{default:void 0},templateValue:{default:""},templateOptions:{default:void 0},unitOptions:{default:void 0},yearOptionsList:{default:void 0},badges:{default:()=>[]}},emits:["unit-change","year-change","template-change","scope-change"],setup(t){const n=t,u=re();ne();const b=se(),p=B(()=>n.unitOptions??u.projectOptions),v=B(()=>n.yearOptionsList??u.yearOptions),q=B(()=>{if(n.templateOptions)return n.templateOptions;const c=b.options("applicable_standard");return c.length>0?c.map(a=>({label:a.label,value:a.value})):[{label:"国企版",value:"soe"},{label:"上市版",value:"listed"}]});return(c,a)=>{const y=K,_=J;return l(),i("div",ie,[t.showUnit?(l(),i(m,{key:0},[s("div",ue,[a[3]||(a[3]=s("span",{class:"gt-info-bar__label"},"单位",-1)),L(_,{"model-value":t.unitValue,size:"small",class:"gt-info-bar__select gt-info-bar__select--unit",filterable:"",onChange:a[0]||(a[0]=e=>c.$emit("unit-change",e))},{default:N(()=>[(l(!0),i(m,null,h(p.value,e=>(l(),j(y,{key:e.id,label:e.name,value:e.id},null,8,["label","value"]))),128))]),_:1},8,["model-value"])]),a[4]||(a[4]=s("div",{class:"gt-info-bar__sep"},null,-1))],64)):g("",!0),t.showYear?(l(),i(m,{key:1},[s("div",ce,[a[5]||(a[5]=s("span",{class:"gt-info-bar__label"},"年度",-1)),L(_,{"model-value":t.yearValue,size:"small",class:"gt-info-bar__select gt-info-bar__select--year",onChange:a[1]||(a[1]=e=>c.$emit("year-change",e))},{default:N(()=>[(l(!0),i(m,null,h(v.value,e=>(l(),j(y,{key:e,label:e+"年",value:e},null,8,["label","value"]))),128))]),_:1},8,["model-value"])]),a[6]||(a[6]=s("div",{class:"gt-info-bar__sep"},null,-1))],64)):g("",!0),t.showTemplate?(l(),i(m,{key:2},[s("div",de,[a[7]||(a[7]=s("span",{class:"gt-info-bar__label"},"模板",-1)),L(_,{"model-value":t.templateValue,size:"small",class:"gt-info-bar__select gt-info-bar__select--tpl",onChange:a[2]||(a[2]=e=>c.$emit("template-change",e))},{default:N(()=>[(l(!0),i(m,null,h(q.value,e=>(l(),j(y,{key:e.value,label:e.label,value:e.value},null,8,["label","value"]))),128))]),_:1},8,["model-value"])]),a[8]||(a[8]=s("div",{class:"gt-info-bar__sep"},null,-1))],64)):g("",!0),t.showScope?(l(),i(m,{key:3},[s("div",me,[a[9]||(a[9]=s("span",{class:"gt-info-bar__label"},"口径",-1)),s("span",pe,Y(t.scopeLabel),1)]),a[10]||(a[10]=s("div",{class:"gt-info-bar__sep"},null,-1))],64)):g("",!0),(l(!0),i(m,null,h(t.badges,(e,r)=>(l(),i(m,{key:r},[s("div",fe,[e.label?(l(),i("span",ge,Y(e.label),1)):g("",!0),s("span",be,Y(e.value),1)]),r<t.badges.length-1?(l(),i("div",ve)):g("",!0)],64))),128)),Q(c.$slots,"default",{},void 0,!0)])}}}),ye=le(H,[["__scopeId","data-v-ce16a040"]]);H.__docgenInfo={exportName:"default",displayName:"GtInfoBar",description:"",tags:{},props:[{name:"showUnit",description:"显示单位选择器",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"showYear",description:"显示年度选择器",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"showTemplate",description:"显示模板选择器",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"showScope",description:"显示口径标签",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"scopeLabel",description:"口径文本",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}},{name:"unitValue",description:"当前选中的单位 ID",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}},{name:"yearValue",description:"当前选中的年度",required:!1,type:{name:"number"},defaultValue:{func:!1,value:"undefined"}},{name:"templateValue",description:"当前选中的模板",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}},{name:"templateOptions",description:"模板选项列表（覆盖 dictStore 默认值）",required:!1,type:{name:"Array",elements:[{name:"TemplateOption"}]},defaultValue:{func:!1,value:"undefined"}},{name:"unitOptions",description:"单位选项列表（覆盖 projectStore 默认值）",required:!1,type:{name:"Array",elements:[{name:"{ id: string; name: string }"}]},defaultValue:{func:!1,value:"undefined"}},{name:"yearOptionsList",description:"年度选项列表（覆盖 projectStore 默认值）",required:!1,type:{name:"Array",elements:[{name:"number"}]},defaultValue:{func:!1,value:"undefined"}},{name:"badges",description:"徽章列表",required:!1,type:{name:"Array",elements:[{name:"InfoBadge"}]},defaultValue:{func:!1,value:"() => []"}}],events:[{name:"unit-change",type:{names:["string"]}},{name:"year-change",type:{names:["number"]}},{name:"template-change",type:{names:["string"]}},{name:"scope-change",type:{names:["string"]}}],slots:[{name:"default"}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/GtInfoBar.vue"]};const Fe={title:"Common/GtInfoBar",component:ye,tags:["autodocs"]},V={args:{badges:[{label:"科目",value:"128 个"},{label:"差异",value:"3 项"}]}},O={args:{showUnit:!0,showYear:!0,unitValue:"1",yearValue:2025,unitOptions:[{id:"1",name:"致同会计师事务所"},{id:"2",name:"示例公司"}],yearOptionsList:[2025,2024,2023],badges:[{label:"状态",value:"已审定"}]}},w={args:{showTemplate:!0,templateValue:"soe",templateOptions:[{label:"国企版",value:"soe"},{label:"上市版",value:"listed"}],badges:[]}},S={args:{showScope:!0,scopeLabel:"合并口径",badges:[{label:"行数",value:"56 行"}]}};var T,A,F;V.parameters={...V.parameters,docs:{...(T=V.parameters)==null?void 0:T.docs,source:{originalSource:`{
  args: {
    badges: [{
      label: '科目',
      value: '128 个'
    }, {
      label: '差异',
      value: '3 项'
    }]
  }
}`,...(F=(A=V.parameters)==null?void 0:A.docs)==null?void 0:F.source}}};var C,G,W;O.parameters={...O.parameters,docs:{...(C=O.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    showUnit: true,
    showYear: true,
    unitValue: '1',
    yearValue: 2025,
    unitOptions: [{
      id: '1',
      name: '致同会计师事务所'
    }, {
      id: '2',
      name: '示例公司'
    }],
    yearOptionsList: [2025, 2024, 2023],
    badges: [{
      label: '状态',
      value: '已审定'
    }]
  }
}`,...(W=(G=O.parameters)==null?void 0:G.docs)==null?void 0:W.source}}};var z,P,U;w.parameters={...w.parameters,docs:{...(z=w.parameters)==null?void 0:z.docs,source:{originalSource:`{
  args: {
    showTemplate: true,
    templateValue: 'soe',
    templateOptions: [{
      label: '国企版',
      value: 'soe'
    }, {
      label: '上市版',
      value: 'listed'
    }],
    badges: []
  }
}`,...(U=(P=w.parameters)==null?void 0:P.docs)==null?void 0:U.source}}};var E,$,x;S.parameters={...S.parameters,docs:{...(E=S.parameters)==null?void 0:E.docs,source:{originalSource:`{
  args: {
    showScope: true,
    scopeLabel: '合并口径',
    badges: [{
      label: '行数',
      value: '56 行'
    }]
  }
}`,...(x=($=S.parameters)==null?void 0:$.docs)==null?void 0:x.source}}};const Ce=["Default","WithSelectors","WithTemplate","WithScope"];export{V as Default,S as WithScope,O as WithSelectors,w as WithTemplate,Ce as __namedExportsOrder,Fe as default};
