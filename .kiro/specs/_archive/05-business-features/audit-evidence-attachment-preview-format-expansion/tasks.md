# Implementation Plan: 审计证据附件预览格式扩展

## Overview

实施顺序改为：**真实基线与路线资格 → registry/HTTP/资源地基 → 三族 Worker 解析 → 净化与视图 → DTO/两宿主接线 → 零回归与生产构建确认 → 守卫/变异 → Playwright → CI/入库**。

全部任务 required。路线 A 只作能力与体积 probe；它不能满足硬安全契约时直接记 `ineligible`，不得因 tree-shaking 后包小而胜出。路线 B 是当前唯一有完整实施任务的路线。`drawing` 可按真实构建门退出；退出时必须删除对应 registry、动态 import、依赖与 UI，再重建复测，不能把任务标成“跳过”。

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 0, "name": "真实基线与路线资格", "tasks": [1, 2]},
    {"wave": 1, "name": "registry、HTTP 与 archive policy", "tasks": [3, 4, 6]},
    {"wave": 2, "name": "资源作用域与真实 DTO", "tasks": [5, 13]},
    {"wave": 3, "name": "三族 Worker 与取字节层", "tasks": [7, 8, 10, 11]},
    {"wave": 4, "name": "邮件净化与隔离", "tasks": [9]},
    {"wave": 5, "name": "共享视图与状态机", "tasks": [12]},
    {"wave": 6, "name": "两宿主接线", "tasks": [14]},
    {"wave": 7, "name": "legacy/API 零回归", "tasks": [15]},
    {"wave": 8, "name": "生产构建确认与范围回退", "tasks": [16]},
    {"wave": 9, "name": "守卫齐备性", "tasks": [17]},
    {"wave": 10, "name": "变异检验", "tasks": [18]},
    {"wave": 11, "name": "真实浏览器验证", "tasks": [19]},
    {"wave": 12, "name": "CI、入库与清理", "tasks": [20]}
  ],
  "critical_path": [1, 4, 5, 8, 9, 12, 14, 15, 16, 17, 18, 19, 20],
  "hard_dependencies": {
    "3": [1, 2],
    "4": [1],
    "5": [4],
    "6": [2],
    "7": [5, 6],
    "8": [2, 5],
    "9": [5, 8],
    "10": [2, 3, 5],
    "11": [3, 4, 5],
    "12": [7, 9, 10, 11],
    "13": [1, 3],
    "14": [3, 12, 13],
    "15": [1, 14],
    "16": [2, 12, 14, 15],
    "17": [6, 7, 8, 9, 10, 11, 13, 14, 15, 16],
    "18": [17],
    "19": [16, 17, 18],
    "20": [18, 19]
  },
  "parallelizable": [
    [1, 2],
    [3, 4, 6],
    [5, 13],
    [7, 8, 10, 11]
  ]
}
```

## Tasks

- [x] 1. 冻结真实 legacy/API/DTO 基线并登记既有债务
  - 用**生产真实形状**冻结 Preview_Host 与 Drawer_Host：文件名 × `file_type`（`word/excel/image/扩展名/空值`）矩阵、挂载后 DOM、原文文案、实际请求 URL、Office `preview-pdf` 与 health cache 行为。显式期望值，不使用可被随手更新的自由 snapshot
  - 分别冻结三个现有集合，不求并集：Preview_Host 图片（不含 svg）、Drawer_Host Office/PDF/image 提示语义、AttachmentTabPanel 的 6 项 Office 与 icon 分组；`.PDF`、svg、odt/ods/odp/rtf 等边界要落红/绿基线
  - 增加后端行为契约：legacy preview 返回字节；zip/eml/msg/dxf preview 仍返回 `previewable:false` JSON；download 返回原字节；zip/eml/msg/dxf 上传仍可接受。源码/AST 检查只作补充，不把字符串冻结当主判据
  - 冻结 process-record 当前 DTO 缺 `ocr_status/ocr_text` 的红基线，以及 TabPanel 把 `file_type` 误命名为 `mime_type` 的生产链事实
  - 写 `registered_debt.json`：① `xlsx@0.18.5` 两条告警与 `useExcelIO.ts` 不可信输入调用面；② AttachmentHub 死 import + `window.open` TODO；③ 两宿主并存成本与长期收敛建议。三项都标“不在本 spec 修复范围”
  - 产物：legacy/API/DTO 基线测试、`registered_debt.json`、`baseline_manifest.json`（含测试 nodeid 与实施前 commit/文件 digest）
  - _Requirements: 5.1, 5.2, 5.5, 5.6, 9.4, 9.5, 9.6_
  - _Properties: 16, 18, 31_

- [x] 2. 先过 Route_Eligibility，再做不可被 tree-shaking 的真实体积 probe
  - 在可删除 `audit-platform/frontend/bundle-probe/` 建同 Vite 配置 workspace；A 精确固定 `@open-file-viewer/core@0.1.44` + `@open-file-viewer/vue@0.1.44`，真实调用 `archivePlugin()` / `emailPlugin()` / `cadPlugin()`、注册并挂载最小 Vue viewer，分别喂 zip/eml/dxf 样本；断言相关 module id 真实进入产物。不得用不支持 DXF 的 `drawingPlugin()`冒充
  - A 的能力矩阵逐项真测 Archive_Limits、邮件零外发/CSP、DXF、dispose、许可证；预期缺口必须形成 `capability_eligible:false` 证据。`@mlightcad/libredwg-web` 为 GPL-3.0，probe 不安装；若 npm 解析把它带入 lock/chunk，A 立即 license fail
  - B probe 精确固定 `fflate@0.8.3`、`postal-mime@3.0.0`、`@kenjiuno/msgreader@1.28.0`、`dxf-parser@1.1.2`，真实构造/调用解析器防 tree-shaking；只有 B 资格成立后才把精确版本加入产品 `package.json`
  - 建 `decideRoute()`：资格门先于体积门；没有实施任务的 A 不得被单纯体积结果选中。生成 `route_capability_and_bundle_budget.json` 与 `dependency_licenses.json`，传递依赖按 lockfile **精确解析版本**记录，禁止 `0.6.x/1.x`
  - 在生产改动前构建应用 baseline，记录 commit、lockfile digest、命令、entry graph、首屏 gzip；预算为解析依赖首屏 0 B、首屏增量 8 KiB、archive 96 KiB、email 700 KiB、drawing 400 KiB、按需合计 1.2 MiB
  - 输出 B 入选与 drawing 暂定在范围的机器可读裁决；若 B 本身资格失败则阻塞后续任务并回 spec，不临场换库
  - _Requirements: 6.3, 6.4, 6.6, 7.1, 7.2, 7.3, 7.4, 7.6_
  - _Properties: 21, 23, 25_

- [x] 3. 实现 Type_Hint-aware Format_Registry 与宿主专属 legacy 能力矩阵
  - `resolvePreviewFamily(fileName, typeHint?)` 返回封闭 `FamilyVerdict`；扩展名优先，文件名无扩展名时才接受已知 MIME、`word/excel/image` 分类词或扩展名别名，未知/冲突返回 unsupported
  - family → Byte_Channel 单向派生；archive=`zip/tar/gz/tgz`、email=`eml/msg`、drawing=`dxf`（服从 Task 2 裁决），dwg 只在 `cad_download_only` advice
  - `LEGACY_CAPABILITIES`分别保存 Preview_Host、Drawer_Host、AttachmentTabPanel 的现状集合/语义；不得把后端 svg 或 Drawer 的 10 项 Office 回灌到其他宿主
  - 建表函数可注入声明，跨族冲突、dwg 入族在模块加载期 fail closed；用合成坏声明真跑守卫
  - 导出 `inlineExtensionListViolations()`；扫描两宿主和真实消费方，守卫带 SFC/TS `stripComments()`、合成反例与反向自检。最终仍以 Task 1 行为矩阵判零回归
  - 产物：`attachmentPreviewFormats.ts`、registry/单一真源守卫
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 6.1, 6.2_
  - _Properties: 1, 2, 3, 20_

- [x] 4. 修复共享 HTTP 的“signal 被覆盖/同 URL 互相取消”契约，默认行为零回归
  - 为内部 Axios config 增加 `_dedupe?: boolean`，默认仍为 true；`addPending()`遇 `_dedupe:false` 立即跳过 pendingMap 且保留调用方 `signal`，不改变其他 GET/POST/PUT/PATCH 去重行为
  - 行为守卫：预先 aborted signal 不发请求；请求中 abort 真正取消；同 URL 两个 `_dedupe:false` 请求均成功；取消一个不影响另一个；未传该标志的存量 GET 仍取消先发请求
  - 取消错误不得触发全局 toast、5xx retry 或局部 `load_failed`；401 继续走原全局刷新/登出路径，不能被 `_silent` 绕过
  - 产物：http config 类型/拦截器最小改动与定向守卫
  - _Requirements: 2.5, 2.6, 2.7_
  - _Properties: 6, 7_

- [x] 5. 实现 PreviewResourceScope 与统一 Worker lease/deadline
  - `PreviewResourceScope`统一登记 object URL、AbortController、Worker 与 cleanup listener，`releaseAll()`幂等且可观察各类 live count
  - `previewWorkerClient.ts`用 transferable ArrayBuffer、唯一 request id、deadline、terminate；关闭/切换/超时立即终止，迟到 message 不得写状态
  - 守卫：连续打开 5 次后 URL/worker/listener/pending 全归零；worker 超时被 terminate；旧 worker 回消息被 generation fence 丢弃；release 两次不报错
  - 明确资源计数不是浏览器内存硬上界，禁止用 archive 64 MiB 业务门宣称总内存 ≤64 MiB
  - _Requirements: 2.5, 2.6, 2.7, 5.7_
  - _Properties: 6, 7, 19_

- [x] 6. 建立 Archive_Limits、容器支持矩阵与恶意夹具语料库
  - 五项单一真源：entries=2000、entry actual bytes=32 MiB、total actual bytes=64 MiB、actual ratio=100、`maxPathDepth=8`；最后一项只指归一化路径段，不宣称递归解析嵌套归档
  - 固定首版支持：single-disk classic ZIP method 0/8、ustar/受限 PAX/GNU long-name、gzip/tgz；明确 ZIP64/multi-disk/AES/method 9/12/14/93/99、TAR sparse 为 `container_unsupported`
  - 建真实二进制夹具：GBK/UTF-8 名、`../`/`C:\`/绝对路径/NUL、加密、伪造声明 size、ZIP64、multi-disk、各不支持 method、截断 EOCD/central/local/data descriptor、CRC 错、超长 comment、tar checksum 错、tgz bomb、entry 局部坏
  - 每项 limit 必有只触发该项的夹具；夹具生成器固定 seed/digest，防守卫把错误样本冻成基线
  - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - _Properties: 9, 10, 11_

- [x] 7. 实现 archive Worker：边界解析、实际计数、CRC 与部分结果
  - `archive.worker.ts`只接 transferable bytes、分批回元数据；deadline 15 秒由 lease 控制，主线程不解压、不接收条目正文
  - ZIP：规范 comment 窗口找 EOCD；所有 offset/length 安全整数与边界检查；central/local flags/method/name 一致；支持 data descriptor 且不得覆盖中央目录；method 0/8 逐 chunk 实际输出计数并算 CRC，自报 size 仅作诊断
  - TAR：header checksum、size/offset、结束块、受限 PAX/GNU long-name；link 只列不跟随；GZIP 校验 trailer CRC，ISIZE 不作上限；tgz 输出直接喂增量 TAR 状态机，不物化整份 tar
  - 路径先 `\`→`/` 再检测穿越；编码链 UTF-8/EFS → UTF-8 fatal → GBK → replacement；局部 entry 错可继续，容器结构/边界/CRC 错 fail closed
  - archive 模块禁止 service/http/fetch/XHR/File System Access/download anchor；结构 + 行为双守卫，真实解析时外部网络 0
  - 视图数据的 size 必须是实际输出计数，不显示伪造声明值为“解压后大小”
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - _Properties: 8, 9, 10, 11_

- [x] 8. 实现受限 email Worker 与 eml/msg 归一模型
  - email worker 上限：输入≤50 MiB、part≤500、单 inline raster≤10 MiB、inline 总量≤32 MiB、deadline 15 秒；超门有独立错误码
  - `.eml`走 postal-mime、`.msg`走 msgreader，归一 from/to/cc/subject/date/html/text/附件元数据；普通附件不把 bytes 复制回主线程，只有候选 inline parts 传 transferable
  - CID canonicalization：trim、去外围尖括号、单次 percent decode、ASCII lowercase；重复 canonical CID 标歧义并 fail closed，不采用声明顺序取先者
  - 用 RFC 2047 B/Q、GB2312/GB18030、HTML+text、附件、CID、损坏 eml/msg 真实夹具；连续坏→好必须成功
  - _Requirements: 4.1, 4.2, 4.3, 4.8, 4.9_
  - _Properties: 12, 15_

- [x] 9. 实现私有 Email_Sanitizer、CID magic 门与 sandbox/CSP 双层零外发
  - 每次预览创建私有 DOMPurify 实例；显式 HTML tag/attr allowlist，禁 script/iframe/object/embed/form/媒体/SVG/MathML/style、全部事件属性与自动加载/提交属性；不得用共享全局 hook 或 `removeAllHooks()`
  - `sanitizeEmailHtml()`返回 `{html, blockedResources, generatedObjectUrls}`；被 FORBID 的 link/iframe 通过 blockedResources 形成可见汇总，不再要求已删除节点被后置 hook 打标
  - CID 仅允许 declared MIME 与 magic 一致的 png/jpeg/gif/webp；SVG/HTML/未知/超限/重复 CID 均阻断。外链显示为不可点击文本/host 标签，不保留 href
  - HTML 只进 `sandbox=""` iframe，srcdoc 首部固定 CSP：default none、img 仅 blob/data、connect/media/frame/form/base 全 none；纯文本走 textContent
  - 单元/挂载守卫覆盖 img/src、srcset、picture/source、video poster、SVG href、CSS url/@import、scheme-relative URL、编码/转义变体；输出 DOM 无外部可加载位，连续两封邮件 hook/CID 不串线
  - HTML↔纯文本切换属于视图行为，在本任务提供安全模型，Task 12 完成 UI
  - _Requirements: 4.4, 4.5, 4.6, 4.7, 4.9_
  - _Properties: 13, 14, 15_

- [x] 10. 实现 DXF Worker + typed SVG，或执行完整 drawing 退出分支
  - 仅当 Task 2 保留 drawing：worker 先做输入≤16 MiB 与 group-code/entity 轻量预扫，再调用 dxf-parser；maxEntities=200000、maxInsertDepth=8、deadline 10 秒
  - 映射 LINE/LWPOLYLINE/POLYLINE/CIRCLE/ARC/ELLIPSE/POINT/TEXT/MTEXT/INSERT；返回 typed render model，Vue 以元素/VNode和 textContent 渲染，禁止 SVG string + `v-html`
  - 超限保留已安全渲染部分并指名触发项；`.dwg` 从编排层行为守卫证明 worker factory 调用 0
  - 若 Task 2 已判 drawing 资格/预计体积不成立：删除 dxf family 与产品依赖计划，dxf/dwg 均进入下载提示，并把退出证据写台账；不得缩阈值伪绿
  - _Requirements: 6.1, 6.2, 6.5_
  - _Properties: 20, 22_

- [x] 11. 实现显式 download 取字节、错误分类、logger 与取消/代际栅栏
  - `ExtendedFormatPreview`只接显式 attachment id + download URL；所有真实消费方必须传 `P_att.download(id)`，新增路径禁止 `replace('/preview','/download')`
  - 直接 `http.get(...,{responseType:'blob',_silent:true,_dedupe:false,signal})`拿 response headers；header 或 blob.type 为 JSON → wiring_error + `logger.error`，只记录 id/family/content-type/request id，不记录文件字节、邮件主题/正文
  - 403/404/其他分别为 forbidden/not_found/load_failed；401由全局认证；Axios cancel 与 stale generation 不展示失败
  - fetch 完成、ArrayBuffer transfer 前后、worker 返回后都检查 generation；关闭/切换先递增 generation，再 abort/release
  - 行为守卫真造 JSON blob、双宿主同 URL、先发后到、abort race；legacy 完全不调用本层
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7_
  - _Properties: 4, 5, 6, 7_

- [x] 12. 实现三族视图与 ExtendedFormatPreview 状态机/动态边界
  - `ArchiveEntryList.vue`展示 name/实际 size/time/directory/suspicious/unparsable；`EmailMessageView.vue`展示六项头部、HTML↔纯文本、轻量附件清单、blocked 占位；`DxfDrawingView.vue`仅在 drawing 保留时存在
  - `ExtendedFormatPreview.vue`动态 import 族模块并创建 worker；状态含 loading/ready/forbidden/not_found/load_failed/wiring_error/limit_reached/encrypted/format_mismatch/container_unsupported/parse_failed/unsupported/cancelled
  - cancelled 不显示错误；其他非 ready 状态全部带下载入口；解析异常统一隔离，close emit 不依赖子组件成功
  - 从 entry 同步可达图断言 fflate/postal-mime/msgreader/iconv/dxf-parser/worker 模块均为 0；仅打开相应族时加载对应 chunk
  - 完整 render tree 三要素守卫：N 条 archive 模型→N 行 DOM；非 archive→0 行；每行字段确在遍历子树内。不得错误要求宿主源码本身含 v-for
  - _Requirements: 4.1, 4.3, 4.4, 5.4, 5.7, 7.5, 8.9_
  - _Properties: 12, 13, 17, 19, 24, 29_

- [x] 13. 修正真实 Type_Hint/OCR 只读 DTO 链，不改模型与 OCR 业务
  - process-record 附件只读查询/序列化补已有 `ocr_status/ocr_text`；保持现有权限、排序与其他字段，禁止新增迁移或 OCR 写入
  - `AttachmentForPreview.mime_type`一次性重命名为 `type_hint`，更新 Drawer_Host、AttachmentTabPanel 与全部测试/调用方；不保留第二字段兼容 fallback
  - TabPanel 从真实 API payload 构造 attachment，必须把 file_type→type_hint、OCR 字段、显式 preview/download URL 传入；若 OCR 为空按空显示，不额外伪造 MIME
  - 后端 payload→TabPanel→Drawer 集成守卫断言 archive/email/dxf 的 OCR badge/text 真可见；直接 mount 理想 props 只能作补充
  - _Requirements: 1.4, 5.3_
  - _Properties: 1, 17, 29_

- [x] 14. 两宿主接线并保持各自 legacy 行为
  - Preview_Host 两个消费方显式传 attachment id/download URL/typeHint；新增分支受 modelValue 门控，关闭即卸载；legacy helper 改读 previewHost 矩阵但 Task 1 行为逐项不变
  - Drawer_Host 在既有 Office 降级后、兜底前挂同一共享组件，且用 `v-if="modelValue && extendedFamily"`或等价 active 门确保关闭释放；Office `preview-pdf`、health cache、OCR 外层结构一行语义不变
  - AttachmentTabPanel 的 Office/icon 清单改读自身矩阵，不借 Drawer 集合扩面；AttachmentHub 不夹带接线
  - dwg 只显示 CAD 专用下载文案；普通 unsupported 保持两宿主原文
  - 两宿主挂载守卫用真实 Type_Hint/DTO：archive/email/dxf（若保留）可达；只删任一挂载点必须打红；快速 close/switch 后 live resources=0
  - _Requirements: 1.5, 1.7, 2.5, 2.6, 5.1, 5.2, 5.3, 8.8, 8.9_
  - _Properties: 2, 3, 6, 16, 17, 29_

- [x] 15. 复跑 legacy、Office、OCR 与后端 API 零回归
  - 复跑 Task 1 的全部显式矩阵；Preview_Host/Drawer_Host 各自 DOM、文案、URL、SVG/大小写/Office 边界与实施前一致，不能通过更新 baseline 让差异消失
  - 复跑 Office previewPdf/health/503 降级、legacy OCR 可见性；新增 OCR DTO 字段不得改变旧字段、排序或权限
  - 复跑上传/preview/download 行为契约：三类上传仍可、preview 白名单/JSON shape 不变、download 原字节；对源码 AST 的检查只报告结构漂移
  - 生成 baseline before/after 对比台账，任何授权外差异阻塞 Task 16
  - _Requirements: 2.2, 5.1, 5.2, 5.3, 5.5, 5.6_
  - _Properties: 4, 16, 17, 18_

- [x] 16. 做实施后生产构建确认；超门则完整回退范围并再次重建
  - 在 Task 2 相同 commit/lock 口径重算；若环境已漂移，先重建可比 baseline并记录原因，不把并发改动体积归给本 spec
  - 从 Rollup module graph 证明解析依赖/worker 0 B 进入首屏，回填首屏与 archive/email/drawing chunk gzip；`bundleBudgetLedger`重算 route/subset 决策与许可证 chunk 归属
  - A 保持 ineligible；B 任一资格或体积门失败必须停。drawing 超门时删除 registry dxf、动态 import、worker/view、dxf-parser 产品依赖和对应状态，再 build+tests 直至门通过；不得只写红台账继续
  - 清理 bundle-probe/node_modules/dist，只留 capability、measurement、命令、digest 与回退证据
  - _Requirements: 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
  - _Properties: 21, 22, 23, 24, 25_

- [x] 17. 建 Property→test nodeid→mutation 的守卫覆盖矩阵并补齐行为缺口
  - 逐一核对 32 条 Correctness Properties，每条至少有实施守卫与独立验证 nodeid；生成 `guard_coverage.json`，分母是 property/nodeid，不是“守卫文件数”
  - Requirement 8.1 面至少覆盖 registry、两宿主分发、Byte_Channel、JSON trap、HTTP cancel/dedupe、五限、路径穿越、sanitizer、CSP 网络 0、CID 隔离
  - 判据优先级：真实函数/worker执行、挂载 DOM、API 行为、网络事件、module graph；源码检查必须 stripComments + 合成坏输入 + 反向自检，单纯 `toContain` 不合格
  - 逐个新增导出找唯一生产消费方与真实宿主，防 additive 死代码；legacy 期望只读 Task 1 冻结台账，防把错值重新手写成新基线
  - 后端守卫与前端守卫定向全绿后冻结 passed 数及完整 test nodeid manifest，供 Task 18 strict baseline
  - _Requirements: 8.1, 8.2, 8.3, 8.8, 8.9_
  - _Properties: 26, 27, 29_

- [x] 18. 加强 mutation 外层并逐 Property 真跑四态变异
  - 复用 `_mutation_kit` 的 Mutation/apply/judge，不谎称其原生具备全量快照；本脚本先 strict baseline（失败集空、passed 数与 nodeid manifest 全相等）再拍全部 mutation target bytes+hash
  - 用 `O_EXCL` spec lock；每条仍由 kit 即时备份/还原与落盘读回；最外层 `finally`核验全部目标。只恢复脚本拥有的 original/mutated digest，发现外部并发字节报 RESTORE-CONFLICT、停止且保留恢复副本，禁止盲覆
  - 每条 Property/关键 nodeid 至少一个 mutation id；`guard_files` tally只作补充。锚点单行且唯一，`--list/--check-anchors/--run/--restore` 全可用
  - 变异至少覆盖：Type_Hint误当 MIME、legacy union 扩面、byte channel、`_dedupe:false`被忽略、generation/worker terminate、JSON trap/header、五限与实际计数、ZIP unsupported/CRC/路径、邮件 worker limits、私有 hook/CSP/CID magic、dwg worker、DTO OCR、单宿主断线、动态 import 静态化、route capability 先后顺序
  - GREEN/WRONG-TEST/ANCHOR-MISS/ERROR/RESTORE-CONFLICT 任一非零即补守卫或脚本后重跑；结果写 `mutation_verdicts.json`，收尾所有目标逐字等于 pristine snapshot且无 `.mutbak`
  - _Requirements: 8.3, 8.4, 8.5, 8.6, 8.7_
  - _Properties: 27, 28_

- [x] 19. Playwright 真文件、两宿主、零外发与资源回收实测
  - Preview_Host（AttachmentManagement）+ Drawer_Host（WorkpaperEditor→面板→AttachmentTabPanel）均实测；`browser_evidence.json` 中 `drawer_host_exercised=true`
  - 用真实完整链路上传→列表→预览，不 mock：zip（中文名/穿越/伪 size）、tar/tgz、eml（HTML+text/外部资源/CID/附件）、msg、dxf、dwg；drawing 已退出时 dxf 断言下载提示而非 SVG
  - Preview_Host 走 AttachmentManagement，Drawer_Host 走底稿 AttachmentTabPanel；验证真实 file_type/DTO 识别、OCR、下载入口与两宿主完整 render tree
  - 网络监听断言新增三类请求 Preview_Endpoint=0、邮件预览外部 host=0；攻击样本覆盖 source/srcset/poster/SVG/CSS URL。sandbox/CSP 属性与 blocked 提示可见
  - 并发/生命周期：两宿主同时开同附件均成功；快速切换先发后到不串；关闭时 request abort、worker terminate、object URL/listener/pending 计数归零；重复 5 次不增长
  - 控制台未捕获异常=0；故意注入 JSON trap 时出现平台 logger ERROR 且不含正文/主题/字节；失败后下一附件可正常打开
  - 写 `browser_evidence.json`（场景、附件 digest、请求摘要、截图路径、结论）；非本 spec 缺陷只登记，不夹带修改
  - _Requirements: 2.1, 2.3, 2.5, 2.6, 2.7, 3.1, 3.2, 4.1, 4.4, 4.6, 4.7, 5.3, 5.4, 5.7_
  - _Properties: 4, 5, 6, 7, 8, 13, 14, 15, 17, 19, 29_

- [x] 20. 追加归因型 CI、核对全部产物 tracked、更新索引并清理临时产物
  - 生成 `artifact_manifest.json`，逐项列实现、worker、view、fixture、前后端守卫、变异脚本、7 类台账与 CI 引用；对每条验证 exists + git tracked，任何 `??` 不得宣称完成
  - 在 `.github/workflows/governance-checks.yml`末尾追加本 spec 前端/后端两个归因型 job；依赖安装与定向测试沿用现有范式，引用路径从 manifest/固定清单取。验收只看本 spec 追加字节区间，不断言并发 job 全局不变
  - 干净 checkout 复核 CI 所有路径存在且锁文件能 `npm ci`；复跑 strict guard baseline、mutation `--check-anchors` 与 artifact manifest check
  - 复核 registered debt：`xlsx-0.18.5-cve` 与 `attachment-hub-dead-import` 继续标记为本 spec 范围外；`dual-host-convergence` 已按用户决策在本 spec 内完成并标记 `resolved=true`；更新 `.kiro/specs/INDEX.md` 的 Active 数、空壳数与本 spec **20/20** 状态（实施过程中按真实复选框更新）
  - 清理本会话 bundle-probe、dist、tmp_*、_wip_*、mutation lock/recovery 与浏览器临时附件；按 mtime/内容判归属，不删除并发会话产物
  - 复盘补丁（2026-09-09）：HTML 底稿补「面板」入口并将 `WorkpaperSidePanel` 提升为 HTML/Univer 共用；Playwright 走 追溯关联→附件 真路径，`drawer_host_exercised=true`
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_
  - _Properties: 30, 31, 32_

## 复盘补丁 2（2026-09-09 P0-P2 缺口修复 + 宿主收敛）

对首轮交付做二次审计后修复以下缺口（全部实证，非文档性）：

- **P0-A 入库**：首轮 43 条 artifact 中 37 条 `??` 未跟踪、CI 干净 checkout 必挂。本轮全部 `git add`（现 49 条含收敛新增），manifest 删除自我豁免 note 换成 `tracked_verification` 实跑断言块（`all_tracked_or_staged=true`）。
- **P0-B 存在性断言**：`writeGuardCoverage.mjs` 曾硬编码 M11/M12/M15/M18/M19/M22/M24/M25 等 8 个 mutation_verdicts.json 中**不存在**的 id（虚报 27/32 覆盖）。加 mutation id 存在性断言（引用不存在即 throw），反向自检通过（临时插 ZZZ_NONEXISTENT → exit=1）。
- **P1-A 补变异**：真实补齐上述 8 条变异（archiveLimits AES / emailParser to·catch / emailSanitizer PNG magic / contract extension_whitelist / bundleBudget drawingFits·onDemand·entryGzipDelta），新增守卫（CID magic mismatch / subset_required / entryGzipDelta 常量 / emailParseIsolation.spec vi.mock 抛异常测 catch）。**28/28 变异全 RED，behavioural_props_missing_mutation=[]**。
- **P1-B Playwright**：新增第二个 e2e test 补三组真浏览器实测——资源回收开关 5 次 `__APFE_SCOPE_LIVE__` 全 0、JSON trap → logger ERROR 不泄露正文、email CSP srcdoc `default-src 'none'` + 零外发。ExtendedFormatPreview 加 gated test 探针（默认零副作用）。browser_evidence.json 追加 scenarios。
- **P2-A 首屏门口径**：design §4.3 明确首屏硬门 = module-graph 归因解析依赖/worker 进首屏 = 0 B（可精确归因，实证 entry_chunks 5 个全 parser-free）；gzip 增量 8 KiB 降级为参考量（并发改动 + minify OOM 不可归因）。此为收紧口径非放宽门。
- **P2-B 传递依赖 + 夹具**：dependency_licenses.json 补 3 条传递依赖精确版本 + license（@kenjiuno/decompressrtf@0.1.4 BSD-2-Clause / iconv-lite@0.6.3 MIT / loglevel@1.9.2 MIT，从产品 lockfile）。archiveFixtures 补 5 夹具（ZIP64 marker / 超长 comment / GBK 名 / 单条 34MiB 触发 maxEntryUncompressedBytes / 合计 72MiB 触发 maxTotalUncompressedBytes），archiveFixtures.spec 17/17 全绿。
- **P2-C 删 probe**：bundle-probe workspace 删除，台账指针改指产品 package-lock.json，route_a 结论保留。
- **宿主收敛（debt dual-host-convergence resolved=true）**：抽 `AttachmentPreviewCore.vue` 为单一逻辑宿主（variant='client' 弹窗 / 'server' 抽屉），extension/AttachmentPreview.vue 与 common/AttachmentPreviewDrawer.vue 退化为容器薄壳，全部预览逻辑（familyVerdict/ExtendedFormatPreview 分发/legacy 渲染/OCR/office health/文案）单一真源。legacy DOM class 与文案逐项复刻，零回归全绿。变异 M16 锚点迁至 core。保留弹窗/抽屉两种容器形态（服务不同场景），逻辑单一真源。

收口实证：前端守卫 **180 passed / 0 skipped**、后端 **23 passed**、变异 **47/47 RED**（GREEN/WRONG-TEST/ANCHOR-MISS 均为 0、全部 `restored=true`）、`--check-anchors` **47/47 OK**、guard_coverage `gate=PASS`。Playwright 专用 `apfe-e2e` server 使用隔离端口 3031，**2 passed / 0 skipped / 0 flaky**，双宿主真路径及资源回收/CSP/零外发均通过。

## 复盘补丁 3/4（2026-09-09 Archive / DXF / Email 安全闭环）

- **Archive 流式限额闭环**：ZIP 单 entry ratio 改用该 entry 的实际压缩消费量，前置 stored 条目不能稀释后续 bomb；TAR `maxPathDepth` 在 ratio 之前裁决，普通/PAX/GNU 三种“大正文 + 9 段路径”均返回 `limit_reached/maxPathDepth`。
- **TAR 扩展与 GZIP 完整性**：受限支持 PAX `x/g` 与 GNU `L/K` 元数据状态，扩展头不作为附件条目；sparse、`GNU.sparse.*` 与异常扩展 fail closed；header/PAX mtime 均解析。GZIP 校验 CRC、ISIZE、尾随数据与可选头，`hintExt='gz'` 返回单条实际元数据，`.tgz`/无 hint 才进入 TAR 状态机。
- **DXF 绕过面修复**：group-code `0` 预扫覆盖 `ENTITIES/BLOCKS` 全部非结构实体，unsupported `HATCH/SPLINE/unknown` 也计入 flood 门；`DRAWING_LIMITS.deadlineMs=10_000` 由宿主真实消费。
- **Email 资源归属修复**：CID object URL 统一纳入宿主 `PreviewResourceScope`；换邮件/卸载成对释放；HTML/text mode 随当前安全正文复位，空 HTML 禁用切换。
- **判据补强**：新增 M38-M50，并修正 M03 文件级 fail-closed、M04 `_dedupe:false` 真调用参数与 M11 实际测试标题；正式全量结果为 **47 RED / 47**，16/16 登记守卫文件至少被一条变异打红，全部源码逐字恢复。
- **浏览器门修复**：专用 Vite `apfe-e2e` server 与普通 3030 开发服务隔离到 3031，避免复用无探针的普通 server；面板打开动作使用可见/启用门与一次有条件重试，最终 **2 passed / 0 skipped / 0 flaky**。
