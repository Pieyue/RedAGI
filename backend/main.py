"""RedAGI AI 红队系统 —— FastAPI 主入口"""

import os
import sys
import asyncio
from contextlib import asynccontextmanager

# ⚠️ 必须在导入任何异步库之前设置事件循环策略（Windows 兼容 psycopg3）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from dotenv import load_dotenv

load_dotenv()

from database import init_global_checkpointer, close_global_checkpointer, init_app_tables, get_global_db_conn
from auth import hash_password
from project_manager import shutdown_all

from routes.auth import router as auth_router
from routes.sessions import router as sessions_router
from routes.chat import router as chat_router
from routes.monitor import router as monitor_router


async def _create_default_user():
    """创建默认用户（admin / admin123）"""
    try:
        async with get_global_db_conn().cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE username = 'admin'")
            existing = await cur.fetchone()
            if not existing:
                default_user = os.getenv("DEFAULT_USER", "admin")
                default_pass = os.getenv("DEFAULT_PASS", "admin123")
                hashed = hash_password(default_pass)
                await cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                    (default_user, hashed),
                )
                await get_global_db_conn().commit()
                print(f"[Info] 默认用户 {default_user} 已创建")
    except Exception as e:
        print(f"[Error] 创建默认用户失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("=" * 50)
    print("[Info] RedAGI 后端启动中...")

    # 初始化数据库
    await init_global_checkpointer()
    await init_app_tables()

    # 创建默认用户
    await _create_default_user()

    print("[Info] 后端启动完成，等待请求...")
    print("=" * 50)

    yield

    # 关闭时清理
    print("[Info] 正在关闭 RedAGI 后端...")
    await shutdown_all()
    await close_global_checkpointer()
    print("[Info] 后端已关闭")


app = FastAPI(
    title="RedAGI AI Red Team System",
    description="多 Agent 协作 AI 红队系统后端 API",
    version="0.1.0",
    lifespan=lifespan,
)


# ── 统一 CORS 中间件：OPTIONS 直接返回 200，非 OPTIONS 也附加 CORS 头 ──
class CORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("Origin", "*")

        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        # 所有响应都附加 CORS 头
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response


app.add_middleware(CORSMiddleware)

# 注册路由
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(monitor_router)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "RedAGI Backend"}


if __name__ == "__main__":
    import uvicorn
    # Windows 下必须使用 asyncio 事件循环（兼容 psycopg3）
    if sys.platform == "win32":
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True, loop="asyncio")
    else:
        uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
