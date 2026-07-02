/** 监控 API —— 消息、进度、命令历史、Agent 对话 */
import { client } from './client';

export interface ChatMessage {
  id: number;
  session_id: string;
  role: string;
  agent_name: string | null;
  content: string;
  created_at: string;
}

export interface ProgressItem {
  num: number;
  title: string;
  description: string;
  status: string;
  timestamp: string;
  updated_at: string | null;
}

export interface CommandHistoryItem {
  id: number;
  agent_name: string;
  command: string;
  result: string;
  timestamp: string;
}

export interface AgentMessageItem {
  id: number;
  from_agent: string;
  to_agent: string;
  content: string;
  msg_type: string;
  created_at: string;
}

export interface ToolExecutionItem {
  id: number;
  agent_name: string;
  action: string;
  summary: string | null;
  detail: string | null;
  created_at: string;
}

export interface AgentStatusItem {
  name: string;
  status: string; // "busy" | "idle"
}

export async function getMessages(sessionId: string): Promise<ChatMessage[]> {
  const res = await client.get(`/api/sessions/${sessionId}/messages`);
  return res.data;
}

export async function getProgress(sessionId: string): Promise<ProgressItem[]> {
  const res = await client.get(`/api/sessions/${sessionId}/progress`);
  return res.data;
}

export async function getCommandHistory(
  sessionId: string,
  agentName?: string,
): Promise<CommandHistoryItem[]> {
  const params = agentName ? { agent_name: agentName } : {};
  const res = await client.get(`/api/sessions/${sessionId}/command-history`, { params });
  return res.data;
}

export async function getAgentMessages(
  sessionId: string,
  fromAgent?: string,
  toAgent?: string,
): Promise<AgentMessageItem[]> {
  const params: Record<string, string> = {};
  if (fromAgent) params.from_agent = fromAgent;
  if (toAgent) params.to_agent = toAgent;
  const res = await client.get(`/api/sessions/${sessionId}/agent-messages`, { params });
  return res.data;
}

export async function getToolExecutions(
  sessionId: string,
  agentName?: string,
  action?: string,
): Promise<ToolExecutionItem[]> {
  const params: Record<string, string> = {};
  if (agentName) params.agent_name = agentName;
  if (action) params.action = action;
  const res = await client.get(`/api/sessions/${sessionId}/tool-executions`, { params });
  return res.data;
}

export async function getAgentStatuses(sessionId: string): Promise<AgentStatusItem[]> {
  const res = await client.get(`/api/sessions/${sessionId}/agent-status`);
  return res.data;
}
