# 底稿 HTML ↔ 在线编辑切换提速 — Requirements

> spec 名：`workpaper-sync-switch-performance`（2026-10-11 新建，上游 = `d2-online-edit-platform-closure` 9/9）
> 范围：平台同步引擎（所有企业、所有走 `useWorkpaperSyncBridge` 的宿主共用），D2 为验收样本。
> 铁律：**不砍任何校验**（roundtrip 等值 / 未管理区域 / structure_hash / identity / fence 全保留）；
> 快路径只跳过「可证明不会改变结果」的重复计算。

## 背景（全部为 2026-10-11 现场实测，D2 和平药房 741 行 / 28,708 字段）

| 场景 | 现在 | 主要耗时 |
|---|---|---|
| OO 没改动 → 回 HTML | ≈0.6 s | 已经很快 |
| HTML 没改动 → 进 OO（复用命中时） | ≈9 s | 浏览器先 GET 整份投影再原样 POST 回去（≈7~8 s）服务端才能判「没变」 |
| HTML 没改动 → 进 OO（刚从 OO 保存回来） | ≈16~25 s | 复用判据被摘要抖动打穿，走全量物化（9~15 s） |
| HTML 改过 → 进 OO | ≈16~25 s | 取投影 + 待提交 + 全量物化 + 编辑器加载 |
| OO 改过并保存 → 回 HTML | ≈20~26 s | 落盘 1~2 s；其余 16~23 s 是三方提取/合并/写回/校验/镜像，前端全程等 |

根因证据（逐值比对相邻版本的 projection 落盘工件）：

- **摘要抖动**：和平药房 rev46(OO)→rev47(HTML)、重药安徽 rev14→rev15 等每一对，业务字段 **0 处差异**；
  差的全是模板骨架行（`GTROW-*`）：和平药房 D2-3 坏账表 8 行 26 字段（24 个公式 0 值 + 2 个「其中：」标签），
  重药安徽另加 D2-2 明细 12 行共 86 字段；且和平药房 D2-2 两侧都有的 12 行骨架行**位置不同**
  （OO 物理序在表头 0~11，store 序在表尾 729~740；HTML 全量物化后 OO 侧仍在表头 ⇒ materialize 不按投影序搬骨架行）。
  ⇒ `_find_business_identity_reuse`（要求 `projection_sha256` 逐字节相等）永不命中，判词还被记成 `miss_content_changed`（归因错误）。
- **浏览器往返**：store-projection 本就是服务端从库里算出来的，却下载到浏览器再原样 POST 回 pending-mutations。
- **重复提取**：OO→HTML 三方提取 base / current / incoming 各一次整册 extract（单次约 3 s），单人编辑时 base 与 current 是同一文件；
  上一次物化校验时已提取过同一份字节，结果没复用。
- **单进程**：start-dev 与 docker-compose 均 1 个 uvicorn worker；CPU 段在线程里跑受 GIL 限制，批量同步无法并行且拖慢其他请求。

## 需求 1（P0）：分阶段计时可观测

1.1 OO→HTML 每次 apply 输出一行结构化计时（各 ApplyStage 相邻耗时 + 总耗时），不改变任何阶段顺序与判据。
1.2 HTML→OO 每次 materialize（含新端点）输出一行结构化计时（注册 / preflight / 复用判定 / 提交 CPU 段 / 开房间 / 总计）。
1.3 前端桥在一次切换内记录各段耗时（冲刷待写、取投影或服务端直取、物化、编辑器挂载、就绪、确认），以只读 `switchTimings` 暴露。
1.4 提供正式工具按底稿列出最近若干次切换的端到端耗时（读事件表，只读），用于回归对比。

## 需求 2（P1）：消除摘要抖动 —— 业务身份按「骨架无关」口径比较

2.1 HTML→OO 复用判定在逐字节摘要未命中时，按**骨架无关业务身份**再判一次：
    非骨架行的行序与全部值严格比较；HTML 侧声明了的骨架行按集合 + 值比较（与位置无关）；HTML 侧未声明的骨架行连同其值不参与比较。
