/**
 * Fallback for any path that no longer exists.
 *
 * This is not decoration — Expo Go reopens the last URL it showed, and the
 * redesign deleted routes (`/diary`, `/recipes/index`) that a device may still
 * have in history. Without this file those launches land on expo-router's
 * built-in "Unmatched Route" dead end; with it they land on the dashboard.
 *
 * A plain redirect rather than a designed 404 page, because inside a mobile
 * app there is nothing useful a user can do with "this screen does not exist"
 * — the only sensible action is the one we take for them.
 */

import { Redirect } from 'expo-router';

import { HOME } from '@/routes';

export default function NotFound() {
  return <Redirect href={HOME} />;
}
