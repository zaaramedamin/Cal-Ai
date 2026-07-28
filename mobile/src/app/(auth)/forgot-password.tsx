/**
 * Request a password reset link.
 *
 * The success state deliberately does not confirm whether an account exists —
 * that would undo the backend's neutral response and hand anyone an
 * account-enumeration tool. The copy is written to read naturally either way.
 */

import { Link, useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';

import { requestPasswordReset } from '@/api/auth';
import { ApiError } from '@/api/client';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { Wordmark } from '@/components/wordmark';
import { TextField } from '@/components/text-field';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);

  async function handleSubmit() {
    setFormError(null);
    if (!email.trim()) {
      setFieldError('Enter your email address.');
      return;
    }
    setFieldError(null);

    setSubmitting(true);
    try {
      const result = await requestPasswordReset(email.trim());
      setSent(true);
      // Present only while there is no mail provider, so the flow can be walked
      // through end to end in development. The backend returns null for this in
      // any other environment.
      setDevToken(result.debug_reset_token);
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.userMessage : 'Something went wrong. Please try again.',
      );
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
          <Text style={text.title}>{sent ? 'Check your email' : 'Reset your password'}</Text>

          {sent ? (
            <>
              <Text style={[text.bodyMuted, styles.subtitle]}>
                If an account exists for {email.trim()}, a reset link is on its way. It expires
                in 30 minutes.
              </Text>

              {devToken && (
                <View style={styles.devBox}>
                  <Text style={styles.devTitle}>Development only</Text>
                  <Text style={[text.bodyMuted, styles.devLine]}>
                    No mail provider is configured yet, so here is the token. Paste it on the
                    next screen.
                  </Text>
                  <Text selectable style={styles.devToken}>
                    {devToken}
                  </Text>
                </View>
              )}

              <View style={styles.actions}>
                <Button
                  label="Enter reset code"
                  onPress={() => router.push('/reset-password')}
                />
              </View>
            </>
          ) : (
            <>
              <Text style={[text.bodyMuted, styles.subtitle]}>
                Enter your email and we&apos;ll send you a link to set a new password.
              </Text>

              <TextField
                label="Email"
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
                  label="Send reset link"
                  onPress={() => void handleSubmit()}
                  loading={submitting}
                />
              </View>
            </>
          )}

          <View style={styles.footer}>
            <Text style={text.bodyMuted}>Remembered it? </Text>
            <Link href="/login" replace style={styles.footerLink}>
              Sign in
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
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clayDeep,
  },
  formErrorText: { ...text.body, fontSize: 14 },
  devBox: {
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.carbs,
    gap: space.xs,
  },
  devTitle: { ...text.overline, color: color.inkMuted },
  devLine: { fontSize: 14, lineHeight: 20 },
  devToken: { ...text.numeric, fontSize: 12, marginTop: space.xs },
  actions: { marginTop: space.xl },
  footer: {
    marginTop: space.xl,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  footerLink: { ...text.label, color: color.clay },
});