2.2 命中即走既有复用路径（零 revision、复用当前 representation 与 room），判词为 `hit` 并在 differences 里注明「骨架行等价」；
    未命中时既有归因逻辑不变。
2.3 不改任何已落盘摘要（`projection_sha256` / pending digest / settlement digest 口径一字不动）；不改 extract / materialize / roundtrip 判据。
2.4 判定为纯函数，平台级（对所有 store 型 entry 生效，无 entry 特例）；配合成样本单测 + 变异 + 真库两家企业相邻版本对拍。

## 需求 3（P2 + P5）：服务端直取投影 + 无改动直通

3.1 新增写端点 `POST …/materialize-from-store`：服务端自己读 store、构造投影（与 store-projection 同一实现）、建 pending mutation 并物化，
    响应与 `/materialize` 同形（同一 `_attach_launch_urls`）；浏览器不再下载、上传整份投影。
3.2 服务端按「store 原始载荷 + 契约 canonical 摘要 + adapter」计算指纹；一次成功物化（提交或复用）后记录「指纹 ↔ 当前 content version」。
    下次请求指纹与 content version 都相同 ⇒ 跳过投影构造、待提交、物化，直接复用当前 representation 开/复用 room 并返回 descriptor（零 revision）。
3.3 指纹记录存进程内有界 LRU（重启/发版即清空，多 worker 各自独立 —— 未命中只是回落正常路径，不影响正确性）。
3.4 前端桥对**所有**宿主自动生效、宿主零改动：桥在调用宿主 `flushHtml()` 期间拦截同 scope 的 `readStoreProjection`
    （返回服务端直取占位，不发请求）；宿主若改写了投影或该 entry 不是 store 型，回落原客户端路径（正确性优先）。
    R20 的「先冲刷待写再取数」顺序保持不变。
3.5 首版发布（R7）、409/422 拒绝码、幂等键、工作流锁定（写 action）语义与原路径一致；端点级测试真发请求（含 401/404/403）。

## 需求 4（P4）：去掉重复提取

4.1 OO→HTML 三方提取：current 与 base 的 artifact sha256 相同时只提取一次（journal 阶段与明细不变）。
4.2 提取结果缓存键补齐为「契约 canonical 摘要 + 提取画像（adapter 构建 / 定义 / binding 序列）+ artifact sha256」；
    物化校验阶段已提取的结果在**发布成功后**写入缓存，供随后的 store-projection / 服务端直取 / 三方提取命中。
4.3 roundtrip 校验本身仍现场提取（不读缓存）；缓存命中结果与冷提取逐字节等价由守卫锁死。

## 需求 5（P3）：OO 保存后先回表单、后台合并

5.1 用户点「保存并回到表单模式」后，incoming 一旦 durable（≈1~2 s）即回到表单；该底稿表单只读并显示「正在合并在线编辑内容」，
    合并完成后原地刷新并解锁；冲突 / 失败在横幅给出裁决 / 重试入口。
5.2 participant 离开改为服务端在 application 终态时自动完成（R19「合并没结束不许离开」规则不变：未终结前不释放）。
5.3 合并期间不得产生 HTML 写入（避免与镜像竞态）；页面离开 / 关闭不丢数据（incoming 已 durable，合并在服务端继续）。

## 需求 6：小项与评估

6.1 页面空闲时预加载 OnlyOffice 脚本（首次切换少一次脚本加载）；P3 落地后取消回表单前的 1.2 s 固定等待。
6.2 P6（同步 CPU 段移到独立进程）只做 ROI 评估写入 design，不实施。
6.3 投影工件名为 `.json.gz` 实为明文（单版 4.3 MB，真压缩约 183 KB）：登记为发现，评估影响面，不在本 spec 改存储格式。

## 验收

- 两家企业（和平药房 / 重药安徽）浏览器实测：回写完成后不再编辑，来回切换进 OO ≤ 5 s（目标 ≈3 s）；OO 保存后感知回表单 ≤ 5 s（P3 后）。
- 每项改动：单元 / 端点 / PG 守卫 + 变异打红；宽回归对基线零新增失败；golden digest 不变；前端失败数 = 基线；行数门通过。
