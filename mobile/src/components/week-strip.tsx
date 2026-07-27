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
import { color, radius, space } from '@/theme/tokens';
import { fontFamily } from '@/theme/typography';

interface WeekStripProps {
  /** ISO date currently shown. */
  selected: string;
  onSelect: (day: string) => void;
}

const DAY_LETTERS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

export function WeekStrip({ selected, onSelect }: WeekStripProps) {
  const today = localDateString();
  // The strip always ends at today: six days back through now. A calendar that
  // scrolls further back can come later; the strip covers the week that streaks
  // and averages talk about.
  const days = Array.from({ length: 7 }, (_, index) => addDays(today, index - 6));

  return (
    <View style={styles.row}>
      {days.map((day) => {
        const isSelected = day === selected;
        const [year, month, date] = day.split('-').map(Number);
        const weekday = new Date(year, month - 1, date).getDay();

        return (
          <Pressable
            key={day}
            onPress={() => onSelect(day)}
            accessibilityRole="button"
            accessibilityState={{ selected: isSelected }}
            accessibilityLabel={`Show ${day}`}
            style={styles.dayHit}
          >
            <Text style={[styles.letter, isSelected && styles.letterSelected]}>
              {DAY_LETTERS[weekday]}
            </Text>
            <View style={[styles.circle, isSelected && styles.circleSelected]}>
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
    color: color.inkFaint,
  },
  letterSelected: { color: color.ink },
  circle: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: color.surface,
  },
  circleSelected: { backgroundColor: color.ink },
  date: {
    fontFamily: fontFamily.semiBold,
    fontSize: 14,
    color: color.inkMuted,
  },
  dateSelected: { color: color.onDark },
});
