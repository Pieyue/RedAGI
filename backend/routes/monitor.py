"""监控路由 —— 任务进度、命令历史、Agent 对话、黑板信息"""

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_global_db_conn
from schemas import (
    MessageResponse,
    ProgressItem,
    CommandHistoryItem,
    AgentMessageItem,
    ToolExecutionItem,
    BlackboardItem,
    AgentStatusItem,
)
from routes.auth import get_current_user
from project_manager import get_project

router = APIRouter(prefix="/api/sessions", tags=["monitor"])


# ── 聊天消息历史 ──────────────────────────────────
@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    """获取指定会话的聊天消息"""
    await _verify_session_owner(session_id, user["user_id"])

    async with get_global_db_conn().cursor() as cur:
        await cur.execute(
            "SELECT id, session_id, role, agent_name, content, created_at "
            "FROM messages WHERE session_id = %s ORDER BY id ASC",
            (session_id,),
        )
        rows = await cur.fetchall()

    return [
        MessageResponse(id=r[0], session_id=r[1], role=r[2], agent_name=r[3], content=r[4], created_at=r[5])
        for r in rows
    ]


# ── 任务进度 ──────────────────────────────────────
@router.get("/{session_id}/progress", response_model=list[ProgressItem])
async def get_progress(session_id: str, user: dict = Depends(get_current_user)):
    """获取任务执行进度"""
    await _verify_session_owner(session_id, user["user_id"])

    async with get_global_db_conn().cursor() as cur:
        await cur.execute(
            "SELECT num, title, description, status, timestamp, updated_at "
            "FROM progress WHERE session_id = %s ORDER BY num ASC",
            (session_id,),
        )
        rows = await cur.fetchall()

    return [
        ProgressItem(num=r[0], title=r[1], description=r[2], status=r[3], timestamp=r[4], updated_at=r[5])
        for r in rows
    ]


# ── 命令历史 ──────────────────────────────────────
@router.get("/{session_id}/command-history", response_model=list[CommandHistoryItem])
async def get_command_history(
    session_id: str,
    agent_name: str | None = Query(None, description="按 Agent 筛选"),
    user: dict = Depends(get_current_user),
):
    """获取命令执行历史"""
    await _verify_session_owner(session_id, user["user_id"])

    query = "SELECT id, agent_name, command, result, timestamp FROM command_history WHERE session_id = %s"
    params = [session_id]

    if agent_name:
        query += " AND agent_name = %s"
        params.append(agent_name)

    query += " ORDER BY id DESC LIMIT 200"

    async with get_global_db_conn().cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()

    results = [
        CommandHistoryItem(id=r[0], agent_name=r[1], command=r[2], result=r[3], timestamp=r[4])
        for r in rows
    ]
    results.reverse()
    return results


# ── Agent 间对话 ──────────────────────────────────
@router.get("/{session_id}/agent-messages", response_model=list[AgentMessageItem])
async def get_agent_messages(
    session_id: str,
    from_agent: str | None = Query(None, description="按发送方筛选"),
    to_agent: str | None = Query(None, description="按接收方筛选"),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    """获取 Agent 间对话记录"""
    await _verify_session_owner(session_id, user["user_id"])

    query = "SELECT id, from_agent, to_agent, content, msg_type, created_at FROM agent_messages WHERE session_id = %s"
    params = [session_id]

    if from_agent:
        query += " AND from_agent = %s"
        params.append(from_agent)
    if to_agent:
        query += " AND to_agent = %s"
        params.append(to_agent)

    query += " ORDER BY id DESC LIMIT %s"
    params.append(limit)

    async with get_global_db_conn().cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()

    results = [
        AgentMessageItem(id=r[0], from_agent=r[1], to_agent=r[2], content=r[3], msg_type=r[4], created_at=r[5])
        for r in rows
    ]
    results.reverse()
    return results


# ── 工具执行记录 ──────────────────────────────────
@router.get("/{session_id}/tool-executions", response_model=list[ToolExecutionItem])
async def get_tool_executions(
    session_id: str,
    agent_name: str | None = Query(None, description="按 Agent 筛选"),
    action: str | None = Query(None, description="按动作类型筛选"),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    """获取工具执行记录"""
    await _verify_session_owner(session_id, user["user_id"])

    query = "SELECT id, agent_name, action, summary, detail, created_at FROM agent_logs WHERE session_id = %s"
    params = [session_id]

    if agent_name:
        query += " AND agent_name = %s"
        params.append(agent_name)
    if action:
        query += " AND action = %s"
        params.append(action)

    query += " ORDER BY id DESC LIMIT %s"
    params.append(limit)

    async with get_global_db_conn().cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()

    results = [
        ToolExecutionItem(id=r[0], agent_name=r[1], action=r[2], summary=r[3], detail=r[4], created_at=r[5])
        for r in rows
    ]
    results.reverse()
    return results


# ── 黑板信息 ──────────────────────────────────────
@router.get("/{session_id}/blackboard", response_model=list[BlackboardItem])
async def get_blackboard(
    session_id: str,
    category: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    """获取黑板共享情报"""
    await _verify_session_owner(session_id, user["user_id"])

    query = "SELECT id, agent_name, category, title, content, priority, status, related_target, created_at FROM blackboard WHERE session_id = %s"
    params = [session_id]

    if category:
        query += " AND category = %s"
        params.append(category)
    if status:
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY priority DESC, created_at DESC LIMIT %s"
    params.append(limit)

    async with get_global_db_conn().cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()

    return [
        BlackboardItem(
            id=r[0], agent_name=r[1], category=r[2], title=r[3],
            content=r[4] if isinstance(r[4], dict) else {},
            priority=r[5], status=r[6], related_target=r[7], created_at=r[8],
        )
        for r in rows
    ]


# ── Agent 状态 ──────────────────────────────────────
@router.get("/{session_id}/agent-status", response_model=list[AgentStatusItem])
async def get_agent_status(session_id: str, user: dict = Depends(get_current_user)):
    """获取 Agent 团队状态（从内存中的 Session 实例读取）"""
    await _verify_session_owner(session_id, user["user_id"])

    project = get_project(session_id)
    if project is None or not project.agents_status:
        return []

    return [
        AgentStatusItem(
            name=name,
            status="busy" if status.is_set() else "idle",
        )
        for name, status in project.agents_status.items()
    ]


# ── 辅助函数 ──────────────────────────────────────
async def _verify_session_owner(session_id: str, user_id: int):
    """验证会话是否属于当前用户"""
    async with get_global_db_conn().cursor() as cur:
        await cur.execute(
            "SELECT user_id FROM sessions WHERE id = %s",
            (session_id,),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    if row[0] != user_id:
        raise HTTPException(status_code=403, detail="无权访问该会话")
