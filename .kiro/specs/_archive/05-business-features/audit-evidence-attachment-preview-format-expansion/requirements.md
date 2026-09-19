# Requirements Document

## Introduction

审计现场的证据附件里有三类格式目前**只能下载到本地打开**：压缩包（客户一次性打包提交的凭证影像）、邮件（`.eml` / `.msg` 形态的函证回函与管理层往来）、CAD 图纸（固定资产盘点的厂房与设备图）。本 spec 为这三类补浏览器内预览，**docx / xlsx / pdf / 图片的既有渲染结果与请求路径不得改变**。

本 spec 是新增能力，不是替换。明确不覆盖：

- 不替换 `@vue-office/{docx,excel,pdf}`，不替换 OnlyOffice / Univer，不改底稿本身的 HTML 渲染器；
- 不改变附件上传准入规则，不改附件数据库模型，不新增数据库迁移；允许为既有 OCR 字段补齐只读 DTO 投影，使已有能力在真实消费链可达；
- 不改变 `/api/attachments/{id}/preview` 既有白名单及返回行为；新增三类只通过已有 download 端点取原始字节；
- 不做 `.dwg` 图形渲染；
- 不做压缩包与邮件附件的二级预览，本轮只展示压缩包清单、邮件正文与邮件附件清单；
- 不修复既有 `xlsx@0.18.5` 供应链告警，本 spec 只登记。

## Glossary

- **Preview_Host**：`audit-platform/frontend/src/components/extension/AttachmentPreview.vue`。弹窗形态预览宿主，真实消费方为 `views/AttachmentManagement.vue` 与 `components/workpaper/WorkpaperAttachmentsDrawer.vue`。
- **Drawer_Host**：`audit-platform/frontend/src/components/common/AttachmentPreviewDrawer.vue`。抽屉形态预览宿主，当前唯一真实消费方为 `components/workpaper/AttachmentTabPanel.vue`。`views/AttachmentHub.vue` 只有死 import 与待办，模板未挂载该宿主。
- **两宿主**：Preview_Host 与 Drawer_Host 的合称。新增能力必须在两者都可达。
- **Type_Hint**：附件链路传入的可选类型提示。后端没有真实 MIME 列；生产 `file_type` 可能是 `word` / `excel` / `image` 分类词、扩展名，或调用方覆盖值。Type_Hint 因此不是内容真相；只有形如已知 MIME 的值才按 MIME 使用，内容安全判定仍靠 magic / 容器结构。
- **Format_Registry**：新增的文件名与 Type_Hint → 渲染器判定单一真源。它同时保存**宿主专属 legacy 能力矩阵**，避免把两个宿主的集合求并集后回灌而改变既有行为。
- **新增三类**：`archive`（`zip` / `tar` / `gz` / `tgz`）、`email`（`eml` / `msg`）、`drawing`（`dxf`）三个渲染族。
- **Legacy_Formats**：本 spec 之前两宿主已支持的 docx / xlsx / pdf / 图片等格式；两个宿主的精确集合并不相同，零回归按宿主分别冻结。
- **Preview_Endpoint**：`GET /api/attachments/{attachment_id}/preview`。对白名单内格式返回字节流，对白名单外格式返回 JSON 对象。
- **Download_Endpoint**：`GET /api/attachments/{attachment_id}/download`。对任意格式返回 `application/octet-stream` 字节流，鉴权与 Preview_Endpoint 同级。
- **Byte_Channel**：新增三类取字节所用的通道，取值为 Download_Endpoint。Legacy_Formats 继续沿用各宿主既有 Preview_Endpoint 路径。
- **JSON_Blob_Trap**：对白名单外格式误调 Preview_Endpoint 且按 blob/arraybuffer 接收时得到 JSON 响应，而非文件字节。
- **Archive_Limits**：压缩包解析的五项资源上限：条目数、单条实际解压字节、总实际解压字节、实际压缩比、归一化路径深度。最后一项不是“递归打开嵌套压缩包”的深度。
- **Zip_Bomb**：实际解压量、压缩比或条目数异常的压缩包。不得信任容器自报大小来判断。
- **Path_Traversal_Entry**：条目名归一化后含 `..`、绝对路径、盘符前缀、NUL 或混合分隔符逃逸形态的条目。
- **Email_Sanitizer**：邮件 HTML 正文的净化与资源重写环节，基于隔离 DOMPurify 实例，不共享有状态 hook。
- **Remote_Asset_Leak**：邮件 HTML 在渲染时引用外部主机资源，泄露审计查阅行为。必须由“净化/资源重写 + sandbox/CSP”两层共同阻断。
- **Bundle_Budget**：新增能力对真实生产构建产物的首屏与按需 chunk 体积门。
- **Route_Eligibility**：候选路线先满足功能、安全、许可证与可销毁性硬门，才有资格参与体积比较。不能满足 Archive_Limits、零外发、DXF 或许可证门的路线不得因包小而胜出。
- **路线 A**：`@open-file-viewer/core` + `@open-file-viewer/vue` 的候选路线；只作真实能力与体积 probe，不预设可进入产品。
- **路线 B**：直接使用压缩包、MIME 邮件、OLE 邮件和 DXF 底层解析库的候选路线。
- **Route_Decision**：先应用 Route_Eligibility，再在合资格路线间按 Bundle_Budget 实测裁决。
- **变异四态**：RED（打红且命中预期守卫）、GREEN（守卫缺陷）、ANCHOR-MISS（锚点未唯一命中）、WRONG-TEST（打红但未命中预期守卫）。

