import { apiRequest } from "./client";
import type { LoginResult, User } from "@/types";

// Raw shapes returned by the backend before we map them to camelCase domain types.
interface LoginResponseDto {
  status: "authenticated" | "mfa_required";
  access_token?: string;
  refresh_token?: string;
  mfa_token?: string;
  user?: { id: string; email: string; name: string; role: string; mfa_enabled: boolean; status: string };
}

function mapUser(dto: NonNullable<LoginResponseDto["user"]>): User {
  return {
    id: dto.id,
    email: dto.email,
    name: dto.name,
    role: dto.role as User["role"],
    mfaEnabled: dto.mfa_enabled,
    status: dto.status as User["status"],
  };
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const dto = await apiRequest<LoginResponseDto>("/auth/login", {
    method: "POST",
    skipAuth: true,
    body: { email, password },
  });

  if (dto.status === "mfa_required") {
    return { status: "mfa_required", mfaToken: dto.mfa_token! };
  }
  return {
    status: "authenticated",
    tokens: { accessToken: dto.access_token!, refreshToken: dto.refresh_token! },
    user: mapUser(dto.user!),
  };
}

// Second step of the login flow: user submits the 6-digit TOTP/SMS code
// alongside the short-lived mfaToken issued by /auth/login.
export async function loginWithTwoFactor(mfaToken: string, code: string): Promise<LoginResult> {
  const dto = await apiRequest<LoginResponseDto>("/auth/login-2fa", {
    method: "POST",
    skipAuth: true,
    body: { mfa_token: mfaToken, code },
  });
  return {
    status: "authenticated",
    tokens: { accessToken: dto.access_token!, refreshToken: dto.refresh_token! },
    user: mapUser(dto.user!),
  };
}

export async function fetchCurrentUser(): Promise<User> {
  const dto = await apiRequest<NonNullable<LoginResponseDto["user"]>>("/auth/me");
  return mapUser(dto);
}

export async function logout(): Promise<void> {
  await apiRequest<void>("/auth/logout", { method: "POST" });
}
