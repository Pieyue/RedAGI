import os
import json
import httpx
import base64
import asyncio
import asyncssh
from psycopg.types.json import Jsonb
from asyncio import Event, Queue
from asyncssh.connection import SSHClientConnection
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from langchain.messages import SystemMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langchain_core.utils.uuid import uuid7
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from database import (
    get_global_checkpointer,
    get_global_db_conn,
    init_global_checkpointer,
    init_database_tables,
)
def _get_model_configs():
    """ 获取模型配置 """
    model_configs = {}
    need_web_search = False
    # 获取领队模型配置
    LEADER_BASE_URL = os.getenv("LEADER_BASE_URL")
    LEADER_API_KEY = os.getenv("LEADER_API_KEY")
    LEADER_MODEL = os.getenv("LEADER_MODEL")
    SYSTEM_PROMPT = open("prompt/Leader.txt", 'r', encoding="utf-8").read()
    EXTRA_BODY, SEARCH_TOOLS = _set_extra_body_and_check_search(LEADER_MODEL)
    if not SEARCH_TOOLS:
        need_web_search =  True
    model_configs["leader"] = {"base_url": LEADER_BASE_URL, "api_key": LEADER_API_KEY, "model": LEADER_MODEL, "system_prompt": SYSTEM_PROMPT, "extra_body": EXTRA_BODY, "search_tools": SEARCH_TOOLS}

    # 获取侦察配置
    RECON_BASE_URL = os.getenv("RECON_BASE_URL")
    RECON_API_KEY = os.getenv("RECON_API_KEY")
    RECON_MODEL = os.getenv("RECON_MODEL")
    SYSTEM_PROMPT = open("prompt/Reconn.txt", 'r', encoding="utf-8").read()
    EXTRA_BODY, SEARCH_TOOLS = _set_extra_body_and_check_search(RECON_MODEL)
    if not SEARCH_TOOLS:
        need_web_search = True
    model_configs["recon"] = {"base_url": RECON_BASE_URL, "api_key": RECON_API_KEY, "model": RECON_MODEL, "system_prompt": SYSTEM_PROMPT, "extra_body": EXTRA_BODY, "search_tools": SEARCH_TOOLS}

    # 获取分析配置
    ANALYSIS_BASE_URL = os.getenv("ANALYSIS_BASE_URL")
    ANALYSIS_API_KEY = os.getenv("ANALYSIS_API_KEY")
    ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL")
    SYSTEM_PROMPT = open("prompt/Analysis.txt", 'r', encoding="utf-8").read()
    EXTRA_BODY, SEARCH_TOOLS = _set_extra_body_and_check_search(ANALYSIS_MODEL)
    if not SEARCH_TOOLS:
        need_web_search = True
    model_configs["analysis"] = {"base_url": ANALYSIS_BASE_URL, "api_key": ANALYSIS_API_KEY, "model": ANALYSIS_MODEL, "system_prompt": SYSTEM_PROMPT, "extra_body": EXTRA_BODY, "search_tools": SEARCH_TOOLS}

    # 获取攻击配置
    ATTACK_BASE_URL = os.getenv("ATTACK_BASE_URL")
    ATTACK_API_KEY = os.getenv("ATTACK_API_KEY")
    ATTACK_MODEL = os.getenv("ATTACK_MODEL")
    SYSTEM_PROMPT = open("prompt/Attack.txt", 'r', encoding="utf-8").read()
    EXTRA_BODY, SEARCH_TOOLS = _set_extra_body_and_check_search(ATTACK_MODEL)
    if not SEARCH_TOOLS:
        need_web_search = True
    model_configs["attack"] = {"base_url": ATTACK_BASE_URL, "api_key": ATTACK_API_KEY, "model": ATTACK_MODEL, "system_prompt": SYSTEM_PROMPT, "extra_body": EXTRA_BODY, "search_tools": SEARCH_TOOLS}

    # 获取报告配置
    REPORT_BASE_URL = os.getenv("REPORT_BASE_URL")
    REPORT_API_KEY = os.getenv("REPORT_API_KEY")
    REPORT_MODEL = os.getenv("REPORT_MODEL")
    SYSTEM_PROMPT = open("prompt/Report.txt", 'r', encoding="utf-8").read()
    EXTRA_BODY, SEARCH_TOOLS = _set_extra_body_and_check_search(REPORT_MODEL)
    if not SEARCH_TOOLS:
        need_web_search = True
    model_configs["report"] = {"base_url": REPORT_BASE_URL, "api_key": REPORT_API_KEY, "model": REPORT_MODEL, "system_prompt": SYSTEM_PROMPT, "extra_body": EXTRA_BODY, "search_tools": SEARCH_TOOLS}

    return model_configs, need_web_search

def _set_extra_body_and_check_search(model_name):
    """ 设置额外请求体并检查是否需要联网搜索 """
    # 判断模型厂商
    if model_name.startswith("qwen"):
        # 如果是通义千问，内置联网搜索功能，添加工具参数就行
        extra_body = {"enable_thinking":True}
        search_tools = {"type": "web_search"}
        return extra_body, search_tools
    else:
        # 如果是deepseek，没有内置联网搜索功能，需要使用Tavily
        extra_body = {"thinking": {"type": "enabled"}}
        if not os.getenv("TAVILY_MCP_URL") or not os.getenv("TAVILY_API_KEY"):
            print(f"\033[91m警告：模型 {model_name} 没有内置联网搜索功能，且TAVILY_MCP_URL或TAVILY_API_KEY未配置，将无法使用联网搜索功能\033[0m")
        return extra_body, None