## Requirements

### Requirement 1: 扩展名到渲染器的单一真源

**User Story:** 作为平台前端维护者，我需要一份扩展名到渲染器的单一真源，以便两宿主对新增格式给出一致判定，同时不改变各自 legacy 行为。

#### Acceptance Criteria

1. THE Format_Registry SHALL 为任一文件名与可选 Type_Hint 返回落在封闭枚举 `{archive, email, drawing, legacy, unsupported}` 内的渲染族。
2. WHEN 同一输入被重复判定，THE Format_Registry SHALL 返回相同结果。
3. THE Format_Registry SHALL 对大小写混合扩展名与文件名前后空白作稳定归一。
4. WHEN 文件名不含扩展名，THE Format_Registry SHALL 仅在 Type_Hint 是已知 MIME、已知分类词或扩展名别名时回退判定；不可判或冲突时返回 `unsupported`，不得把 Type_Hint 当内容证明。
5. THE Format_Registry SHALL 把 Legacy_Formats 判为 `legacy`，并以宿主专属能力矩阵保持两个宿主实施前的 legacy 结果。
6. THE Format_Registry SHALL 为每个渲染族给出 Byte_Channel；`legacy` 为 Preview_Endpoint，新增三类为 Download_Endpoint。
7. THE Format_Registry SHALL 提供守卫可调用的断言，扫描两宿主及真实消费方源码，把 registry 外自带的扩展名字面量清单报为违规。
8. IF 一个扩展名同时出现在不同渲染族，或 `dwg` 被放入可渲染族，THEN 模块加载 SHALL fail closed。

### Requirement 2: 取字节通道、并发与生命周期

**User Story:** 作为审计助理，我需要新增格式点开就能看，且快速关闭或切换时不会串附件、继续占用资源或把接线错误伪装成“不支持”。

#### Acceptance Criteria

1. WHEN 渲染族为新增三类之一，THE 两宿主 SHALL 从 Download_Endpoint 取字节。
2. WHEN 渲染族为 `legacy`，THE 两宿主 SHALL 继续沿用实施前的请求 URL 与渲染路径。
3. WHEN 新增三类取回的响应为 `application/json`，THE 两宿主 SHALL 判为 JSON_Blob_Trap，展示明确失败态并通过平台 logger 记 ERROR；日志不得包含文件字节、邮件正文或主题。
4. WHEN 取字节失败，THE 两宿主 SHALL 区分 403「无权访问」、404「文件不存在」与其他「加载失败」；401 继续由平台全局认证刷新/登出链处理，不伪装成本地 403。
5. WHEN 宿主关闭、切换附件或卸载，THE 两宿主 SHALL 取消本次可取消请求、终止解析 worker，并释放全部对象 URL 与解析器资源。
6. THE 两宿主 SHALL 在重复打开同一附件时不累积对象 URL、worker、监听器或 pending request。
7. IF 响应在宿主关闭或切换后到达，THEN THE 两宿主 SHALL 以“取消 + 单调代际栅栏”双保险丢弃结果；取消能力不得被共享 HTTP 去重层覆盖，同 URL 的两个宿主请求不得互相取消。

### Requirement 3: 压缩包预览与资源上限

**User Story:** 作为现场经理，我需要在不下载的情况下看清压缩包中的证据清单，同时恶意或损坏压缩包不能卡死主界面。

#### Acceptance Criteria

