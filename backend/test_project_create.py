import asyncio
import httpx

async def test_project_create():
    async with httpx.AsyncClient() as client:
        # Login
        login_resp = await client.post(
            "http://localhost:8000/api/auth/login",
            json={"username": "testuser888", "password": "test123456"}
        )
        login_data = login_resp.json()
        print("Login response:", login_data)
        
        if login_data.get("code") != 200:
            print("Login failed")
            return
        
        token = login_data["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create project
        project_resp = await client.post(
            "http://localhost:8000/api/projects",
            headers=headers,
            json={
                "client_name": "Test Client",
                "audit_year": 2025,
                "project_type": "annual",
                "accounting_standard": "enterprise"
            }
        )
        print("Project create response:", project_resp.json())

if __name__ == '__main__':
    asyncio.run(test_project_create())
