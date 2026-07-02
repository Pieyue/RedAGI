# RedAGI — AI 红队协作系统

<div align="center">

**基于多 Agent 协作的自动化红队渗透测试平台**

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.137+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-blueviolet.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

</div>

---
**当前项目处于开发初期阶段，功能尚不完善，欢迎各界人士提供宝贵意见和建议，共同推动项目发展。**
## 项目介绍

RedAGI 是一个基于大语言模型的多 Agent 协作红队渗透测试系统。系统模拟真实红队行动流程，通过 **Leader（领队）、Recon（侦察）、Analysis（分析）、Attack（攻击）、Report（报告）** 五个 AI Agent 的自主协作，完成从目标侦察到报告生成的全流程自动化渗透测试。

用户只需提供任务目标，系统即可自动编排侦察、分析、攻击、报告四个阶段，各 Agent 通过消息队列进行异步通讯，借助黑板系统共享情报，最终输出结构化的专业红队行动报告。

## 核心功能

### 多 Agent 协作体系

| Agent | 角色 | 职责 |
|-------|------|------|
| **Leader** | 领队/总指挥 | 任务规划、分配、进度跟踪、行动终止 |
| **Recon** | 侦察员 | 信息收集、端口扫描、服务识别、资产发现 |
| **Analysis** | 分析师 | 漏洞分析、攻击面评估、攻击方案设计 |
| **Attack** | 攻击者 | 漏洞利用、权限获取、证据收集 |
| **Report** | 报告员 | 行动报告整理与生成 |

### 工具链集成

- **网络空间测绘**：集成奇安信 Hunter API，支持被动资产发现
- **Kali Linux 远程控制**：通过 SSH 连接 Kali 容器，执行 nmap、Metasploit 等渗透测试工具
- **联网搜索**：支持通义千问内置搜索及 Tavily MCP 外部搜索
- **黑板系统**：Agent 间共享情报的结构化知识库（支持 JSONB 存储、GIN 索引）
- **进度管理**：Leader 可创建、更新、追踪多步骤任务进度

### Web 应用

- **用户认证**：JWT 令牌认证，支持多用户
- **多会话管理**：支持创建、切换、删除多个独立渗透任务
- **实时聊天**：通过 WebSocket 实时展示 Agent 对话与行动进展
- **监控面板**：右侧面板展示任务进度、工具执行记录、Agent 对话、黑板情报
- **深色主题**：现代化深色 UI 设计，支持拖拽调整面板宽度
- **国际化**：内置中英文双语支持

### 系统可靠性

- **LangGraph Checkpoint**：基于 PostgreSQL 的 Agent 状态持久化，支持后端重启后恢复会话
- **消息管理器**：自动检测 Agent 空闲状态，超时提醒防止任务卡死
- **三层防护机制**：stop_event 停止信号 + 状态追踪 + 自动恢复
- **工具调用容错**：空流自动重试、未完成 tool_calls 自动修复

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React + Vite)                │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ Sidebar  │  │   ChatArea   │  │    RightPanel      │    │
│  │ 会话列表  │  │  WebSocket   │  │ 进度/日志/对话/黑板 │    │
│  └──────────┘  └──────────────┘  └────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────┴──────────────────────────────────┐
│                   Backend (FastAPI + Uvicorn)                │
│  ┌────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐    │
│  │  Auth  │ │ Sessions │ │   Chat    │ │   Monitor    │    │
│  │  JWT   │ │  CRUD    │ │ WebSocket │ │  进度/日志    │    │
│  └────────┘ └──────────┘ └───────────┘ └──────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Project Manager (Session 生命周期)        │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │                 Session 实例                      │  │   │
│  │  │  ┌─────────┐ ┌──────────┐ ┌──────────────────┐  │  │   │
│  │  │  │ Message │ │  Agent   │ │   Tool Registry  │  │  │   │
│  │  │  │ Manager │ │ Invoker  │ │ 通讯/测绘/终端/黑板│  │  │   │
│  │  │  └─────────┘ └──────────┘ └──────────────────┘  │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │  PostgreSQL  │ │  Kali Linux  │ │   LLM API    │
  │  数据存储    │ │  攻击平台    │ │  通义千问/DS  │
  │  Checkpoint  │ │  SSH 控制    │ │  + Tavily    │
  └──────────────┘ └──────────────┘ └──────────────┘
