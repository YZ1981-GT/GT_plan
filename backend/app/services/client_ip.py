"""客户端 IP 提取（V274 抽出，audit_log 中间件与 auth_service 共用）

优先 X-Forwarded-For 第一跳（经 Nginx 代理时为真实客户端），
回退 ASGI 连接对端地址；无连接信息返回 None。
"""


def extract_client_ip(headers, client=None) -> str | None:
    """从请求头 / 连接对象提取客户端 IP。

    ``headers``：支持 Starlette Headers 或任何 ``get(key)`` 大小写不敏感的映射；
    ``client``：``request.client``（有 ``host`` 属性）或 None。
    """
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For 格式: client, proxy1, proxy2 —— 第一跳是客户端
        return forwarded.split(",")[0].strip() or None
    if client is not None and getattr(client, "host", None):
        return client.host
    return None
