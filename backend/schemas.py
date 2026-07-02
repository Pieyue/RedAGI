"""Pydantic 请求/响应模型"""

from datetime import datetime
from pydantic import BaseModel


# ── 认证 ──────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


# ── 会话 ──────────────────────────────────────────
class SessionCreate(BaseModel):
    title: str


class SessionResponse(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class SessionStatus(BaseModel):
    id: str
    status: str


# ── 聊天消息 ──────────────────────────────────────
class MessageResponse(BaseModel):
    id: int
    session_id: str
    role: str          # "user" / "agent"
    agent_name: str | None
    content: str
    created_at: datetime


class ChatSend(BaseModel):
    content: str


# ── 进度 ──────────────────────────────────────────
class ProgressItem(BaseModel):
    num: int
    title: str
    description: str
    status: str
    timestamp: datetime
    updated_at: datetime | None


# ── 命令历史 ──────────────────────────────────────
class CommandHistoryItem(BaseModel):
    id: int
    agent_name: str
    command: str
    result: str
    timestamp: datetime


# ── Agent 对话 ────────────────────────────────────
class AgentMessageItem(BaseModel):
    id: int
    from_agent: str
    to_agent: str
    content: str
    msg_type: str
    created_at: datetime


# ── 工具执行记录 ──────────────────────────────────
class ToolExecutionItem(BaseModel):
    id: int
    agent_name: str
    action: str
    summary: str | None
    detail: str | None
    created_at: datetime


# ── 黑板 ──────────────────────────────────────────
class BlackboardItem(BaseModel):
    id: int
    agent_name: str
    category: str
    title: str
    content: dict
    priority: str
    status: str
    related_target: str | None
    created_at: datetime


# ── Agent 状态 ──────────────────────────────────────
class AgentStatusItem(BaseModel):
    name: str
    status: str  # "busy" / "idle"


# ── 通用 ──────────────────────────────────────────
class ErrorResponse(BaseModel):
    detail: str
