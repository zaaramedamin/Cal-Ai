/**
 * Foods you said were wrong, and what came of it.
 *
 * Deliberately parallel to `submissions.tsx`, and for the same reason: a report
 * answered with silence teaches people not to file another one, and the whole
 * value of the feature is that somebody bothers to check a label against what
 * the app shows.
 *
 * Both outcomes are shown as an answer rather than a verdict on the reporter.
 * "No change made" comes with what was actually done — checked against the
 * source, and it matches — because a dismissal with no explanation reads as
 * having been ignored, which is the same lesson as no reply at all.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { type FoodReport, myReports } from '@/api/review';
import { BackHeader } from '@/components/back-header';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { useT } from '@/i18n';
import type { StringKey } from '@/i18n/strings';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const BADGE: Record<
  FoodReport['status'],
  { icon: keyof typeof Ionicons.glyphMap; tint: string; label: StringKey }
> = {
  open: { icon: 'time-outline', tint: color.warning, label: 'report.statusOpen' },
  accepted: { icon: 'checkmark-circle', tint: color.positive, label: 'report.statusAccepted' },
  dismissed: { icon: 'remove-circle', tint: color.inkFaint, label: 'report.statusDismissed' },
};

/** What was done, in the reporter's words rather than the enum's. */
const RESOLUTION: Record<'corrected' | 'withdrawn', StringKey> = {
  corrected: 'report.resolvedCorrected',
  withdrawn: 'report.resolvedWithdrawn',
};

const REASON: Record<FoodReport['reason'], StringKey> = {
  wrong_numbers: 'report.wrongNumbers',
  wrong_name: 'report.wrongName',
  duplicate: 'report.duplicate',
  not_food: 'report.notFood',
  other: 'report.other',
};

export default function ReportsScreen() {
  const t = useT();
  const [items, setItems] = useState<FoodReport[] | null>(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      void myReports()
        .then((rows) => {
          if (!cancelled) setItems(rows);
        })
        .catch(() => {
          if (!cancelled) setItems([]);
        });
      return () => {
        cancelled = true;
      };
    }, []),
  );

  if (items === null) {
    return (
      <Screen>
        <View style={styles.centered}>
          <ActivityIndicator color={color.ink} />
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <BackHeader />
        <Text style={text.title}>{t('report.mine')}</Text>

        {items.length === 0 ? (
          <Text style={[text.bodyMuted, styles.empty]}>{t('report.empty')}</Text>
        ) : (
          items.map((item) => {
            const badge = BADGE[item.status];
            return (
              <Card key={item.id} style={styles.card}>
                <View style={styles.head}>
                  <View style={styles.headText}>
                    <Text style={text.label}>{item.food.name}</Text>
                    <Text style={text.bodyMuted}>{t(REASON[item.reason])}</Text>
                  </View>
                  <View style={[styles.badge, { backgroundColor: `${badge.tint}22` }]}>
                    <Ionicons name={badge.icon} size={14} color={badge.tint} />
                    <Text style={[styles.badgeText, { color: badge.tint }]}>
                      {t(badge.label)}
                    </Text>
                  </View>
                </View>

                {/* What you said, kept visible. A report resolved weeks later is
                    unreadable without it — nobody remembers which of four foods
                    they said what about. */}
                {item.note && (
                  <View style={styles.note}>
                    <Text style={styles.noteText}>{item.note}</Text>
                  </View>
                )}

                {item.resolution && (
                  <Text style={styles.hint}>{t(RESOLUTION[item.resolution])}</Text>
                )}
                {item.status === 'dismissed' && !item.resolution_note && (
                  <Text style={styles.hint}>{t('report.dismissedHint')}</Text>
                )}
                {item.resolution_note && (
                  <Text style={styles.hint}>{item.resolution_note}</Text>
                )}
              </Card>
            );
          })
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { paddingTop: space.lg, paddingBottom: space.xxl, gap: space.md },
  empty: { marginTop: space.lg, lineHeight: 22 },

  card: { gap: space.md, paddingVertical: space.lg },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  headText: { flex: 1, gap: 2 },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
  },
  badgeText: { ...text.label, fontSize: 11 },

  note: {
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.wash,
    borderLeftWidth: 3,
    borderLeftColor: color.inkFaint,
  },
  noteText: { ...text.body, fontSize: 13, lineHeight: 19 },
  hint: { ...text.bodyMuted, fontSize: 12, lineHeight: 17 },
});
