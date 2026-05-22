import{l as k,c as x,e as E,f as $,d as F}from"./index-BITwLRGo.js";/* empty css             *//* empty css                   *//* empty css                  *//* empty css                  *//* empty css                     *//* empty css                  */import"./el-tooltip-l0sNRNKZ.js";/* empty css                    *//* empty css                        *//* empty css               */import{k as S,l as f,q as l,u as _,z as u,p as e,C as r,A as i,B as V,G as A,r as q}from"./vue.esm-bundler-RyamH92g.js";import{_ as z}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const G={class:"gt-prefill-summary"},H={class:"gt-prefill-old"},I={class:"gt-prefill-new"},P=S({__name:"PrefillDiffPanel",props:{visible:{type:Boolean},changes:{},summary:{}},emits:["update:visible","accept-all","accept-selected","cancel"],setup(n){const c=q([]);function B(s){c.value=s.map(t=>t.cell_ref)}function p(s){return s==null?"-":s.toLocaleString("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2})}return(s,t)=>{const m=x,o=$,N=E,g=F,T=k;return _(),f(T,{"model-value":n.visible,"onUpdate:modelValue":t[3]||(t[3]=a=>s.$emit("update:visible",a)),title:"预填充变更预览",width:"800px","append-to-body":""},{footer:l(()=>[e(g,{onClick:t[0]||(t[0]=a=>s.$emit("cancel"))},{default:l(()=>[...t[4]||(t[4]=[r("取消",-1)])]),_:1}),e(g,{type:"primary",disabled:c.value.length===0&&n.changes.length>0,onClick:t[1]||(t[1]=a=>s.$emit("accept-selected",c.value))},{default:l(()=>[r(" 应用选中 ("+i(c.value.length)+") ",1)]),_:1},8,["disabled"]),e(g,{type:"success",onClick:t[2]||(t[2]=a=>s.$emit("accept-all"))},{default:l(()=>[r(" 全部接受 ("+i(n.changes.length)+") ",1)]),_:1})]),default:l(()=>[u("div",G,[e(m,{type:"info"},{default:l(()=>[r("总变更 "+i(n.summary.total_changes),1)]),_:1}),e(m,{type:"success"},{default:l(()=>[r("新增 "+i(n.summary.new_cells),1)]),_:1}),e(m,{type:"warning"},{default:l(()=>[r("修改 "+i(n.summary.modified_cells),1)]),_:1}),n.summary.highlight_count>0?(_(),f(m,{key:0,type:"danger"},{default:l(()=>[r(" ⚠️ 大幅变动 "+i(n.summary.highlight_count),1)]),_:1})):V("",!0)]),e(N,{data:n.changes,border:"",size:"small","max-height":"400px",onSelectionChange:B},{default:l(()=>[e(o,{type:"selection",width:"40"}),e(o,{prop:"sheet",label:"Sheet",width:"150"}),e(o,{prop:"cell_ref",label:"单元格",width:"80"}),e(o,{prop:"formula",label:"公式",width:"200","show-overflow-tooltip":""}),e(o,{label:"旧值",width:"120"},{default:l(({row:a})=>[u("span",H,i(p(a.old_value)),1)]),_:1}),e(o,{label:"新值",width:"120"},{default:l(({row:a})=>[u("span",I,i(p(a.new_value)),1)]),_:1}),e(o,{label:"变动",width:"80"},{default:l(({row:a})=>[u("span",{class:A({"gt-prefill-highlight":a.is_highlight})},i(a.change_pct!=null?`${a.change_pct.toFixed(1)}%`:"-"),3)]),_:1})]),_:1},8,["data"])]),_:1},8,["model-value"])}}}),U=z(P,[["__scopeId","data-v-ef2b1dfc"]]);P.__docgenInfo={exportName:"default",displayName:"PrefillDiffPanel",description:"",tags:{},props:[{name:"visible",required:!0,type:{name:"boolean"}},{name:"changes",required:!0,type:{name:"Array",elements:[{name:"PrefillChange"}]}},{name:"summary",required:!0,type:{name:`{\r
  total_changes: number\r
  new_cells: number\r
  modified_cells: number\r
  highlight_count: number\r
}`}}],events:[{name:"update:visible",type:{names:["boolean"]}},{name:"cancel"},{name:"accept-selected",type:{names:["Array"],elements:[{name:"string"}]}},{name:"accept-all"}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/workpaper/PrefillDiffPanel.vue"]};const ae={title:"Common/PrefillDiffPanel",component:U,tags:["autodocs"]},L=[{sheet:"审定表D2-1",cell_ref:"E5",formula:'=TB("6001","期末余额")',old_value:12e5,new_value:135e4,change_pct:12.5,is_highlight:!1},{sheet:"审定表D2-1",cell_ref:"E8",formula:'=TB("6051","期末余额")',old_value:5e5,new_value:68e4,change_pct:36,is_highlight:!0},{sheet:"明细表D2-2",cell_ref:"C3",formula:'=AUX("6001","客户","A公司","期末余额")',old_value:null,new_value:25e4,change_pct:null,is_highlight:!1}],d={args:{visible:!0,changes:L,summary:{total_changes:3,new_cells:1,modified_cells:2,highlight_count:1}}},h={args:{visible:!0,changes:[{sheet:"审定表F2-1",cell_ref:"D4",formula:'=TB("1403","期末余额")',old_value:8e5,new_value:82e4,change_pct:2.5,is_highlight:!1}],summary:{total_changes:1,new_cells:0,modified_cells:1,highlight_count:0}}};var v,b,y;d.parameters={...d.parameters,docs:{...(v=d.parameters)==null?void 0:v.docs,source:{originalSource:`{
  args: {
    visible: true,
    changes: sampleChanges,
    summary: {
      total_changes: 3,
      new_cells: 1,
      modified_cells: 2,
      highlight_count: 1
    }
  }
}`,...(y=(b=d.parameters)==null?void 0:b.docs)==null?void 0:y.source}}};var w,C,D;h.parameters={...h.parameters,docs:{...(w=h.parameters)==null?void 0:w.docs,source:{originalSource:`{
  args: {
    visible: true,
    changes: [{
      sheet: '审定表F2-1',
      cell_ref: 'D4',
      formula: '=TB("1403","期末余额")',
      old_value: 800000,
      new_value: 820000,
      change_pct: 2.5,
      is_highlight: false
    }],
    summary: {
      total_changes: 1,
      new_cells: 0,
      modified_cells: 1,
      highlight_count: 0
    }
  }
}`,...(D=(C=h.parameters)==null?void 0:C.docs)==null?void 0:D.source}}};const ne=["Default","NoHighlights"];export{d as Default,h as NoHighlights,ne as __namedExportsOrder,ae as default};
