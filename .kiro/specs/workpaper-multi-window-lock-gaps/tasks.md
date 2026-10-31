# 底稿多窗口编辑锁两处漏洞收口 — 任务

> spec: `workpaper-multi-window-lock-gaps`

- [x] 1. 窗口编号认领（R1.1 / R1.2 / R1.5，D1 / D1b）：`clientInstance.ts` 新增 `claimClientInstanceId()`（Web Locks 认领、被占换号、不可用保留）；不提供 Web Locks 时 localStorage 登记（页面隐藏注销、往返缓存恢复重登、被丢弃后重载认回）；生成编号改用 `newUuid`；单测覆盖复制标签页换号、刷新保留、opener、非安全上下文（13 例）
- [x] 2. 认领接线（R1.3 / R1.4，D2 / D3）：`main.ts` 启动认领；`useEditingLock.acquire / forceAcquire` 等认领；`crossWindowAuth` 按当前编号比较；单测
- [x] 3. 写请求带窗口编号（R2.6，D5）：`http.ts` 非 GET 请求加头；`WorkpaperWordEditor` 导入原生请求加头；单测
- [x] 4. 前端只读拦截（R2.1 / R2.2，D6）：`GtWpToolbar` readonly、`GtWpRenderer` 传入并拦导入、Word「导入数据」只读禁用；单测
- [x] 5. 后端内容写入校验编辑锁（R2.3 / R2.4 / R2.5，D4）：`find_blocking_lock` + `dedicated_wp_gate` 接入；单测覆盖持锁人 / 同人他窗 / 他人 / 无锁 / 过期 / 非内容路由 / GET（14 例）
- [x] 6. 浏览器实测（【测试】公式同步乙有限公司_2025 · D4，自起无头 Chrome）：`http://127.0.0.1:3030`（安全上下文）与 `http://192.168.20.60:3030`（非安全上下文，无 Web Locks / `crypto.randomUUID`）各一轮，共 34 项全过 —— 复制标签页换新编号、只读横幅、导入 / 增行禁用、锁表只有原窗口一行；复制窗口直接 PUT `checklist-responses` 与 POST `d4/import-data` 均 423「你的另一个窗口」，持锁窗口 200 / 过门禁（缺文件 422）；关掉复制窗口原锁仍在；刷新原窗口编号不变、仍可编辑；离开后锁释放
- [x] 7. 回归与提交：主工作区相关前端 26 文件 150 过、4 红（与 HEAD 同：authTokenSingleSource / rawRequestAuth 违规集合不变、GtWpRuntimeBoundary.pbt 2 例换回 HEAD 版渲染器同红）；提交树（HEAD + 本 spec）干净检出：前端 25 文件 137 过、4 例 + 1 文件失败与 HEAD 逐条相同，门禁相关既有后端 251 例 248 过、3 红与 HEAD 相同（G11 页签集合、F2 AI 生成 503），新增后端 14 过；变异前端 F1~F21、后端 B1~B4 全红在预期断言、阴性对照全绿；单区域 vue-tsc 改动文件 0 新增（阳性对照报 TS2322）；只提交本 spec 文件（`main.ts` / `http.ts` / INDEX 按「HEAD + 本 spec 改动块」暂存）
