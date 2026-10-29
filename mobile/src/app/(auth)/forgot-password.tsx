/**
 * Request a password reset link.
 *
 * The success state deliberately does not confirm whether an account exists —
 * that would hand anyone an account-enumeration tool. The copy is written to
 * read naturally either way.
 *
 * **What changed with Supabase.** This used to end on a "here is your token,
 * paste it on the next screen" panel, because no mail provider was configured
 * and the flow could not otherwise be walked through. Supabase sends a real
 * email, so the token never passes through the app at all — the user opens the
 * link and lands on the reset screen with a session already established.
 */

import { Link } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '@/auth/context';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { Wordmark } from '@/components/wordmark';
import { authErrorKey } from '@/auth/errors';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function ForgotPasswordScreen() {
  const { requestPasswordReset } = useAuth();
  const t = useT();

  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit() {
    setFormError(null);
    if (!email.trim()) {
      setFieldError(t('auth.needEmail'));
      return;
    }
    setFieldError(null);

    setSubmitting(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (error) {
      // Note the asymmetry with the sign-in form: a *successful* request never
      // reveals whether the account exists, because that would be an
      // enumeration tool. A genuine failure — rate limit, no network, an
      // unconfigured build — is safe to name and useless to hide.
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
          <Text style={text.title}>{sent ? t('auth.resetSent') : t('auth.resetTitle')}</Text>

          {sent ? (
            <Text style={[text.bodyMuted, styles.subtitle]}>
              {t('auth.resetSentBody', { email: email.trim() })}
            </Text>
          ) : (
            <>
              <Text style={[text.bodyMuted, styles.subtitle]}>{t('auth.resetSubtitle')}</Text>

              <TextField
                label={t('auth.email')}
                value={email}
                onChangeText={setEmail}
                error={fieldError}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                textContentType="emailAddress"
                autoComplete="email"
                returnKeyType="go"
                onSubmitEditing={() => void handleSubmit()}
                editable={!submitting}
              />

              {formError && (
                <View style={styles.formError} accessibilityRole="alert">
                  <Text style={styles.formErrorText}>{formError}</Text>
                </View>
              )}

              <View style={styles.actions}>
                <Button
                  label={t('auth.resetSend')}
                  onPress={() => void handleSubmit()}
                  loading={submitting}
                />
              </View>
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
