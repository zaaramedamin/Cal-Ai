/**
 * Week-strip date selector — seven circles, one per day, today on the right.
 *
 * Replaces prev/next arrows: a week at a glance shows *which* days were logged
 * (filled dot) and lets the user jump straight to one, where arrows force a
 * blind walk. Days after today are not rendered as tappable — there is nothing
 * to see in the future.
 */

import { Pressable, StyleSheet, Text, View } from 'react-native';

import { addDays, localDateString } from '@/api/diary';
import { useLanguage } from '@/i18n';
import { WEEKDAY_KEYS } from '@/i18n/strings';
import { color, elevation, radius, space } from '@/theme/tokens';
import { fontFamily } from '@/theme/typography';

interface WeekStripProps {
  /** ISO date currently shown. */
  selected: string;
  onSelect: (day: string) => void;
}

export function WeekStrip({ selected, onSelect }: WeekStripProps) {
  const { t, language } = useLanguage();
  const today = localDateString();
  // The strip always ends at today: six days back through now. A calendar that
  // scrolls further back can come later; the strip covers the week that streaks
  // and averages talk about.
  const days = Array.from({ length: 7 }, (_, index) => addDays(today, index - 6));

  return (
    <View style={styles.row}>
      {days.map((day) => {
        const isSelected = day === selected;
        const isToday = day === today;
        const [year, month, date] = day.split('-').map(Number);
        const asDate = new Date(year, month - 1, date);
        const weekday = asDate.getDay();
        // Spoken as "Tuesday 23 September", not read digit by digit off the
        // ISO string "2026-09-23" the label used to carry.
        const spoken = asDate.toLocaleDateString(language, {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
        });

        return (
          <Pressable
            key={day}
            onPress={() => onSelect(day)}
            accessibilityRole="button"
            accessibilityState={{ selected: isSelected }}
            accessibilityLabel={t('week.showDay', { date: spoken })}
            style={styles.dayHit}
          >
            <Text style={[styles.letter, isSelected && styles.letterSelected]}>
              {t(WEEKDAY_KEYS[weekday])}
            </Text>
            <View
              style={[
                styles.circle,
                // Today keeps a marker even when another day is selected —
                // otherwise scrolling back loses your anchor in the week.
                isToday && !isSelected && styles.circleToday,
                isSelected && styles.circleSelected,
              ]}
            >
              <Text style={[styles.date, isSelected && styles.dateSelected]}>{date}</Text>
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  dayHit: {
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.xs,
    minWidth: 40,
  },
  letter: {
    fontFamily: fontFamily.semiBold,
    fontSize: 11,
    color: color.inkMuted,
  },
  letterSelected: { color: color.accent },
  circle: {
    width: 38,
    height: 38,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.surface,
  },
  circleSelected: { backgroundColor: color.accent, ...elevation.mid },
  date: {
    fontFamily: fontFamily.semiBold,
    fontSize: 14,
    color: color.inkMuted,
  },
  circleToday: { borderWidth: 1.5, borderColor: color.accentTintStrong },
  dateSelected: { color: color.onDark },
});
