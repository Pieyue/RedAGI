/** 会话管理 API */
import { client } from './client';

export interface Session {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export async function listSessions(): Promise<Session[]> {
  const res = await client.get('/api/sessions');
  return res.data;
}

export async function createSession(title: string): Promise<Session> {
  const res = await client.post('/api/sessions', { title });
  return res.data;
}

export async function deleteSession(id: string): Promise<void> {
  await client.delete(`/api/sessions/${id}`);
}

export async function stopSession(id: string): Promise<void> {
  await client.post(`/api/sessions/${id}/stop`);
}