class Session:
    def __init__(self, session_id):
        self.session_id: str = session_id                             # 会话 ID
        self.stop_event = Event()                                     # 任务停止标志
        self.stop_event.set()                                         # 默认停止状态，用户发消息时 clear
        self.message_queue = Queue(maxsize=100)                       # 消息队列
        self._tool_use_event = Event()                                # 创建一个事件,用于记录工具使用
        self.agents: dict[str, CompiledStateGraph] = {}               # 存储所有agents
        self.agents_status: dict[str, Event] = {}                     # 存储所有agents状态
        self.kali_conn: dict[str, SSHClientConnection] = {}           # 存储所有kali连接,用于在任务结束时关闭
        self.checkpointer = None                                      # checkpointer将在异步初始化时设置
        self._broadcast_callback = None                               # Agent消息广播回调: async fn(agent_name, content)

        ####################### 初始化工具-START #######################
        #### 通讯工具-START ####
        self.send_message_leader_tool = StructuredTool.from_function(
            name="send_message", coroutine=self._send_message_leader
        )
        self.send_message_recon_tool = StructuredTool.from_function(
            name="send_message", coroutine=self._send_message_recon
        )
        self.send_message_analysis_tool = StructuredTool.from_function(
            name="send_message", coroutine=self._send_message_analysis
        )
        self.send_message_attack_tool = StructuredTool.from_function(
            name="send_message", coroutine=self._send_message_attack
        )
        self.send_message_report_tool = StructuredTool.from_function(
            name="send_message", coroutine=self._send_message_report
        )
        #### 通讯工具-END ####
        # 网络空间测绘工具
        self.network_mapping_tool = StructuredTool.from_function(
            name="network_mapping", coroutine=self._network_mapping
        )

        #### kali控制工具-START ####
        # 为每个Agent创建独立的命令执行工具
        self.exec_kali_command_leader_tool = StructuredTool.from_function(
            name="exec_kali_command", coroutine=self._exec_kali_command_leader
        )
        self.exec_kali_command_recon_tool = StructuredTool.from_function(
            name="exec_kali_command", coroutine=self._exec_kali_command_recon
        )
        self.exec_kali_command_analysis_tool = StructuredTool.from_function(
            name="exec_kali_command", coroutine=self._exec_kali_command_analysis
        )
        self.exec_kali_command_attack_tool = StructuredTool.from_function(
            name="exec_kali_command", coroutine=self._exec_kali_command_attack
        )
        self.exec_kali_command_report_tool = StructuredTool.from_function(
            name="exec_kali_command", coroutine=self._exec_kali_command_report
        )

        # 为每个Agent创建独立的终端重连工具
        self.restart_kali_terminal_leader_tool = StructuredTool.from_function(
            name="restart_kali_terminal", coroutine=self._restart_kali_terminal_leader
        )
        self.restart_kali_terminal_recon_tool = StructuredTool.from_function(
            name="restart_kali_terminal", coroutine=self._restart_kali_terminal_recon
        )
        self.restart_kali_terminal_analysis_tool = StructuredTool.from_function(
            name="restart_kali_terminal", coroutine=self._restart_kali_terminal_analysis
        )
        self.restart_kali_terminal_attack_tool = StructuredTool.from_function(
            name="restart_kali_terminal", coroutine=self._restart_kali_terminal_attack
        )
        self.restart_kali_terminal_report_tool = StructuredTool.from_function(
            name="restart_kali_terminal", coroutine=self._restart_kali_terminal_report
        )

        # 为每个Agent创建独立的历史记录查询工具
        self.get_command_history_leader_tool = StructuredTool.from_function(
            name="get_command_history", coroutine=self._get_command_history_leader
        )
        self.get_command_history_recon_tool = StructuredTool.from_function(
            name="get_command_history", coroutine=self._get_command_history_recon
        )
        self.get_command_history_analysis_tool = StructuredTool.from_function(
            name="get_command_history", coroutine=self._get_command_history_analysis
        )
        self.get_command_history_attack_tool = StructuredTool.from_function(
            name="get_command_history", coroutine=self._get_command_history_attack
        )
        self.get_command_history_report_tool = StructuredTool.from_function(
            name="get_command_history", coroutine=self._get_command_history_report
        )

        #### kali控制工具-END ####

        #### 黑板工具-START ####
        self.write_to_blackboard_tool = StructuredTool.from_function(
            name="write_to_blackboard", coroutine=self._write_to_blackboard
        )
        self.read_blackboard_tool = StructuredTool.from_function(
            name="read_blackboard", coroutine=self._read_blackboard
        )
        self.update_blackboard_tool = StructuredTool.from_function(
            name="update_blackboard", coroutine=self._update_blackboard
        )
        #### 黑板工具-END ####

        #### 进度管理工具-START ####
        self.get_progress_tool = StructuredTool.from_function(
            name="get_progress", coroutine=self._get_progress
        )
        self.manage_progress_tool = StructuredTool.from_function(
            name="manage_progress", coroutine=self._manage_progress
        )
        #### 进度管理工具-END ####

        # 任务停止工具
        self.stop_task_tool = StructuredTool.from_function(
            name="stop_task", coroutine=self._stop_task
        )
        ####################### 初始化工具-END #######################
    
    async def initialize(self):
        """异步初始化方法:使用全局checkpointer、初始化Agents和Kali终端"""
        # 使用全局checkpointer（不单独为每个Project创建连接）
        if get_global_checkpointer() is None:
            raise RuntimeError("请先调用 await init_global_checkpointer() 初始化全局数据库连接")
        self.checkpointer = get_global_checkpointer()

        # 初始化数据库表结构
        await init_database_tables(self.session_id)
            
        # 初始化Agent
        await self._init_agents()
        self.agent_names = set(self.agents.keys())

        # 记录各Agent状态,clear为空闲,set为忙碌,供消息消息管理器等待
        self.agents_status = {name: Event() for name in self.agent_names}

        # 初始化Kali终端
        await self.init_kali_terminal()

    #################### 初始化MCP和Agents ####################
    async def _init_agents(self):
        """ 初始化MCP和Agents """
        model_configs, need_web_search = _get_model_configs()
        agents = {name: None for name in model_configs.keys()}  # {名称: 实例}
        tavily_tools = None
        if need_web_search and os.getenv("TAVILY_MCP_URL") and os.getenv("TAVILY_API_KEY"):
            client = MultiServerMCPClient({
                "tavily": {
                    "url": os.getenv("TAVILY_MCP_URL"),
                    "headers": {"Authorization": f"Bearer {os.getenv('TAVILY_API_KEY')}"},
                    "transport": "http"
                }
            })
            tavily_tools = await client.get_tools()
        for name, config in model_configs.items():
            # 给Agent分配工具
            if name == "leader":
                tools = [
                    self.send_message_leader_tool,
                    self.stop_task_tool,
                    self.manage_progress_tool,
                    self.get_progress_tool,
                    self.write_to_blackboard_tool,
                    self.read_blackboard_tool,
                    self.update_blackboard_tool
                ]
            elif name == "recon":
                tools = [
                    self.send_message_recon_tool,
                    self.network_mapping_tool,
                    self.exec_kali_command_recon_tool,
                    self.get_command_history_recon_tool,
                    self.restart_kali_terminal_recon_tool,
                    self.get_progress_tool,
                    self.write_to_blackboard_tool,
                    self.read_blackboard_tool,
                    self.update_blackboard_tool
                ]
            elif name == "analysis":
                tools = [
                    self.send_message_analysis_tool,
                    self.exec_kali_command_analysis_tool,
                    self.get_command_history_analysis_tool,
                    self.restart_kali_terminal_analysis_tool,
                    self.get_progress_tool,
                    self.write_to_blackboard_tool,
                    self.read_blackboard_tool,
                    self.update_blackboard_tool
                ]
            elif name == "attack":
                tools = [
                    self.send_message_attack_tool,
                    self.exec_kali_command_attack_tool,
                    self.get_command_history_attack_tool,
                    self.restart_kali_terminal_attack_tool,
                    self.get_progress_tool,
                    self.write_to_blackboard_tool,
                    self.read_blackboard_tool,
                    self.update_blackboard_tool
                ]
            elif name == "report":
                tools = [
                    self.send_message_report_tool,
                    self.exec_kali_command_report_tool,
                    self.get_command_history_report_tool,
                    self.restart_kali_terminal_report_tool,
                    self.get_progress_tool,
                    self.write_to_blackboard_tool,
                    self.read_blackboard_tool,
                    self.update_blackboard_tool
                ]
            else:
                raise ValueError(f"未知的Agent名称：{name}")
            # 配置联网搜索工具，每个Agent都应该有
            if config.get("search_tools"):
                # 内置联网搜索的直接启用
                tools.append(config["search_tools"])
            elif tavily_tools is not None:
                # 没有内置联网搜索的，使用Tavily
                tools.extend(tavily_tools)
            agents[name] = self._create_agent(
                base_url=config["base_url"],
                api_key=config["api_key"],
                model=config["model"],
                tools=tools,
                system_prompt=config["system_prompt"],
                extra_body=config["extra_body"],
                name=name
            )
        # 将初始化得到的agents赋给self.agents
        self.agents = agents

    def _create_agent(self, base_url: str, api_key: str, model: str, tools: list, system_prompt: str, extra_body: dict,
                      name: str):
        """ 创建Agent团队 """
        llm = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            extra_body=extra_body,
            streaming=True
        )
        agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=SystemMessage(content=system_prompt),
            name=name,
            checkpointer=self.checkpointer  # 使用PostgreSQL作为检查点
        )
        return agent

    async def close(self):
        """关闭项目:仅关闭Kali连接，不关闭全局数据库连接"""
        # 关闭Kali连接
        for conn in self.kali_conn.values():
            conn.close()
            await conn.wait_closed()
        self.kali_conn.clear()
        print(f"[Info] Project {self.session_id} 已关闭")

    def set_broadcast_callback(self, callback):
        """设置 Agent 消息广播回调，用于 WebSocket 实时推送"""
        self._broadcast_callback = callback

    async def _add_command_history(self, agent_name: str, command: str, result: str):
        """ 添加命令历史记录 """
        if self.stop_event.is_set():
            return  # 任务已停止，跳过数据库写入
        try:
            async with get_global_db_conn().cursor() as cur:
                await cur.execute("""
                    INSERT INTO command_history (session_id, agent_name, command, result)
                    VALUES (%s, %s, %s, %s)
                """, (self.session_id, agent_name, command, result))
                await get_global_db_conn().commit()
        except Exception as e:
            return print(f"[Error] 添加命令历史记录失败: {e}")

    async def _add_tool_execution(self, agent_name: str, action: str, summary: str = None, detail: str = None):
        """ 添加工具执行记录 """
        if self.stop_event.is_set():
            return  # 任务已停止，跳过数据库写入
        try:
            async with get_global_db_conn().cursor() as cur:
                await cur.execute("""
                    INSERT INTO agent_logs (session_id, agent_name, action, summary, detail)
                    VALUES (%s, %s, %s, %s, %s)
                """, (self.session_id, agent_name, action, summary, detail))
                await get_global_db_conn().commit()
        except Exception as e:
            print(f"[Error] 添加工具执行记录失败: {e}")

    async def _save_agent_message(self, from_agent: str, to_agent: str, content: str, msg_type: str):
        """ 保存 Agent 间对话到数据库 """
        if self.stop_event.is_set():
            return  # 任务已停止，跳过数据库写入
        try:
            async with get_global_db_conn().cursor() as cur:
                await cur.execute("""
                    INSERT INTO agent_messages (session_id, from_agent, to_agent, content, msg_type)
                    VALUES (%s, %s, %s, %s, %s)
                """, (self.session_id, from_agent, to_agent, content, msg_type))
                await get_global_db_conn().commit()
        except Exception as e:
            print(f"[Error] 保存 Agent 对话失败: {e}")

    ##################### 工具定义-START ####################
    ######### 消息发送工具-START #########
    # 为每一个Agent创建一个消息发送工具，确保From不会被伪造
    async def _send_message_leader(self, To:str, content: str, type: str):
        """
        通过此工具向其它Agent成员分发任务并进行交流
        将消息投入消息队列，由系统后台管理并发送消息
        本工具是异步的：调用后立即返回"已投递"，对方的回复不会通过本工具返回。回复会作为新消息在稍后自动送达你的下一次唤醒中。如需等待回复，请直接结束当前轮次即可。
        你可以与以下Agent交流：
        recon-侦察员，负责信息收集
        analysis-分析师，分析目标可能存在的漏洞和值得进攻的资产
        attack-攻击者，负责对目标发起攻击
        report-报告撰写员，负责在最后总结任务并生成报告文档
        注意：不能给自己发送消息，不能发送空白消息，To的名字必须严格符合上述名单，From为System的是系统的自动提示，你无需也不能回复
        :param To: 发给谁
        :param content: 要发送的消息
        :param type: 消息类型： request | task_complete | warning
        :return: 投递成功/失败信息
        """
        # 检查是否还有agent正在工作
        for name, agent_status in self.agents_status.items():
            if name != "leader" and agent_status.is_set():
                return f"Error: {name}还没有完成工作，其完成当前任务并回复消息后再发送其它消息。不要违反系统规定，不要跳步，不要幻想不存在的记录。请立刻停止对话轮次以等待。"

        if To == 'report':
            # 检查是否还有 pending 状态的进度
            try:
                async with get_global_db_conn().cursor() as cur:
                    await cur.execute(
                        "SELECT num, title FROM progress WHERE session_id = %s AND status = 'pending'",
                        (self.session_id,)
                    )
                    pending_items = await cur.fetchall()
                if pending_items:
                    pending_list = ", ".join([f"#{item[0]}-{item[1]}" for item in pending_items])
                    return f"Error: 还有未完成的步骤 [{pending_list}] 处于 pending 状态，请先让它们完成后再联系 report 撰写报告。"
            except Exception as e:
                print(f"[Error] 检查 pending 进度失败: {e}")


        return await self._send_message_base("leader", To, content, type)

    async def _send_message_recon(self, To:str, content: str, type: str):
        """
        通过此工具向其它Agent成员通讯
        将消息投入消息队列，由系统后台管理并发送消息
        本工具是异步的：调用后立即返回"已投递"，对方的回复不会通过本工具返回。回复会作为新消息在稍后自动送达你的下一次唤醒中。如需等待回复，请直接结束当前轮次即可。
        你可以与以下Agent交流：
        leader-领队，整个任务总指挥
        analysis-分析师，分析目标可能存在的漏洞和值得进攻的资产
        attack-攻击者，负责对目标发起攻击
        report-报告撰写员，负责在最后总结任务并生成报告文档
        注意：不能给自己发送消息，不能发送空白消息，To的名字必须严格符合上述名单，From为System的是系统的自动提示，你无需也不能回复
        :param To: 发给谁
        :param content: 要发送的消息
        :param type: 消息类型： request | task_complete | warning
        :return: 投递成功/失败信息
        """
        return await self._send_message_base("recon", To, content, type)

    async def _send_message_analysis(self, To:str, content: str, type: str):
        """
        通过此工具向其它Agent成员通讯
        将消息投入消息队列，由系统后台管理并发送消息
        本工具是异步的：调用后立即返回"已投递"，对方的回复不会通过本工具返回。回复会作为新消息在稍后自动送达你的下一次唤醒中。如需等待回复，请直接结束当前轮次即可。
        你可以与以下Agent交流：
        leader-领队，整个任务总指挥
        recon-侦察员，负责信息收集
        attack-攻击者，负责对目标发起攻击
        report-报告撰写员，负责在最后总结任务并生成报告文档
        注意：不能给自己发送消息，不能发送空白消息，To的名字必须严格符合上述名单,From为System的是系统的自动提示，你无需也不能回复
        :param To: 发给谁
        :param content: 要发送的消息
        :param type: 消息类型： request | task_complete | warning
        :return: 投递成功/失败信息
        """
        return await self._send_message_base("analysis", To, content, type)

    async def _send_message_attack(self, To:str, content: str, type: str):
        """
        通过此工具向其它Agent成员通讯
        将消息投入消息队列，由系统后台管理并发送消息
        本工具是异步的：调用后立即返回"已投递"，对方的回复不会通过本工具返回。回复会作为新消息在稍后自动送达你的下一次唤醒中。如需等待回复，请直接结束当前轮次即可。
        你可以与以下Agent交流：
        leader-领队，整个任务总指挥
        recon-侦察员，负责信息收集
        analysis-分析师，分析目标可能存在的漏洞和值得进攻的资产
        report-报告撰写员，负责在最后总结任务并生成报告文档
        注意：不能给自己发送消息，不能发送空白消息，To的名字必须严格符合上述名单,From为System的是系统的自动提示，你无需也不能回复
        :param To: 发给谁
        :param content: 要发送的消息
        :param type: 消息类型： request | task_complete | warning
        :return: 投递成功/失败信息
        """
        return await self._send_message_base("attack", To, content, type)

    async def _send_message_report(self, To:str, content: str, type: str):
        """
        通过此工具向其它Agent成员通讯
        将消息投入消息队列，由系统后台管理并发送消息
        本工具是异步的：调用后立即返回"已投递"，对方的回复不会通过本工具返回。回复会作为新消息在稍后自动送达你的下一次唤醒中。如需等待回复，请直接结束当前轮次即可。
        你可以与以下Agent交流：
        leader-领队，整个任务总指挥
        recon-侦察员，负责信息收集
        analysis-分析师，分析目标可能存在的漏洞和值得进攻的资产
        attack-攻击者，负责对目标发起攻击
        注意：不能给自己发送消息，不能发送空白消息，To的名字必须严格符合上述名单，From为System的是系统的自动提示，你无需也不能回复
        :param To: 发给谁
        :param content: 要发送的消息
        :param type: 消息类型： request | task_complete | warning
        :return: 投递成功/失败信息
        """
        return await self._send_message_base("report", To, content, type)

    async def _send_message_base(self, From: str, To: str, content: str, type: str):
        """
        消息发送基础方法
        :param From: 起始Agent
        :param To: 目标Agent
        :param content: 要发送的消息
        :param type: 消息类型： request | task_complete | warning
        :return: 投递成功/失败信息
        """
        self._tool_use_event.set()

        if self.stop_event.is_set():
            return "System: 用户已经终止了任务，请结束对话，不要再调用任何工具，直到被再次唤醒"
        if type not in ["request", "task_complete", "warning"]:
            return "type参数错误"
        # 记录工具执行
        await self._add_tool_execution(
            agent_name=From,
            action="send_message",
            summary=f"向 {To} 发送{type}消息",
            detail=f"内容: {content[:200]}" if len(content) > 200 else f"内容: {content}"
        )

        From = From.lower().strip()
        To = To.lower().strip()
        if From not in self.agent_names:
            return f"{From} 不是有效的Agent"
        if To not in self.agent_names:
            return f"{To} 不是有效的Agent"
        if From == To:
            return "不能向自己发送消息"
        if content == "":
            return "content不能为空"

        message = {
            "From": From,
            "To": To,
            "content": content,
            "type": type
        }
        await self.message_queue.put(message)

        return "System: 你发送的消息已投递至消息队列，系统稍后会自动发送给对方。现在请立刻结束当前对话，不要再调用任何工具，直到被再次唤醒"

    # 消息处理任务，负责维护消息队列和实际发送信息
    async def message_manager(self):
        """
        消息管理器
        每隔0.5秒检查一次所有Agent的状态
        如果连续10秒所有Agent都处于空闲状态，向最后收到消息的Agent发送提醒
        如果连续1分钟所有Agent都处于空闲状态，向Leader发送提醒
        """
        print(f"[Info] 消息管理器已启动 (session={self.session_id})")
        idle_counter = 0.0     # 记录所有Agent连续空闲的秒数
        ten_sec_remind_flag = False
        one_min_remind_flag = False
        last_agent = self.agents["leader"]
        while True:
            if self.stop_event.is_set():    # 如果停止事件被设置，退出
                print(f"[Info] 消息管理器已停止 (session={self.session_id})")
                return
            await asyncio.sleep(0.5)  # 每隔0.5秒检查一次

            # 处理消息队列中的所有消息
            while not self.message_queue.empty():
                # 在处理每条消息前都检查停止信号
                if self.stop_event.is_set():
                    print("[Info] 检测到停止信号，清空消息队列并退出")
                    # 清空剩余消息
                    while not self.message_queue.empty():
                        self.message_queue.get_nowait()
                    print("[Info] 消息路由已停止")
                    return
                    
                message:dict[str,str] = await self.message_queue.get()
                # 发送消息
                To = message["To"].lower().strip()
                From = message["From"].lower().strip()
                content = message["content"]
                type = message["type"].lower().strip()

                # 消息发出时立即保存到数据库
                try:
                    await self._save_agent_message(From, To, content, type)
                except Exception as e:
                    print(f"[Error] 保存发出的消息失败: {e}")

                target_agent = self.agents[To]
                last_agent = target_agent

                # 有新消息发出，重置空闲计数器和提醒标志
                idle_counter = 0.0
                ten_sec_remind_flag = False

                asyncio.create_task(
                    self._invoke_agent(target_agent, From, json.dumps({"From": From, "content": content, "type": type}, ensure_ascii=False))
                )

            # 检查所有Agent是否都处于空闲状态
            all_idle = all(not status.is_set() for status in self.agents_status.values())
            if all_idle and not self._tool_use_event.is_set():
                idle_counter += 0.5

                if idle_counter > 60*5 and last_agent.name != "leader":
                    # 5分钟无操作，代表最后收到消息的Agent可能失联，向Leader发送提醒并重置计数器
                    asyncio.create_task(
                        self._invoke_agent(self.agents["leader"], "System", json.dumps({"From": "System", "content": f"已有5分钟未执行任何操作，如果任务还未完成，代表{last_agent.name}已失联，请派其它Agent代替，如果无需进一步操作或需要等待用户发送新指示请调用stop_task停止行动\n这是系统消息，无需回复"}, ensure_ascii=False))
                    )
                    # 重置计数器
                    idle_counter = 0.0
                    one_min_remind_flag = False
                    ten_sec_remind_flag = False

                elif idle_counter > 60 and one_min_remind_flag == False:
                    # 连续1分钟所有Agent空闲，向Leader发送提醒并重置计数器
                    asyncio.create_task(
                        self._invoke_agent(self.agents["leader"], "System", json.dumps({"From": "System", "content": f"整个系统已有1分钟未执行任何操作，如果任务还未完成，请询问{last_agent.name}当前状态，如果失联请派其它Agent代替，如果无需进一步操作或需要等待用户发送新指示请调用stop_task停止行动\n这是系统消息，无需回复"}, ensure_ascii=False))
                    )
                    one_min_remind_flag = True

                elif idle_counter > 30 and not self._tool_use_event.is_set() and not ten_sec_remind_flag:
                    # 连续30秒所有Agent空闲，向最后收到消息的Agent发送提醒
                    if last_agent.name == "leader":
                        asyncio.create_task(
                            self._invoke_agent(last_agent, "System", json.dumps(
                                {"From": "System", "content": "你已经30秒没有活动，请检查状态，如果无需进一步操作或需要等待用户发送新指示请调用stop_task停止行动\n这是系统消息，无需回复"},
                                ensure_ascii=False))
                        )
                    else:
                        asyncio.create_task(
                            self._invoke_agent(last_agent, "System", json.dumps({"From": "System", "content": "你已经30秒没有活动，请检查状态，如果你的任务已完成请向leader汇报\n这是系统消息，无需回复"}, ensure_ascii=False))
                        )
                    ten_sec_remind_flag = True
            else:
                # 有Agent在忙碌，重置空闲计数器
                idle_counter = 0.0
                ten_sec_remind_flag = False
                self._tool_use_event.clear()

    async def _invoke_agent(self, agent: CompiledStateGraph, From: str, content: str):
        """ 包装invoke调用，防止阻塞message_manager ，对空流异常自动重试"""
        max_retries = 3
        for attempt in range(max_retries):
            print({"From": From, "content": content})
            # 检查是否需要停止
            if self.stop_event.is_set():
                print(f'[Info] 检测到停止信号，取消向 {agent.name} 发送消息')
                self.agents_status[agent.name].clear()
                return
            
            try:
                if From == "System":
                    message = {"messages": [SystemMessage(content=content)]}
                else:
                    message = {"messages": [AIMessage(content=content)]}

                # 发送前检测Agent是否空闲，如果忙碌就等待（同时检查停止信号）
                while self.agents_status[agent.name].is_set():
                    if self.stop_event.is_set():
                        print(f'[Info] 等待Agent空闲时检测到停止信号，取消向 {agent.name} 发送消息')
                        self.agents_status[agent.name].clear()
                        return
                    await asyncio.sleep(0.5)

                self.agents_status[agent.name].set()  # 发送前设置Agent为忙碌

                # 修复 checkpoint 中可能存在的未完成 tool_calls
                await self._fix_pending_tool_calls(agent, f"{self.session_id}_{agent.name}")

                # 使用 asyncio.wait_for 设置超时，并在停止时取消任务
                try:
                    invoke_task = agent.ainvoke(
                        message,
                        config={"configurable": {"thread_id": f"{self.session_id}_{agent.name}"}}
                    )
                    response = await asyncio.wait_for(invoke_task, timeout=None)
                except asyncio.CancelledError:
                    print(f'[Info] 向 {agent.name} 发送消息的任务被取消')
                    self.agents_status[agent.name].clear()
                    return
                self.agents_status[agent.name].clear()    # 回复后设置Agent为空闲

                # 提取最后一个 AIMessage 的文本内容
                response_text = ""
                for msg in reversed(response.get("messages", [])):
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

                # 保存 Agent 间对话到数据库（只保存回复，发出的消息已在 message_manager 中保存）
                try:
                    if response_text:
                        incoming_content = json.loads(content)
                        original_from = incoming_content.get("From", "unknown")
                        await self._save_agent_message(agent.name, original_from, response_text, "response")
                except Exception:
                    pass

                # 广播 Agent 回复到 WebSocket（如果注册了回调）
                if self._broadcast_callback and response_text:
                    try:
                        await self._broadcast_callback(agent.name, response_text)
                    except Exception:
                        pass

                print(f'{From}向 {agent.name} 发送消息："{response_text[:100] if response_text else "(无文本)"}"')
                return response_text  # 成功则退出
            except ValueError as e:
                if "No generations found in stream" in str(e) and attempt < max_retries - 1:
                    print(f'[Warn] {agent.name} 响应流为空，第{attempt+1}次重试...')
                    await asyncio.sleep(2)
                    continue
                # 非空流错误或重试耗尽，按原逻辑处理
                self.agents_status[agent.name].clear()
                print(f'[Error] {From} 向 {agent.name} 发送消息失败：{e}。失败消息: "{content}"')
                return
            except Exception as e:
                self.agents_status[agent.name].clear()
                print(f'[Error] {From} 向 {agent.name} 发送消息失败：{e}。失败消息: "{content}"')
                return

    async def _fix_pending_tool_calls(self, agent: CompiledStateGraph, thread_id: str):
        """
        修复 checkpoint 中未完成的 tool_calls 消息链。
        当 Agent 的上一条消息包含 tool_calls 但缺少对应 ToolMessage 时，
        补填占位 ToolMessage 以满足 API 的消息格式要求。
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            state = await agent.aget_state(config)
            if not state or not state.values:
                return
            messages = state.values.get("messages", [])
            if not messages:
                return
            last_msg = messages[-1]
            # 检查最后一条消息是否是带有 tool_calls 的 AIMessage
            if isinstance(last_msg, AIMessage) and getattr(last_msg, 'tool_calls', None):
                tool_calls = last_msg.tool_calls
                # 检查这些 tool_calls 是否已有对应的 ToolMessage 回复
                existing_tool_call_ids = {
                    msg.tool_call_id for msg in messages
                    if isinstance(msg, ToolMessage)
                }
                missing_tool_calls = [
                    tc for tc in tool_calls
                    if tc.get("id") not in existing_tool_call_ids
                ]
                if missing_tool_calls:
                    print(f"[Warn] {agent.name} checkpoint 中有 {len(missing_tool_calls)} 个未响应的 tool_calls，补填占位 ToolMessage")
                    dummy_messages = [
                        ToolMessage(
                            content="[System] 工具执行被中断，未获取到结果",
                            tool_call_id=tc["id"]
                        )
                        for tc in missing_tool_calls
                    ]
                    await agent.aupdate_state(config, {"messages": dummy_messages})
        except Exception as e:
            print(f"[Warn] 修复 {agent.name} 未完成 tool_calls 失败: {e}")

    # 消息管理启动器
    def start_message_manager(self):
        """ 启动异步任务 """
        asyncio.create_task(self.message_manager())
    # 等待所有Agent间消息处理完毕
    async def wait_for_replies(self):
        """等待任务完成"""
        await self.stop_event.wait()
    ######### 消息发送工具-END #########

    ######### 网络空间测绘工具-START #########
    async def _network_mapping(self, query: str, page: int = 1, page_size: int = 10) -> list[dict[str, str]] | str:
        """
        使用奇安信Hunter进行网络空间测绘
        注意：内网目标不应使用
        :param query: 查询语法
        :param page: 查询页码
        :param page_size: 每一页返回数量(不能小于10)
        :return:查询结果/错误信息
        """

        # 检查是否需要停止
        if self.stop_event.is_set():
            return "[Info] 用户已经终止了任务，请结束会话，不要再调用任何工具，直到被再次唤醒"

        self._tool_use_event.set()
        # 记录工具执行
        await self._add_tool_execution(
            agent_name="recon",
            action="network_mapping",
            summary=f"Hunter查询: {query[:50]}",
            detail=f"查询: {query}, 页码: {page}, 每页: {page_size}"
        )

        if page_size < 10:
            return "[Error] page_size 不能小于10"
        try:
            search = base64.urlsafe_b64encode(query.encode("utf-8")).decode()
            request_url = f"https://hunter.qianxin.com/openApi/search?api-key={os.getenv('HUNTER_API_KEY')}&search={search}&page={page}&page_size={page_size}"
            async with httpx.AsyncClient() as client:
                response = await client.get(request_url)
                result = response.json()["data"]["arr"]
            return result
        except Exception as e:
            error_msg = f"[Error] Hunter 查询失败：{e}"
            await self._add_tool_execution(
                agent_name="recon",
                action="network_mapping",
                summary="Hunter查询失败",
                detail=error_msg
            )
            return error_msg
    ######### 网络空间测绘工具-END #########

    ######### Kali控制工具-START #########
    async def init_kali_terminal(self):
        """ 初始化Kali Linux交互终端-为每一个Agent创建一个独立的非交互终端,互不干扰 """
        success_count = 0
        for agent_name in self.agent_names:
            try:
                await self.create_kali_terminal(agent_name)
                success_count += 1
            except Exception as e:
                print(f"[Warn] Agent {agent_name} Kali 终端初始化失败: {e}")
        print(f"[Info] 已为 {success_count}/{len(self.agent_names)} 个Agent初始化终端")

    async def create_kali_terminal(self, agent_name: str):
        """
        创建一个全新的SSH连接并分配可交互终端
        :param agent_name: agent名称
        """
        host = os.getenv("KALI_HOST")
        user = os.getenv("KALI_USER", "root")
        ssh_key = os.getenv("KALI_SSH_KEY")

        if not host or not user:
            raise ValueError(f"KALI_HOST 和 KALI_USER 环境变量未配置")

        if ssh_key:
            # base64 解码密钥
            import base64
            from asyncssh import import_private_key
            key_data = base64.b64decode(ssh_key.strip()).decode("utf-8")
            key = import_private_key(key_data)
            conn = await asyncssh.connect(host, username=user,
                                          client_keys=[key], known_hosts=None)
        else:
            raise ValueError(f"未配置 KALI_SSH_KEY，无法连接 Kali")

        self.kali_conn[agent_name] = conn
    # 为每个Agent创建独立的命令执行工具方法
    async def _exec_kali_command_leader(self, command: str, timeout: float = 30.0) -> str:
        """
        在kali容器中执行非交互式命令
        如果要执行的命令可能耗时较长，请将其放到后台，并将输出重定向到文件
        应避免使用交互命令(如less、vim等)
        :param command: 要执行的命令
        :param timeout: 超时时间(秒)
        :return: 执行结果
        """
        return await self._exec_kali_command_base("leader", command, timeout)

    async def _exec_kali_command_recon(self, command: str, timeout: float = 30.0) -> str:
        """
        在kali容器中执行非交互式命令
        如果要执行的命令可能耗时较长，请将其放到后台，并将输出重定向到文件
        应避免使用交互命令(如less、vim等)
        :param command: 要执行的命令
        :param timeout: 超时时间(秒)
        :return: 执行结果
        """
        return await self._exec_kali_command_base("recon", command, timeout)

    async def _exec_kali_command_analysis(self, command: str, timeout: float = 30.0) -> str:
        """
        在kali容器中执行非交互式命令
        如果要执行的命令可能耗时较长，请将其放到后台，并将输出重定向到文件
        应避免使用交互命令(如less、vim等)
        :param command: 要执行的命令
        :param timeout: 超时时间(秒)
        :return: 执行结果
        """
        return await self._exec_kali_command_base("analysis", command, timeout)

    async def _exec_kali_command_attack(self, command: str, timeout: float = 30.0) -> str:
        """
        在kali容器中执行非交互式命令
        如果要执行的命令可能耗时较长，请将其放到后台，并将输出重定向到文件
        应避免使用交互命令(如less、vim等)
        :param command: 要执行的命令
        :param timeout: 超时时间(秒)
        :return: 执行结果
        """
        return await self._exec_kali_command_base("attack", command, timeout)

    async def _exec_kali_command_report(self, command: str, timeout: float = 30.0) -> str:
        """
        在kali容器中执行非交互式命令
        如果要执行的命令可能耗时较长，请将其放到后台，并将输出重定向到文件
        应避免使用交互命令(如less、vim等)
        :param command: 要执行的命令
        :param timeout: 超时时间(秒)
        :return: 执行结果
        """
        return await self._exec_kali_command_base("report", command, timeout)

    async def _exec_kali_command_base(self, agent_name: str, command: str, timeout: float = 30.0) -> str:
        """
        命令执行基础方法
        :param agent_name: 你的身份
        :param command: 要执行的命令
        :param timeout: 超时时间(秒)
        :return: 执行结果
        """
        self._tool_use_event.set()
        
        # 检查是否需要停止
        if self.stop_event.is_set():
            return "[Info] 用户已经终止了任务，请结束会话，不要再调用任何工具，直到被再次唤醒"

        print(f"[Debug] {agent_name} 执行命令：{command}，超时时间：{timeout}秒")

        # 记录工具执行开始
        await self._add_tool_execution(
            agent_name=agent_name,
            action="exec_kali_command",
            summary=f"执行命令: {command[:100]}",
            detail=f"完整命令: {command}"
        )
        
        # 取出连接
        conn = self.kali_conn.get(agent_name)
        if conn is None:
            return f"[Error] {agent_name} 的 Kali 终端未连接，无法执行命令"
        try:
            # 在命令执行期间也定期检查停止信号
            res = await conn.run(command, timeout=timeout, check=False)
            # 合并stdout和stderr，确保错误信息也能返回
            output = res.stdout + res.stderr
            try:
                # 把命令记录添加到历史表中
                await self._add_command_history(agent_name, command, output)
            except Exception as e:
                print(f"[Error] 添加命令历史失败：{e}")
            return output
        except Exception as e:
            error_msg = f"[Error] 命令执行失败：{e}"
            # 记录执行失败
            await self._add_tool_execution(
                agent_name=agent_name,
                action="exec_kali_command",
                summary=f"命令执行失败: {command[:50]}",
                detail=error_msg
            )
            return error_msg

    async def _get_kali_command_history_base(self, agent_name: str, rows: int = 10, keyword: str = None) -> str:
        """
        查看最近rows条命令记录
        :param agent_name: Agent身份
        :param rows: 记录条数
        :param keyword: 关键字搜索，匹配命令或结果中包含该关键字的记录（不区分大小写）。
            默认为 None，即返回全部记录。
            例如 keyword="nmap" 可筛选出所有与 nmap 相关的命令记录。
            当有多条匹配时，可与 rows 配合限制返回数量。
        :return: 终端历史内容
        """
        self._tool_use_event.set()
        try:
            async with get_global_db_conn().cursor() as cur:
                if keyword:
                    await cur.execute(
                        "SELECT command, result FROM command_history "
                        "WHERE agent_name = %s AND session_id = %s "
                        "AND (command ILIKE %s OR result ILIKE %s) "
                        "ORDER BY id DESC LIMIT %s",
                        (agent_name, self.session_id, f"%{keyword}%", f"%{keyword}%", rows)
                    )
                else:
                    await cur.execute(
                        "SELECT command, result FROM command_history "
                        "WHERE agent_name = %s AND session_id = %s "
                        "ORDER BY id DESC LIMIT %s",
                        (agent_name, self.session_id, rows)
                    )
                rows = await cur.fetchall()
                
                if not rows:
                    if keyword:
                        return f"[Info] {agent_name} 的命令历史中未找到包含 '{keyword}' 的记录"
                    return f"[Info] {agent_name} 暂无命令历史记录"

                # 输出最终结果
                result = ""
                for row in rows:
                    for column in row:
                        result += column + '\n'
                
                return result
        except Exception as e:
            return f"[Error] 查询命令历史失败: {e}"
    
    # 为每个Agent创建独立的历史记录查询工具方法
    async def _get_command_history_leader(self, rows: int = 10, keyword: str = None) -> str:
        """
        查看自己最近的命令执行记录
        :param rows: 要查询的记录条数（默认10条）
        :param keyword: 关键字搜索，匹配命令或结果中包含该关键字的记录（不区分大小写），默认为 None
        :return: 格式化的命令历史记录
        """
        return await self._get_kali_command_history_base("leader", rows, keyword)
    
    async def _get_command_history_recon(self, rows: int = 10, keyword: str = None) -> str:
        """
        查看自己最近的命令执行记录
        :param rows: 要查询的记录条数（默认10条）
        :param keyword: 关键字搜索，匹配命令或结果中包含该关键字的记录（不区分大小写），默认为 None
        :return: 格式化的命令历史记录
        """
        return await self._get_kali_command_history_base("recon", rows, keyword)
    
    async def _get_command_history_analysis(self, rows: int = 10, keyword: str = None) -> str:
        """
        查看自己最近的命令执行记录
        :param rows: 要查询的记录条数（默认10条）
        :param keyword: 关键字搜索，匹配命令或结果中包含该关键字的记录（不区分大小写），默认为 None
        :return: 格式化的命令历史记录
        """
        return await self._get_kali_command_history_base("analysis", rows, keyword)
    
    async def _get_command_history_attack(self, rows: int = 10, keyword: str = None) -> str:
        """
        查看自己最近的命令执行记录
        :param rows: 要查询的记录条数（默认10条）
        :param keyword: 关键字搜索，匹配命令或结果中包含该关键字的记录（不区分大小写），默认为 None
        :return: 格式化的命令历史记录
        """
        return await self._get_kali_command_history_base("attack", rows, keyword)
    
    async def _get_command_history_report(self, rows: int = 10, keyword: str = None) -> str:
        """
        查看自己最近的命令执行记录
        :param rows: 要查询的记录条数（默认10条）
        :param keyword: 关键字搜索，匹配命令或结果中包含该关键字的记录（不区分大小写），默认为 None
        :return: 格式化的命令历史记录
        """
        return await self._get_kali_command_history_base("report", rows, keyword)

    # 为每个Agent创建独立的终端重连工具方法
    async def _restart_kali_terminal_leader(self) -> str:
        """
        重启终端连接，新连接会覆盖原有的终端连接，直接使用exec_kali_command就可以向新终端发送命令
        :return: 成功/失败信息
        """
        return await self._restart_kali_terminal_base("leader")

    async def _restart_kali_terminal_recon(self) -> str:
        """
        重启终端连接，新连接会覆盖原有的终端连接，直接使用exec_kali_command就可以向新终端发送命令
        :return: 成功/失败信息
        """
        return await self._restart_kali_terminal_base("recon")

    async def _restart_kali_terminal_analysis(self) -> str:
        """
        重启终端连接，新连接会覆盖原有的终端连接，直接使用exec_kali_command就可以向新终端发送命令
        :return: 成功/失败信息
        """
        return await self._restart_kali_terminal_base("analysis")

    async def _restart_kali_terminal_attack(self) -> str:
        """
        重启终端连接，新连接会覆盖原有的终端连接，直接使用exec_kali_command就可以向新终端发送命令
        :return: 成功/失败信息
        """
        return await self._restart_kali_terminal_base("attack")

    async def _restart_kali_terminal_report(self) -> str:
        """
        重启终端连接，新连接会覆盖原有的终端连接，直接使用exec_kali_command就可以向新终端发送命令
        :return: 成功/失败信息
        """
        return await self._restart_kali_terminal_base("report")

    async def _restart_kali_terminal_base(self, agent_name: str) -> str:
        """
        重启终端连接基础方法
        :param agent_name: Agent身份
        :return: 成功/失败信息
        """
        if self.stop_event.is_set():
            return "[Info] 用户已经终止了任务，请结束会话，不要再调用任何工具，直到被再次唤醒"

        self._tool_use_event.set()

        if agent_name not in self.agent_names:
            return f"[Error] 找不到该成员：{agent_name}"

        try:
            await self.create_kali_terminal(agent_name)
            return "重启成功"
        except Exception as e:
            return f"[Error] 重启终端失败：{e}"
    ######### Kali控制工具-END #########

    async def get_steps(self):
        """ 获取当前行动进度 """
        try:
            async with get_global_db_conn().cursor() as cur:
                await cur.execute(
                    "SELECT step FROM steps WHERE session_id = %s",
                    (self.session_id,)
                )
                records = await cur.fetchall()

                if not records:
                    return "当前没有行动进度"
                return records
        except Exception as e:
            print(f"获取步骤失败：{e}")
            return f"[Error] 获取步骤失败：{e}"

    async def _write_to_blackboard(self, agent_name: str, category: str, title: str,
                                   content: dict,  # 参数类型改为 dict
                                   priority: str = "medium",
                                   related_target: str = None) -> str:
        """
        【共享协作工具】将发现的重要情报写入团队共享黑板。

        【使用场景】
        - 侦察员发现新资产、开放端口或服务时。
        - 分析员确认漏洞、验证CVE或分析出攻击面时。
        - 攻击手获取凭据、成功提权或发现特定配置时。
        - 任何需要其他成员知晓或跟进的信息。

        【参数说明】
        :param category (str): 信息分类，必须为以下值之一：
            - 'asset_discovery': 资产发现 (IP、域名、开放端口)
            - 'vulnerability': 漏洞信息 (CVE、弱版本、逻辑漏洞)
            - 'credential': 凭据信息 (用户名、密码、Hash、Key)
            - 'exploit_result': 攻击结果 (Shell获取、提权成功)
            - 'network_info': 网络拓扑 (网段、防火墙规则)
            - 'configuration': 敏感配置 (配置文件泄露、备份文件)
        :param title (str): 简短、明确的标题摘要 (例如: "发现192.168.1.10开放SSH服务")。
        :param content (dict): 详细内容，必须为字典格式。建议包含以下标准字段以便他人查询：
            - 'target' (str): 目标IP或域名 (必填)。
            - 'port' (int): 端口号 (如果是服务类)。
            - 'service' (str): 服务名称或组件名。
            - 'severity' (str): 严重程度。
            - 'data' (str/dict): 具体数据 (如banner内容、密码哈希等)。
        :param priority (str): 优先级，必须为以下值之一：
            - 'low': 普通信息
            - 'medium': 中等重要 (默认)
            - 'high': 高危，需立即关注
            - 'critical': 关键路径，如管理员凭据或RCE漏洞
        :param related_target (str): 关联的目标对象 (通常是IP)，用于快速索引。

        【注意事项】
        - 写入前请确保 content 字典中包含 'target' 字段。
        - 不要重复写入完全相同的信息。
        - 如果是验证后的信息，请在 content 中添加 'verified': true 字段。

        :return: 操作结果提示
        """
        self._tool_use_event.set()
        if self.stop_event.is_set():
            return "[Info] 用户已经终止了任务，请结束会话，不要再调用任何工具，直到被再次唤醒"
        
        # 记录工具执行
        await self._add_tool_execution(
            agent_name=agent_name,
            action="write_to_blackboard",
            summary=f"写入黑板: {title}",
            detail=f"类别: {category}, 优先级: {priority}, 内容：{content}"
        )
        
        try:
            # psycopg 会自动将 dict 转换为 PostgreSQL 的 JSONB 格式
            async with get_global_db_conn().cursor() as cur:
                await cur.execute("""
                                  INSERT INTO blackboard
                                  (session_id, agent_name, category, title, content, priority, related_target)
                                  VALUES (%s, %s, %s, %s, %s, %s, %s)
                                  """, (self.session_id, agent_name, category, title, Jsonb(content),
                                        priority, related_target))
                await get_global_db_conn().commit()
            return f"信息已写入黑板: {title}"
        except Exception as e:
            print(f"写入黑板失败：{e}")
            return f"[Error] 写入黑板失败: {e}"

    async def _read_blackboard(self, agent_name: str, category: str = None, status: str = None,
                               related_target: str = None,
                               json_filters: dict = None,
                               limit: int = 20) -> str:
        """
        【情报检索工具】从团队共享黑板中查询其他Agent收集的信息。

        【使用场景】
        - 攻击前查询目标是否存在已知漏洞或凭据。
        - 侦察前查询是否已有该IP的端口信息，避免重复扫描。
        - 分析时查找所有高危漏洞。
        - 任务中查看团队目前的整体进展。

        【参数说明】
        :param agent_name (str): 【必填】你的身份标识，用于记录日志。
            必须传入你的 Agent 名称，例如 \"recon\"、\"analysis\"、\"attack\"、\"report\" 或 \"leader\"。
        :param category (str, optional): 按类别筛选。例如: 'vulnerability', 'credential'。
        :param status (str, optional): 按状态筛选。
            - 'active': 待处理情报
            - 'verified': 已验证情报
            - 'used': 已被利用
        :param related_target (str, optional): 按目标IP/域名筛选。
        :param json_filters (dict, optional): 【高级功能】根据 content 内容的内部字段进行深度筛选。
            这是一个字典，用于匹配 JSONB 内部的 key-value。
            示例用法:
            1. 查找所有严重程度为 'high' 的记录: {"severity": "high"}
            2. 查找所有端口为 80 的记录: {"port": 80}
            3. 查找所有已验证的记录: {"verified": true}
            注意: json_filters 中的键必须对应写入时 content 字典里的键。
        :param limit (int): 返回的最大记录数，默认为 20。

        【返回说明】
        返回格式化的文本列表，包含每条情报的来源、类别、标题和详细内容。
        如果没有匹配项，将返回 "暂无相关信息"。

        :return: 格式化的情报列表字符串
        """
        self._tool_use_event.set()
        
        # 记录工具执行
        await self._add_tool_execution(
            agent_name=agent_name,
            action="read_blackboard",
            summary=f"读取黑板: {category or '全部'}",
            detail=f"类别: {category}, 状态: {status}, 目标: {related_target}, 过滤器: {json_filters}, 限制: {limit}"
        )
        
        try:
            query = "SELECT * FROM blackboard WHERE session_id = %s"
            params = [self.session_id]
        
            if category:
                query += " AND category = %s"
                params.append(category)
            if status:
                query += " AND status = %s"
                params.append(status)
            if related_target:
                query += " AND related_target = %s"
                params.append(related_target)
        
            # --- JSONB 特有查询逻辑 ---
            if json_filters:
                for key, value in json_filters.items():
                    # 使用 ->> 提取 JSON 文本值进行比较
                    # 例如: content->>'severity' = 'high'
                    query += f" AND content->>%s = %s"
                    params.extend([key, value])
        
            query += " ORDER BY priority DESC, created_at DESC LIMIT %s"
            params.append(limit)
        
            async with get_global_db_conn().cursor() as cur:
                await cur.execute(query, params)
                records = await cur.fetchall()
        
            if not records:
                return "黑板中暂无相关信息"
        
            # psycopg 读取 JSONB 列时，会自动转换回 Python dict
            result_lines = []
            for record in records:
                # record[5] 现在是一个 dict 对象，不是 string
                content_dict = record[5]
        
                result_lines.append(f"ID: {record[0]} | 来源: {record[2]} | 类别: {record[3]}")
                result_lines.append(f"标题: {record[4]}")
                # 可以直接像操作字典一样格式化输出
                detail = f"详情: {json.dumps(content_dict, ensure_ascii=False, indent=2)}"
                result_lines.append(detail)
                result_lines.append("-" * 40)
        
            return "\n".join(result_lines)
        except Exception as e:
            return f"[Error] 读取黑板失败: {e}"

    async def _update_blackboard(self, agent_name: str, record_id: int,
                                 category: str = None,
                                 title: str = None,
                                 content: dict = None,
                                 priority: str = None,
                                 status: str = None,
                                 related_target: str = None) -> str:
        """
        【情报维护工具】根据记录 ID 修改黑板中已有的情报条目。
        只需传入需要修改的字段，未传入的字段保持原值不变。修改成功后自动更新 updated_at 时间戳。

        【使用场景】
        - 漏洞验证后，将状态从 'active' 更新为 'verified'。
        - 凭据被成功利用后，标记状态为 'used'。
        - 扫描获得更多信息后，补充/更新 content 详细内容。
        - 调整情报的优先级（如从 'medium' 提升为 'high'）。
        - 纠正之前写入的错误信息。

        【参数说明】
        :param agent_name (str): 【必填】你的身份标识，用于记录日志。
            必须传入你的 Agent 名称，例如 \"recon\"、\"analysis\"、\"attack\"、\"report\" 或 \"leader\"。
        :param record_id (int): 要修改的黑板记录 ID（必填）。
            可通过 _read_blackboard 查询获取目标记录的 ID。
        :param category (str, optional): 新的信息分类。
            可选值: 'asset_discovery', 'vulnerability', 'credential', 'exploit_result', 'network_info', 'configuration'
        :param title (str, optional): 新的标题摘要。
        :param content (dict, optional): 新的详细内容字典，会整体替换原有 content。
            如需局部更新，建议先用 _read_blackboard 获取原 content，修改后再传入。
            建议保持以下标准字段:
            - 'target' (str): 目标IP或域名
            - 'port' (int): 端口号
            - 'service' (str): 服务名称
            - 'severity' (str): 严重程度
            - 'data' (str/dict): 具体数据
            - 'verified' (bool): 是否已验证
        :param priority (str, optional): 新的优先级。
            可选值: 'low', 'medium', 'high', 'critical'
        :param status (str, optional): 新的状态标记。
            可选值:
            - 'active': 待处理（默认）
            - 'verified': 已验证
            - 'used': 已被利用
            - 'archived': 已归档
        :param related_target (str, optional): 新的关联目标 IP/域名。

        【注意事项】
        - record_id 必须来自 _read_blackboard 返回结果中的 ID 字段。
        - 只更新你明确传入的字段，未传入的字段不受影响。
        - content 参数会整体替换原有内容，而非合并。
        - 修改操作会验证 record_id 是否属于当前项目，防止误改他人数据。

        :return: 操作结果字符串，成功时返回 "黑板记录 {record_id} 已更新"，
                 记录不存在时返回 "未找到记录 {record_id}"，失败时返回错误信息
        """
        self._tool_use_event.set()
        if self.stop_event.is_set():
            return "[Info] 用户已经终止了任务，请结束会话，不要再调用任何工具，直到被再次唤醒"
        
        # 记录工具执行
        await self._add_tool_execution(
            agent_name=agent_name,
            action="update_blackboard",
            summary=f"更新黑板记录: {record_id}",
            detail=f"状态: {status}, 优先级: {priority}"
        )
        
        try:
            # 构建动态 SET 子句
            set_clauses = []
            params = []

            if category is not None:
                set_clauses.append("category = %s")
                params.append(category)
            if title is not None:
                set_clauses.append("title = %s")
                params.append(title)
            if content is not None:
                set_clauses.append("content = %s")
                params.append(Jsonb(content))
            if priority is not None:
                set_clauses.append("priority = %s")
                params.append(priority)
            if status is not None:
                set_clauses.append("status = %s")
                params.append(status)
            if related_target is not None:
                set_clauses.append("related_target = %s")
                params.append(related_target)

            if not set_clauses:
                return "[Error] 未提供任何需要更新的字段"

            # 自动更新 updated_at 时间戳
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")

            # 拼接 SQL，通过 session_id 约束防止跨项目修改
            query = f"UPDATE blackboard SET {', '.join(set_clauses)} WHERE id = %s AND session_id = %s"
            params.extend([record_id, self.session_id])

            async with get_global_db_conn().cursor() as cur:
                await cur.execute(query, params)
                await get_global_db_conn().commit()
                if cur.rowcount == 0:
                    return f"未找到记录 {record_id}，请确认 ID 是否正确且属于当前项目"

            return f"黑板记录 {record_id} 已更新"
        except Exception as e:
            return f"[Error] 更新黑板失败: {e}"

    async def _get_progress(self, agent_name: str) -> str:
        """
        【任务进度查看工具】获取当前任务的全部执行进度。

        【使用场景】
        - 开始执行分配给你的子任务前，了解一下整体任务的进度。
        - 完成自己的步骤后，查看其他成员的步骤是否也已完成。
        - Leader 在分发新任务前，确认当前各步骤状态。
        - 任务卡住时，查看哪些步骤处于 'fail' 或 'pause' 状态。

        【参数说明】
        :param agent_name (str): 【必填】你的身份标识，用于记录日志。
            必须传入你的 Agent 名称，例如 \"recon\"、\"analysis\"、\"attack\"、\"report\" 或 \"leader\"。

        【返回格式】
        每条记录按以下格式输出:
            #{序号} [{状态}] {标题}
                描述: {描述内容}
                创建时间: {timestamp}
                更新时间: {updated_at}

        状态标识说明:
            pending   - 待执行，尚未开始
            running   - 执行中
            done      - 已完成
            fail      - 执行失败，需要关注
            pause     - 已暂停

        记录按序号升序排列。如果暂无进度记录，返回 "暂无进度记录"。

        【注意事项】
        - 本工具仅供查看，不能修改进度。如需更新进度，请告知 Leader 使用 _manage_progress 工具。
        - 执行你的子任务前后都建议调用此工具，以便了解自己在整体任务中的位置。

        :return: 格式化的全部进度信息字符串
        """
        self._tool_use_event.set()
        
        # 记录工具执行
        await self._add_tool_execution(
            agent_name=agent_name,
            action="get_progress",
            summary="获取任务进度",
            detail="查看当前任务的全部执行进度"
        )
        
        try:
            async with get_global_db_conn().cursor() as cur:
                await cur.execute(
                    "SELECT num, title, description, status, timestamp, updated_at "
                    "FROM progress WHERE session_id = %s ORDER BY num ASC",
                    (self.session_id,)
                )
                records = await cur.fetchall()

            if not records:
                return "暂无进度记录"

            lines = []
            for r in records:
                lines.append(f"#{r[0]} [{r[3]}] {r[1]}")
                if r[2]:
                    lines.append(f"    描述: {r[2]}")
                lines.append(f"    创建时间: {r[4]}")
                lines.append(f"    更新时间: {r[5] or r[4]}")
                lines.append("")
            return "\n".join(lines).strip()
        except Exception as e:
            return f"[Error] 获取进度失败: {e}"

    ######### Leader 专用工具-START #########
    # 任务进度管理工具（增删改查）
    async def _manage_progress(self, method: str,
                               num: int = None,
                               title: str = None,
                               description: str = None,
                               status: str = None) -> str:
        """
        管理当前任务的执行进度，支持增删改查四种操作。

        【一、创建步骤 —— method='create'】
        向进度表中添加一个新的步骤。序号由系统自动分配（从 1 开始递增），无需手动指定。

        【使用场景】
        - 任务开始时，规划并创建所有执行步骤。
        - 执行过程中发现需要新增的子步骤。

        【必填参数】
        :param method: 固定为 'create'
        :param title (str): 步骤标题，简要概括本步骤要做什么。
            例如: "端口扫描"、"漏洞验证"、"凭据爆破"
        :param description (str): 步骤详细描述，说明具体要执行的操作和预期产出。
        :param status (str): 步骤初始状态，必须为以下值之一:
            - 'pending': 待执行
            - 'running': 执行中
            - 'done': 已完成
            - 'fail': 执行失败
            - 'pause': 已暂停
            新建步骤通常设为 'pending' 或 'running'。

        【返回示例】
        "步骤 #1 - 端口扫描 已创建"

        【二、查询步骤 —— method='read'】
        读取当前任务的所有进度记录，或按序号/状态筛选。

        【使用场景】
        - 了解当前整体进度，查看哪些步骤已完成、哪些待处理。
        - 查找特定序号的步骤详情。
        - 筛选所有失败步骤以便重试。

        【参数说明】
        :param num (int, optional): 按步骤序号筛选，不传则返回所有步骤。
        :param status (str, optional): 按状态筛选。
            可选值: 'pending', 'running', 'done', 'fail', 'pause'
            不传则不过滤状态。
        :param title: 读取时忽略此参数。
        :param description: 读取时忽略此参数。

        【返回示例】
        #1 [done] 端口扫描 - 对目标进行全端口扫描...
        #2 [running] 漏洞验证 - 验证发现的漏洞是否可利用...
        #3 [pending] 凭据爆破 - 使用收集到的凭据尝试登录...

        【三、更新步骤 —— method='update'】
        更新指定序号步骤的标题、描述和/或状态。只更新传入的字段。
        修改成功后自动刷新 updated_at 时间戳。

        【使用场景】
        - 步骤开始执行时，将状态改为 'running'。
        - 步骤完成后，将状态改为 'done'。
        - 步骤失败时，将状态改为 'fail' 并补充失败原因到 description。
        - 需要暂停某步骤时，将状态改为 'pause'。
        - 调整步骤的标题或描述使其更准确。

        【参数说明】
        :param num (int): 要更新的步骤序号（必填）。
        :param title (str, optional): 新的步骤标题，不传则保持不变。
        :param description (str, optional): 新的步骤描述，不传则保持不变。
        :param status (str, optional): 新的状态。
            可选值: 'pending', 'running', 'done', 'fail', 'pause'

        【返回示例】
        "步骤 #1 已更新"

        【注意事项】
        - num 用于定位要修改的记录，不能通过此方法修改 num 本身。
        - 如果传入的 num 不存在，返回未找到提示。

        【四、删除步骤 —— method='delete'】
        从进度表中删除指定序号的步骤。

        【使用场景】
        - 步骤规划错误，需要移除。
        - 某个步骤不再需要执行。
        - 任务范围调整，缩减步骤。

        【参数说明】
        :param num (int): 要删除的步骤序号（必填）。
        :param title: 删除时忽略此参数。
        :param description: 删除时忽略此参数。
        :param status: 删除时忽略此参数。

        :return: 操作结果字符串
        """
        self._tool_use_event.set()
        if self.stop_event.is_set():
            return "[Info] 用户已经终止了任务，请结束会话，不要再调用任何工具，直到被再次唤醒"

        for name, agent_status in self.agents_status.items():
            if name != "leader" and agent_status.is_set():
                return "Error: 请等待其他Agent完成当前任务并回复消息后再决定下一步。不要违反系统规定"

        # 防御性类型检查：确保 status 是字符串而非 Event 等其它类型
        if status is not None and not isinstance(status, str):
            print(f"[Warn] manage_progress 收到非字符串 status: {type(status).__name__}={status}，已忽略")
            status = None

        # 记录工具执行
        await self._add_tool_execution(
            agent_name="leader",
            action=f"manage_progress_{method}",
            summary=f"进度管理: {method} #{num if num else ''}",
            detail=f"方法: {method}, 序号: {num}, 标题: {title[:50] if title else ''}"
        )
        
        try:
            async with get_global_db_conn().cursor() as cur:
                if method == "create":
                    if title is None or status is None:
                        return "[Error] create 操作需要 title、status 参数"
                    
                    # 始终自动分配序号（获取当前最大序号 + 1）
                    await cur.execute(
                        "SELECT COALESCE(MAX(num), 0) FROM progress WHERE session_id = %s",
                        (self.session_id,)
                    )
                    max_num_result = await cur.fetchone()
                    final_num = (max_num_result[0] if max_num_result else 0) + 1
                    
                    await cur.execute("""
                        INSERT INTO progress (session_id, num, title, description, status)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (self.session_id, final_num, title, description or "", status))
                    await get_global_db_conn().commit()
                    return f"步骤 #{final_num} - {title} 已创建"

                elif method == "read":
                    query = "SELECT num, title, description, status, timestamp, updated_at FROM progress WHERE session_id = %s"
                    params = [self.session_id]

                    if num is not None:
                        query += " AND num = %s"
                        params.append(num)
                    if status:
                        query += " AND status = %s"
                        params.append(status)

                    query += " ORDER BY num ASC"
                    await cur.execute(query, params)
                    records = await cur.fetchall()

                    if not records:
                        return "暂无进度记录"

                    lines = []
                    for r in records:
                        lines.append(f"#{r[0]} [{r[3]}] {r[1]}")
                        if r[2]:
                            lines.append(f"    描述: {r[2]}")
                        lines.append(f"    更新时间: {r[5] or r[4]}")
                        lines.append("")
                    return "\n".join(lines).strip()

                elif method == "update":
                    if num is None:
                        return "[Error] update 操作需要 num 参数"

                    set_parts = []
                    vals = []
                    if title is not None:
                        set_parts.append("title = %s")
                        vals.append(title)
                    if description is not None:
                        set_parts.append("description = %s")
                        vals.append(description)
                    if status is not None:
                        set_parts.append("status = %s")
                        vals.append(status)

                    if not set_parts:
                        return "[Error] update 操作至少需要 title、description、status 中的一个"

                    set_parts.append("updated_at = CURRENT_TIMESTAMP")
                    query = f"UPDATE progress SET {', '.join(set_parts)} WHERE session_id = %s AND num = %s"
                    vals.extend([self.session_id, num])

                    await cur.execute(query, vals)
                    await get_global_db_conn().commit()
                    if cur.rowcount == 0:
                        return f"未找到步骤 #{num}，请确认序号是否正确"
                    return f"步骤 #{num} 已更新"

                elif method == "delete":
                    if num is None:
                        return "[Error] delete 操作需要 num 参数"
                    await cur.execute(
                        "DELETE FROM progress WHERE session_id = %s AND num = %s",
                        (self.session_id, num)
                    )
                    await get_global_db_conn().commit()
                    if cur.rowcount == 0:
                        return f"未找到步骤 #{num}，请确认序号是否正确"
                    return f"步骤 #{num} 已删除"

                else:
                    return f"[Error] 不支持的方法: {method}，可选值为 create、read、update、delete"

        except Exception as e:
            return f"[Error] 进度管理失败: {e}"

    # 行动停止工具
    async def _stop_task(self, name:str = "leader") -> str:
        """
        如果你认为行动已经完成/失败，可以终止了，或者遇到无法处理的问题需要用户介入，就调用这个工具
        调用后，不要再执行其它任何操作，也不要回复其它队员的消息，结束对话
        :param name: 调用者身份，leader 调用时会检查未完成任务，user 调用时强制终止
        :return: 操作成功/失败
        """
        # user 强制终止，跳过所有检查
        if name == "user":
            self.stop_event.set()
            print(f"[Info] {self.session_id} 用户强制终止任务")
            try:
                await self._update_session_status_async()
            except Exception as e:
                print(f"[Warn] _stop_task 更新会话状态失败: {e}")
            for agent_name, conn in self.kali_conn.items():
                try:
                    conn.close()
                    await conn.wait_closed()
                    print(f"[Info] 已关闭 {agent_name} 的 Kali SSH 连接")
                except Exception as e:
                    print(f"[Warn] 关闭 {agent_name} Kali SSH 连接失败: {e}")
            self.kali_conn.clear()
            return "操作成功"

        # leader 调用时，检查消息队列中是否还有未派发的消息
        if self.message_queue.qsize() > 0:
            return "[Error] 消息队列中还有未派发的消息，请先等待所有Agent回复 task_complete 后再调用 stop_task"
        # leader 调用时，检查是否有 Agent 仍在工作
        for busy_agent, busy_status in self.agents_status.items():
            if busy_agent != "leader" and busy_status.is_set():
                return f"[Error] {busy_agent} 正在工作，请等待其执行完成并返回结果后再调用 stop_task"
        # leader 调用时，检查进度表中是否所有步骤都已完成（done 或 fail）
        try:
            async with get_global_db_conn().cursor() as cur:
                await cur.execute(
                    "SELECT num, title, status FROM progress WHERE session_id = %s AND status NOT IN ('done', 'fail')",
                    (self.session_id,)
                )
                incomplete = await cur.fetchall()
                if incomplete:
                    incomplete_info = ", ".join([f"#{r[0]} {r[1]}({r[2]})" for r in incomplete])
                    return f"[Error] 以下任务步骤尚未完成，请等待相关Agent回复 task_complete 后再调用 stop_task：{incomplete_info}"
        except Exception as e:
            print(f"[Warn] stop_task 检查进度表失败: {e}")

        self.stop_event.set()
        print(f"[Info] {self.session_id} 任务已停止")
        try:
            await self._update_session_status_async()
        except Exception as e:
            print(f"[Warn] _stop_task 更新会话状态失败: {e}")
        for agent_name, conn in self.kali_conn.items():
            try:
                conn.close()
                await conn.wait_closed()
                print(f"[Info] 已关闭 {agent_name} 的 Kali SSH 连接")
            except Exception as e:
                print(f"[Warn] 关闭 {agent_name} Kali SSH 连接失败: {e}")
        self.kali_conn.clear()
        return "操作成功"

    async def _update_session_status_async(self):
        """异步更新数据库中的会话状态为 stopped"""
        try:
            async with get_global_db_conn().cursor() as cur:
                await cur.execute(
                    "UPDATE sessions SET status = 'stopped', updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (self.session_id,),
                )
                await get_global_db_conn().commit()
        except Exception as e:
            print(f"[Warn] _stop_task 更新会话状态失败: {e}")
    ######### Leader 专用工具-END #########
    ##################### 工具定义-END ####################

if __name__ == "__main__":
    from langchain.messages import HumanMessage
    from dotenv import load_dotenv
    load_dotenv()
    async def test():
        # 程序启动时初始化全局数据库连接池
        await init_global_checkpointer()
        
        session_id = str(uuid7())
        project = Session(session_id)
        # 使用异步初始化方法（会自动使用全局checkpointer）
        await project.initialize()
        project.start_message_manager()
        leader = project.agents["leader"]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(os.getenv("LEADER_MODEL"))

                res = await leader.ainvoke({"messages": HumanMessage(content="测试任务：让recon ping一下localhost，得到结果就stop_task")}, config={"configurable": {"thread_id": session_id}})
                break
            except ValueError as e:
                if "No generations found in stream" in str(e) and attempt < max_retries - 1:
                    print(f"[Warn] leader 响应流为空，第{attempt+1}次重试...")
                    await asyncio.sleep(2)
                else:
                    raise
        print(res["messages"])
        await project.wait_for_replies()

    asyncio.run(test())