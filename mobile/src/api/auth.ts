/**
 * Auth endpoint bindings.
 *
 * Hand-written for now; Phase 3 generates these from the OpenAPI schema. The
 * shapes mirror `backend/app/schemas/auth.py` — that duplication is exactly what
 * code generation will remove.
 */

import { apiRequest } from './client';

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface AuthResult extends TokenPair {
  user: User;
}

export function register(email: string, password: string): Promise<AuthResult> {
  return apiRequest<AuthResult>('/api/v1/auth/register', {
    method: 'POST',
    body: { email, password },
  });
}

export function login(email: string, password: string): Promise<AuthResult> {
  return apiRequest<AuthResult>('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  });
}

/**
 * Not marked `authenticated`: it carries the refresh token in the body and must
 * never trigger the client's refresh-on-401 path, which would recurse.
 */
export function refreshTokens(refreshToken: string): Promise<TokenPair> {
  return apiRequest<TokenPair>('/api/v1/auth/refresh', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  });
}

export function logout(refreshToken: string): Promise<void> {
  return apiRequest<void>('/api/v1/auth/logout', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  });
}

export function getCurrentUser(): Promise<User> {
  return apiRequest<User>('/api/v1/users/me', { authenticated: true });
}

export interface PasswordResetRequested {
  message: string;
  /** Development only — the backend never populates this outside development. */
  debug_reset_token: string | null;
}

export function requestPasswordReset(email: string): Promise<PasswordResetRequested> {
  return apiRequest<PasswordResetRequested>('/api/v1/auth/password-reset/request', {
    method: 'POST',
    body: { email },
  });
}

export function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  return apiRequest<void>('/api/v1/auth/password-reset/confirm', {
    method: 'POST',
    body: { token, new_password: newPassword },
  });
}
