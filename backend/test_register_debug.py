import asyncio
from app.core.database import async_session
from app.models.core import User
from app.schemas.auth import UserCreate
from app.models.base import UserRole
from app.services.auth_service import create_user

async def test_register():
    db = async_session()
    try:
        user_data = UserCreate(
            username='testuser999',
            email='test999@example.com',
            password='test123456',
            role=UserRole.auditor
        )
        result = await create_user(user_data, db)
        print('Success:', result)
    except Exception as e:
        print(f'Error: {type(e).__name__}: {str(e)}')
        import traceback
        traceback.print_exc()
    finally:
        await db.close()

if __name__ == '__main__':
    asyncio.run(test_register())
