"""Post-implementation pressure test runner

与 Task 1 使用相同 Locust 脚本 (locustfile_import.py)，
验证实施后的改进效果。

执行方法（需 Docker + 2 个 worker 实例）:
    locust -f tests/load/locustfile_import.py --host=http://localhost:9980

预期结果（实施后）:
  ✅ 同项目并发导入：Redis SET NX EX → 第二个 worker 立即收到 409
     - 验证方法：观测 /import 端点 409 响应比例应接近 50%
  ✅ 地址坐标库缓存踩踏：asyncio.Lock single-flight → DB 查询仅 1 次
     - 验证方法：DB pg_stat_statements 查询 build_workpaper_entries 调用数
  ✅ Web worker 内存：OCR 服务化 → RSS < 200MB
     - 验证方法：docker stats 观测 web worker 容器内存

对比基线：
  - Task 1 运行结果作为基线
  - 本次运行结果对比基线确认改进幅度
  - 如果改进不显著，排查 Redis 连接 / 锁 TTL / single-flight 锁粒度

注意：
  - 实际执行需要完整的 Docker 环境
  - 确保 OCR_SERVICE_URL 已配置指向 ocr-service 容器
  - 确保 Redis 连通且 import_lock:* keys 可写
"""

if __name__ == "__main__":
    print("Post-implementation pressure test")
    print("=" * 60)
    print("请使用以下命令运行 Locust 压测：")
    print()
    print("  locust -f tests/load/locustfile_import.py --host=http://localhost:9980")
    print()
    print("验证清单：")
    print("  1. 同项目并发导入 → 观察 409 响应（Redis 锁互斥）")
    print("  2. 地址坐标库 → pg_stat_statements 查询数 = 1（single-flight）")
    print("  3. Web worker RSS → docker stats < 200MB（OCR 服务化）")
    print("=" * 60)
