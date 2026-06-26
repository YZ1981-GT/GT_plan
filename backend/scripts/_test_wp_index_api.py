"""测试 /wp-index API 是否正常返回"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import ASGITransport, AsyncClient
from app.main import app
from app.core.security import create_access_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def test():
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2)
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT id FROM users WHERE username='admin' LIMIT 1"))
        user_id = str(r.scalar())
    await engine.dispose()

    token = create_access_token({"sub": user_id, "type": "access"})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/projects/0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49/wp-index",
            headers=headers,
        )
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            print(f"Items count: {len(items)}")
            # Show first 3
            for item in items[:3]:
                print(f"  {item.get('wp_code'):12s} id={item.get('id','?')[:12]}... wp_index_id={item.get('wp_index_id','?')[:12]}...")
        else:
            print(f"Error: {resp.text[:500]}")

asyncio.run(test())
