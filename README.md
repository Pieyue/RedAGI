<div align="center">

# RedAGI — AI Red Team Collaboration System

**An Automated Red Team Penetration Testing Platform Powered by Multi-Agent Collaboration**

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.137+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-blueviolet.svg)](https://langchain-ai.github.io/langgraph/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

[中文文档](./README_CN.md)

</div>

---

**This project is in early development. Features are not yet complete. Contributions, feedback, and suggestions are welcome to help drive the project forward.**

## Introduction

RedAGI is a multi-agent collaborative red team penetration testing system powered by large language models. It simulates real-world red team operations through the autonomous collaboration of five AI Agents — **Leader, Recon, Analysis, Attack, and Report** — completing the full workflow from target reconnaissance to report generation.

Users simply provide a mission objective, and the system automatically orchestrates four phases: reconnaissance, analysis, attack, and reporting. Agents communicate asynchronously via a message queue, share intelligence through a blackboard system, and ultimately produce a structured, professional red team engagement report.

## Core Features

### Multi-Agent Collaboration System

| Agent | Role | Responsibilities |
|-------|------|------------------|
| **Leader** | Commander | Task planning, delegation, progress tracking, mission termination |
| **Recon** | Scout | Information gathering, port scanning, service identification, asset discovery |
| **Analysis** | Analyst | Vulnerability analysis, attack surface assessment, attack plan design |
| **Attack** | Attacker | Exploitation, privilege acquisition, evidence collection |
| **Report** | Reporter | Report compilation and generation |

### Toolchain Integration

- **Cyberspace Mapping**: QiAnXin Hunter API integration for passive asset discovery
- **Kali Linux Remote Control**: SSH connection to Kali containers for executing nmap, Metasploit, and other penetration testing tools
- **Web Search**: Built-in Qwen search and Tavily MCP external search support
- **Blackboard System**: Structured knowledge base for inter-agent intelligence sharing (JSONB storage, GIN indexing)
- **Progress Management**: Leader can create, update, and track multi-step task progress

### Web Application

- **User Authentication**: JWT token-based authentication with multi-user support
- **Multi-Session Management**: Create, switch, and delete multiple independent penetration testing tasks
- **Real-Time Chat**: WebSocket-based live display of Agent conversations and action progress
- **Monitoring Panel**: Right-side panel showing task progress, tool execution logs, Agent dialogues, and blackboard intelligence
- **Dark Theme**: Modern dark UI design with draggable panel resizing
- **Internationalization**: Built-in Chinese and English bilingual support

### System Reliability

- **LangGraph Checkpoint**: PostgreSQL-based Agent state persistence, enabling session recovery after backend restart
- **Message Manager**: Automatic Agent idle detection with timeout alerts to prevent task deadlock
- **Three-Layer Protection**: stop_event signal + state tracking + automatic recovery
- **Tool Call Fault Tolerance**: Automatic retry on empty streams and automatic repair of incomplete tool_calls

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React + Vite)                │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ Sidebar  │  │   ChatArea   │  │    RightPanel      │    │
│  │Sessions  │  │  WebSocket   │  │Progress/Logs/      │    │
│  │  List    │  │              │  │Chat/Blackboard     │    │
│  └──────────┘  └──────────────┘  └────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────┴──────────────────────────────────┐
│                   Backend (FastAPI + Uvicorn)                │
│  ┌────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐    │
│  │  Auth  │ │ Sessions │ │   Chat    │ │   Monitor    │    │
│  │  JWT   │ │  CRUD    │ │ WebSocket │ │Progress/Logs │    │
│  └────────┘ └──────────┘ └───────────┘ └──────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │            Project Manager (Session Lifecycle)        │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │                 Session Instance                  │  │   │
│  │  │  ┌─────────┐ ┌──────────┐ ┌──────────────────┐  │  │   │
│  │  │  │ Message │ │  Agent   │ │   Tool Registry  │  │  │   │
│  │  │  │ Manager │ │ Invoker  │ │ Comms/Map/       │  │  │   │
│  │  │  │         │ │          │ │ Terminal/Board   │  │  │   │
│  │  │  └─────────┘ └──────────┘ └──────────────────┘  │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │  PostgreSQL  │ │  Kali Linux  │ │   LLM API    │
  │  Data Store  │ │ Attack Plat. │ │  Qwen/DS     │
  │  Checkpoint  │ │  SSH Control │ │  + Tavily    │
  └──────────────┘ └──────────────┘ └──────────────┘
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19 + TypeScript + Vite + lucide-react + react-markdown |
| **Backend** | Python 3.13+ / FastAPI / Uvicorn |
| **Agent Framework** | LangChain + LangGraph + LangGraph Checkpoint PostgreSQL |
| **LLM** | Qwen / DeepSeek, with web search support |
| **Database** | PostgreSQL (business data + Agent state persistence) |
| **Remote Execution** | AsyncSSH (connect to Kali Linux container) |
| **Authentication** | JWT (python-jose) + bcrypt + passlib |
| **Search** | Built-in Qwen search / Tavily MCP |
| **Mapping** | QiAnXin Hunter API |

## Project Structure

