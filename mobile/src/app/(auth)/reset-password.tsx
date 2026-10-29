/**
 * Set a new password, reached by opening the emailed link.
 *
 * **This screen no longer takes a code.** Under the hand-built auth the user was
 * emailed a token and typed or pasted it here. Supabase instead puts the token
 * in the link itself: opening it deep-links into the app, the client exchanges
 * it for a short-lived session, and the only thing left to ask for is the new
 * password.
 *
 * That exchange is the fiddly part, because Supabase has used two link formats.
 * Newer projects send `?token_hash=...&type=recovery`, redeemed with
 * `verifyOtp`. Older ones put `access_token` and `refresh_token` in the URL
 * *fragment* — after the `#`, which `Linking.parse` does not treat as query
 * parameters. Both are handled below, because which one arrives depends on
 * project settings rather than on anything in this codebase.
 *
 * Arriving with no link at all is a real case too: the route can be navigated to
 * directly. Without a session there is nothing to update, so the screen says the
 * link is invalid rather than showing a form that cannot work.
 */

import * as Linking from 'expo-linking';
import { Link, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';

import { supabase } from '@/auth/supabase';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { Wordmark } from '@/components/wordmark';
import { authErrorKey } from '@/auth/errors';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

/** Checked here as well as by Supabase, so the error is immediate. */
const MIN_PASSWORD = 8;

type Stage = 'checking' | 'ready' | 'invalid' | 'done';

/** Pull the recovery credentials out of whichever link format arrived. */
function credentialsFrom(url: string): { tokenHash?: string; access?: string; refresh?: string } {
  const parsed = Linking.parse(url);
  const query = (parsed.queryParams ?? {}) as Record<string, string | undefined>;

  // The fragment is not parsed as query parameters, so the older format has to
  // be read by hand.
  const fragment = url.includes('#') ? url.slice(url.indexOf('#') + 1) : '';
  const hashParams = new URLSearchParams(fragment);

  return {
    tokenHash: query.token_hash ?? hashParams.get('token_hash') ?? undefined,
    access: query.access_token ?? hashParams.get('access_token') ?? undefined,
    refresh: query.refresh_token ?? hashParams.get('refresh_token') ?? undefined,
  };
}

export default function ResetPasswordScreen() {
  const router = useRouter();
  const t = useT();

  const [stage, setStage] = useState<Stage>('checking');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const establish = useCallback(async (url: string | null) => {
    // A session may already exist because the auth listener fired with a
    // PASSWORD_RECOVERY event before this screen mounted — the usual case on a
    // cold start from the emailed link.
    const { data } = await supabase.auth.getSession();
    if (data.session) {
      setStage('ready');
      return;
    }

    if (!url) {
      setStage('invalid');
      return;
    }

    const { tokenHash, access, refresh } = credentialsFrom(url);

    if (tokenHash) {
      const { error } = await supabase.auth.verifyOtp({ type: 'recovery', token_hash: tokenHash });
      setStage(error ? 'invalid' : 'ready');
      return;
    }

    if (access && refresh) {
      const { error } = await supabase.auth.setSession({
        access_token: access,
        refresh_token: refresh,
      });
      setStage(error ? 'invalid' : 'ready');
      return;
    }

    setStage('invalid');
  }, []);

  useEffect(() => {
    let cancelled = false;

    // `getInitialURL` covers a cold start; the listener covers the app already
    // running when the link is opened. Both happen in practice — the second
    // whenever the app is still backgrounded from requesting the reset.
    void Linking.getInitialURL().then((url) => {
      if (!cancelled) void establish(url);
    });

    const subscription = Linking.addEventListener('url', ({ url }) => {
      if (!cancelled) void establish(url);
    });

    return () => {
      cancelled = true;
      subscription.remove();
    };
  }, [establish]);

  async function handleSubmit() {
    setFormError(null);

    if (password.length < MIN_PASSWORD) {
      setFieldError(t('auth.passwordTooShort'));
      return;
    }
    if (password !== confirm) {
      setFieldError(t('auth.passwordsDiffer'));
      return;
    }
    setFieldError(null);

    setSubmitting(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      // The recovery session becomes an ordinary one, so the user is now signed
      // in. Sending them into the app rather than back to a login form is both
      // fewer steps and a truthful reflection of their state.
      setStage('done');
      router.replace('/');
    } catch (error) {
      setFormError(t(authErrorKey(error)));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Wordmark size={18} />

          {stage === 'checking' && <Text style={[text.bodyMuted, styles.subtitle]}>…</Text>}

          {stage === 'invalid' && (
            <>
              <Text style={text.title}>{t('auth.resetTitle')}</Text>
              <Text style={[text.bodyMuted, styles.subtitle]}>{t('auth.resetLinkInvalid')}</Text>
              <View style={styles.actions}>
                <Button
                  label={t('auth.resetSend')}
                  onPress={() => router.replace('/forgot-password')}
                />
              </View>
            </>
          )}

          {stage === 'ready' && (
            <>
              <Text style={text.title}>{t('auth.setPassword')}</Text>

              <View style={styles.fields}>
                <TextField
                  label={t('auth.newPassword')}
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  autoCapitalize="none"
                  autoComplete="new-password"
                  textContentType="newPassword"
                  editable={!submitting}
                />
                <TextField
                  label={t('auth.confirmPassword')}
                  value={confirm}
                  onChangeText={setConfirm}
                  error={fieldError}
                  secureTextEntry
                  autoCapitalize="none"
                  autoComplete="new-password"
                  textContentType="newPassword"
                  returnKeyType="go"
                  onSubmitEditing={() => void handleSubmit()}
                  editable={!submitting}
                />
              </View>

              {formError && (
                <View style={styles.formError} accessibilityRole="alert">
                  <Text style={styles.formErrorText}>{formError}</Text>
                </View>
              )}

              <View style={styles.actions}>
                <Button
                  label={t('auth.setPassword')}
                  onPress={() => void handleSubmit()}
                  loading={submitting}
                />
              </View>
            </>
          )}

          {stage === 'done' && (
            <>
              <Text style={text.title}>{t('auth.resetDone')}</Text>
              <Text style={[text.bodyMuted, styles.subtitle]}>{t('auth.resetDoneBody')}</Text>
            </>
          )}

          <View style={styles.footer}>
            <Link href="/login" replace style={styles.footerLink}>
              {t('auth.backToSignIn')}
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { flexGrow: 1, paddingBottom: space.xxl },
  subtitle: { marginTop: space.sm, marginBottom: space.xl },
  fields: { marginTop: space.xl, gap: space.lg },
  formError: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.dangerTint,
    borderLeftWidth: 3,
    borderLeftColor: color.danger,
  },
  formErrorText: { ...text.body, fontSize: 14 },
  actions: { marginTop: space.xl },
  footer: {
    marginTop: space.xl,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  footerLink: { ...text.label, color: color.accent },
});
