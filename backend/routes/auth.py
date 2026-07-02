"""认证路由 —— 登录、令牌刷新"""

import os
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth import (
    verify_password,
    create_access_token,
    decode_access_token,
)
from database import get_global_db_conn
from schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """从 JWT 令牌中解析当前用户，所有受保护接口共用此依赖"""
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="无效的认证令牌")
    user_id = payload.get("user_id")
    username = payload.get("username")
    if not user_id or not username:
        raise HTTPException(status_code=401, detail="令牌格式无效")
    return {"user_id": user_id, "username": username}


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """用户登录，返回 JWT 访问令牌"""
    async with get_global_db_conn().cursor() as cur:
        await cur.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (req.username,),
        )
        row = await cur.fetchone()

    if not row or not verify_password(req.password, row[2]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user_id, username = row[0], row[1]
    token = create_access_token({"user_id": user_id, "username": username})
    return TokenResponse(access_token=token, user_id=user_id, username=username)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(user: dict = Depends(get_current_user)):
    """刷新 JWT 令牌"""
    token = create_access_token({"user_id": user["user_id"], "username": user["username"]})
    return TokenResponse(access_token=token, user_id=user["user_id"], username=user["username"])
