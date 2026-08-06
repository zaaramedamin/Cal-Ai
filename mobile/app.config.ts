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
   * Locked to light rather than 'automatic'. Dark mode is a real design pass —
   * the ring tracks, card shadows and macro hues all need re-tuning against a
   * dark ground — and shipping 'automatic' before that pass means half the
   * users see a broken-looking app.
   */
  userInterfaceStyle: 'light',

  android: {
    adaptiveIcon: {
      // Black, matching the launcher icon. The adaptive background is a flat
      // colour behind the foreground layer, so it has to agree with the mark or
      // the icon reads differently on launchers that use a round mask.
      backgroundColor: '#111216',
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
    // Reads the device's language and region. Like expo-secure-store above, the
    // plugin does nothing inside Expo Go — the module falls back to a JS
    // implementation — but it must be declared now so the first real build does
    // not silently lose locale detection.
    'expo-localization',
    [
      'expo-splash-screen',
      {
        // `paper`, so the splash is continuous with the app background instead of
        // flashing a different colour on launch.
        backgroundColor: '#F4F5F7',
        image: './assets/images/splash-icon.png',
        imageWidth: 76,
      },
    ],
    [
      // Barcode scanning. Same reasoning as the picker below: this string is
      // the only chance to say *why* before the user decides, and a bare
      // "Cal Ai would like to access the camera" is the commonest reason a
      // permission gets denied.
      'expo-camera',
      {
        cameraPermission:
          'Cal Ai uses the camera to read a barcode. The code is read on your device — no photograph is taken or stored.',
        // Never recorded, so the config plugin must not add RECORD_AUDIO to the
        // Android manifest. An unused dangerous permission is something users
        // notice and hold against an app.
        microphonePermission: false,
        recordAudioAndroid: false,
      },
    ],
    [
      // Meal photo scanning. The strings below are what iOS shows in the
      // permission dialog, and they are the only chance to explain *why* before
      // the user decides — a generic "CalAi would like to access the camera" is
      // the most common reason a permission gets denied.
      'expo-image-picker',
      {
        cameraPermission: 'CalAi uses your camera to identify the food on your plate.',
        photosPermission: 'CalAi reads a photo you choose so it can identify the food in it.',
        // We never record audio. Set false so the config plugin does not add
        // RECORD_AUDIO to the Android manifest — an unused dangerous permission
        // is something a user will notice and hold against the app.
        microphonePermission: false,
      },
    ],
  ],

  /*
   * Values the app needs at runtime, read through `expo-constants`.
   *
   * They come from the environment at *build* time, so a release build carries
   * whatever was set when it was made. `EXPO_PUBLIC_` is Expo's convention for
   * "this ends up in the bundle" — an honest prefix, because it does.
   *
   * The anon key belonging in a client bundle is not an oversight: Supabase's
   * security model assumes an attacker has it, and controls access through token
   * verification and row-level security. The database password, by contrast,
   * must never come near this file.
   */
  extra: {
    supabaseUrl: process.env.EXPO_PUBLIC_SUPABASE_URL ?? '',
    supabaseAnonKey: process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '',
  },

  experiments: {
    // Generates route types from the file tree, so a typo in a navigation path
    // is a compile error rather than a dead link found in testing.
    typedRoutes: true,
    reactCompiler: true,
  },
};

export default config;
