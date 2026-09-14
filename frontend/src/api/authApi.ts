import { API_BASE_URL } from "./client";

export type AuthUser = {
  id: number;
  username: string;
  role: string;
};

export type LoginResult = {
  token: string;
  user: AuthUser;
};

// 登录：成功返回 token 与用户信息；失败抛出带中文提示的错误。
async function login(username: string, password: string): Promise<LoginResult> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const message =
      (data as { message?: string } | null)?.message ?? "账号或密码错误";
    throw new Error(message);
  }

  return data as LoginResult;
}

// 校验当前 token 对应的用户。
async function me(token: string): Promise<{ user: AuthUser }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    throw new Error("登录已过期");
  }

  return res.json();
}

export const authApi = { login, me };
