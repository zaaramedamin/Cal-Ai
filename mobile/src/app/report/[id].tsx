/**
 * Report a food whose numbers look wrong.
 *
 * The counterpart to `/food/new` and the submission flow. That direction is how
 * a food gets into the shared database; this is how one already in gets
 * challenged — including the USDA and Open Food Facts rows nobody here typed
 * and nobody here has ever checked.
 *
 * **The screen says out loud that reporting changes nothing on its own.** That
 * is not modesty, it is the design: a report that could edit a nutrition value
 * would put the number in the gift of whoever complained loudest, and would
 * hand anybody a way to delete a competitor's product. An admin compares it
 * against the source and decides. Saying so up front also sets the expectation
 * correctly — the alternative is a user who reports a food, sees it unchanged
 * an hour later, and concludes the button does nothing.
 *
 * A reason *and* an optional note, rather than free text alone. The reason is
 * what makes a pile of reports sortable and decides what can even be done about
 * it; the note is where "the pack says 250, you say 180" goes, which is the part
 * that actually resolves it.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { apiErrorMessage } from '@/api/errors';
import { REPORT_REASONS, type ReportReason, reportFood } from '@/api/review';
import { Button } from '@/components/button';
import { OptionList } from '@/components/option-list';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { type Translate, useT } from '@/i18n';
import type { StringKey } from '@/i18n/strings';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

/** Label and hint keys per reason, so the sheet is one map away from the API. */
const COPY: Record<ReportReason, { label: StringKey; hint: StringKey }> = {
  wrong_numbers: { label: 'report.wrongNumbers', hint: 'report.wrongNumbersHint' },
  wrong_name: { label: 'report.wrongName', hint: 'report.wrongNameHint' },
  duplicate: { label: 'report.duplicate', hint: 'report.duplicateHint' },
  not_food: { label: 'report.notFood', hint: 'report.notFoodHint' },
  other: { label: 'report.other', hint: 'report.otherHint' },
};

function reasonOptions(t: Translate) {
  return REPORT_REASONS.map((value) => ({
    value,
    label: t(COPY[value].label),
    description: t(COPY[value].hint),
  }));
}

export default function ReportFoodScreen() {
  const router = useRouter();
  const t = useT();
  const { id } = useLocalSearchParams<{ id: string }>();

  const [reason, setReason] = useState<ReportReason | null>(null);
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!reason || sending) return;
    setSending(true);
    setError(null);
    try {
      await reportFood(id, reason, note);
      setSent(true);
    } catch (caught) {
      // 409 is the one failure with a specific meaning: this account already has
      // an open report on this food. Saying so beats "could not send", which
      // invites a third attempt that will fail the same way.
      setError(
        caught instanceof ApiError && caught.status === 409
          ? t('report.already')
          : apiErrorMessage(t, caught, 'report.failed'),
      );
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return (
      <Screen>
        <View style={styles.centered}>
          <Text style={text.title}>{t('report.sent')}</Text>
          <Text style={[text.bodyMuted, styles.sentBody]}>{t('report.sentBody')}</Text>
          <Button label={t('common.done')} onPress={() => router.back()} />
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Text style={text.overline}>{t('report.link')}</Text>
            <Pressable onPress={() => router.back()} accessibilityRole="button">
              <Text style={styles.link}>{t('common.cancel')}</Text>
            </Pressable>
          </View>

          <Text style={text.title}>{t('report.title')}</Text>
          <Text style={[text.bodyMuted, styles.lede]}>{t('report.lede')}</Text>

          <OptionList options={reasonOptions(t)} value={reason} onChange={setReason} />

          <View style={styles.noteField}>
            <TextField
              label={t('report.noteLabel')}
              value={note}
              onChangeText={setNote}
              placeholder={t('report.notePlaceholder')}
              autoCapitalize="sentences"
              multiline
              // Android centres multiline text vertically by default, which puts
              // a one-line note in the middle of a three-line box and makes the
              // field look broken. iOS already tops-aligns.
              textAlignVertical="top"
              maxLength={500}
              style={styles.noteInput}
            />
          </View>

          {error && (
            <View style={styles.callout} accessibilityRole="alert">
              <Text style={styles.calloutText}>{error}</Text>
            </View>
          )}

          <View style={styles.actions}>
            <Button
              label={sending ? t('report.sending') : t('report.send')}
              disabled={reason === null}
              loading={sending}
              onPress={() => void send()}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { paddingBottom: space.xxl },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: space.md,
  },
  link: { ...text.label, color: color.clay },
  lede: { lineHeight: 21, marginTop: space.xs, marginBottom: space.lg },
  noteField: { marginTop: space.lg },
  noteInput: { minHeight: 88, paddingTop: space.sm },
  actions: { marginTop: space.xl },
  centered: { flex: 1, justifyContent: 'center', gap: space.md },
  sentBody: { lineHeight: 21, marginBottom: space.lg },
  callout: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clayDeep,
  },
  calloutText: { ...text.body, fontSize: 14 },
});
