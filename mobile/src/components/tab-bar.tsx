/**
 * The floating tab bar.
 *
 * A pill that hovers over the content rather than a slab welded to the bottom
 * edge, with the logging action as a separate circle beside it.
 *
 * **Why the action sits outside the pill.** A tab bar answers "where am I";
 * every item in it is a place. Logging a meal is not a place, and putting it
 * inside the pill would make one of five identical-looking items behave
 * completely differently — you tap it expecting a screen and get a sheet. Held
 * apart, in a different shape and the only filled colour on the bar, it reads as
 * a button because it looks like one. It is also the most-used control in the
 * app, and the corner your thumb reaches most easily.
 *
 * **The action opens a menu, it does not jump straight to the camera.** There
 * are four ways to log — a photo, a saved meal, the catalogue, a search — and
 * only one of them is the camera. Wiring the button directly to `/scan` made the
 * other three reachable only from a second button on the dashboard, which is why
 * two plus-buttons briefly existed on one screen. One button, four routes.
 *
 * **Why a custom component and not `tabBarStyle`.** The pill has to float clear
 * of the safe-area inset, and the action button has to sit outside the pill's
 * own bounds. Neither is expressible through the options object, which styles
 * one full-width container.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { slotForNow } from '@/api/diary';
import { currentSelectedDay } from '@/features/diary/selected-day';
import { useT } from '@/i18n';
import { color, elevation, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

/**
 * How much room a scrolling screen must leave at its bottom.
 *
 * Exported because the bar floats *over* the content: without this the last card
 * on every tab sits underneath it, which looks like a rendering bug and hides a
 * control. Derived here rather than guessed at each call site, so changing the
 * bar's size cannot silently clip three screens.
 *
 * The safe-area inset is added by the screen, since only it knows its own.
 */
export const TAB_DOCK_HEIGHT = 60 + space.md * 2;

/** Icons per route. Kept here so the tab bar owns its own presentation. */
const ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  index: 'home',
  progress: 'stats-chart',
  settings: 'person',
};

export function FloatingTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const t = useT();
  const [menuOpen, setMenuOpen] = useState(false);

  /** Whatever day the diary is showing, so + on Tuesday logs into Tuesday. */
  function go(
    pathname: '/scan' | '/meals' | '/catalogue' | '/search' | '/barcode',
    withSlot = false,
  ) {
    setMenuOpen(false);
    const day = currentSelectedDay();
    router.push(
      withSlot
        ? { pathname, params: { day, slot: slotForNow() } }
        : { pathname, params: { day } },
    );
  }

  return (
    <>
      {menuOpen && (
        <Animated.View
          entering={FadeIn.duration(150)}
          exiting={FadeOut.duration(120)}
          style={StyleSheet.absoluteFill}
        >
          <Pressable
            onPress={() => setMenuOpen(false)}
            accessibilityLabel={t('a11y.closeMenu')}
            style={styles.scrim}
          />
        </Animated.View>
      )}

      {menuOpen && (
        <Animated.View
          entering={FadeIn.duration(160)}
          exiting={FadeOut.duration(120)}
          style={[styles.menu, { bottom: Math.max(insets.bottom, space.md) + 84 }]}
        >
          <MenuRow icon="camera" label={t('home.scanMeal')} onPress={() => go('/scan')} />
          {/* Ordered above search on purpose. The catalogue is the path that
              works for someone who does not already know what USDA calls their
              food, which is most people most of the time; search is the escape
              hatch for the thing the catalogue does not carry. */}
          <MenuRow icon="restaurant" label={t('home.myMeals')} onPress={() => go('/meals')} />
          <MenuRow
            icon="nutrition"
            label={t('home.ingredients')}
            onPress={() => go('/catalogue', true)}
          />
          <MenuRow
            icon="barcode"
            label={t('home.scanBarcode')}
            onPress={() => go('/barcode', true)}
          />
          <MenuRow
            icon="search"
            label={t('home.searchFood')}
            onPress={() => go('/search', true)}
          />
        </Animated.View>
      )}

      <View
        style={[styles.dock, { paddingBottom: Math.max(insets.bottom, space.md) }]}
        pointerEvents="box-none"
      >
      <View style={styles.pill} accessibilityRole="tablist">
        {state.routes.map((route, index) => {
          const { options } = descriptors[route.key];
          const label = options.title ?? route.name;
          const focused = state.index === index;

          return (
            <Pressable
              key={route.key}
              // "tab" rather than "button", so a screen reader says "Home, tab,
              // 1 of 3" and the user knows they are choosing a place.
              accessibilityRole="tab"
              accessibilityState={{ selected: focused }}
              accessibilityLabel={label}
              // No hitSlop. Each tab is already ~48pt tall, and a 44pt slop on
              // every side overlapped the neighbouring tabs.
              onPress={() => {
                const event = navigation.emit({
                  type: 'tabPress',
                  target: route.key,
                  canPreventDefault: true,
                });
                // Respecting `defaultPrevented` is what lets a screen intercept
                // its own tab press — tapping the active tab to scroll to top,
                // for instance. Navigating unconditionally would break that.
                if (!focused && !event.defaultPrevented) {
                  navigation.navigate(route.name);
                }
              }}
              style={[styles.tab, focused && styles.tabActive]}
            >
              <Ionicons
                name={focused ? (ICONS[route.name] ?? 'ellipse') : outline(ICONS[route.name])}
                size={20}
                color={focused ? color.accent : color.inkMuted}
              />
              <Text style={[styles.label, focused && styles.labelActive]}>{label}</Text>
            </Pressable>
          );
        })}
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel={menuOpen ? t('a11y.closeLogMenu') : t('a11y.logFood')}
        accessibilityState={{ expanded: menuOpen }}
        // No hitSlop: the button is 58pt already. A 44pt slop reached ~36pt into
        // the pill beside it, and because this button is drawn on top, a tap on
        // the right-hand side of the last tab opened the log menu instead.
        onPress={() => setMenuOpen((open) => !open)}
        style={({ pressed }) => [styles.action, pressed && styles.actionPressed]}
      >
        <Ionicons name={menuOpen ? 'close' : 'add'} size={30} color={color.onDark} />
        </Pressable>
      </View>
    </>
  );
}

