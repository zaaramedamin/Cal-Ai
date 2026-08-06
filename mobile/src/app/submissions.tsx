/**
 * Foods you have offered to the shared database, and what happened to them.
 *
 * **Why a rejection shows its reason.** A refusal with no explanation is the
 * fastest way to stop somebody contributing again — they cannot tell whether
 * they made a fixable mistake or whether the whole idea was unwelcome. The
 * backend requires a note on every rejection precisely so this screen has
 * something to show.
 *
 * The screening verdict is *not* shown while a submission is still pending. It
 * is advice for the reviewer, and telling an author "the AI thinks this is
 * suspect" before a human has looked would read as a decision that has not been
 * made.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { type ReviewStatus, type Submission, mySubmissions } from '@/api/review';
import { BackHeader } from '@/components/back-header';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { useT } from '@/i18n';
import type { StringKey } from '@/i18n/strings';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const BADGE: Record<
  ReviewStatus,
  { icon: keyof typeof Ionicons.glyphMap; tint: string; label: StringKey }
> = {
  private: { icon: 'lock-closed', tint: color.inkFaint, label: 'submit.statusPrivate' },
  pending: { icon: 'time-outline', tint: color.warning, label: 'submit.statusPending' },
  approved: { icon: 'checkmark-circle', tint: color.positive, label: 'submit.statusApproved' },
  rejected: { icon: 'close-circle', tint: color.danger, label: 'submit.statusRejected' },
};

export default function SubmissionsScreen() {
  const t = useT();
  const [items, setItems] = useState<Submission[] | null>(null);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      void mySubmissions()
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
        <Text style={text.title}>{t('submit.title')}</Text>

        {items.length === 0 ? (
          <Text style={[text.bodyMuted, styles.empty]}>{t('submit.empty')}</Text>
        ) : (
          items.map((item) => {
            const badge = BADGE[item.review_status];
            return (
              <Card key={item.food.id} style={styles.card}>
                <View style={styles.head}>
                  <View style={styles.headText}>
                    <Text style={text.label}>{item.food.name}</Text>
                    {item.food.brand && (
                      <Text style={text.bodyMuted}>{item.food.brand}</Text>
                    )}
                  </View>
                  <View style={[styles.badge, { backgroundColor: `${badge.tint}22` }]}>
                    <Ionicons name={badge.icon} size={14} color={badge.tint} />
                    <Text style={[styles.badgeText, { color: badge.tint }]}>
                      {t(badge.label)}
                    </Text>
                  </View>
                </View>

                {/* Only after a decision. See the note at the top of this file. */}
                {item.review_note && (
                  <View style={styles.note}>
                    <Text style={styles.noteText}>{item.review_note}</Text>
                  </View>
                )}

                {item.review_status === 'pending' && (
                  <Text style={styles.hint}>{t('submit.pendingHint')}</Text>
                )}
                {item.review_status === 'approved' && (
                  <Text style={styles.hint}>{t('submit.approvedHint')}</Text>
                )}
                {item.review_status === 'rejected' && (
                  <Text style={styles.hint}>{t('submit.rejectedHint')}</Text>
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
