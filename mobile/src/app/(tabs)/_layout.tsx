/**
 * The signed-in tab shell: Home, Progress, Settings.
 *
 * Tabs rather than a stack of buttons because the three destinations are peers
 * the user moves between constantly — the diary is not "above" progress. The
 * logging action deliberately is NOT a tab: it is a floating button on the
 * screens where logging makes sense, because a tab that triggers an action
 * rather than showing a place breaks the mental model of a tab bar.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

import { color, elevation, radius, space } from '@/theme/tokens';
import { fontFamily } from '@/theme/typography';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        // Indigo marks the active tab, matching every other 'this is live'
        // signal in the app. A black active tab is indistinguishable from the
        // label text beside it.
        tabBarActiveTintColor: color.accent,
        tabBarInactiveTintColor: color.inkFaint,
        tabBarStyle: {
          backgroundColor: color.surface,
          borderTopWidth: 0,
          height: 64,
          paddingTop: space.sm,
          paddingBottom: space.sm,
          borderTopLeftRadius: radius.lg,
          borderTopRightRadius: radius.lg,
          ...elevation.mid,
        },
        tabBarLabelStyle: {
          fontFamily: fontFamily.semiBold,
          fontSize: 11,
        },
        sceneStyle: { backgroundColor: color.canvas },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color: tint, size }) => (
            <Ionicons name="home" size={size} color={tint} />
          ),
        }}
      />
      <Tabs.Screen
        name="progress"
        options={{
          title: 'Progress',
          tabBarIcon: ({ color: tint, size }) => (
            <Ionicons name="stats-chart" size={size} color={tint} />
          ),
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarIcon: ({ color: tint, size }) => (
            <Ionicons name="settings-sharp" size={size} color={tint} />
          ),
        }}
      />
    </Tabs>
  );
}
