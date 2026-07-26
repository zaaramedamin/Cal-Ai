/**
 * Health endpoint binding.
 *
 * Hand-written for Phase 0. From Phase 3 these types come from the generated
 * OpenAPI client instead — see the note at the top of `client.ts`. The literal
 * unions here mirror the `Literal[...]` declarations on the Python side, which
 * is exactly the duplication code generation will remove.
 */

import { apiGet } from './client';

export type HealthStatus = 'ok' | 'degraded';
export type DbStatus = 'ok' | 'unreachable';

export interface Health {
  status: HealthStatus;
  version: string;
  db: DbStatus;
}

export function getHealth(): Promise<Health> {
  return apiGet<Health>('/api/v1/health');
}
