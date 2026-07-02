"""WebSocket 聊天路由 —— 用户与 Leader Agent 实时对话"""

import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from database import get_global_db_conn
from project_manager import ensure_project
from langchain.messages import HumanMessage, SystemMessage

router = APIRouter()


async def _update_session_status(session_id: str, status: str):
    """更新数据库中的会话状态"""
    try:
        async with get_global_db_conn().cursor() as cur:
            await cur.execute(
                "UPDATE sessions SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (status, session_id),
            )
            await get_global_db_conn().commit()
    except Exception as e:
        print(f"[Warn] 更新会话状态失败: {e}")


async def _save_user_message(session_id: str, content: str):
    """保存用户消息到数据库"""
    try:
        async with get_global_db_conn().cursor() as cur:
            await cur.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (%s, 'user', %s) RETURNING id",
                (session_id, content),
            )
            await get_global_db_conn().commit()
    except Exception as e:
        print(f"[Warn] 保存用户消息失败: {e}")


async def _save_agent_message(session_id: str, agent_name: str, content: str):
    """保存 Agent 回复到数据库"""
    try:
        async with get_global_db_conn().cursor() as cur:
            await cur.execute(
                "INSERT INTO messages (session_id, role, agent_name, content) VALUES (%s, 'agent', %s, %s)",
                (session_id, agent_name, content),
            )
            await get_global_db_conn().commit()
    except Exception as e:
        print(f"[Warn] 保存 Agent 消息失败: {e}")


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(ws: WebSocket, session_id: str):
    """
    WebSocket 聊天端点。
    客户端发送: {"content": "..."}
    服务端回复: {"type": "response", "content": "..."} 或 {"type": "error", "content": "..."}
    服务端通知: {"type": "status", "status": "running"|"stopped"}
    """
    await ws.accept()

    async def _safe_send(data: dict):
        """安全发送 JSON，忽略客户端已断开的情况"""
        try:
            await ws.send_json(data)
        except WebSocketDisconnect:
            pass

    async def _safe_close():
        """安全关闭连接"""
        try:
            await ws.close()
        except Exception:
            pass

    # 验证 JWT 令牌（从查询参数获取）
    token = ws.query_params.get("token")
    if not token:
        await _safe_send({"type": "error", "content": "缺少认证令牌"})
        await _safe_close()
        return
    try:
        from auth import decode_access_token
        payload = decode_access_token(token)
    except Exception:
        await _safe_send({"type": "error", "content": "无效的认证令牌"})
        await _safe_close()
        return

    # Agent 团队延迟初始化：用户首次发消息时才创建
    project = None
    leader = None

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            content = data.get("content", "").strip()
            if not content:
                await ws.send_json({"type": "error", "content": "消息不能为空"})
                continue

            # 用户首次发消息时才初始化 Agent 团队
            if project is None:
                project = await ensure_project(session_id)
                if project is None:
                    await ws.send_json({"type": "error", "content": "会话初始化失败，请删除该会话后重新创建"})
                    continue

                leader = project.agents.get("leader")
                if leader is None:
                    await ws.send_json({"type": "error", "content": "Leader Agent 未就绪"})
                    continue

                # 注册广播回调：Agent 间对话也推送到前端聊天区
                async def broadcast_agent_message(agent_name: str, content: str):
                    try:
                        await _save_agent_message(session_id, agent_name, content)
                        await ws.send_json({"type": "agent_message", "agent": agent_name, "content": content})
                    except Exception:
                        pass

                project.set_broadcast_callback(broadcast_agent_message)

                # 首次初始化：启动消息管理器（Agent 间消息路由）
                project.stop_event.clear()
                project.start_message_manager()
                await _update_session_status(session_id, "running")
                await ws.send_json({"type": "status", "status": "running"})

            # 如果任务已停止（用户停止后重新发消息），恢复运行
            if project.stop_event.is_set():
                # 重新初始化 Kali SSH 连接（stop_task 会关闭它们）
                try:
                    await project.init_kali_terminal()
                except Exception as e:
                    print(f"[Warn] 重新初始化 Kali 终端失败: {e}")

                project.stop_event.clear()
                project.start_message_manager()
                await _update_session_status(session_id, "running")
                await ws.send_json({"type": "status", "status": "running"})
                
                # 为未完成的 tool_calls 添加响应，避免 API 报错（保留所有历史记忆）
                try:
                    config = {"configurable": {"thread_id": f"{session_id}_leader"}}
                    state = await leader.aget_state(config)
                    if state and state.values.get("messages"):
                        messages = list(state.values["messages"])
                        from langchain.messages import AIMessage, ToolMessage
                        last_msg = messages[-1] if messages else None
                        if isinstance(last_msg, AIMessage) and hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                            # 为每个未完成的 tool_call 添加中断响应
                            tool_responses = []
                            for tc in last_msg.tool_calls:
                                tool_responses.append(
                                    ToolMessage(
                                        content="工具执行已被用户中断",
                                        tool_call_id=tc.get("id", "")
                                    )
                                )
                            updated_messages = messages + tool_responses
                            await leader.aupdate_state(config, {"messages": updated_messages})
                            print(f"[Info] 为 {len(tool_responses)} 个 tool_calls 添加了中断响应")
                except Exception as e:
                    print(f"[Warn] 处理 tool_calls 失败: {e}")

            # 保存用户消息
            await _save_user_message(session_id, content)

            # 发送运行状态
            await ws.send_json({"type": "status", "status": "running"})

            # 将用户消息包装成 JSON 格式，与 Agent 间消息格式保持一致
            user_message_json = json.dumps({
                "From": "User",
                "content": content
            }, ensure_ascii=False)
            
            messages = [HumanMessage(content=user_message_json)]

            # 调用 Leader Agent
            config = {"configurable": {"thread_id": f"{session_id}_leader"}}

            # 标记 Leader 为忙碌状态（供团队面板显示）
            project.agents_status["leader"].set()
            try:
                response = await leader.ainvoke(
                    {"messages": messages},
                    config=config,
                )

                # 提取 AIMessage 文本
                response_text = ""
                for msg in reversed(response.get("messages", [])):
                    from langchain.messages import AIMessage
                    if not isinstance(msg, AIMessage):
                        continue
                    c = getattr(msg, "content", "") or ""
                    if isinstance(c, str) and c.strip():
                        response_text = c
                        break
                    elif isinstance(c, list):
                        for block in c:
                            if isinstance(block, dict) and block.get("type") == "text":
                                t = block.get("text", "")
                                if isinstance(t, str) and t.strip():
                                    response_text = t
                                    break
                        if response_text:
                            break

                if response_text:
                    await _save_agent_message(session_id, "leader", response_text)
                    await ws.send_json({"type": "response", "content": response_text})
                else:
                    await ws.send_json({"type": "response", "content": "(Leader 未返回文本内容)"})

            except ValueError as e:
                if "No generations found in stream" in str(e):
                    await ws.send_json({"type": "error", "content": "Leader 响应流为空，请重试"})
                else:
                    await ws.send_json({"type": "error", "content": f"调用 Leader 失败: {e}"})
            except Exception as e:
                await ws.send_json({"type": "error", "content": f"调用 Leader 失败: {e}"})
            finally:
                # 无论成功或失败，都清除忙碌状态
                project.agents_status["leader"].clear()

            # 检查任务状态
            if project.stop_event.is_set():
                await _update_session_status(session_id, "stopped")
                await ws.send_json({"type": "status", "status": "stopped"})

    except WebSocketDisconnect:
        print(f"[Info] WebSocket 断开: session={session_id}")
    except Exception as e:
        print(f"[Error] WebSocket 异常: {e}")
        try:
            await ws.send_json({"type": "error", "content": f"服务异常: {e}"})
        except Exception:
            pass
