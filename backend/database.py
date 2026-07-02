import os
import sys
import asyncio
import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

load_dotenv()

if sys.platform == "win32":
    # Windows 下使用 SelectorEventLoop 以兼容 psycopg
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 全局数据库连接池（供所有Project实例共享）
_global_checkpointer = None
_global_checkpointer_manager = None
_global_db_conn = None  # 全局原始数据库连接（用于直接执行SQL）


async def init_global_checkpointer():
    """
    初始化全局checkpointer连接池和原始数据库连接
    应在程序启动时调用一次，所有Project实例共享此连接
    """
    global _global_checkpointer, _global_checkpointer_manager, _global_db_conn
    if _global_checkpointer is not None:
        return _global_checkpointer

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL 未配置，请在 backend/.env 中设置有效的 PostgreSQL 连接字符串")

    # 1. 初始化原始数据库连接（用于执行自定义SQL）
    _global_db_conn = await psycopg.AsyncConnection.connect(database_url)
    # 启用 autocommit：每条 SQL 自动提交，避免失败事务污染后续请求
    await _global_db_conn.set_autocommit(True)
    print("[Info] 全局数据库原始连接已建立（autocommit 模式）")

    # 2. 初始化LangGraph checkpointer（内部会复用连接或创建新连接）
    _global_checkpointer_manager = AsyncPostgresSaver.from_conn_string(database_url)
    _global_checkpointer = await _global_checkpointer_manager.__aenter__()
    await _global_checkpointer.setup()
    print("[Info] 全局数据库连接池已初始化")

    return _global_checkpointer


async def close_global_checkpointer():
    """
    关闭全局checkpointer连接池和原始数据库连接
    应在程序结束时调用
    """
    global _global_checkpointer, _global_checkpointer_manager, _global_db_conn

    # 关闭原始数据库连接
    if _global_db_conn:
        await _global_db_conn.close()
        _global_db_conn = None
        print("[Info] 全局数据库原始连接已关闭")

    # 关闭checkpointer管理器
    if _global_checkpointer_manager:
        await _global_checkpointer_manager.__aexit__(None, None, None)
        _global_checkpointer = None
        _global_checkpointer_manager = None
        print("[Info] 全局数据库连接池已关闭")


def get_global_checkpointer():
    """获取全局checkpointer实例"""
    return _global_checkpointer


def get_global_db_conn():
    """获取全局原始数据库连接（使用前会清理可能存在的失败事务）"""
    return _global_db_conn


async def safe_db_cursor():
    """
    获取数据库游标，自动清理可能存在的失败事务。
    """
    if _global_db_conn is not None:
        try:
            await _global_db_conn.rollback()
        except Exception:
            pass
    return _global_db_conn.cursor()


