import{y as S}from"./index-BITwLRGo.js";/* empty css             *//* empty css                  */import{k as V,v as n,F as v,I as p,z as i,G as l,A as c,B as d,C as m,p as I,q as f,u as a}from"./vue.esm-bundler-RyamH92g.js";import{_ as O}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const T={key:0,class:"gt-breadcrumb"},U=["onClick"],q={key:1,class:"gt-breadcrumb-sep"},z={class:"gt-breadcrumb-popover"},G=["onClick"],P={class:"gt-breadcrumb-item gt-breadcrumb-item--current"},L=V({__name:"DrilldownBreadcrumb",props:{stack:{}},emits:["jump"],setup(e){const A={"/trial-balance":"试算表","/drilldown":"穿透查询","/ledger":"明细账","/aux-summary":"辅助余额","/workpapers":"底稿列表","/adjustments":"调整分录","/reports":"报表","/disclosure-notes":"附注","/materiality":"重要性","/misstatements":"错报"};function u(o){if(o.label)return o.label;const t=o.source_view||"";for(const[r,s]of Object.entries(A))if(t.includes(r))return s;const b=t.split("/").filter(Boolean);return b[b.length-1]||"未知"}return(o,t)=>{const b=S;return e.stack.length>0?(a(),n("div",T,[e.stack.length<=5?(a(!0),n(v,{key:0},p(e.stack,(r,s)=>(a(),n("span",{key:s,class:l(["gt-breadcrumb-item",{"gt-breadcrumb-item--current":s===e.stack.length-1}]),onClick:F=>s<e.stack.length-1&&o.$emit("jump",s)},[r.direction?(a(),n("span",{key:0,class:l(["gt-breadcrumb-direction",`gt-breadcrumb-direction--${r.direction}`])},c(r.direction==="down"?"↓":"↑"),3)):d("",!0),m(" "+c(u(r))+" ",1),s<e.stack.length-1?(a(),n("span",q,">")):d("",!0)],10,U))),128)):(a(),n(v,{key:1},[i("span",{class:"gt-breadcrumb-item",onClick:t[0]||(t[0]=r=>o.$emit("jump",0))},[e.stack[0].direction?(a(),n("span",{key:0,class:l(["gt-breadcrumb-direction",`gt-breadcrumb-direction--${e.stack[0].direction}`])},c(e.stack[0].direction==="down"?"↓":"↑"),3)):d("",!0),m(" "+c(u(e.stack[0]))+" ",1),t[2]||(t[2]=i("span",{class:"gt-breadcrumb-sep"},">",-1))]),I(b,{trigger:"hover",width:200,placement:"bottom"},{reference:f(()=>[...t[3]||(t[3]=[i("span",{class:"gt-breadcrumb-item gt-breadcrumb-ellipsis"},"...",-1)])]),default:f(()=>[i("div",z,[(a(!0),n(v,null,p(e.stack.slice(1,e.stack.length-2),(r,s)=>(a(),n("div",{key:s+1,class:"gt-breadcrumb-popover-item",onClick:F=>o.$emit("jump",s+1)},[r.direction?(a(),n("span",{key:0,class:l(["gt-breadcrumb-direction",`gt-breadcrumb-direction--${r.direction}`])},c(r.direction==="down"?"↓":"↑"),3)):d("",!0),m(" "+c(u(r)),1)],8,G))),128))])]),_:1}),t[5]||(t[5]=i("span",{class:"gt-breadcrumb-sep"},">",-1)),i("span",{class:"gt-breadcrumb-item",onClick:t[1]||(t[1]=r=>o.$emit("jump",e.stack.length-2))},[e.stack[e.stack.length-2].direction?(a(),n("span",{key:0,class:l(["gt-breadcrumb-direction",`gt-breadcrumb-direction--${e.stack[e.stack.length-2].direction}`])},c(e.stack[e.stack.length-2].direction==="down"?"↓":"↑"),3)):d("",!0),m(" "+c(u(e.stack[e.stack.length-2]))+" ",1),t[4]||(t[4]=i("span",{class:"gt-breadcrumb-sep"},">",-1))]),i("span",P,[e.stack[e.stack.length-1].direction?(a(),n("span",{key:0,class:l(["gt-breadcrumb-direction",`gt-breadcrumb-direction--${e.stack[e.stack.length-1].direction}`])},c(e.stack[e.stack.length-1].direction==="down"?"↓":"↑"),3)):d("",!0),m(" "+c(u(e.stack[e.stack.length-1])),1)])],64))])):d("",!0)}}}),x=O(L,[["__scopeId","data-v-ac717ca9"]]);L.__docgenInfo={exportName:"default",displayName:"DrilldownBreadcrumb",description:"",tags:{},props:[{name:"stack",required:!0,type:{name:"Array",elements:[{name:"NavigationEntry"}]}}],events:[{name:"jump",type:{names:["number"]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/DrilldownBreadcrumb.vue"]};const W={title:"Common/DrilldownBreadcrumb",component:x,tags:["autodocs"]},g={args:{stack:[{source_view:"/trial-balance",direction:"down"},{source_view:"/drilldown",direction:"down"},{source_view:"/ledger",label:"明细账 1001"}]}},k={args:{stack:[{source_view:"/disclosure-notes",label:"附注",direction:"up"},{source_view:"/reports",label:"资产负债表",direction:"up"},{source_view:"/trial-balance",label:"试算表"}]}},w={args:{stack:[{source_view:"/trial-balance",direction:"down"},{source_view:"/drilldown",direction:"down"},{source_view:"/ledger",direction:"down"},{source_view:"/aux-summary",direction:"down"},{source_view:"/workpapers",direction:"down"},{source_view:"/adjustments",label:"调整分录"}]}};var y,h,C;g.parameters={...g.parameters,docs:{...(y=g.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    stack: [{
      source_view: '/trial-balance',
      direction: 'down' as const
    }, {
      source_view: '/drilldown',
      direction: 'down' as const
    }, {
      source_view: '/ledger',
      label: '明细账 1001'
    }]
  }
}`,...(C=(h=g.parameters)==null?void 0:h.docs)==null?void 0:C.source}}};var D,$,B;k.parameters={...k.parameters,docs:{...(D=k.parameters)==null?void 0:D.docs,source:{originalSource:`{
  args: {
    stack: [{
      source_view: '/disclosure-notes',
      label: '附注',
      direction: 'up' as const
    }, {
      source_view: '/reports',
      label: '资产负债表',
      direction: 'up' as const
    }, {
      source_view: '/trial-balance',
      label: '试算表'
    }]
  }
}`,...(B=($=k.parameters)==null?void 0:$.docs)==null?void 0:B.source}}};var j,N,E;w.parameters={...w.parameters,docs:{...(j=w.parameters)==null?void 0:j.docs,source:{originalSource:`{
  args: {
    stack: [{
      source_view: '/trial-balance',
      direction: 'down' as const
    }, {
      source_view: '/drilldown',
      direction: 'down' as const
    }, {
      source_view: '/ledger',
      direction: 'down' as const
    }, {
      source_view: '/aux-summary',
      direction: 'down' as const
    }, {
      source_view: '/workpapers',
      direction: 'down' as const
    }, {
      source_view: '/adjustments',
      label: '调整分录'
    }]
  }
}`,...(E=(N=w.parameters)==null?void 0:N.docs)==null?void 0:E.source}}};const X=["Default","UpDrillDirection","CollapsedLong"];export{w as CollapsedLong,g as Default,k as UpDrillDirection,X as __namedExportsOrder,W as default};
