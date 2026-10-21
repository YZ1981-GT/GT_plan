# 需求：A 循环在线编辑驱动收口

## 背景与问题

`sync/__tests__/bridgeMaterializeDriven.spec.ts` 是平台级守卫，判据双向锁死：
**「挂了 `WorkpaperSyncEditorHost` 或建了 `useWorkpaperSyncBridge` 的宿主，必须有人调用
`bridge.switchToOnlyOffice()` 驱动 materialize」**。当前该守卫 3 条红，点名 A 循环宿主：

- 14 个「挂了 EditorHost 却无驱动」（hollow）
- 17 个「建了 bridge 却无驱动」（built-not-driven）

实证根因（现算，非推测）：commit `f20789453`「a-lane2-docx：mode 收敛 14 宿主」
只把各宿主的 `mode` ref 收敛成 `'html' | 'docx'` 并接了 `el-segmented`，**但没有一个
组件调用 `switchToOnlyOffice()`**。以 `GtA101GovernanceCommunication.vue` 为样本：

```
const syncBridge = useWorkpaperSyncBridge({ entryId, wpId, projectId, sheetKey,
  capability: capabilityForEntry(_ENTRY_ID), flushHtml, reloadHtml })
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
// 模板：<WorkpaperSyncEditorHost v-if="syncOoDescriptor" :descriptor :bridge />
//        <div v-else>正在打开同步编辑器…</div>
const mode = ref<'html' | 'docx'>('html')   // 绑 el-segmented，但无人 watch→switchToOnlyOffice
```

⇒ `syncBridge.descriptor.value` 恒 null ⇒ `v-if` 永不成立 ⇒ 用户切「在线编辑」后
**永远停在「正在打开同步编辑器…」那行字**。所有静态门全绿（import 齐、组件挂了、
桥建了、契约有、类型过），只有这条运行时守卫能抓到。f20789453 的配套是后端
`backend/tests/workpaper_sync/test_a_lane2_docx_authority.py`，前端驱动从未补上。

## 关键事实（现算核实，供设计约束）

1. **capability 支持 OO**：A entries 的 capability 是 `single_onlyoffice`
   （`workpaperSyncManifest.generated.ts`，manifest 现算 91 条），而
   `workpaperSyncModeStorage.ts` 第 63 行 `single_onlyoffice: ['oo']` ⇒
   `switchToOnlyOffice()` 的 capability 守卫**不会拒绝** A entries。故驱动可用。

2. **flushHtml 已 404 容错**：各宿主的 `flushHtml` 对 `readStoreProjection` 的 404
   （后端无 per-entry adapter）已 catch 返回空投影，走「无投影」路径，与改线前 legacy
   等价。capability 升 bidirectional 后自动失效。本 spec 不碰后端 adapter。

3. **17 宿主并非完全同构**，分三类（现算分类，见 design §1）：
   - **A 类（14 个，近同构）**：模板用 `<WorkpaperSyncEditorHost v-if="syncOoDescriptor">`
     + fallback「正在打开…」；`mode = ref<'html'|'docx'>`；有自己的 `checkOOHealth` +
     `flushPendingSaves`。只差「把 mode 切换接到 switchToOnlyOffice/switchToHtml」。
     名单：A101 / A111 / A112 / A115 / A121 / A171 / A1721 / A1731 / A173 / A174 /
     A176 / A182 / A271 / A81 / A91。（A177 归 B 类）
   - **B 类（A177）**：在挂 EditorHost 前多一层 `ooGenerating`/`ooReady`（先生成 Word）
     + `@change="handleModeChange"` + mode 用中文串 `'结构化视图'|'在线编辑'`。驱动需保留
     这层预生成。
   - **C 类（A38）**：在线编辑走 **legacy `GtOnlyOfficeSheet`**（`sheet-name="A3-8"`
     `:whole-workbook`），同时建了**死** `syncBridge`（从不挂 EditorHost、从不驱动）。
     被守卫 `bridgeBuiltNotDriven` 点名。需裁决：接桥 or 删死桥（见 design §4）。
   - 另 A176 在切换时有 `generate-docx` / `sync-from-docx` 自定义流，驱动需兼容。

4. **守卫识别真驱动的条件**（`bridgeMaterializeDriven.spec.ts` 的 `drivingWrappers()`
   固定点闭包）：模块体里出现 `switchToOnlyOffice(` 调用表达式即被收为 driver；宿主调用
   该模块导出的 wrapper（`\b<导出名>\s*\(`）即判为「被驱动」。故新建 `useARenderModeSwitch`
   内部调 `switchToOnlyOffice` 并被 15 个宿主调用即可全部转绿（与 G 循环 useGRenderModeSwitch
   同机制）。

## 需求

### R1 建立 A 循环统一在线编辑驱动（对标 useHSyncMode，裁剪掉 A 不需要的部分）
- R1.1 新建 `sync/useARenderModeSwitch.ts`（或等价命名），收敛「健康/竞态/门禁/
  descriptor/四分支保存/失败可见」六件事到单一实现。A 循环整册单一 OO 文档，
  **不需要** H/G 的 managed/unmanaged sheet 分派与 legacyMode。
