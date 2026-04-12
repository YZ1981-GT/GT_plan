import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def reset_database():
    """Drop existing enum types to allow fresh migration"""
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform')
    
    # List of enum types to drop (from migration files)
    enum_types = [
        'user_role',
        'project_type', 
        'project_status',
        'project_user_role',
        'permission_level',
        'account_direction',
        'account_category',
        'account_source',
        'mapping_type',
        'adjustment_type',
        'review_status',
        'import_status',
        'misstatement_type',
        'report_type',
        'report_line_mapping_type',
        'consol_method',
        'elimination_entry_type',
        'component_status',
        'evaluation_status',
        'forex_method',
        'financial_report_type',
    ]
    
    async with engine.begin() as conn:
        for enum_type in enum_types:
            try:
                await conn.execute(text(f"DROP TYPE IF EXISTS {enum_type} CASCADE"))
                print(f"Dropped enum type: {enum_type}")
            except Exception as e:
                print(f"Failed to drop {enum_type}: {e}")
        
        # Drop all tables
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        print("Reset schema public")
    
    await engine.dispose()
    print("Database reset complete")

if __name__ == '__main__':
    asyncio.run(reset_database())
