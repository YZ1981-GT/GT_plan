import{v as B,d as D}from"./index-BITwLRGo.js";/* empty css             *//* empty css                   *//* empty css                  */import{k as R,K as S,v as r,z as e,p as q,q as L,F as y,I as A,C as c,A as i,B as E,u as g,y as u}from"./vue.esm-bundler-RyamH92g.js";import{_ as F}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const I={class:"gt-vr-heatmap"},M={class:"gt-heatmap-header"},z={class:"gt-heatmap-grid"},G={class:"gt-heatmap-cell gt-heatmap-row-header"},K=["onClick"],T=["onClick"],J=["onClick"],O={key:0,class:"gt-heatmap-total"},j={class:"sev-blocking"},P={class:"sev-warning"},Q={class:"sev-info"},H=R({__name:"VRHeatmap",props:{matrix:{},total:{},loading:{type:Boolean}},emits:["cell-click","refresh"],setup(t){function f(o,n){if(n===0)return"#fff";const s={blocking:["#ffcdd2","#ef5350","#c62828"],warning:["#fff3e0","#ff9800","#e65100"],info:["#f5f5f5","#bdbdbd","#616161"]},l=s[o]||s.info;return n<=2?l[0]:n<=5?l[1]:l[2]}return(o,n)=>{const s=D,l=B;return S((g(),r("div",I,[e("div",M,[n[2]||(n[2]=e("h3",null,"风险热力图",-1)),q(s,{size:"small",onClick:n[0]||(n[0]=a=>o.$emit("refresh"))},{default:L(()=>[...n[1]||(n[1]=[c("刷新",-1)])]),_:1})]),e("div",z,[n[3]||(n[3]=e("div",{class:"gt-heatmap-cell gt-heatmap-corner"},null,-1)),n[4]||(n[4]=e("div",{class:"gt-heatmap-cell gt-heatmap-col-header sev-blocking"},"阻断",-1)),n[5]||(n[5]=e("div",{class:"gt-heatmap-cell gt-heatmap-col-header sev-warning"},"警告",-1)),n[6]||(n[6]=e("div",{class:"gt-heatmap-cell gt-heatmap-col-header sev-info"},"提示",-1)),(g(!0),r(y,null,A(t.matrix,a=>(g(),r(y,{key:a.cycle},[e("div",G,i(a.cycle),1),e("div",{class:"gt-heatmap-cell gt-heatmap-data",style:u({background:f("blocking",a.blocking)}),onClick:k=>o.$emit("cell-click",{cycle:a.cycle,severity:"blocking"})},i(a.blocking||""),13,K),e("div",{class:"gt-heatmap-cell gt-heatmap-data",style:u({background:f("warning",a.warning)}),onClick:k=>o.$emit("cell-click",{cycle:a.cycle,severity:"warning"})},i(a.warning||""),13,T),e("div",{class:"gt-heatmap-cell gt-heatmap-data",style:u({background:f("info",a.info)}),onClick:k=>o.$emit("cell-click",{cycle:a.cycle,severity:"info"})},i(a.info||""),13,J)],64))),128))]),t.total?(g(),r("div",O,[n[7]||(n[7]=c(" 合计：",-1)),e("span",j,i(t.total.blocking)+" 阻断",1),n[8]||(n[8]=c(" / ",-1)),e("span",P,i(t.total.warning)+" 警告",1),n[9]||(n[9]=c(" / ",-1)),e("span",Q,i(t.total.info)+" 提示",1)])):E("",!0)])),[[l,t.loading]])}}}),U=F(H,[["__scopeId","data-v-4a451b98"]]);H.__docgenInfo={exportName:"default",displayName:"VRHeatmap",description:"",tags:{},props:[{name:"matrix",required:!0,type:{name:"Array",elements:[{name:"HeatmapRow"}]}},{name:"total",required:!0,type:{name:"union",elements:[{name:"{ blocking: number; warning: number; info: number }"},{name:"null"}]}},{name:"loading",required:!1,type:{name:"boolean"}}],events:[{name:"refresh"},{name:"cell-click",type:{names:["{ cycle: string; severity: string }"]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/qc/VRHeatmap.vue"]};const tn={title:"Common/VRHeatmap",component:U,tags:["autodocs"]},N=[{cycle:"D",blocking:2,warning:5,info:1},{cycle:"E",blocking:0,warning:3,info:2},{cycle:"F",blocking:1,warning:4,info:0},{cycle:"G",blocking:0,warning:2,info:3},{cycle:"H",blocking:3,warning:6,info:1},{cycle:"I",blocking:0,warning:1,info:1},{cycle:"J",blocking:0,warning:2,info:0},{cycle:"K",blocking:1,warning:3,info:2},{cycle:"L",blocking:0,warning:1,info:1},{cycle:"M",blocking:0,warning:0,info:1},{cycle:"N",blocking:1,warning:2,info:0}],m={args:{matrix:N,total:{blocking:8,warning:29,info:12},loading:!1}},d={args:{matrix:[],total:null,loading:!0}},p={args:{matrix:N.map(t=>({...t,blocking:0,warning:0,info:0})),total:{blocking:0,warning:0,info:0},loading:!1}};var b,v,h;m.parameters={...m.parameters,docs:{...(b=m.parameters)==null?void 0:b.docs,source:{originalSource:`{
  args: {
    matrix: sampleMatrix,
    total: {
      blocking: 8,
      warning: 29,
      info: 12
    },
    loading: false
  }
}`,...(h=(v=m.parameters)==null?void 0:v.docs)==null?void 0:h.source}}};var w,x,C;d.parameters={...d.parameters,docs:{...(w=d.parameters)==null?void 0:w.docs,source:{originalSource:`{
  args: {
    matrix: [],
    total: null,
    loading: true
  }
}`,...(C=(x=d.parameters)==null?void 0:x.docs)==null?void 0:C.source}}};var _,V,$;p.parameters={...p.parameters,docs:{...(_=p.parameters)==null?void 0:_.docs,source:{originalSource:`{
  args: {
    matrix: sampleMatrix.map(r => ({
      ...r,
      blocking: 0,
      warning: 0,
      info: 0
    })),
    total: {
      blocking: 0,
      warning: 0,
      info: 0
    },
    loading: false
  }
}`,...($=(V=p.parameters)==null?void 0:V.docs)==null?void 0:$.source}}};const on=["Default","Loading","AllClear"];export{p as AllClear,m as Default,d as Loading,on as __namedExportsOrder,tn as default};