```

### 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | React 19 + TypeScript + Vite + lucide-react + react-markdown |
| **后端** | Python 3.13+ / FastAPI / Uvicorn |
| **Agent 框架** | LangChain + LangGraph + LangGraph Checkpoint PostgreSQL |
| **LLM** | 通义千问 (Qwen) / DeepSeek，支持联网搜索 |
| **数据库** | PostgreSQL（业务数据 + Agent 状态持久化） |
| **远程执行** | AsyncSSH（连接 Kali Linux 容器） |
| **认证** | JWT (python-jose) + bcrypt + passlib |
| **搜索** | 通义千问内置搜索 / Tavily MCP |
| **测绘** | 奇安信 Hunter API |

## 项目结构

```
RedAGI/
├── backend/                    # 后端
│   ├── prompt/                 # Agent 系统提示词
│   │   ├── Leader.txt          # 领队 Prompt
│   │   ├── Reconn.txt          # 侦察 Prompt
│   │   ├── Analysis.txt        # 分析 Prompt
│   │   ├── Attack.txt          # 攻击 Prompt
│   │   └── Report.txt          # 报告 Prompt
│   ├── routes/                 # API 路由
│   │   ├── auth.py             # 认证接口
│   │   ├── sessions.py         # 会话管理接口
│   │   ├── chat.py             # WebSocket 聊天接口
│   │   └── monitor.py          # 监控数据接口
│   ├── Agents.py               # Agent 核心逻辑（Session 类、工具定义）
│   ├── database.py             # 数据库连接与表初始化
│   ├── project_manager.py      # Session 生命周期管理
│   ├── main.py                 # FastAPI 主入口
│   ├── auth.py                 # 认证工具函数
│   ├── schemas.py              # Pydantic 数据模型
│   ├── .env                    # 环境变量配置
│   └── pyproject.toml          # Python 依赖
├── frontend/                   # 前端
│   ├── src/
│   │   ├── api/                # API 客户端
│   │   ├── components/         # UI 组件
│   │   ├── pages/              # 页面
│   │   ├── App.tsx             # 路由与入口
│   │   ├── i18n.tsx            # 国际化
│   │   └── styles.css          # 全局样式
│   ├── package.json
│   └── vite.config.ts
└── pyproject.toml              # 根目录工作区配置
```

## 部署方法

### 环境要求

- **Python** >= 3.13
- **Node.js** >= 18
- **PostgreSQL** >= 14
- **Kali Linux** 容器或虚拟机（用于攻击工具执行）

### 1. 克隆项目

```bash
git clone <repository-url>
cd RedAGI
```

### 2. 配置 PostgreSQL

```sql
CREATE DATABASE "RedAGI";
```

### 3. 配置后端

```bash
cd backend

# 安装依赖（使用 uv）
uv sync

# 或手动安装
pip install -r requirements.txt
```

编辑 `backend/.env` 文件，配置以下关键项：

```ini
# LLM 配置（每个 Agent 可独立配置不同模型）
LEADER_BASE_URL=https://api.deepseek.com
LEADER_API_KEY=your-api-key
LEADER_MODEL=deepseek-chat
# ... 其他 Agent 同理

# 数据库
DATABASE_URL=postgresql://user:password@localhost:5432/RedAGI

# Kali SSH 配置
KALI_HOST=192.168.x.x
KALI_SSH_KEY=<base64 编码的 SSH 私钥>

# 奇安信Hunter网络空间测绘（可选）
HUNTER_API_KEY=your-hunter-key

# 联网搜索（可选，DeepSeek 模型需要）
TAVILY_MCP_URL=your-tavily-mcp-url
TAVILY_API_KEY=your-tavily-key

# Web 应用
JWT_SECRET=your-jwt-secret
DEFAULT_USER=your-username
DEFAULT_PASS=your-password
```

### 4. 启动后端

```bash
cd backend
python main.py
```

后端默认运行在 `http://127.0.0.1:8000`

### 5. 构建并启动前端

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev

# 或构建生产版本
npm run build
```

前端开发服务器默认运行在 `http://localhost:5173`

### 6. 访问系统

打开浏览器访问前端地址，使用.env文件中的用户名和密码登录

## 使用流程

1. **创建任务**：点击新建任务，输入任务标题和渗透测试目标
2. **自动执行**：Leader 自动编排任务，依次调度 Recon → Analysis → Attack → Report
3. **实时监控**：通过聊天区域查看 Agent 对话，右侧面板查看进度、日志和情报
4. **获取报告**：Report Agent 完成后，在 Kali 容器 `/root/report/` 目录下获取完整红队报告

## 法律与免责声明

> **重要提示：本项目仅供安全研究、授权渗透测试和教育培训使用。**

1. **授权要求**：使用本系统对任何目标进行渗透测试前，**必须**获得目标系统所有者的明确书面授权。未经授权对计算机系统发起攻击属于违法行为。

2. **用途限制**：本系统不得用于任何非法目的，包括但不限于：未授权的系统入侵、数据窃取、服务中断、恶意软件传播等。

3. **责任免除**：本软件按"原样"提供，作者不对因使用或无法使用本软件所造成的任何直接、间接、附带、特殊或后果性的损害承担责任。使用者需自行承担使用本系统的一切风险和法律责任。

4. **合规性**：使用者应确保其行为符合所在国家/地区的所有适用法律法规。

5. **AI 生成内容**：本系统使用大语言模型驱动 Agent 行为，AI 生成的内容可能存在不准确或错误的情况。使用者应独立验证所有输出的准确性，不应将 AI 输出作为唯一依据。

6. **工具风险**：系统通过 Kali Linux 执行实际渗透测试命令，某些操作可能对目标系统造成影响。使用者应充分理解所执行命令的风险，并在可控环境中运行。

## 许可证

本项目采用 [MIT License](./LICENSE) 开源。
