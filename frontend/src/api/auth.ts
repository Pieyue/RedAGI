/** 认证 API */
import { client } from './client';

export interface LoginParams {
  username: string;
  password: string;
}

export async function login(params: LoginParams) {
  const res = await client.post('/api/auth/login', params);
  return res.data;
}

export async function refreshToken() {
  const res = await client.post('/api/auth/refresh');
  return res.data;
}