1. WHEN 渲染族为 `archive`，THE 两宿主 SHALL 展示条目名、**实际**解压后大小、修改时间与目录标识。
2. THE 压缩包解析 SHALL 在浏览器内的专用 Worker 完成，不向平台外主机发字节，不落盘，不在主线程做解压。
3. THE 压缩包解析 SHALL 对 Archive_Limits 五项逐项设限；任一项触发时终止 worker 任务、保留已安全产出的条目元数据，并指名触发项。该业务计数不得宣称为浏览器进程内存硬上界。
4. WHEN 压缩包为 Zip_Bomb，THE 解析 SHALL 按实际流式输出计数，在达到总量或压缩比上限前中止，不依赖中央目录、gzip ISIZE 等自报字段。
5. THE 压缩包解析 SHALL 标记 Path_Traversal_Entry，且解析模块结构上不得引用文件系统写出接口。
6. THE 压缩包解析 SHALL 按声明编码解码条目名；声明缺失时 UTF-8 严格尝试、GBK 回退、最终替换解码，单个坏名字不得中断整包。
7. WHEN 压缩包受密码保护，THE 两宿主 SHALL 展示「该压缩包已加密，请下载后打开」。
8. IF 扩展名与实际内容不符，THEN THE 两宿主 SHALL 依据 magic 与容器结构展示格式不符；ZIP64、多磁盘、AES 或不支持的压缩方法须得到明确“当前不支持”状态，不得误报为普通损坏或按 deflate 强解。
9. THE 解析 SHALL 隔离条目级失败并继续安全条目；容器级边界、offset、CRC 或结构错误 SHALL fail closed。

### Requirement 4: 邮件预览与零外发

**User Story:** 作为审计助理，我需要在平台内查阅函证邮件要素与正文，同时邮件内容不能通过远程资源或主动内容泄露项目行为。

#### Acceptance Criteria

1. WHEN 渲染族为 `email`，THE 两宿主 SHALL 展示发件人、收件人、抄送、主题、发送时间与正文。
2. THE 邮件解析 SHALL 同时支持 MIME `.eml` 与 OLE `.msg`，并在专用 Worker 中执行有输入、部件数、内嵌资源量和墙钟时间上限的解析。
3. THE 两宿主 SHALL 列出邮件附件文件名与大小；普通附件不得无必要地复制回主线程。
4. WHEN 同时有 HTML 与纯文本正文，THE 两宿主 SHALL 默认展示净化 HTML，并提供纯文本切换。
5. THE Email_Sanitizer SHALL 移除脚本、事件属性、表单、主动媒体、SVG/MathML、`javascript:` 与所有未显式允许的标签/属性。
6. THE 两宿主 SHALL 以资源重写和 sandbox iframe CSP 两层阻断 Remote_Asset_Leak；净化漏判时 CSP 仍不得让浏览器向外部主机发请求。被阻断资源须有可见占位或汇总说明。
7. THE 邮件正文中的 `cid:` SHALL 只把经声明 MIME + magic 双判的安全栅格图片转换为本次 scope 的对象 URL；重复/歧义 CID、SVG/HTML 部件均 fail closed。
8. WHEN 头部采用 RFC 2047 或非 UTF-8 字符集，THE 解析 SHALL 输出可读中文。
9. IF 邮件解析失败，THEN 两宿主 SHALL 展示原因与下载入口，失败不得污染下一封邮件的 CID、hook、worker 或状态。

### Requirement 5: 预览与既有能力不互相干扰

**User Story:** 作为质量控制复核合伙人，我需要确认新增预览没有改变既有附件、Office 转 PDF 与 OCR 链路。

#### Acceptance Criteria

1. THE 两宿主对各自 Legacy_Formats 的分支结果、DOM、文案与请求 URL SHALL 与实施前逐项一致；不得用两宿主集合并集改变 SVG、大小写或 Office 格式行为。
2. THE Drawer_Host 的 `preview-pdf` 与健康探测 SHALL 不受影响。
3. THE Drawer_Host 的 OCR 状态徽标与 OCR 文本 SHALL 通过真实 process-record DTO → TabPanel → Drawer 链路在新增三类视图中可达，不得仅靠直接 mount 理想 props 假绿。
4. THE 两宿主 SHALL 保留下载入口，新增三类所有失败态均可下载。
5. THE 本 spec SHALL 不改变 Preview_Endpoint 白名单与返回结构。
6. THE 本 spec SHALL 不改变上传准入规则，并登记后端当前无扩展名白名单的实测事实。
7. WHEN 新解析器抛异常，THE 两宿主 SHALL 捕获并保持宿主可关闭，不让页面整体崩溃。

### Requirement 6: CAD 与许可证裁决

**User Story:** 作为内网私有化部署负责人，我需要 CAD 预览的许可证与资源边界先定清楚。

#### Acceptance Criteria

1. THE `drawing` 族 SHALL 只含 `dxf`；`dwg` 不进入解析集合。
2. WHEN 扩展名为 `dwg`，THE 两宿主 SHALL 展示下载后用 CAD 软件打开的专用文案。
3. THE 产品依赖 SHALL 不引入 GPL 系依赖；新增运行时依赖许可证只允许 MIT/MIT-0、Apache-2.0、BSD 系。
4. THE 交付 SHALL 记录每个直接与传递依赖的精确解析版本、许可证、是否进入产品 chunk 与选用理由。
5. IF `dxf` 使 Bundle_Budget 不成立，THEN `drawing` 整族 SHALL 退出并记录数据，不得缩小上限或放宽门。
6. THE 直接依赖 SHALL 用精确版本，传递依赖 SHALL 由 lockfile 锁定并按解析版本核验。

