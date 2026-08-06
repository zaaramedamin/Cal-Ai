/**
 * The signed-in tab shell: Home, Progress, Settings.
 *
 * Tabs rather than a stack of buttons because the three destinations are peers
 * the user moves between constantly — the diary is not "above" progress. The
 * logging action deliberately is NOT a tab: it is a floating button on the
 * screens where logging makes sense, because a tab that triggers an action
 * rather than showing a place breaks the mental model of a tab bar.
 */

import { Tabs } from 'expo-router';

import { FloatingTabBar } from '@/components/tab-bar';
import { useT } from '@/i18n';
import { color } from '@/theme/tokens';

export default function TabsLayout() {
  // The bar renders `options.title`, so these titles are the visible labels
  // under the icons rather than metadata.
  const t = useT();

  return (
    <Tabs
      // The bar is a floating pill with the logging action beside it, which no
      // combination of `tabBarStyle` options can express — see components/tab-bar.
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: color.canvas },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t('nav.home') }} />
      <Tabs.Screen name="progress" options={{ title: t('nav.progress') }} />
      <Tabs.Screen name="settings" options={{ title: t('nav.settings') }} />
    </Tabs>
  );
}
