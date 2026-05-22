import{l as K,n as Q,o as X,p as Z,d as ee}from"./index-BITwLRGo.js";/* empty css             *//* empty css                   *//* empty css                  *//* empty css                  *//* empty css                    *//* empty css                     *//* empty css                  *//* empty css               *//* empty css                  */import{k as te,l as ae,q as u,c as E,u as l,z as o,p as i,C as V,G as le,v as s,A as d,B as x,F as w,I as z,y as A,r as c}from"./vue.esm-bundler-RyamH92g.js";import{_ as oe}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const ne={class:"gt-print-controls"},re={key:0,class:"gt-print-title"},se={key:1,class:"gt-print-subtitle"},ie={class:"gt-print-table",border:"1",cellspacing:"0",cellpadding:"4"},de={key:0},ue={class:"gt-print-footer"},U=te({__name:"GtPrintPreview",props:{modelValue:{type:Boolean},data:{},columns:{},title:{default:""},subtitle:{default:""},footerLeft:{default:""},footerRight:{default:""}},emits:["update:modelValue"],setup(n,{emit:H}){const b=n,I=H,k=E({get:()=>b.modelValue,set:a=>I("update:modelValue",a)}),m=c("a4-portrait"),p=c(!0),y=c(!0),C=c(null),D=E(()=>b.columns.filter(a=>!a.hidden));function O(a,e){if(e.formatter)return e.formatter(a[e.prop],a);const r=a[e.prop];return r==null||r===""?"":String(r)}function W(){const a=C.value;if(!a)return;const e=window.open("","_blank","width=900,height=700");if(!e)return;const r=m.value.includes("landscape")?"landscape":"portrait";e.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>${b.title||"打印预览"}</title>
      <style>
        @page { size: ${r}; margin: 15mm; }
        body { font-family: 'Microsoft YaHei', sans-serif; font-size: var(--gt-font-size-xs); }
        .gt-print-title { text-align: center; font-size: var(--gt-font-size-xl); font-weight: bold; margin-bottom: 8px; }
        .gt-print-subtitle { text-align: center; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-bottom: 12px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid var(--gt-color-text-primary); padding: 4px 8px; font-size: var(--gt-font-size-xs); }
        th { background: var(--gt-color-border-lighter); font-weight: bold; }
        .gt-print-footer { display: flex; justify-content: space-between; margin-top: 12px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
        ${p.value?"":"th, td { border: none; }"}
      </style>
    </head>
    <body>${a.innerHTML}</body>
    </html>
  `),e.document.close(),e.focus(),setTimeout(()=>{e.print(),e.close()},300)}return(a,e)=>{const r=X,M=Q,P=Z,Y=ee,j=K;return l(),ae(j,{modelValue:k.value,"onUpdate:modelValue":e[3]||(e[3]=t=>k.value=t),title:"打印预览",width:"90%",top:"3vh","close-on-click-modal":!1,"append-to-body":"",class:"gt-print-preview-dialog"},{default:u(()=>[o("div",ne,[i(M,{modelValue:m.value,"onUpdate:modelValue":e[0]||(e[0]=t=>m.value=t),size:"small",style:{width:"120px"}},{default:u(()=>[i(r,{label:"A4 纵向",value:"a4-portrait"}),i(r,{label:"A4 横向",value:"a4-landscape"}),i(r,{label:"A3 横向",value:"a3-landscape"})]),_:1},8,["modelValue"]),i(P,{modelValue:p.value,"onUpdate:modelValue":e[1]||(e[1]=t=>p.value=t),size:"small"},{default:u(()=>[...e[4]||(e[4]=[V("显示网格线",-1)])]),_:1},8,["modelValue"]),i(P,{modelValue:y.value,"onUpdate:modelValue":e[2]||(e[2]=t=>y.value=t),size:"small"},{default:u(()=>[...e[5]||(e[5]=[V("显示表头",-1)])]),_:1},8,["modelValue"]),e[7]||(e[7]=o("span",{style:{flex:"1"}},null,-1)),i(Y,{type:"primary",size:"small",onClick:W},{default:u(()=>[...e[6]||(e[6]=[V("🖨️ 打印",-1)])]),_:1})]),o("div",{ref_key:"printAreaRef",ref:C,class:le(["gt-print-area",[m.value,{"no-grid":!p.value}]])},[n.title?(l(),s("div",re,d(n.title),1)):x("",!0),n.subtitle?(l(),s("div",se,d(n.subtitle),1)):x("",!0),o("table",ie,[y.value?(l(),s("thead",de,[o("tr",null,[(l(!0),s(w,null,z(D.value,t=>(l(),s("th",{key:t.prop,style:A({width:t.width?t.width+"px":"auto"})},d(t.label),5))),128))])])):x("",!0),o("tbody",null,[(l(!0),s(w,null,z(n.data,(t,J)=>(l(),s("tr",{key:J},[(l(!0),s(w,null,z(D.value,h=>(l(),s("td",{key:h.prop,style:A({textAlign:h.align||"left"})},d(O(t,h)),5))),128))]))),128))])]),o("div",ue,[o("span",null,d(n.footerLeft),1),o("span",null,"共 "+d(n.data.length)+" 行",1),o("span",null,d(n.footerRight||new Date().toLocaleDateString()),1)])],2)]),_:1},8,["modelValue"])}}}),me=oe(U,[["__scopeId","data-v-800c5df9"]]);U.__docgenInfo={exportName:"default",displayName:"GtPrintPreview",description:"",tags:{},props:[{name:"modelValue",required:!0,type:{name:"boolean"}},{name:"data",required:!0,type:{name:"Array",elements:[{name:"Record",elements:[{name:"string"},{name:"any"}]}]}},{name:"columns",required:!0,type:{name:"Array",elements:[{name:"PrintColumn"}]}},{name:"title",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}},{name:"subtitle",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}},{name:"footerLeft",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}},{name:"footerRight",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}}],events:[{name:"update:modelValue",type:{names:["boolean"]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/GtPrintPreview.vue"]};const ke={title:"Common/GtPrintPreview",component:me,tags:["autodocs"]},_=[{prop:"code",label:"科目编号",width:100},{prop:"name",label:"科目名称",width:200},{prop:"debit",label:"借方",width:120,align:"right"},{prop:"credit",label:"贷方",width:120,align:"right"}],$=[{code:"1001",name:"库存现金",debit:5e4,credit:0},{code:"1002",name:"银行存款",debit:495e4,credit:1e5},{code:"1012",name:"其他货币资金",debit:12e4,credit:0}],f={args:{modelValue:!0,data:$,columns:_,title:"试算平衡表",subtitle:"2025年度"}},g={args:{modelValue:!0,data:$,columns:_,title:"科目余额表",footerLeft:"致同会计师事务所",footerRight:"2025-01-15"}},v={args:{modelValue:!0,data:[],columns:_,title:"空表格预览"}};var L,S,q;f.parameters={...f.parameters,docs:{...(L=f.parameters)==null?void 0:L.docs,source:{originalSource:`{
  args: {
    modelValue: true,
    data: sampleData,
    columns: sampleColumns,
    title: '试算平衡表',
    subtitle: '2025年度'
  }
}`,...(q=(S=f.parameters)==null?void 0:S.docs)==null?void 0:q.source}}};var G,R,B;g.parameters={...g.parameters,docs:{...(G=g.parameters)==null?void 0:G.docs,source:{originalSource:`{
  args: {
    modelValue: true,
    data: sampleData,
    columns: sampleColumns,
    title: '科目余额表',
    footerLeft: '致同会计师事务所',
    footerRight: '2025-01-15'
  }
}`,...(B=(R=g.parameters)==null?void 0:R.docs)==null?void 0:B.source}}};var N,F,T;v.parameters={...v.parameters,docs:{...(N=v.parameters)==null?void 0:N.docs,source:{originalSource:`{
  args: {
    modelValue: true,
    data: [],
    columns: sampleColumns,
    title: '空表格预览'
  }
}`,...(T=(F=v.parameters)==null?void 0:F.docs)==null?void 0:T.source}}};const Ce=["Default","WithFooter","EmptyData"];export{f as Default,v as EmptyData,g as WithFooter,Ce as __namedExportsOrder,ke as default};
