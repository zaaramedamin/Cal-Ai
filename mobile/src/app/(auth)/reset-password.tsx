/**
 * Set a new password using a reset token.
 *
 * Reachable two ways: from the deep link `calai://reset-password?token=...`,
 * which prefills the token, or by navigating here and pasting it. Supporting
 * both matters because deep links are fragile — the email client may strip the
 * scheme, or open the link in a browser that cannot hand it to the app.
 */

import { Link, useLocalSearchParams, useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  type TextInput,
  View,
} from 'react-native';

import { confirmPasswordReset } from '@/api/auth';
import { ApiError } from '@/api/client';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { Wordmark } from '@/components/wordmark';
import { TextField } from '@/components/text-field';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const PASSWORD_MIN_LENGTH = 8;

export default function ResetPasswordScreen() {
  const router = useRouter();
  // expo-router parses the query string of the deep link into typed params.
  const params = useLocalSearchParams<{ token?: string }>();

  const [token, setToken] = useState(params.token ?? '');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [errors, setErrors] = useState<{ token?: string; password?: string; confirm?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const passwordRef = useRef<TextInput>(null);
  const confirmRef = useRef<TextInput>(null);

  function validate(): boolean {
    const next: typeof errors = {};
    if (!token.trim()) next.token = 'Paste the code from your reset email.';
    if (!password) next.password = 'Choose a new password.';
    else if (password.length < PASSWORD_MIN_LENGTH)
      next.password = `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
    if (password !== confirmation) next.confirm = "Those passwords don't match.";

    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit() {
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await confirmPasswordReset(token.trim(), password);
      setDone(true);
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.userMessage : 'Something went wrong. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (done) {
    return (
      <Screen>
        <View style={styles.doneBlock}>
          <Wordmark size={18} />
          <Text style={text.title}>Password updated</Text>
          <Text style={[text.bodyMuted, styles.subtitle]}>
            You&apos;ve been signed out everywhere else as a precaution. Sign in with your new
            password.
          </Text>
          <Button label="Sign in" onPress={() => router.replace('/login')} />
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
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Wordmark size={18} />
          <Text style={text.title}>Choose a new password</Text>
          <Text style={[text.bodyMuted, styles.subtitle]}>
            Reset codes expire 30 minutes after they&apos;re sent and work only once.
          </Text>

          <View style={styles.fields}>
            <TextField
              label="Reset code"
              value={token}
              onChangeText={setToken}
              error={errors.token}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              editable={!submitting}
            />

            <TextField
              ref={passwordRef}
              label="New password"
              value={password}
              onChangeText={setPassword}
              error={errors.password}
              hint={`At least ${PASSWORD_MIN_LENGTH} characters`}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="newPassword"
              autoComplete="new-password"
              returnKeyType="next"
              onSubmitEditing={() => confirmRef.current?.focus()}
              editable={!submitting}
            />

            <TextField
              ref={confirmRef}
              label="Confirm new password"
              value={confirmation}
              onChangeText={setConfirmation}
              error={errors.confirm}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="newPassword"
              autoComplete="new-password"
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
              label="Update password"
              onPress={() => void handleSubmit()}
              loading={submitting}
            />
          </View>

          <View style={styles.footer}>
            <Text style={text.bodyMuted}>Code expired? </Text>
            <Link href="/forgot-password" replace style={styles.footerLink}>
              Request a new one
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
  fields: { gap: space.lg },
  formError: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clayDeep,
  },
  formErrorText: { ...text.body, fontSize: 14 },
  actions: { marginTop: space.xl },
  footer: {
    marginTop: space.xl,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  footerLink: { ...text.label, color: color.clay },
  doneBlock: { flex: 1, justifyContent: 'center', gap: space.sm },
});
