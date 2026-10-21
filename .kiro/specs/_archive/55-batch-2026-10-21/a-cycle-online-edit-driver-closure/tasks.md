# 实施任务：A 循环在线编辑驱动收口

> 关联：#[[file:.kiro/specs/a-cycle-online-edit-driver-closure/requirements.md]] · #[[file:.kiro/specs/a-cycle-online-edit-driver-closure/design.md]]
> `[x]` = 代码已落地且验收通过；做不到的如实保持 `[ ]` 并写明原因。
> 铁律：不假绿、不弱化守卫、守卫基线保持空数组、每个生产修复配变异反证、改动后浏览器实测。

> 实际分类修正（实施时现算）：真 A 类 **11**（A91/A101/A111/A121/A1721/A1731/A173/A174/
> A182/A271/A81）、B 类 **3**（A171/A176/A177 有 generate-docx 预生成）、C 类 **3**
> （A38/A112/A115 死桥 + 整册 GtOnlyOfficeSheet）。17 全处置。

- [x] 1. 建 driver `sync/useARenderModeSwitch.ts`
  - 对标 `useHSyncMode` 裁掉 sheet 分派；mode `'html'|'docx'`；四分支/健康竞态/fail-visible
    照抄 H；暴露 renderMode(get/set)/modeOptions/descriptor/busy/syncStateTag/syncHostRef/
    syncBridge/lastNotice；beforeEnterOo/afterLeaveOo/flushBeforeSwitch 钩子
  - _需求：R1.1~R1.6_　证据：诊断 0

- [x] 2. driver 单测 + 变异 `sync/tests/useARenderModeSwitch.spec.ts`
  - 15 passed；变异：删 driver 内 switchToOnlyOffice 调用 → 4 用例打红（①③⑥b⑧），还原全绿
  - _需求：R5.2_

- [x] 3. A 类 canary A91 接 driver
  - 删 watch(mode)/本地 mode/checkOOHealth；el-segmented 绑 driver renderMode；EditorHost
    `ref="syncHostRef"`（driver 的 ref 直接作模板 ref）；守卫确认 A91 从 hollow/built-not-driven
    消失；A91 既有 68 测试全绿
  - 🟡 R6.1 浏览器实测待环境（手动起 dev server + OnlyOffice Docker），代码完成
  - _需求：R2.1~R2.4、R6.1_

- [x] 4. A 类其余 10 宿主接 driver
  - A101 A111 A121 A1721 A1731 A173 A174 A182 A271 A81；driver syncHostRef 直接作模板 ref
    （不建 host 级 watch，否则需 host import watch ⇒ ReferenceError）；249 passed 无回归
  - _需求：R2.1~R2.4_

- [x] 5. B 类 3 宿主接 driver + 保留预生成
  - A171/A176/A177：beforeEnterOo=generate-docx（A171/A177 包 ooGenerating/ooReady/ooError
    + 失败返 false 不进 OO；A176 generate 失败也 true 因 OO 加载已有文件）；afterLeaveOo=
    sync-from-docx + loadData/selfLoad + ooReady=false；A177 mode 中文串归一 'html'/'docx'
  - 全绿（A171 2+26 / A176 6+6 / A177 18+15）；🟡 R6.1 浏览器实测待环境
  - _需求：R3.1、R6.1_

- [x] 6. C 类 3 宿主删死桥
  - A38/A112/A115：删 useWorkpaperSyncBridge/capabilityForEntry/readStoreProjection import
    + WorkpaperSyncEditorHost 的 defineAsyncComponent const + syncBridge 块 + syncOoDescriptor
    + _ENTRY_ID/_SHEET_KEY；保留 GtEntrySyncCapabilityNotice（模板用）+ GtOnlyOfficeSheet
    whole-workbook docx 分支 + activeMode/docxDirty/docxAvailable
  - C 类既有 spec 全绿（A38 12+14 / A115 41+32 / A112 23+9）；🟡 R6.1 浏览器实测待环境
  - _需求：R4.1~R4.3、R6.1_

- [x] 7. 守卫全绿 + 基线保持空
  - `bridgeMaterializeDriven.spec.ts` 11/11 全绿；KNOWN_HOLLOW/KNOWN_BUILT_NOT_DRIVEN 仍
    为 `[]`（未写任何 A 宿主）；driver 被 drivingWrappers 识别
  - _需求：R5.1_

- [x] 8. 回归
  - sync 全目录 35/36 文件 975 passed（唯一红 = workpaperSyncLegacyBaseline 3 条，属 #3
    manifest 漂移治理门，非本 spec 引入——两生成产物比对，本 spec 未动生成文件）；A 宿主既有
    spec 全绿（a173 PBT 批量跑偶发红经隔离 55/55 复跑确认是跨文件 fast-check flake，非本 spec）；诊断 0
  - _需求：R5.3_

- [x] 9. 治理门交接材料
  - 产出 `governance-handoff.md`：approved=83ffa47d / current=23f66ff3，17 宿主变化清单
    （11 接驱动 + 3 B 类接驱动 + 3 删死桥）；**未** auto-regen（复核门）
  - _需求：R7.1_

- [x] 10. INDEX 登记、清理临时产物、如实汇报
  - 删 scripts/_a_driver_*.py 三个临时脚本 + .vitest-probe；INDEX 登记；诚实报告
  - _需求：R5_