async def init_database_tables(session_id: str):
    """
    初始化数据库表结构（使用全局数据库连接）
    :param session_id: 会话ID
    """
    if _global_db_conn is None:
        raise RuntimeError("全局数据库连接未初始化，请先调用 init_global_checkpointer()")
    try:
        async with _global_db_conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS command_history(
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    agent_name VARCHAR(255) NOT NULL,
                    command TEXT NOT NULL,
                    result TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS progress(
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    num INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT NOT NULL,
                    status VARCHAR(255) NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (session_id, num)
                );
                CREATE TABLE IF NOT EXISTS blackboard (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    agent_name VARCHAR(255) NOT NULL,
                    category VARCHAR(50) NOT NULL,      -- 信息类型
                    title VARCHAR(255) NOT NULL,        -- 简短标题
                    content JSONB NOT NULL,              -- 详细内容(JSON格式更灵活)
                    priority VARCHAR(20) DEFAULT 'medium', -- 优先级: low/medium/high/critical
                    status VARCHAR(20) DEFAULT 'active',   -- 状态: active/verified/used/archived
                    related_target VARCHAR(255),        -- 关联目标(IP/域名)
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 创建索引提高查询效率
                CREATE INDEX IF NOT EXISTS idx_blackboard_session ON blackboard(session_id);
                CREATE INDEX IF NOT EXISTS idx_blackboard_category ON blackboard(category);
                CREATE INDEX IF NOT EXISTS idx_blackboard_status ON blackboard(status);
                CREATE INDEX IF NOT EXISTS idx_blackboard_target ON blackboard(related_target);
                CREATE INDEX IF NOT EXISTS idx_blackboard_content_gin ON blackboard USING GIN (content);
            """)
            await _global_db_conn.commit()

            # 迁移：为已有表添加 UNIQUE 约束（如果尚未添加）
            # 先检查约束是否已存在
            await cur.execute("""
                SELECT COUNT(*) FROM pg_constraint 
                WHERE conname = 'uq_progress_session_num'
            """)
            constraint_exists = (await cur.fetchone())[0] > 0
            if not constraint_exists:
                # 清理重复数据：按 session_id 分组，对重复的 num 重新编号
                await cur.execute("""
                    SELECT id, session_id, num FROM progress 
                    ORDER BY session_id, id
                """)
                rows = await cur.fetchall()
                # 按 session_id 分组，检测并修复重复 num
                from collections import defaultdict
                session_nums = defaultdict(list)  # session_id -> [(id, num)]
                for r_id, r_sid, r_num in rows:
                    session_nums[r_sid].append((r_id, r_num))
                
                for sid, entries in session_nums.items():
                    seen_nums = set()
                    duplicates = []
                    for entry_id, entry_num in entries:
                        if entry_num in seen_nums:
                            duplicates.append(entry_id)
                        else:
                            seen_nums.add(entry_num)
                    # 为重复记录重新分配序号
                    if duplicates:
                        max_num = max(n for _, n in entries)
                        for dup_id in duplicates:
                            max_num += 1
                            await cur.execute(
                                "UPDATE progress SET num = %s WHERE id = %s",
                                (max_num, dup_id)
                            )
                
                # 添加 UNIQUE 约束
                await cur.execute(
                    "ALTER TABLE progress ADD CONSTRAINT uq_progress_session_num UNIQUE (session_id, num)"
                )
                print("[Info] progress 表已添加 UNIQUE(session_id, num) 约束")
            await _global_db_conn.commit()
        print(f"[Info] Session {session_id} 数据库表初始化完成")
    except Exception as e:
        print(f"[Error] 数据库表初始化失败: {e}")
        try:
            await _global_db_conn.rollback()
        except Exception:
            pass
        raise


async def init_app_tables():
    """
    初始化Web应用层的数据库表（用户、会话、消息、Agent日志）
    应在程序启动时调用一次
    """
    if _global_db_conn is None:
        raise RuntimeError("全局数据库连接未初始化，请先调用 init_global_checkpointer()")
    try:
        statements = [
            # 用户表
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # 会话表
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR(36) PRIMARY KEY,
                user_id INT REFERENCES users(id),
                title VARCHAR(500) NOT NULL,
                status VARCHAR(20) DEFAULT 'idle',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # 聊天消息表
            """
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(36) REFERENCES sessions(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL,
                agent_name VARCHAR(50),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Agent调用日志表
            """
            CREATE TABLE IF NOT EXISTS agent_logs (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(36) REFERENCES sessions(id) ON DELETE CASCADE,
                agent_name VARCHAR(50) NOT NULL,
                action VARCHAR(50) NOT NULL,
                summary TEXT,
                detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Agent间对话记录表
            """
            CREATE TABLE IF NOT EXISTS agent_messages (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL,
                from_agent VARCHAR(50) NOT NULL,
                to_agent VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                msg_type VARCHAR(20) NOT NULL DEFAULT 'request',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_logs_session ON agent_logs(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_messages_session ON agent_messages(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_messages_from ON agent_messages(from_agent)",
            "CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON agent_messages(to_agent)",
        ]
        async with _global_db_conn.cursor() as cur:
            for stmt in statements:
                await cur.execute(stmt)
            await _global_db_conn.commit()
        print("[Info] 应用层数据库表初始化完成")
    except Exception as e:
        print(f"[Error] 应用层数据库表初始化失败: {e}")
        raise