- R1.2 mode 取值域 `'html' | 'docx'`（与 A 各宿主既有 `el-segmented` value 一致，
  不改成 `'onlyoffice'`）。
- R1.3 HTML→docx：`switchToOnlyOffice()`（内部先 flushHtml→pending→materialize）；
  切前跑一次 `flushBeforeSwitch`（宿主的 flushPendingSaves）。
- R1.4 docx→HTML 四分支（与 useHSyncMode 逐条同构）：
  ① `state==='applied'` → `reloadAfterApplied()`（秒切）
  ② `!dirty` → `leaveWithoutSaving()`（丝滑）
  ③ dirty 且 `canForcesave` 且有 editorHostRef → `editorHost.forceSave()`（慢但不丢改动）
  ④ dirty 但桥不放行 → `persistMode('html')` + **明示未同步**（sticky notice，不静默）
- R1.5 健康门禁移进 `switchMode`（await 兜底），**不用** `disabled: !ooHealthy`
  （D4 已实证 disabled 会在未就绪时吞掉点击）。
- R1.6 失败 fail-visible：错误经桥 `lastError`；driver 补一条 sticky `lastNotice`，
  不吞 unhandled rejection（computed setter 落点）。

### R2 A 类 14 宿主接驱动（每宿主最小改动）
- R2.1 每宿主用 `useARenderModeSwitch({ entryId, wpId, projectId, isReadonly,
  flushHtml, reloadHtml, flushBeforeSwitch })`，`el-segmented` 的 `v-model` 绑
  driver 的 `renderMode`（computed get/set），删除原 `watch(mode)` 里只 flush 不驱动
  的死逻辑。
- R2.2 模板 `<WorkpaperSyncEditorHost ref="syncHostRef" v-if="descriptor">` 补 ref，
  供四分支③的 forceSave。
- R2.3 保留各宿主原有 `checkOOHealth`/健康禁用选项行为由 driver 的 `modeOptions`
  统一接管，但不得回归（OO 不可用时「在线编辑」不可切但可点、由 driver fail-visible）。
- R2.4 不改宿主的业务逻辑（章节/表格/签发区），只改 mode 接线。

### R3 A177（B 类）保留预生成层
- R3.1 保留 `ooGenerating`/`ooReady` 预生成 Word 的那层；driver 的 OO 分支在预生成
  完成后再 `switchToOnlyOffice`。mode 中文串归一到 `'html'|'docx'`（或 driver 适配）。

### R4 A38（C 类）裁决并执行
- R4.1 设计阶段现算 A38 的死桥是否有任何引用方（descriptor/busy/switching 是否被模板或
  其它逻辑用到）。
- R4.2 二选一（design §4 给出判据与推荐）：
  - (a) **接桥**：把 docx 分支从 `GtOnlyOfficeSheet` 换成 `WorkpaperSyncEditorHost` +
    driver（与 A 类一致）；或
  - (b) **删死桥**：若 A3-8 确需留 legacy 整册 OO（whole-workbook，桥不支持整册），
    则删除 A38 里未用的 `useWorkpaperSyncBridge`/`syncOoDescriptor`/EditorHost import，
    让守卫的 `bridgeBuiltNotDriven` 不再点名它（它本就不该建桥）。
- R4.3 不得为了过守卫而「假接」（建桥但 descriptor 恒 null 换个写法）。

### R5 守卫转绿且不弱化
- R5.1 `bridgeMaterializeDriven.spec.ts` 3 条红全绿，`KNOWN_HOLLOW` /
  `KNOWN_BUILT_NOT_DRIVEN` 保持空数组（**不往基线写任何 A 宿主** —— 那等于祝福未完成迁移）。
- R5.2 driver 新增单测：四分支逐条命中、健康竞态兜底、fail-visible、switchToOnlyOffice
  真被调用；变异反证（删驱动→对应宿主被判空壳）。
- R5.3 回归：15+ A 宿主既有测试 + sync 全目录不新增失败。

### R6 浏览器实测
- R6.1 至少 1 个 A 类宿主（如 A91）+ A177（B 类）+ A38（C 类裁决后）在浏览器切「在线
  编辑」真打开 OO（descriptor 非 null、不再停「正在打开…」），切回结构化四分支正确。

### R7 治理门联动（交接给 #3）
- R7.1 A 宿主接驱动会改变 discoverer 的 mount 源 → `approved_source_digest` 需重新复核。
  本 spec 完成后，mount diff 的「新增驱动」是可解释的良性变化，交 workpaperSyncLegacyBaseline
  治理门（人工复核→更新 approved digest→重算 manifest+legacy baseline）。本 spec 负责
  产出「哪些 mount 变了、为什么」的复核材料。

## 非目标
- 不接后端 per-entry adapter（capability 维持 single_onlyoffice，flushHtml 404 容错已兜）。
- 不改 A 宿主业务逻辑。
- 不自动跑 manifest/legacy baseline 重算（那是 R7 的人工复核门，另行）。
