"""Session 生命周期管理器 —— 创建、查找、销毁 Session 实例"""

import asyncio
from Agents import Session
from database import get_global_db_conn, get_global_checkpointer, safe_db_cursor


# { session_id -> Session }
_projects: dict[str, Session] = {}

# 所有 Agent 名称（用于清理 checkpointer 中的 thread）
_AGENT_NAMES = ["leader", "recon", "analysis", "attack", "report"]


def get_project(session_id: str) -> Session | None:
    """根据 session_id 获取已存在的 Session 实例"""
    return _projects.get(session_id)


async def ensure_project(session_id: str) -> Session | None:
    """
    获取或重建 Session 实例，用于后端重启后恢复会话。
    - 如果内存中已有实例，直接返回
    - 如果 DB 中有该会话记录，自动重建 Session
    - 如果 DB 中也无记录，返回 None
    """
    # 内存中已有，直接返回
    if session_id in _projects:
        return _projects[session_id]

    # 检查数据库中有没有这个会话
    try:
        cur = await safe_db_cursor()
        async with cur:
            await cur.execute("SELECT id, status FROM sessions WHERE id = %s", (session_id,))
            row = await cur.fetchone()
    except Exception as e:
        print(f"[Warn] ensure_project 查询会话失败: {e}")
        return None

    if row is None:
        return None  # DB 中也没有，确实是新会话

    # DB 中有记录但内存中丢失 → 重建 Session
    print(f"[Info] 恢复会话 {session_id}（后端重启后自动重建）")
    try:
        return await create_project(session_id)
    except Exception as e:
        print(f"[Error] 恢复会话 {session_id} 失败: {e}")
        # 清理无法恢复的孤立会话
        try:
            cur = await safe_db_cursor()
            async with cur:
                await cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
            print(f"[Info] 已清理无法恢复的孤立会话 {session_id}")
        except Exception:
            pass
        return None


async def create_project(session_id: str, is_restore: bool = False, was_running: bool = True) -> Session:
    """
    创建一个新的 Session 实例并完成异步初始化
    stop_event 默认为 set（停止状态），由 chat.py 在用户发消息时 clear 并启动消息管理器
    """
    if session_id in _projects:
        return _projects[session_id]

    project = Session(session_id)
    await project.initialize()

    _projects[session_id] = project
    print(f"[Info] Session {session_id} 已创建并初始化（stop_event 默认已设置）")
    return project


async def _cleanup_session_data(session_id: str):
    """
    删除会话相关的所有数据库记录，包括：
    - 业务表：command_history, progress, blackboard, agent_logs, agent_messages, messages
    - LangGraph checkpointer 表：checkpoints, checkpoint_writes, checkpoint_blobs
    """
    try:
        cur = await safe_db_cursor()
        async with cur:
            await cur.execute("DELETE FROM command_history WHERE session_id = %s", (session_id,))
            await cur.execute("DELETE FROM progress WHERE session_id = %s", (session_id,))
            await cur.execute("DELETE FROM blackboard WHERE session_id = %s", (session_id,))
            await cur.execute("DELETE FROM agent_logs WHERE session_id = %s", (session_id,))
            await cur.execute("DELETE FROM agent_messages WHERE session_id = %s", (session_id,))
            await cur.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
        print(f"[Info] 会话 {session_id} 的业务数据已清理")

        cur = await safe_db_cursor()
        async with cur:
            for agent_name in _AGENT_NAMES:
                thread_id = f"{session_id}_{agent_name}"
                await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
                await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
                await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
        print(f"[Info] 会话 {session_id} 的 checkpointer 数据已清理")
    except Exception as e:
        print(f"[Error] 清理会话 {session_id} 数据失败: {e}")
        try:
            await get_global_db_conn().rollback()
        except Exception:
            pass


async def destroy_project(session_id: str):
    """关闭并移除 Session 实例，同时清理数据库"""
    project = _projects.pop(session_id, None)
    if project is None:
        return

    try:
        project.stop_event.set()
        await asyncio.sleep(1)
        await project.close()
    except Exception as e:
        print(f"[Warn] Session {session_id} 关闭异常: {e}")

    await _update_session_status(session_id, "stopped")
    await _cleanup_session_data(session_id)
    print(f"[Info] Session {session_id} 已销毁")


async def stop_project_task(session_id: str) -> bool:
    """
    停止 Session 的任务执行（用户主动终止，强制停止）
    :return: 是否成功
    """
    project = _projects.get(session_id)
    if project is None:
        return False
    await project._stop_task(force=True)
    return True


async def _update_session_status(session_id: str, status: str):
    """更新数据库中的会话状态"""
    try:
        cur = await safe_db_cursor()
        async with cur:
            await cur.execute(
                "UPDATE sessions SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, session_id),
            )
    except Exception as e:
        print(f"[Warn] 更新会话状态失败: {e}")


async def shutdown_all():
    """
    程序退出时优雅关闭所有 Session（仅关闭连接，不删除数据库数据）
    destroy_project 会删除数据库数据，仅应在用户主动删除会话时调用
    """
    for sid in list(_projects.keys()):
        project = _projects.pop(sid, None)
        if project is None:
            continue
        try:
            project.stop_event.set()
            await asyncio.sleep(0.5)
            await project.close()
        except Exception as e:
            print(f"[Warn] 关闭 Session {sid} 异常: {e}")
        try:
            await _update_session_status(sid, "stopped")
        except Exception:
            pass
        print(f"[Info] Session {sid} 已关闭（数据已保留）")
