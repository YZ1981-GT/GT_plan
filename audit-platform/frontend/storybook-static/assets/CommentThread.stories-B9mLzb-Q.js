import{k as j,d as J,c as K,g as P}from"./index-BITwLRGo.js";/* empty css             *//* empty css                 *//* empty css                  *//* empty css                 *//* empty css               */import{k as Q,v as r,F as V,I as E,l as h,z as a,p as c,q as m,r as k,u as t,G as W,A as v,C as i,B as y}from"./vue.esm-bundler-RyamH92g.js";import{_ as X}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./_commonjsHelpers-CqkleIqs.js";const Y={class:"gt-comment-thread"},Z={key:0,class:"gt-ct-list"},ee={class:"gt-ct-header"},te={class:"gt-ct-author"},se={class:"gt-ct-time"},ne={class:"gt-ct-content"},re={key:0,class:"gt-ct-replies"},ae={class:"gt-ct-reply-author"},oe={class:"gt-ct-reply-time"},le={class:"gt-ct-reply-content"},ce={key:1,class:"gt-ct-reply-input"},me={class:"gt-ct-reply-actions"},ie={key:2,class:"gt-ct-actions"},de={class:"gt-ct-new"},q=Q({__name:"CommentThread",props:{comments:{},currentUser:{}},emits:["add","reply","resolve","delete"],setup(T,{emit:F}){const A=F,d=k(""),g=k(-1),u=k("");function R(){d.value.trim()&&(A("add",d.value.trim()),d.value="")}function G(o){u.value.trim()&&(A("reply",o,u.value.trim()),u.value="",g.value=-1)}function z(o){if(!o)return"";try{const e=new Date(o);return`${e.getMonth()+1}/${e.getDate()} ${e.getHours()}:${String(e.getMinutes()).padStart(2,"0")}`}catch{return o}}return(o,e)=>{const H=K,$=j,p=J,L=P;return t(),r("div",Y,[T.comments.length?(t(),r("div",Z,[(t(!0),r(V,null,E(T.comments,(s,l)=>{var U;return t(),r("div",{key:s.id||l,class:W(["gt-ct-item",{"gt-ct-item--resolved":s.resolved}])},[a("div",ee,[a("span",te,v(s.author||"匿名"),1),a("span",se,v(z(s.createdAt)),1),s.resolved?(t(),h(H,{key:0,size:"small",type:"success",effect:"plain"},{default:m(()=>[...e[3]||(e[3]=[i("已解决",-1)])]),_:1})):y("",!0)]),a("div",ne,v(s.content),1),(U=s.replies)!=null&&U.length?(t(),r("div",re,[(t(!0),r(V,null,E(s.replies,(n,O)=>(t(),r("div",{key:O,class:"gt-ct-reply"},[a("span",ae,v(n.author||"匿名"),1),a("span",oe,v(z(n.createdAt)),1),a("div",le,v(n.content),1)]))),128))])):y("",!0),g.value===l?(t(),r("div",ce,[c($,{modelValue:u.value,"onUpdate:modelValue":e[0]||(e[0]=n=>u.value=n),type:"textarea",rows:2,placeholder:"输入回复...",size:"small"},null,8,["modelValue"]),a("div",me,[c(p,{size:"small",onClick:e[1]||(e[1]=n=>g.value=-1)},{default:m(()=>[...e[4]||(e[4]=[i("取消",-1)])]),_:1}),c(p,{size:"small",type:"primary",onClick:n=>G(l)},{default:m(()=>[...e[5]||(e[5]=[i("回复",-1)])]),_:1},8,["onClick"])])])):y("",!0),g.value!==l?(t(),r("div",ie,[c(p,{text:"",size:"small",onClick:n=>{g.value=l,u.value=""}},{default:m(()=>[...e[6]||(e[6]=[i("💬 回复",-1)])]),_:1},8,["onClick"]),s.resolved?y("",!0):(t(),h(p,{key:0,text:"",size:"small",onClick:n=>o.$emit("resolve",l)},{default:m(()=>[...e[7]||(e[7]=[i("✅ 标记解决",-1)])]),_:1},8,["onClick"])),c(p,{text:"",size:"small",type:"danger",onClick:n=>o.$emit("delete",l)},{default:m(()=>[...e[8]||(e[8]=[i("🗑️ 删除",-1)])]),_:1},8,["onClick"])])):y("",!0)],2)}),128))])):(t(),h(L,{key:1,description:"暂无批注","image-size":40})),a("div",de,[c($,{modelValue:d.value,"onUpdate:modelValue":e[2]||(e[2]=s=>d.value=s),type:"textarea",rows:2,placeholder:"添加批注...",size:"small"},null,8,["modelValue"]),c(p,{size:"small",type:"primary",disabled:!d.value.trim(),onClick:R,style:{"margin-top":"6px"}},{default:m(()=>[...e[9]||(e[9]=[i("添加批注",-1)])]),_:1},8,["disabled"])])])}}}),ue=X(q,[["__scopeId","data-v-27d8ec4e"]]);q.__docgenInfo={exportName:"default",displayName:"CommentThread",description:"",tags:{},props:[{name:"comments",required:!0,type:{name:"Array",elements:[{name:"CommentItem"}]}},{name:"currentUser",required:!1,type:{name:"string"}}],events:[{name:"resolve",type:{names:["number"]}},{name:"delete",type:{names:["number"]}},{name:"add",type:{names:["string"]}},{name:"reply",type:{names:["number"]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/CommentThread.vue"]};const Ae={title:"Common/CommentThread",component:ue,tags:["autodocs"]},pe=[{id:"1",author:"张经理",content:"请核实该科目余额与银行对账单是否一致",createdAt:"2026-05-20T10:30:00",resolved:!1,replies:[{author:"李助理",content:"已核对，差异为 ¥500，属于在途款项",createdAt:"2026-05-20T11:00:00"}]},{id:"2",author:"王合伙人",content:"该调整分录需要补充审计依据",createdAt:"2026-05-19T14:20:00",resolved:!0}],_={args:{comments:pe,currentUser:"李助理"}},f={args:{comments:[],currentUser:"张经理"}},C={args:{comments:[{id:"1",author:"质控",content:"请确认重要性水平计算依据",createdAt:"2026-05-18T09:00:00",resolved:!1,replies:[{author:"项目经理",content:"依据净利润 5%",createdAt:"2026-05-18T09:30:00"},{author:"质控",content:"建议同时考虑收入基准",createdAt:"2026-05-18T10:00:00"},{author:"项目经理",content:"已补充双基准对比",createdAt:"2026-05-18T11:00:00"}]}],currentUser:"质控"}};var b,w,N;_.parameters={..._.parameters,docs:{...(b=_.parameters)==null?void 0:b.docs,source:{originalSource:`{
  args: {
    comments: sampleComments,
    currentUser: '李助理'
  }
}`,...(N=(w=_.parameters)==null?void 0:w.docs)==null?void 0:N.source}}};var x,B,D;f.parameters={...f.parameters,docs:{...(x=f.parameters)==null?void 0:x.docs,source:{originalSource:`{
  args: {
    comments: [],
    currentUser: '张经理'
  }
}`,...(D=(B=f.parameters)==null?void 0:B.docs)==null?void 0:D.source}}};var S,I,M;C.parameters={...C.parameters,docs:{...(S=C.parameters)==null?void 0:S.docs,source:{originalSource:`{
  args: {
    comments: [{
      id: '1',
      author: '质控',
      content: '请确认重要性水平计算依据',
      createdAt: '2026-05-18T09:00:00',
      resolved: false,
      replies: [{
        author: '项目经理',
        content: '依据净利润 5%',
        createdAt: '2026-05-18T09:30:00'
      }, {
        author: '质控',
        content: '建议同时考虑收入基准',
        createdAt: '2026-05-18T10:00:00'
      }, {
        author: '项目经理',
        content: '已补充双基准对比',
        createdAt: '2026-05-18T11:00:00'
      }]
    }],
    currentUser: '质控'
  }
}`,...(M=(I=C.parameters)==null?void 0:I.docs)==null?void 0:M.source}}};const ze=["Default","Empty","ManyReplies"];export{_ as Default,f as Empty,C as ManyReplies,ze as __namedExportsOrder,Ae as default};
