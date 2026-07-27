# Expo HAS CHANGED

Read the exact versioned docs at https://docs.expo.dev/versions/v54.0.0/ before writing any code.

This project is pinned to **SDK 54**, not the latest SDK. That is deliberate: the target test
device runs Expo Go 54, and Expo Go only ever supports a single SDK version. Do not "helpfully"
upgrade Expo, React Native or React — it will break loading on the device.

Revisit this when the project moves to a development build (planned for Phase 7), at which point
Expo Go stops being the constraint and the SDK can move forward again.

Note that expo-router forked React Navigation and no longer re-exports it. Every navigation API
comes from `expo-router` entry points, never from `@react-navigation/*`.
