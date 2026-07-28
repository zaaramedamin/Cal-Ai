/**
 * Profile, targets and weight bindings.
 *
 * Mirrors `backend/app/schemas/profile.py`. Phase 3 generates these from the
 * OpenAPI schema; until then the duplication is deliberate and visible.
 */

import { apiRequest } from './client';

export type Sex = 'male' | 'female';
export type ActivityLevel = 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active';
export type Goal = 'cut' | 'maintain' | 'lean_bulk' | 'bulk';

export interface MacroTargets {
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

export interface DerivationStep {
  label: string;
  value: string;
  detail: string;
}

export interface Targets {
  bmr: number;
  tdee: number;
  calories: number;
  uncapped_calories: number;
  macros: MacroTargets;
  was_clamped: boolean;
  warnings: string[];
  derivation: DerivationStep[];
}

export interface Profile {
  sex: Sex;
  birth_date: string;
  height_cm: number;
  activity_level: ActivityLevel;
  goal: Goal;
  target_weight_kg: number | null;
  /** kg per week, always positive — the goal supplies the direction.
      Null only for profiles saved before the pace picker existed. */
  weekly_rate_kg: number | null;
  timezone: string;
  onboarding_completed_at: string | null;
}

export interface ProfileWithTargets {
  profile: Profile;
  current_weight_kg: number;
  targets: Targets;
}

export interface ProfileInput {
  sex: Sex;
  birth_date: string;
  height_cm: number;
  weight_kg: number;
  activity_level: ActivityLevel;
  goal: Goal;
  target_weight_kg?: number | null;
  /** Omitted or null means "use the default pace for this goal". */
  weekly_rate_kg?: number | null;
  timezone: string;
}

export function getProfile(): Promise<ProfileWithTargets> {
  return apiRequest<ProfileWithTargets>('/api/v1/profile', { authenticated: true });
}

export function saveProfile(input: ProfileInput): Promise<ProfileWithTargets> {
  return apiRequest<ProfileWithTargets>('/api/v1/profile', {
    method: 'PUT',
    body: input,
    authenticated: true,
  });
}

export interface WeightEntry {
  id: string;
  weight_kg: number;
  recorded_on: string;
}

export function logWeight(weightKg: number): Promise<WeightEntry> {
  return apiRequest<WeightEntry>('/api/v1/profile/weight', {
    method: 'POST',
    body: { weight_kg: weightKg },
    authenticated: true,
  });
}

/**
 * The device's IANA timezone, sent once at onboarding.
 *
 * The server decides which local day a diary entry belongs to, but it needs to
 * know where the user is to do that. `Intl` is the only portable source on
 * React Native; UTC is the honest fallback rather than guessing from an offset,
 * which cannot distinguish zones that share one.
 */
export function deviceTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}
