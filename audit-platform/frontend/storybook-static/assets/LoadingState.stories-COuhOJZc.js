import{G as D,r as N,g as I,m as z,z as A}from"./index-BITwLRGo.js";/* empty css             *//* empty css                 *//* empty css                 */import{k as G,v as l,l as d,p as u,q as M,A as F,B as O,D as $,u as a,E as j}from"./vue.esm-bundler-RyamH92g.js";import{_ as H}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const J={class:"loading-state"},K={key:1,class:"spinner-wrap"},P={key:0,class:"loading-text"},w=G({__name:"LoadingState",props:{loading:{type:Boolean,default:!1},skeleton:{type:Boolean,default:!0},rows:{default:3},text:{default:""},empty:{type:Boolean,default:!1},emptyText:{default:"暂无数据"},error:{type:Boolean,default:!1},errorText:{default:"加载失败"}},setup(e){return(q,Q)=>{const b=D,B=N,h=I,C=z;return a(),l("div",J,[e.loading&&e.skeleton?(a(),d(b,{key:0,rows:e.rows,animated:""},null,8,["rows"])):e.loading?(a(),l("div",K,[u(B,{class:"is-loading",size:32},{default:M(()=>[u(j(A))]),_:1}),e.text?(a(),l("span",P,F(e.text),1)):O("",!0)])):e.empty?(a(),d(h,{key:2,description:e.emptyText},null,8,["description"])):e.error?(a(),d(C,{key:3,type:"error",title:e.errorText,"show-icon":"",closable:!1},null,8,["title"])):$(q.$slots,"default",{key:4},void 0,!0)])}}}),V=H(w,[["__scopeId","data-v-909a2062"]]);w.__docgenInfo={exportName:"default",displayName:"LoadingState",description:"",tags:{},props:[{name:"loading",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"skeleton",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"true"}},{name:"rows",required:!1,type:{name:"number"},defaultValue:{func:!1,value:"3"}},{name:"text",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"''"}},{name:"empty",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"emptyText",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"'暂无数据'"}},{name:"error",required:!1,type:{name:"boolean"},defaultValue:{func:!1,value:"false"}},{name:"errorText",required:!1,type:{name:"string"},defaultValue:{func:!1,value:"'加载失败'"}}],slots:[{name:"default"}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/LoadingState.vue"]};const ae={title:"Common/LoadingState",component:V,tags:["autodocs"]},t={args:{loading:!0,skeleton:!0,rows:3}},r={args:{loading:!0,skeleton:!1,text:"正在加载数据..."}},o={args:{loading:!1,empty:!0,emptyText:"暂无底稿数据"}},n={args:{loading:!1,error:!0,errorText:"网络连接失败，请稍后重试"}},s={args:{loading:!1,empty:!1,error:!1},render:e=>({components:{LoadingState:V},setup:()=>({args:e}),template:'<LoadingState v-bind="args"><p>数据加载完成，这里是实际内容。</p></LoadingState>'})};var m,c,i;t.parameters={...t.parameters,docs:{...(m=t.parameters)==null?void 0:m.docs,source:{originalSource:`{
  args: {
    loading: true,
    skeleton: true,
    rows: 3
  }
}`,...(i=(c=t.parameters)==null?void 0:c.docs)==null?void 0:i.source}}};var p,f,g;r.parameters={...r.parameters,docs:{...(p=r.parameters)==null?void 0:p.docs,source:{originalSource:`{
  args: {
    loading: true,
    skeleton: false,
    text: '正在加载数据...'
  }
}`,...(g=(f=r.parameters)==null?void 0:f.docs)==null?void 0:g.source}}};var y,S,x;o.parameters={...o.parameters,docs:{...(y=o.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    loading: false,
    empty: true,
    emptyText: '暂无底稿数据'
  }
}`,...(x=(S=o.parameters)==null?void 0:S.docs)==null?void 0:x.source}}};var k,_,v;n.parameters={...n.parameters,docs:{...(k=n.parameters)==null?void 0:k.docs,source:{originalSource:`{
  args: {
    loading: false,
    error: true,
    errorText: '网络连接失败，请稍后重试'
  }
}`,...(v=(_=n.parameters)==null?void 0:_.docs)==null?void 0:v.source}}};var E,L,T;s.parameters={...s.parameters,docs:{...(E=s.parameters)==null?void 0:E.docs,source:{originalSource:`{
  args: {
    loading: false,
    empty: false,
    error: false
  },
  render: args => ({
    components: {
      LoadingState
    },
    setup: () => ({
      args
    }),
    template: '<LoadingState v-bind="args"><p>数据加载完成，这里是实际内容。</p></LoadingState>'
  })
}`,...(T=(L=s.parameters)==null?void 0:L.docs)==null?void 0:T.source}}};const te=["Default","SpinnerMode","EmptyState","ErrorState","ContentLoaded"];export{s as ContentLoaded,t as Default,o as EmptyState,n as ErrorState,r as SpinnerMode,te as __namedExportsOrder,ae as default};
