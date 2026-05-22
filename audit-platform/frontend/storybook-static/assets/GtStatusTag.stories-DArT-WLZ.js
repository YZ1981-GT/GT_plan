import{c as D}from"./index-BITwLRGo.js";/* empty css             *//* empty css               */import{k as G,l as N,q,c as l,u as C,C as V,A as h}from"./vue.esm-bundler-RyamH92g.js";import{u as j}from"./dict-f6tOPmPh.js";import"./_commonjsHelpers-CqkleIqs.js";import"./pinia-C5bunAeq.js";import"./apiProxy-DePeTMgn.js";import"./auth-CjxQtL2d.js";import"./iframe-DRCZA9bM.js";const K=G({__name:"GtStatusTag",props:{dictKey:{},value:{},size:{default:"small"}},setup(u){const e=u,t=j(),w=l(()=>e.value&&t.loaded?t.type(e.dictKey,e.value):"info"),T=l(()=>{if(!e.value)return"—";if(t.loaded){const a=t.label(e.dictKey,e.value);if(a&&a!==e.value)return a}return e.value});return(a,k)=>{const x=D;return C(),N(x,{type:w.value,size:u.size,effect:"light"},{default:q(()=>[V(h(T.value),1)]),_:1},8,["type","size"])}}});K.__docgenInfo={exportName:"default",displayName:"GtStatusTag",description:"",tags:{},props:[{name:"dictKey",description:"dictStore 字典键（如 'wp_status'、'adjustment_status'）",required:!0,type:{name:"string"}},{name:"value",description:"当前状态值",required:!0,type:{name:"union",elements:[{name:"string"},{name:"undefined"},{name:"null"}]}},{name:"size",description:"标签尺寸，默认 small",required:!1,type:{name:"union",elements:[{name:'"large"'},{name:'"default"'},{name:'"small"'}]},defaultValue:{func:!1,value:"'small'"}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/GtStatusTag.vue"]};const J={title:"Common/GtStatusTag",component:K,tags:["autodocs"],argTypes:{size:{control:"select",options:["large","default","small"]}}},s={args:{dictKey:"wp_status",value:"draft"}},r={args:{dictKey:"adjustment_status",value:"approved",size:"default"}},n={args:{dictKey:"wp_status",value:null}},o={args:{dictKey:"wp_status",value:"completed",size:"large"}};var c,i,p;s.parameters={...s.parameters,docs:{...(c=s.parameters)==null?void 0:c.docs,source:{originalSource:`{
  args: {
    dictKey: 'wp_status',
    value: 'draft'
  }
}`,...(p=(i=s.parameters)==null?void 0:i.docs)==null?void 0:p.source}}};var m,d,f;r.parameters={...r.parameters,docs:{...(m=r.parameters)==null?void 0:m.docs,source:{originalSource:`{
  args: {
    dictKey: 'adjustment_status',
    value: 'approved',
    size: 'default'
  }
}`,...(f=(d=r.parameters)==null?void 0:d.docs)==null?void 0:f.source}}};var g,v,_;n.parameters={...n.parameters,docs:{...(g=n.parameters)==null?void 0:g.docs,source:{originalSource:`{
  args: {
    dictKey: 'wp_status',
    value: null
  }
}`,...(_=(v=n.parameters)==null?void 0:v.docs)==null?void 0:_.source}}};var y,S,z;o.parameters={...o.parameters,docs:{...(y=o.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    dictKey: 'wp_status',
    value: 'completed',
    size: 'large'
  }
}`,...(z=(S=o.parameters)==null?void 0:S.docs)==null?void 0:z.source}}};const M=["Default","ReviewStatus","NullValue","LargeSize"];export{s as Default,o as LargeSize,n as NullValue,r as ReviewStatus,M as __namedExportsOrder,J as default};
