/**
 * Water bindings. Mirrors `backend/app/api/v1/water.py`.
 */

import { apiRequest } from './client';

export interface WaterEntry {
  id: string;
  millilitres: number;
  logged_at: string;
}

export interface WaterDay {
  day: string;
  total_ml: number;
  /**
   * Null means the user has not set a goal — not zero, and not a default.
   *
   * The card shows the intake with no denominator in that case. Every "two
   * litres a day" figure is a rule of thumb, and this app does not print rules
   * of thumb as somebody's personal target.
   */
  goal_ml: number | null;
  entries: WaterEntry[];
}

export function getWaterDay(day?: string): Promise<WaterDay> {
  const suffix = day ? `?day=${day}` : '';
  return apiRequest<WaterDay>(`/api/v1/water${suffix}`, { authenticated: true });
}

/** Log a drink. Returns the whole day, so the client never sums it itself. */
export function logWater(millilitres: number, day?: string): Promise<WaterDay> {
  return apiRequest<WaterDay>('/api/v1/water', {
    method: 'POST',
    authenticated: true,
    body: { millilitres, day },
  });
}

export function undoWater(entryId: string): Promise<void> {
  return apiRequest<void>(`/api/v1/water/${entryId}`, {
    method: 'DELETE',
    authenticated: true,
  });
}

export function setWaterGoal(goalMl: number | null): Promise<WaterDay> {
  return apiRequest<WaterDay>('/api/v1/water/goal', {
    method: 'PUT',
    authenticated: true,
    body: { goal_ml: goalMl },
  });
}
