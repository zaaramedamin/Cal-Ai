/**
 * Expo app configuration.
 *
 * TypeScript rather than the `app.json` the template ships with, because this
 * file will need to read environment variables (the deployed API URL, the EAS
 * project id) once we reach Phase 7. A JSON file cannot do that, and discovering
 * it at deploy time means rewriting the config under pressure. It also lets the
 * config carry comments explaining *why* a value is what it is.
 */

import type { ExpoConfig } from 'expo/config';

const config: ExpoConfig = {
  name: 'CalAi',
  slug: 'calai',
  version: '0.1.0',
  orientation: 'portrait',
  icon: './assets/images/icon.png',
  // Deep-link scheme (calai://). expo-router needs it, and Phase 1 will use it
  // for the email flows.
  scheme: 'calai',

  /*
   * Locked to light rather than 'automatic'.
   *
   * The palette is a warm paper-and-ink system. Dark mode is not an inversion of
   * it — `paper` flipped to near-black loses the whole reason the palette reads
   * as food rather than fitness, and the three macro hues need different
   * lightness relationships against a dark ground to stay distinguishable.
   * That is a real design pass, so it is a Phase 6 item. Shipping 'automatic'
   * now would mean half the users seeing a broken-looking app.
   */
  userInterfaceStyle: 'light',

  android: {
    adaptiveIcon: {
      backgroundColor: '#FBF8F3',
      foregroundImage: './assets/images/android-icon-foreground.png',
      backgroundImage: './assets/images/android-icon-background.png',
      monochromeImage: './assets/images/android-icon-monochrome.png',
    },
    predictiveBackGestureEnabled: false,
  },

  web: {
    output: 'static',
    favicon: './assets/images/favicon.png',
  },

  plugins: [
    'expo-router',
    // Configures the native keystore/keychain access. It has no effect inside
    // Expo Go, which cannot apply config plugins, but it must be declared now so
    // the first real build in Phase 7 is not missing it.
    'expo-secure-store',
    [
      'expo-splash-screen',
      {
        // `paper`, so the splash is continuous with the app background instead of
        // flashing a different colour on launch.
        backgroundColor: '#FBF8F3',
        image: './assets/images/splash-icon.png',
        imageWidth: 76,
      },
    ],
  ],

  experiments: {
    // Generates route types from the file tree, so a typo in a navigation path
    // is a compile error rather than a dead link found in testing.
    typedRoutes: true,
    reactCompiler: true,
  },
};

export default config;
