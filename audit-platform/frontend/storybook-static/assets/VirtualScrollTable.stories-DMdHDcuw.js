import{k as B,N as L,w as F,u as l,v as o,z as u,F as p,I as v,y as c,A as y,G as E,D as G,C as R,B as W,r as b,c as x}from"./vue.esm-bundler-RyamH92g.js";import{a as O}from"./formatters-DqKoiXDY.js";import{_ as j}from"./_plugin-vue_export-helper-DlAUqK2U.js";const J={class:"gt-virtual-table"},K={class:"gt-vt-header"},P=["onClick"],Q={class:"gt-vt-footer"},U={key:0,class:"gt-vt-hint"},T=B({__name:"VirtualScrollTable",props:{data:{},columns:{},rowHeight:{default:36},height:{default:500},bufferSize:{default:10},activeIndex:{default:null}},emits:["row-click"],setup(r){L(t=>({v954673ac:e.rowHeight+"px"}));const e=r,g=b(null),f=b(0),M=x(()=>e.data.length*e.rowHeight),z=x(()=>{const t=Math.max(0,Math.floor(f.value/e.rowHeight)-e.bufferSize),s=Math.ceil(e.height/e.rowHeight),a=Math.min(e.data.length,t+s+e.bufferSize*2);return e.data.slice(t,a).map((i,n)=>({...i,_index:t+n,_top:(t+n)*e.rowHeight,_key:i.id||i.voucher_no||`row-${t+n}`}))});function q(t){f.value=t.target.scrollTop}function N(t,s){return t==null?"-":s.formatter?s.formatter(t):typeof t=="number"?t===0?"-":O(t):String(t)}return F(()=>e.data.length,()=>{g.value&&(g.value.scrollTop=0),f.value=0}),(t,s)=>(l(),o("div",J,[u("div",K,[(l(!0),o(p,null,v(r.columns,a=>(l(),o("div",{key:a.key,class:"gt-vt-cell gt-vt-th",style:c({width:a.width||"auto",flex:a.width?"none":"1",textAlign:a.align||"left"})},y(a.label),5))),128))]),u("div",{ref_key:"scrollContainer",ref:g,class:"gt-vt-body",style:c({height:r.height+"px"}),onScroll:q},[u("div",{style:c({height:M.value+"px",position:"relative"})},[(l(!0),o(p,null,v(z.value,(a,i)=>(l(),o("div",{key:a._key||i,class:E(["gt-vt-row",{"gt-vt-row--active":r.activeIndex===a._index,"gt-vt-row--stripe":a._index%2===1}]),style:c({position:"absolute",top:a._top+"px",width:"100%"}),onClick:n=>t.$emit("row-click",a,a._index)},[(l(!0),o(p,null,v(r.columns,n=>(l(),o("div",{key:n.key,class:"gt-vt-cell",style:c({width:n.width||"auto",flex:n.width?"none":"1",textAlign:n.align||"left"})},[G(t.$slots,n.key,{row:a,value:a[n.key]},()=>[R(y(N(a[n.key],n)),1)],!0)],4))),128))],14,P))),128))],4)],36),u("div",Q,[u("span",null,"共 "+y(r.data.length.toLocaleString())+" 条",1),r.data.length>1e3?(l(),o("span",U,"虚拟滚动已启用")):W("",!0)])]))}}),X=j(T,[["__scopeId","data-v-6c359c1b"]]);T.__docgenInfo={exportName:"default",displayName:"VirtualScrollTable",description:"",tags:{},props:[{name:"data",required:!0,type:{name:"Array",elements:[{name:"any"}]}},{name:"columns",required:!0,type:{name:"Array",elements:[{name:"VTColumn"}]}},{name:"rowHeight",required:!1,type:{name:"number"},defaultValue:{func:!1,value:"36"}},{name:"height",required:!1,type:{name:"number"},defaultValue:{func:!1,value:"500"}},{name:"bufferSize",required:!1,type:{name:"number"},defaultValue:{func:!1,value:"10"}},{name:"activeIndex",required:!1,type:{name:"union",elements:[{name:"number"},{name:"null"}]},defaultValue:{func:!1,value:"null"}}],events:[{name:"row-click",type:{names:["any"]}}],slots:[{name:"col.key",scoped:!0,bindings:[{name:"name",title:"binding"},{name:"row",title:"binding"},{name:"value",title:"binding"}]}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/VirtualScrollTable.vue"]};const te={title:"Common/VirtualScrollTable",component:X,tags:["autodocs"]},w=[{key:"code",label:"科目编号",width:"120px"},{key:"name",label:"科目名称",width:"200px"},{key:"balance",label:"期末余额",width:"150px",align:"right"}],D=Array.from({length:200},(r,e)=>({id:`row-${e}`,code:`${1001+e}`,name:`科目名称 ${e+1}`,balance:Math.round(Math.random()*1e6)})),d={args:{columns:w,data:D,height:400,rowHeight:36}},m={args:{columns:w,data:Array.from({length:5e3},(r,e)=>({id:`row-${e}`,code:`${1001+e}`,name:`明细科目 ${e+1}`,balance:Math.round(Math.random()*5e6)})),height:500,rowHeight:36}},h={args:{columns:w,data:D,height:400,activeIndex:5}};var _,k,S;d.parameters={...d.parameters,docs:{...(_=d.parameters)==null?void 0:_.docs,source:{originalSource:`{
  args: {
    columns: sampleColumns,
    data: sampleData,
    height: 400,
    rowHeight: 36
  }
}`,...(S=(k=d.parameters)==null?void 0:k.docs)==null?void 0:S.source}}};var C,V,$;m.parameters={...m.parameters,docs:{...(C=m.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    columns: sampleColumns,
    data: Array.from({
      length: 5000
    }, (_, i) => ({
      id: \`row-\${i}\`,
      code: \`\${1001 + i}\`,
      name: \`明细科目 \${i + 1}\`,
      balance: Math.round(Math.random() * 5000000)
    })),
    height: 500,
    rowHeight: 36
  }
}`,...($=(V=m.parameters)==null?void 0:V.docs)==null?void 0:$.source}}};var H,A,I;h.parameters={...h.parameters,docs:{...(H=h.parameters)==null?void 0:H.docs,source:{originalSource:`{
  args: {
    columns: sampleColumns,
    data: sampleData,
    height: 400,
    activeIndex: 5
  }
}`,...(I=(A=h.parameters)==null?void 0:A.docs)==null?void 0:I.source}}};const ae=["Default","LargeDataset","WithActiveRow"];export{d as Default,m as LargeDataset,h as WithActiveRow,ae as __namedExportsOrder,te as default};
