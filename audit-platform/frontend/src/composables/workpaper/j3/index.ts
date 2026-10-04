export * from './useJ3FormulaEngine'
export * from './useJ3OptionPricingEngine'
// ⚠️ useJ3FormData / useJ3Detail / useJ3Integration 已移除
//    （spec j2-j3-non-entry-hosts-and-orphan-cleanup，JN-3 整簇不可达）：
//    🔴 **两层判定**才能定性 —— 单看一层会把 useJ3FormData 判成「活着」：
//      · useJ3FormData（151 行）入边 3 = 本 barrel + useJ3Detail + useJ3Integration
//      · useJ3Detail 自身入边 1（**只**本 barrel）
//      · useJ3Integration 自身入边 **0**
//      · 本 barrel 入边 **0**（现算）
//    ⇒ 三者只经一个孤立 barrel 相连，整簇从任何真实宿主都到不了。
//    🔴 随簇消失的联动（现状：整簇不可达 ⇒ 这些联动本来就没跑过）：
//      `events/publish` 4 处（FormData 1 + Integration 3）· `cross-wp-references/batch` 1 处
//      （Integration）· `checklist-responses` PUT 1 处 · `render-config` GET 3 处。
//    🔴 useJ3FormData 的 item_id 形态是 `` `J3-${key}` `` —— **写**路径生产命中 0
//    （唯一写它的就是这个不可达模块）。但**读**路径有 2 处：`j3/core/J3TabIndex.vue`
//    的 `progressKeys: ['J3-detail', …]` / `['J3-check', …]` ⇒ 那两个键**永远读到空**，
//    J3 完成度恒少算两项。这是删除**暴露**出来的既有缺陷，不是删除**造成**的。
export * from './useJ3CrossSheet'
export * from './useJ3Check'
// ⚠️ useJ3DualMode 已移除（spec j2-j3-non-entry-hosts-and-orphan-cleanup，OD-4）：
//    **二阶孤儿** —— 生产边只有本 barrel（入度 1、零测试边），本 barrel 入边现算 **0**。
//    🔴 它还直调 `GET /api/workpapers/onlyoffice/health` —— 命中
//    `legacy_deletion_paradigm` step 6 明禁项（OO 探测只能经 sync bridge 的 materialize
//    协议）。现在无危害只因整个模块不可达；顺着 barrel 接起来就是**绕过 bridge 的旁路**。
//    它自带的 checkOOHealth 与共享基类重复且更弱（无 _silent、无信封双形态兼容）。
export * from './useJ3ImportExport'
export * from './useJ3Disclosure'
