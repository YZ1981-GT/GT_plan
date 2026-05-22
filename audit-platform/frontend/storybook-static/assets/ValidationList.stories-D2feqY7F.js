import{e as B,f as V,c as S,d as N,g as L}from"./index-BITwLRGo.js";/* empty css             *//* empty css                 *//* empty css                     *//* empty css                  */import"./el-tooltip-l0sNRNKZ.js";/* empty css                    *//* empty css                        *//* empty css                  *//* empty css               */import{k as M,v as z,p as e,q as n,l as c,B as d,u as m,C as g,A}from"./vue.esm-bundler-RyamH92g.js";import"./_commonjsHelpers-CqkleIqs.js";const F={class:"validation-list"},b=M({__name:"ValidationList",props:{findings:{}},emits:["fix"],setup(l){function E(t){return t==="high"?"danger":t==="medium"?"warning":t==="low"?"info":void 0}return(t,p)=>{const C=S,s=V,D=N,T=B,Y=L;return m(),z("div",F,[e(T,{data:l.findings,stripe:"",size:"small","max-height":"500"},{default:n(()=>[e(s,{prop:"severity",label:"严重度",width:"80"},{default:n(({row:i})=>[e(C,{type:E(i.severity),size:"small"},{default:n(()=>[g(A(i.severity),1)]),_:2},1032,["type"])]),_:1}),e(s,{prop:"check_type",label:"类型",width:"160"}),e(s,{prop:"message",label:"描述","min-width":"300","show-overflow-tooltip":""}),e(s,{prop:"fix_suggestion",label:"建议",width:"200","show-overflow-tooltip":""}),e(s,{label:"操作",width:"80"},{default:n(({row:i})=>[i.fix_suggestion?(m(),c(D,{key:0,size:"small",text:"",type:"primary",onClick:q=>t.$emit("fix",[i.id])},{default:n(()=>[...p[0]||(p[0]=[g("修复",-1)])]),_:1},8,["onClick"])):d("",!0)]),_:1})]),_:1},8,["data"]),l.findings.length?d("",!0):(m(),c(Y,{key:0,description:"暂无校验结果"}))])}}});b.__docgenInfo={exportName:"default",displayName:"ValidationList",description:"",tags:{},props:[{name:"findings",required:!0,type:{name:"Array",elements:[{name:"any"}]}}],events:[{name:"fix",type:{names:["Array"],elements:[{name:"string"}]}}],sourceFiles:["D:/GT_plan/audit-platform/frontend/src/components/common/ValidationList.vue"]};const X={title:"Common/ValidationList",component:b,tags:["autodocs"]},O=[{id:"1",severity:"high",check_type:"勾稽校验",message:"资产负债表借贷不平衡，差异 ¥12,500",fix_suggestion:"检查调整分录"},{id:"2",severity:"medium",check_type:"完整性",message:"科目 6601 缺少辅助账明细",fix_suggestion:"补充辅助账数据"},{id:"3",severity:"low",check_type:"格式校验",message:"日期格式不统一（混用 YYYY-MM-DD 和 YYYY/MM/DD）",fix_suggestion:null}],o={args:{findings:O}},a={args:{findings:[{id:"1",severity:"high",check_type:"三角勾稽",message:"期末余额 ≠ 期初 + 本期借方 - 本期贷方",fix_suggestion:"重新计算余额"},{id:"2",severity:"high",check_type:"跨表校验",message:"TB 合计与报表总资产不一致",fix_suggestion:"核对报表映射"}]}},r={args:{findings:[]}};var u,_,f;o.parameters={...o.parameters,docs:{...(u=o.parameters)==null?void 0:u.docs,source:{originalSource:`{
  args: {
    findings: sampleFindings
  }
}`,...(f=(_=o.parameters)==null?void 0:_.docs)==null?void 0:f.source}}};var y,h,v;a.parameters={...a.parameters,docs:{...(y=a.parameters)==null?void 0:y.docs,source:{originalSource:`{
  args: {
    findings: [{
      id: '1',
      severity: 'high',
      check_type: '三角勾稽',
      message: '期末余额 ≠ 期初 + 本期借方 - 本期贷方',
      fix_suggestion: '重新计算余额'
    }, {
      id: '2',
      severity: 'high',
      check_type: '跨表校验',
      message: 'TB 合计与报表总资产不一致',
      fix_suggestion: '核对报表映射'
    }]
  }
}`,...(v=(h=a.parameters)==null?void 0:h.docs)==null?void 0:v.source}}};var x,k,w;r.parameters={...r.parameters,docs:{...(x=r.parameters)==null?void 0:x.docs,source:{originalSource:`{
  args: {
    findings: []
  }
}`,...(w=(k=r.parameters)==null?void 0:k.docs)==null?void 0:w.source}}};const Z=["Default","HighSeverityOnly","Empty"];export{o as Default,r as Empty,a as HighSeverityOnly,Z as __namedExportsOrder,X as default};
