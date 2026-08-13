/**
 * Water intake, on the dashboard.
 *
 * **Optimistic, because the alternative is worse than a rare wrong number.**
 * Tapping a glass is the fastest interaction in the app — people log four in a
 * row while filling a bottle — and a spinner between each one makes it feel
 * broken. The total updates immediately and the server's answer replaces it a
 * moment later; if the request fails, the tap is rolled back and the user sees
 * the true figure. Wrong for 200ms beats sluggish forever.
 *
 * **No goal is a first-class state.** When the user has not set a target the
 * card shows what they drank and nothing else — no ring, no percentage, no
 * "of 2,000 ml". Inventing a denominator would be the same mistake as inventing
 * a calorie count, and this is the screen where it would be easiest to do
 * without anyone noticing.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { type WaterDay, logWater, undoWater } from '@/api/water';
import { Card } from '@/components/card';
import { useT } from '@/i18n';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { fontFamily, text } from '@/theme/typography';

/**
 * The three sizes offered.
 *
 * A glass, a mug and a bottle — objects rather than numbers, because nobody
 * measures what they drink. The millilitre figures are conventional serving
 * sizes, which is a claim about crockery and not about nutrition.
 */
const QUICK_ADDS = [
  { ml: 250, icon: 'water-outline' as const },
  { ml: 330, icon: 'cafe-outline' as const },
  { ml: 500, icon: 'flask-outline' as const },
];

export function WaterCard({ day, onChange }: { day: WaterDay; onChange: (day: WaterDay) => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  const add = useCallback(
    async (millilitres: number) => {
      if (busy) return;
      setBusy(true);

      const previous = day;
      // Optimistic. The id is a placeholder the server's response replaces —
      // it is never sent anywhere, only used as a React key for the instant
      // between the tap and the reply.
      onChange({
        ...day,
        total_ml: day.total_ml + millilitres,
        entries: [
          ...day.entries,
          { id: `pending-${Date.now()}`, millilitres, logged_at: new Date().toISOString() },
        ],
      });

      try {
        onChange(await logWater(millilitres, day.day));
      } catch {
        // Put the real figure back. Silently: the user tapped a glass, and a
        // modal about it would be a bigger interruption than the miscount.
        onChange(previous);
      } finally {
        setBusy(false);
      }
    },
    [busy, day, onChange],
  );

  const undoLast = useCallback(async () => {
    const last = day.entries[day.entries.length - 1];
    if (!last || busy || last.id.startsWith('pending-')) return;

    setBusy(true);
    const previous = day;
    onChange({
      ...day,
      total_ml: Math.max(0, day.total_ml - last.millilitres),
      entries: day.entries.slice(0, -1),
    });

    try {
      await undoWater(last.id);
    } catch {
      onChange(previous);
    } finally {
      setBusy(false);
    }
  }, [busy, day, onChange]);

  const litres = (day.total_ml / 1000).toFixed(day.total_ml % 1000 === 0 ? 0 : 1);
  const progress = day.goal_ml ? Math.min(1, day.total_ml / day.goal_ml) : null;

  return (
    <Card style={styles.card}>
      <View style={styles.head}>
        <View style={styles.headLeft}>
          <View style={styles.iconCircle}>
            <Ionicons name="water" size={16} color={color.water} />
          </View>
          <Text style={text.label}>{t('water.title')}</Text>
        </View>

        {day.entries.length > 0 && (
          <Pressable onPress={() => void undoLast()} hitSlop={HIT_SLOP_MIN} disabled={busy}>
            <Text style={styles.undo}>{t('water.undo')}</Text>
          </Pressable>
        )}
      </View>

      <View style={styles.readout}>
        <Text style={styles.total}>{litres}</Text>
        <Text style={styles.unit}>
          {day.goal_ml
            ? t('water.ofGoal', { goal: (day.goal_ml / 1000).toFixed(1) })
            : t('water.litres')}
        </Text>
      </View>

      {/* Only drawn when there is a real target to draw it against. */}
      {progress !== null && (
        <View style={styles.track}>
          <View style={[styles.fill, { width: `${progress * 100}%` }]} />
        </View>
      )}

      <View style={styles.adds}>
        {QUICK_ADDS.map((option) => (
          <Pressable
            key={option.ml}
            onPress={() => void add(option.ml)}
            disabled={busy}
            hitSlop={HIT_SLOP_MIN}
            accessibilityRole="button"
            accessibilityLabel={t('water.addLabel', { ml: option.ml })}
            style={({ pressed }) => [styles.add, pressed && styles.addPressed]}
          >
            <Ionicons name={option.icon} size={18} color={color.water} />
            <Text style={styles.addText}>+{option.ml}</Text>
          </Pressable>
        ))}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.md + 2, paddingVertical: space.lg },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headLeft: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  iconCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: color.waterTint,
    alignItems: 'center',
    justifyContent: 'center',
  },
  undo: { ...text.bodyMuted, fontSize: 13, color: color.water, fontFamily: fontFamily.semiBold },

  readout: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.sm,
    paddingVertical: space.xs,
  },
  total: {
    ...text.numeric,
    fontSize: 38,
    lineHeight: 44,
    color: color.ink,
    fontFamily: fontFamily.extraBold,
  },
  unit: { ...text.bodyMuted, fontSize: 14, color: color.inkMuted },

  track: {
    height: 8,
    borderRadius: radius.pill,
    backgroundColor: color.wash,
    overflow: 'hidden',
  },
  fill: { height: '100%', borderRadius: radius.pill, backgroundColor: color.water },

  adds: { flexDirection: 'row', gap: space.sm, marginTop: space.xs },
  add: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    paddingVertical: space.md,
    paddingHorizontal: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.waterTint,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  addPressed: { opacity: 0.8, transform: [{ scale: 0.97 }] },
  addText: { ...text.label, fontSize: 13, color: color.ink },
});
