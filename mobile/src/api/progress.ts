/**
 * Progress bindings. Mirrors `backend/app/api/v1/progress.py`.
 */

import { apiRequest } from './client';

export interface DayCalories {
  day: string;
  kcal: number;
}

export interface WeightPoint {
  recorded_on: string;
  weight_kg: number;
}

export interface Progress {
  streak_days: number;
  logged_today: boolean;
  last_7_days: DayCalories[];
  weekly_average_kcal: number;
  /** Daily target the week chart draws its reference line at. 0 before any weigh-in. */
  target_calories: number;
  current_weight_kg: number | null;
  target_weight_kg: number | null;
  weight_series: WeightPoint[];
  bmi: number | null;
  bmi_category: 'underweight' | 'healthy' | 'overweight' | 'obese' | null;
}

export function getProgress(): Promise<Progress> {
  return apiRequest<Progress>('/api/v1/progress', { authenticated: true });
}