### Requirement 7: 资格门、依赖体积门与路线裁决

**User Story:** 作为前端性能负责人，我需要候选路线先证明功能与安全等价，再以真实构建体积裁决。

#### Acceptance Criteria

1. THE Route_Decision SHALL 先应用 Route_Eligibility；不满足 Archive_Limits、零外发、DXF、可销毁性或许可证的路线不得因体积更小而胜出。合资格路线之间再按实测体积裁决。
2. THE 体积实测 SHALL 基于真实 Vite 生产构建产物，不用解包大小或依赖清单推算。
3. THE 实测 SHALL 分别报告首屏加载增量与各附件预览按需 chunk 增量。
4. WHEN 路线 A 资格通过但首屏超门，THE Route_Decision SHALL 取路线 B；路线 A probe 必须真实调用 `archivePlugin()` / `emailPlugin()` / `cadPlugin()` 并挂载 Vue 适配器，不能被 tree-shaking 做成空探针。
5. THE 三类解析代码 SHALL 按需加载，未打开预览的用户不加载解析依赖或 worker 代码。
6. THE 交付 SHALL 记录 Bundle_Budget 数值、依据、构建命令、基线 commit/lockfile digest 与实测结果。
7. IF 合资格路线都超首屏门，THEN SHALL 缩减到能过门的格式子集，不放宽门；实施后确认门失败时必须回退对应格式再重建复测，不能只回填红台账。

### Requirement 8: 守卫与变异检验

**User Story:** 作为质量负责人，我需要守卫本身被证明能打红，并且变异运行不能污染并发工作树。

#### Acceptance Criteria

1. THE 守卫 SHALL 覆盖 registry、两宿主分发、Byte_Channel、JSON_Blob_Trap、HTTP 取消/去重、Archive_Limits、路径穿越、Email_Sanitizer、CSP 零外发与 CID 隔离。
2. THE 守卫 SHALL 以真实执行、挂载 DOM、网络事件或结构解析为判据；源码检查只能作补充，且必须剥注释、具备合成反例与反向自检。
3. THE 变异检验 SHALL 为每条 Correctness Property / 关键 test nodeid 建立至少一个变异映射，不以“某文件曾打红”代替性质覆盖。
4. WHEN 判读为 GREEN，THE 交付 SHALL 补强守卫，不得记为代码正确。
5. WHEN 锚点命中数不等于一，THE 判读 SHALL 为 ANCHOR-MISS 并报告实际次数。
6. THE 变异脚本 SHALL 先跑严格基线；基线通过后才对全部声明目标拍字节+hash 快照并获取独占锁，收尾 `finally` 恢复本脚本拥有的全部变异并逐字核验。冻结 passed 数与 test nodeid 集合漂移 SHALL ABORT；不得把全仓长期 dirty 误称为基线失败，也不得盲目覆盖外部并发编辑。
7. THE 变异检验 SHALL 在判 GREEN 前读回确认变异已落盘。
8. THE 守卫 SHALL 断言两宿主都接上新增三类，并以真实生产 Type_Hint / DTO 形状到达。
9. THE 守卫 SHALL 从每个宿主挂载后的完整 render tree 观察遍历、外层族门控与行内字段嵌套；遍历可位于共享子组件，不得错误要求宿主源码自身含 `v-for`。

### Requirement 9: 交付物入库与遗留登记

**User Story:** 作为项目维护者，我需要守卫和脚本真进版本库，并把顺带发现的既有缺陷登记下来。

#### Acceptance Criteria

1. THE 交付 SHALL 逐项核对本 spec 全部产物的版本库跟踪状态，未跟踪项不得被宣称完成。
2. WHEN 守卫挂入 CI，THE 被引用路径 SHALL 在版本库中存在且已跟踪。
3. THE CI 改动 SHALL 按本 spec 追加字节区间归因，不以其他并发 job 完全不变为判据。
4. THE 交付 SHALL 登记 `xlsx@0.18.5` 原型链污染与正则 DoS 告警及不可信上传字节调用位置，并明确不在本 spec 修复范围。
5. THE 交付 SHALL 登记 `AttachmentHub.vue` 的死 import / `window.open` 待办，并明确不在本 spec 修复范围。
6. THE 交付 SHALL 登记两宿主并存的维护成本与收敛建议，本 spec 不执行 legacy 宿主合并。
7. THE 会话产生的临时诊断产物 SHALL 在收口前按归属清除。
