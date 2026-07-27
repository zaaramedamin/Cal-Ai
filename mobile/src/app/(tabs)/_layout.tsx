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

import { cardShadow, color } from '@/theme/tokens';
import { fontFamily } from '@/theme/typography';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: color.ink,
        tabBarInactiveTintColor: color.inkFaint,
        tabBarStyle: {
          backgroundColor: color.surface,
          borderTopWidth: 0,
          ...cardShadow,
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
