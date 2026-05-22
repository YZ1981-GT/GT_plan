import{d as $}from"./index-BITwLRGo.js";/* empty css             *//* empty css                  */import{k as N,v as x,z as u,A as z,p as D,q as d,l as g,B as i,c as f,u as m,C as l}from"./vue.esm-bundler-RyamH92g.js";import{u as V}from"./usePermission-H0jjNiOp.js";import{_ as q}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";import"./auth-CjxQtL2d.js";import"./pinia-C5bunAeq.js";import"./iframe-DRCZA9bM.js";const E={key:0,class:"gt-batch-bar"},j={class:"gt-batch-bar-count"},H={class:"gt-batch-bar-actions"},S=N({__name:"BatchActionBar",props:{selectedCount:{},selectedIds:{}},emits:["batch-action"],setup(t){const{can:s}=V(),A=f(()=>s("adjustment:review")),h=f(()=>s("adjustment:review"));return(o,e)=>{const c=$;return t.selectedCount>0?(m(),x("div",E,[u("span",j,"已选 "+z(t.selectedCount)+" 个底稿",1),u("div",H,[D(c,{size:"small",type:"primary",onClick:e[0]||(e[0]=p=>o.$emit("batch-action",{action:"submit_review",ids:t.selectedIds}))},{default:d(()=>[...e[3]||(e[3]=[l(" 📤 批量提交复核 ",-1)])]),_:1}),A.value?(m(),g(c,{key:0,size:"small",type:"warning",onClick:e[1]||(e[1]=p=>o.$emit("batch-action",{action:"return_to_draft",ids:t.selectedIds}))},{default:d(()=>[...e[4]||(e[4]=[l(" ↩️ 批量退回 ",-1)])]),_:1})):i("",!0),h.value?(m(),g(c,{key:1,size:"small",type:"success",onClick:e[2]||(e[2]=p=>o.$emit("batch-action",{action:"mark_complete",ids:t.selectedIds}))},{default:d(()=>[...e[5]||(e[5]=[l(" ✅ 批量标记完成 ",-1)])]),_:1})):i("",!0)])])):i("",!0)}}}),M=q(S,[["__scopeId","data-v-c853ff4d"]]);S.__docgenInfo={exportName:"default",displayName:"BatchActionBar",description:"",tags:{},props:[{name:"selectedCount",required:!0,type:{name:"number"}},{name:"selectedIds",required:!0,type:{name:"Array",elements:[{name:"string"}]}}],events:[{name:"batch-action",type:{names:["{ action: string; ids: string[] }"]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/workpaper/BatchActionBar.vue"]};const U={title:"Common/BatchActionBar",component:M,tags:["autodocs"]},a={args:{selectedCount:3,selectedIds:["wp-001","wp-002","wp-003"]}},n={args:{selectedCount:12,selectedIds:Array.from({length:12},(t,s)=>`wp-${String(s+1).padStart(3,"0")}`)}},r={args:{selectedCount:0,selectedIds:[]}};var C,y,B;a.parameters={...a.parameters,docs:{...(C=a.parameters)==null?void 0:C.docs,source:{originalSource:`{
  args: {
    selectedCount: 3,
    selectedIds: ['wp-001', 'wp-002', 'wp-003']
  }
}`,...(B=(y=a.parameters)==null?void 0:y.docs)==null?void 0:B.source}}};var b,v,w;n.parameters={...n.parameters,docs:{...(b=n.parameters)==null?void 0:b.docs,source:{originalSource:`{
  args: {
    selectedCount: 12,
    selectedIds: Array.from({
      length: 12
    }, (_, i) => \`wp-\${String(i + 1).padStart(3, '0')}\`)
  }
}`,...(w=(v=n.parameters)==null?void 0:v.docs)==null?void 0:w.source}}};var I,k,_;r.parameters={...r.parameters,docs:{...(I=r.parameters)==null?void 0:I.docs,source:{originalSource:`{
  args: {
    selectedCount: 0,
    selectedIds: []
  }
}`,...(_=(k=r.parameters)==null?void 0:k.docs)==null?void 0:_.source}}};const W=["Default","ManySelected","Hidden"];export{a as Default,r as Hidden,n as ManySelected,W as __namedExportsOrder,U as default};
