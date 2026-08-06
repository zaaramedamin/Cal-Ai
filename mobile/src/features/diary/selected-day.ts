/**
 * Which day the diary is showing.
 *
 * Module-level for one specific reason: the logging button lives in the tab bar,
 * which is rendered outside every screen and cannot see the dashboard's state.
 * Without this, tapping + while looking at Tuesday would log into today —
 * silently, and only noticed when the numbers on Tuesday never move.
 *
 * Deliberately tiny. It holds one string and has no notion of the diary itself;
 * the dashboard remains the only thing that decides what a day *means*.
 */

import { useSyncExternalStore } from 'react';

/** Today in the device's local calendar, as `YYYY-MM-DD`. */
export function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const date = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${date}`;
}

let selected = today();
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

export function setSelectedDay(day: string): void {
  if (day === selected) return;
  selected = day;
  emit();
}

/**
 * Reset to today.
 *
 * Called when the dashboard unmounts, so a day chosen on Tuesday does not still
 * be the target a week later. A stale value here is a wrong diary entry.
 */
export function resetSelectedDay(): void {
  setSelectedDay(today());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function snapshot(): string {
  return selected;
}

export function useSelectedDay(): string {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}

/** For callers outside React — the tab bar's press handler. */
export function currentSelectedDay(): string {
  return selected;
}
