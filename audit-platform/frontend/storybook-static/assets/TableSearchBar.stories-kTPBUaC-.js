import{k as G,x as K,d as F,p as J}from"./index-BITwLRGo.js";/* empty css             *//* empty css                    *//* empty css                        *//* empty css                  *//* empty css                 */import{k as O,w as j,l as k,q as n,T as H,n as L,u as i,v as h,z as o,p as r,J as b,x as w,A as S,B as c,C as d,r as $}from"./vue.esm-bundler-RyamH92g.js";import{_ as P}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const Q={key:0,class:"gt-search-bar"},X={class:"gt-search-bar-row"},Y={key:0,class:"gt-search-info"},Z={key:0,class:"gt-search-bar-row"},A=O({__name:"TableSearchBar",props:{isVisible:{type:Boolean},keyword:{},replaceText:{},matchInfo:{},hasMatches:{type:Boolean},caseSensitive:{type:Boolean},showReplace:{type:Boolean}},emits:["update:keyword","update:replaceText","update:caseSensitive","search","next","prev","close","replace-one","replace-all"],setup(t){const D=t,y=$(null),m=$(!1);return j(()=>D.isVisible,a=>{a&&L(()=>{var e;return(e=y.value)==null?void 0:e.focus()})}),(a,e)=>{const g=G,l=F,W=K,U=J;return i(),k(H,{name:"gt-slide-down"},{default:n(()=>[t.isVisible?(i(),h("div",Q,[o("div",X,[e[15]||(e[15]=o("div",{class:"gt-search-bar-icon"},"🔍",-1)),r(g,{ref_key:"inputRef",ref:y,"model-value":t.keyword,"onUpdate:modelValue":e[0]||(e[0]=s=>a.$emit("update:keyword",s)),size:"small",placeholder:"输入关键词搜索表格内容...",clearable:"",class:"gt-search-input",onKeyup:[e[1]||(e[1]=b(w(s=>a.$emit("next"),["exact"]),["enter"])),e[2]||(e[2]=b(w(s=>a.$emit("prev"),["shift"]),["enter"])),e[3]||(e[3]=b(s=>a.$emit("close"),["escape"]))]},null,8,["model-value"]),t.keyword?(i(),h("span",Y,S(t.matchInfo),1)):c("",!0),r(W,{size:"small",class:"gt-search-nav"},{default:n(()=>[r(l,{onClick:e[4]||(e[4]=s=>a.$emit("prev")),disabled:!t.hasMatches,title:"上一个 (Shift+Enter)"},{default:n(()=>[...e[12]||(e[12]=[o("span",{style:{"font-size":"var(--gt-font-size-xs)"}},"▲",-1)])]),_:1},8,["disabled"]),r(l,{onClick:e[5]||(e[5]=s=>a.$emit("next")),disabled:!t.hasMatches,title:"下一个 (Enter)"},{default:n(()=>[...e[13]||(e[13]=[o("span",{style:{"font-size":"var(--gt-font-size-xs)"}},"▼",-1)])]),_:1},8,["disabled"])]),_:1}),r(U,{"model-value":t.caseSensitive,"onUpdate:modelValue":e[6]||(e[6]=s=>{a.$emit("update:caseSensitive",!!s),a.$emit("search")}),size:"small",class:"gt-search-case"},{default:n(()=>[...e[14]||(e[14]=[d("Aa",-1)])]),_:1},8,["model-value"]),t.showReplace?(i(),k(l,{key:1,size:"small",class:"gt-search-replace-btn",onClick:e[7]||(e[7]=s=>m.value=!m.value)},{default:n(()=>[d(S(m.value?"收起":"替换"),1)]),_:1})):c("",!0),o("div",{class:"gt-search-close",onClick:e[8]||(e[8]=s=>a.$emit("close")),title:"关闭 (Esc)"},"✕")]),m.value&&t.showReplace?(i(),h("div",Z,[e[18]||(e[18]=o("div",{class:"gt-search-bar-icon",style:{opacity:"0"}},"🔍",-1)),r(g,{"model-value":t.replaceText,"onUpdate:modelValue":e[9]||(e[9]=s=>a.$emit("update:replaceText",s)),size:"small",placeholder:"替换为...",clearable:"",class:"gt-search-input"},null,8,["model-value"]),r(l,{size:"small",onClick:e[10]||(e[10]=s=>a.$emit("replace-one")),disabled:!t.hasMatches,class:"gt-search-action-btn"},{default:n(()=>[...e[16]||(e[16]=[d("替换",-1)])]),_:1},8,["disabled"]),r(l,{size:"small",onClick:e[11]||(e[11]=s=>a.$emit("replace-all")),disabled:!t.hasMatches,class:"gt-search-action-btn"},{default:n(()=>[...e[17]||(e[17]=[d("全部",-1)])]),_:1},8,["disabled"])])):c("",!0)])):c("",!0)]),_:1})}}}),_=P(A,[["__scopeId","data-v-8d345261"]]);A.__docgenInfo={exportName:"default",displayName:"TableSearchBar",description:"",tags:{},props:[{name:"isVisible",required:!0,type:{name:"boolean"}},{name:"keyword",required:!0,type:{name:"string"}},{name:"replaceText",required:!1,type:{name:"string"}},{name:"matchInfo",required:!0,type:{name:"string"}},{name:"hasMatches",required:!0,type:{name:"boolean"}},{name:"caseSensitive",required:!0,type:{name:"boolean"}},{name:"showReplace",required:!1,type:{name:"boolean"}}],events:[{name:"update:keyword",type:{names:["string"]}},{name:"next"},{name:"prev"},{name:"close"},{name:"update:caseSensitive",type:{names:["boolean"]}},{name:"search"},{name:"update:replaceText",type:{names:["string"]}},{name:"replace-one"},{name:"replace-all"}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/TableSearchBar.vue"]};const me={title:"Common/TableSearchBar",component:_,tags:["autodocs"]},u={args:{isVisible:!0,keyword:"",matchInfo:"0/0",hasMatches:!1,caseSensitive:!1}},p={args:{isVisible:!0,keyword:"银行",matchInfo:"1/3",hasMatches:!0,caseSensitive:!1}},f={args:{isVisible:!0,keyword:"应收",replaceText:"应付",matchInfo:"2/5",hasMatches:!0,caseSensitive:!1,showReplace:!0}},v={args:{isVisible:!0,keyword:"ABC",matchInfo:"0/0",hasMatches:!1,caseSensitive:!0}};var V,B,T;u.parameters={...u.parameters,docs:{...(V=u.parameters)==null?void 0:V.docs,source:{originalSource:`{
  args: {
    isVisible: true,
    keyword: '',
    matchInfo: '0/0',
    hasMatches: false,
    caseSensitive: false
  }
}`,...(T=(B=u.parameters)==null?void 0:B.docs)==null?void 0:T.source}}};var M,C,x;p.parameters={...p.parameters,docs:{...(M=p.parameters)==null?void 0:M.docs,source:{originalSource:`{
  args: {
    isVisible: true,
    keyword: '银行',
    matchInfo: '1/3',
    hasMatches: true,
    caseSensitive: false
  }
}`,...(x=(C=p.parameters)==null?void 0:C.docs)==null?void 0:x.source}}};var I,z,R;f.parameters={...f.parameters,docs:{...(I=f.parameters)==null?void 0:I.docs,source:{originalSource:`{
  args: {
    isVisible: true,
    keyword: '应收',
    replaceText: '应付',
    matchInfo: '2/5',
    hasMatches: true,
    caseSensitive: false,
    showReplace: true
  }
}`,...(R=(z=f.parameters)==null?void 0:z.docs)==null?void 0:R.source}}};var E,q,N;v.parameters={...v.parameters,docs:{...(E=v.parameters)==null?void 0:E.docs,source:{originalSource:`{
  args: {
    isVisible: true,
    keyword: 'ABC',
    matchInfo: '0/0',
    hasMatches: false,
    caseSensitive: true
  }
}`,...(N=(q=v.parameters)==null?void 0:q.docs)==null?void 0:N.source}}};const ce=["Default","WithMatches","WithReplace","CaseSensitive"];export{v as CaseSensitive,u as Default,p as WithMatches,f as WithReplace,ce as __namedExportsOrder,me as default};
