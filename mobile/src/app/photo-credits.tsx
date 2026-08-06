/**
 * Who photographed the food in this app.
 *
 * **Why this screen exists at all.** The catalogue photographs come from
 * Wikimedia Commons under CC BY and CC BY-SA, and both licences require the
 * photographer to be named wherever the image appears. Printing a credit under
 * every grid tile would bury the catalogue in six-point grey text, so they are
 * collected here — which is how apps normally satisfy attribution for a set of
 * images used decoratively.
 *
 * This is a legal obligation rather than a courtesy. If a photo is swapped for
 * one taken in-house, its row disappears from this list on its own, because the
 * backend only returns photos that carry an attribution.
 */

import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { type PhotoCredit, photoCredits } from '@/api/catalogue';
import { BackHeader } from '@/components/back-header';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { useT } from '@/i18n';
import { color, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function PhotoCreditsScreen() {
  const t = useT();
  const [credits, setCredits] = useState<PhotoCredit[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    void photoCredits()
      .then((rows) => {
        if (!cancelled) setCredits(rows);
      })
      .catch(() => {
        if (!cancelled) setCredits([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (credits === null) {
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
        <Text style={text.title}>{t('credits.title')}</Text>
        <Text style={[text.bodyMuted, styles.lede]}>{t('credits.lede')}</Text>

        {credits.length === 0 ? (
          <Text style={text.bodyMuted}>{t('credits.empty')}</Text>
        ) : (
          <Card style={styles.list}>
            {credits.map((credit, index) => (
              <Pressable
                key={credit.slug}
                style={[styles.row, index > 0 && styles.divided]}
                disabled={!credit.source_url}
                onPress={() => {
                  if (credit.source_url) void Linking.openURL(credit.source_url);
                }}
              >
                <Text style={text.label}>{credit.name_en}</Text>
                <Text style={styles.credit}>{credit.attribution}</Text>
                {credit.source_url && (
                  <Text style={styles.link}>{t('credits.view')}</Text>
                )}
              </Pressable>
            ))}
          </Card>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  scroll: { paddingTop: space.lg, paddingBottom: space.xxl, gap: space.md },
  lede: { lineHeight: 21 },

  list: { paddingVertical: space.xs },
  row: { paddingVertical: space.md, gap: 3 },
  divided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: color.hairline },
  credit: { ...text.bodyMuted, fontSize: 12, lineHeight: 17 },
  link: { ...text.bodyMuted, fontSize: 12, color: color.accent, marginTop: 2 },
});
