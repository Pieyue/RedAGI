"""会话管理路由"""

from langchain_core.utils.uuid import uuid7

from fastapi import APIRouter, HTTPException, Depends

from database import get_global_db_conn, safe_db_cursor
from project_manager import stop_project_task, destroy_project
from schemas import SessionCreate, SessionResponse, SessionStatus
from routes.auth import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionResponse])
async def list_sessions(user: dict = Depends(get_current_user)):
    """获取当前用户的所有会话（按更新时间倒序）"""
    cur = await safe_db_cursor()
    async with cur:
        await cur.execute(
            "SELECT id, title, status, created_at, updated_at "
            "FROM sessions WHERE user_id = %s ORDER BY updated_at DESC",
            (user["user_id"],),
        )
        rows = await cur.fetchall()

    return [
        SessionResponse(id=r[0], title=r[1], status=r[2], created_at=r[3], updated_at=r[4])
        for r in rows
    ]


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(req: SessionCreate, user: dict = Depends(get_current_user)):
    """创建新会话（仅建 DB 记录，Agent 团队在用户首次发消息时初始化）"""
    session_id = str(uuid7())

    cur = await safe_db_cursor()
    async with cur:
        await cur.execute(
            "INSERT INTO sessions (id, user_id, title, status) VALUES (%s, %s, %s, 'idle')",
            (session_id, user["user_id"], req.title),
        )

    # 获取最终状态
    cur = await safe_db_cursor()
    async with cur:
        await cur.execute(
            "SELECT id, title, status, created_at, updated_at FROM sessions WHERE id = %s",
            (session_id,),
        )
        row = await cur.fetchone()

    return SessionResponse(id=row[0], title=row[1], status=row[2], created_at=row[3], updated_at=row[4])


@router.delete("/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    """删除会话并销毁 Project"""
    cur = await safe_db_cursor()
    async with cur:
        await cur.execute(
            "SELECT id FROM sessions WHERE id = %s AND user_id = %s",
            (session_id, user["user_id"]),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="会话不存在")

    await destroy_project(session_id)

    cur = await safe_db_cursor()
    async with cur:
        await cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))

    return {"detail": "会话已删除"}


@router.post("/{session_id}/stop")
async def stop_session(session_id: str, user: dict = Depends(get_current_user)):
    """停止会话的任务执行"""
    cur = await safe_db_cursor()
    async with cur:
        await cur.execute(
            "SELECT id FROM sessions WHERE id = %s AND user_id = %s",
            (session_id, user["user_id"]),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="会话不存在")

    success = await stop_project_task(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="会话未处于运行状态")

    return {"detail": "任务已停止"}
