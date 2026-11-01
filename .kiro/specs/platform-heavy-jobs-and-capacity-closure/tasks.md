# 平台重任务、交互性能与容量闭环 — 任务

完成必须有代码和对应测试/现场证据；外部环境项保持 `[ ]*`。

## 批 0 基线与观测

- [ ] 0.1 固化当前 production build、核心页面、重任务、连接池与事件循环基线。
- [ ] 0.2 增加 pool checkout wait/hold/timeout、event-loop lag、任务 queue age 与 Office/OCR/LLM 排队指标。
  - 已完成：DB pool wait/hold/timeout、event-loop lag、LibreOffice 与 bulk import 深度/年龄；待 OCR、LLM slot、AI durable queue 统一暴露。
- [ ] 0.3 建立不会写共享 PG 的性能测试选择器与专用数据库硬闸门。

## 批 A 事件循环与文件内存止血

- [ ] A1 Ledger preview 解析移到受控线程；文件数、总字节、sheet、preview_rows 有硬上限和真实进度。
  - 已完成：线程隔离、文件/总字节/sheet/preview_rows 上限、CSV 有界缓冲、复杂大表禁止 full mode；待把服务端解析进度改为可恢复任务。
- [x] A2 批量导出一次取元数据，在线程直接写临时 ZIP 后原子改名；无 BytesIO 双份驻留。
- [x] A3 前端底稿批量下载切异步任务、展示真实进度/失败/下载，不再同步等待整包。
- [x] A4 bulk import 先落 spool，只传路径；增加全局/用户/项目并发与内存预算。
- [x] A5 LibreOffice 唯一 profile、communicate、排队上限/acquire timeout、Retry-After 与指标。
- [ ] A6 流式下载提前释放 DB，会话与文件句柄在取消时及时关闭。
  - 已完成：附件、底稿 ZIP、bulk SSE/下载、chain/ledger SSE、doc AI 外层 session；待治理其余 FileResponse 及 wp_chat 生成器内 session。
- [x] A7 同输入验证文件 SHA/ZIP 清单/导入摘要不变，并测并发时 health/event-loop lag。

## 批 B 耐久任务

- [ ] B1 设计并迁移公共 durable job/job attempt，V/R 成对且动态取号。
- [ ] B2 实现 claim/lease/heartbeat/fence/retry/cancel/idempotency 与恢复 worker。
- [ ] B3 迁移底稿导出与 bulk import；旧内存任务只作兼容读并设退役日期。
- [ ] B4 迁移公式推送、附注批量 AI、合并重新汇总；按阶段发 typed SSE。
- [ ] B5 前端统一任务状态组件，断线后从状态端点恢复。
- [ ] B6 kill/reload/重复提交/租约过期故障注入证明零重复副作用。

## 批 C 批量 SQL 与重计算

- [ ] C1 公式推送现状 statement counter 与 10/1000/10000 单元基线。
  - 已完成：adapter 级 10/1000/10000 计数守卫；现为固定 3 次 cursor execute，待专用 PG 环境记录旧/新完整 run 基线。
- [ ] C2 目标底稿批取、mutation 批量 CAS、附注按章节一次锁写；逐项结果对拍。
  - 已完成：目标底稿单次批取、同底稿 mutation 一次锁读 + 批量 CAS；待附注按章节一次锁写与真实 PG 并发 barrier。
- [ ] C3 合并附注一次预取记录/公式、内存后序、批量写；修正空 section_ids 语义。
  - 已完成：空数组零工作、记录一次预取、全局/项目公式各一次查询、聚合内存后序与章节统一 flush；待叶子来源整章批取和差额纯内存内核。
- [ ] C4 Ledger 导入分阶段 profiler；COPY/staging/set-based 合并把真实大项目目标压到 5 分钟内。
- [ ] C5 知识词法/向量路径真实 EXPLAIN 与量级基准；按证据实施索引/pgvector。

## 批 D 前端大表与请求反馈

- [ ] D1 TB 1000/5000 行虚拟化 canary，保持编辑、选区、右键、注释、公式和可访问性。
  - 现有 GtVirtualTable 不支持离屏逻辑选区/编辑，未在交互契约齐全前冒险切生产路径。
- [x] D2 TrialBalance 全表 deep watch 改行级增量重算。
- [ ] D3 附注与合并表按 canary 结果接虚拟化；活动格才挂编辑器。
- [ ] D4 披露自动同步改 revision/patch 单飞 + latest pending，失败可见且可重试。
- [x] D5 HTTP `_background` 不驱动全局 NProgress；无幂等键的写请求不自动重试。
- [ ] D6 大 GET/保存热路径减少 clone/stringify；用 1/10/50MB 夹具记录长任务和 heap。
  - 已完成：普通 JSON 写请求只 stringify 一次、完整正文指纹、single-flight follower 优先单次 structuredClone、TB debounce 到 drain 才冻结；待 1/10/50MB 浏览器 heap/long-task 现场证据。
- [ ] D7 内网 HTTP 多标签 SSE 围栏选主；1/6/12 标签始终单项目一条连接。

## 批 E 容量架构

- [ ] E1 PgBouncer transaction 模式契约与 2%→25%→100% 灰度脚本；连接预算按副本计算。
- [ ] E2 EventBus、任务、配额、进度和失效状态外置；2/4/8 worker 零丢失/零重复验证。
- [x] E3 修正 Locust UUID/信封/账号池/端点；6000 阶段无样本强制 FAIL。
- [ ] E4 构建可销毁大数据容量环境与分布式负载机。
- [ ]* E5 100→1000→3000→6000 VU，6000 稳态 30 分钟；提交原始 CSV/JSON/摘要。
- [ ]* E6 达成核心读 p95≤300ms、p99≤1s、核心错误率<0.1%，零泄露/超时/事件丢失/数据损坏。

## 收尾

- [ ] F1 相关测试、正式构建、包体预算、Playwright、PG 计划和故障注入全通过。
- [ ] F2 更新 6000 前置文档，勘误历史零样本假绿，不改 append-only 历史记录。
- [ ] F3 更新 INDEX/memory；只提交本任务 owned 文件。