```
RedAGI/
├── backend/                    # Backend
│   ├── prompt/                 # Agent system prompts
│   │   ├── Leader.txt          # Leader Prompt
│   │   ├── Reconn.txt          # Recon Prompt
│   │   ├── Analysis.txt        # Analysis Prompt
│   │   ├── Attack.txt          # Attack Prompt
│   │   └── Report.txt          # Report Prompt
│   ├── routes/                 # API routes
│   │   ├── auth.py             # Authentication endpoints
│   │   ├── sessions.py         # Session management endpoints
│   │   ├── chat.py             # WebSocket chat endpoints
│   │   └── monitor.py          # Monitoring data endpoints
│   ├── Agents.py               # Agent core logic (Session class, tool definitions)
│   ├── database.py             # Database connection & table initialization
│   ├── project_manager.py      # Session lifecycle management
│   ├── main.py                 # FastAPI entry point
│   ├── auth.py                 # Authentication utilities
│   ├── schemas.py              # Pydantic data models
│   ├── .env                    # Environment variables
│   └── pyproject.toml          # Python dependencies
├── frontend/                   # Frontend
│   ├── src/
│   │   ├── api/                # API client
│   │   ├── components/         # UI components
│   │   ├── pages/              # Pages
│   │   ├── App.tsx             # Router & entry point
│   │   ├── i18n.tsx            # Internationalization
│   │   └── styles.css          # Global styles
│   ├── package.json
│   └── vite.config.ts
└── pyproject.toml              # Root workspace configuration
```

## Deployment

### Prerequisites

- **Python** >= 3.13
- **Node.js** >= 18
- **PostgreSQL** >= 14
- **Kali Linux** container or VM (for attack tool execution)

### 1. Clone the Repository

```bash
git clone https://github.com/Pieyue/RedAGI.git
cd RedAGI
```

### 2. Configure PostgreSQL

```sql
CREATE DATABASE "RedAGI";
```

### 3. Configure Backend

```bash
cd backend

# Install dependencies (using uv)
uv sync

# Or install manually
pip install -r requirements.txt
```

Edit `backend/.env` and configure the following key settings:

```ini
# LLM configuration (each Agent can use a different model independently)
LEADER_BASE_URL=your-llm-url
LEADER_API_KEY=your-api-key
LEADER_MODEL=your-llm-model
# ... same for other Agents

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/RedAGI

# Kali SSH configuration
KALI_HOST=192.168.x.x
KALI_SSH_KEY=<base64-encoded SSH private key>

# QiAnXin Hunter cyberspace mapping (optional)
HUNTER_API_KEY=your-hunter-key

# Web search (optional, required for DeepSeek models)
TAVILY_MCP_URL=your-tavily-mcp-url
TAVILY_API_KEY=your-tavily-key

# Web application
JWT_SECRET=your-jwt-secret
DEFAULT_USER=your-username
DEFAULT_PASS=your-password
```

### 4. Start Backend

```bash
cd backend
python main.py
```

The backend runs on `http://127.0.0.1:8000` by default.

### 5. Build & Start Frontend

```bash
cd frontend

# Install dependencies
npm install

# Development mode
npm run dev

# Or build for production
npm run build
```

The frontend dev server runs on `http://localhost:5173` by default.

### 6. Access the System

Open your browser and navigate to the frontend URL. Log in using the credentials configured in the `.env` file.

## Usage Workflow

1. **Create Task**: Click "New Task", enter a task title and penetration testing target
2. **Auto Execution**: Leader automatically orchestrates the task, dispatching Recon → Analysis → Attack → Report in sequence
3. **Real-Time Monitoring**: View Agent conversations in the chat area, and check progress, logs, and intelligence in the right panel
4. **Get Report**: After the Report Agent completes, retrieve the full red team report from the `/root/report/` directory on the Kali container

## Legal Disclaimer

> **IMPORTANT: This project is intended solely for security research, authorized penetration testing, and educational training.**

1. **Authorization Required**: Before using this system to conduct penetration testing on any target, you **MUST** obtain explicit written authorization from the target system owner. Unauthorized attacks on computer systems are illegal.

2. **Use Restrictions**: This system must not be used for any illegal purposes, including but not limited to: unauthorized system intrusion, data theft, service disruption, malware distribution, etc.

3. **Liability Disclaimer**: This software is provided "as is". The authors shall not be liable for any direct, indirect, incidental, special, or consequential damages arising from the use or inability to use this software. Users assume all risks and legal responsibilities associated with using this system.

4. **Compliance**: Users must ensure their actions comply with all applicable laws and regulations in their jurisdiction.

5. **AI-Generated Content**: This system uses large language models to drive Agent behavior. AI-generated content may contain inaccuracies or errors. Users should independently verify all outputs and should not rely solely on AI outputs as a single source of truth.

6. **Tool Risks**: The system executes actual penetration testing commands through Kali Linux. Certain operations may impact target systems. Users should fully understand the risks of executed commands and operate in a controlled environment.

## Roadmap

1. Study existing multi-agent automated penetration testing systems and academic papers to explore best practices for multi-agent collaboration.
2. Strengthen security by containerizing the frontend, backend, database, and Kali host into Docker containers, with IP whitelisting to safeguard system access.
3. Add SMS / email verification code functionality.
4. Introduce new Agents (reverse engineering, summarization, image recognition, etc.) to assist in red team operations.
5. Conduct extensive testing to ensure system stability.

## License

This project is open-sourced under the [MIT License](./LICENSE).
