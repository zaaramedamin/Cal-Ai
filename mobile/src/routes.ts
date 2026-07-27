/**
 * Route constants that paper over a typed-routes bug.
 *
 * SDK 54's typed-route generator does not emit `'/'` when the only index route
 * lives inside a group — it offers `'/(tabs)/index'` instead. But the runtime
 * router never serves explicit `/index` paths, so navigating to the "typed"
 * spelling lands on Unmatched Route. Types and runtime disagree; the runtime
 * wins, so we navigate to `'/'` and cast past the generated union.
 *
 * Every redirect to the dashboard goes through this constant so the workaround
 * lives in exactly one place and can be deleted the day the generator is fixed.
 */

import type { Href } from 'expo-router';

export const HOME = '/' as Href;