function MenuRow({
  icon,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={styles.menuRow}>
      {/* The label is a tap target too */}
      <View style={styles.menuLabelPill}>
        <Text style={styles.menuLabel}>{label}</Text>
      </View>
      <View style={styles.menuIcon}>
        <Ionicons name={icon} size={22} color={color.onDark} />
      </View>
    </Pressable>
  );
}

/**
 * The outline variant of a tab icon, for tabs that are not selected.
 *
 * Filled for the current tab and outlined for the rest, so the selection reads
 * by shape as well as colour — colour alone is exactly what a colour-blind user
 * cannot see.
 */
function outline(name: keyof typeof Ionicons.glyphMap | undefined): keyof typeof Ionicons.glyphMap {
  const candidate = `${name ?? 'ellipse'}-outline`;
  return candidate in Ionicons.glyphMap
    ? (candidate as keyof typeof Ionicons.glyphMap)
    : (name ?? 'ellipse');
}

const styles = StyleSheet.create({
  dock: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
  },
  pill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    backgroundColor: color.surface,
    borderRadius: radius.pill,
    paddingVertical: space.xs + 2,
    paddingHorizontal: space.xs,
    borderWidth: 1,
    borderColor: color.hairline,
    ...elevation.glass,
  },
  tab: {
    alignItems: 'center',
    gap: 3,
    paddingVertical: space.xs + 2,
    paddingHorizontal: space.md + 2,
    borderRadius: radius.pill,
  },
  tabActive: { backgroundColor: color.accentTintStrong },
  label: {
    fontFamily: fontFamily.semiBold,
    fontSize: 11,
    // inkMuted, not inkFaint: the faint grey is 2.2:1 and the labels of the
    // tabs you are *not* on are exactly the ones you need to read.
    color: color.inkMuted,
  },
  labelActive: { color: color.accent, fontFamily: fontFamily.bold },
  action: {
    width: 58,
    height: 58,
    borderRadius: 29,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.accent,
    ...elevation.accentGlow,
  },
  actionPressed: { opacity: 0.88, transform: [{ scale: 0.95 }] },

  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: color.scrim },
  menu: { position: 'absolute', right: space.md, gap: space.sm, alignItems: 'flex-end' },
  menuRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  menuLabelPill: {
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    ...elevation.mid,
  },
  menuLabel: { ...text.label, fontSize: 13, color: color.ink },
  menuIcon: {
    width: 46,
    height: 46,
    borderRadius: 23,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.accent,
    ...elevation.accentGlow,
  },
});

