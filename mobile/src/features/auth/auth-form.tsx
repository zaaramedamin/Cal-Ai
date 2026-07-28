/**
 * The shared body of the login and register screens.
 *
 * They differ in copy, in whether the password field asks for confirmation, and
 * in where the footer link goes — not in structure. Two near-identical screens
 * would drift: a fix to keyboard handling or error display would land in one and
 * not the other.
 */

import { Link } from 'expo-router';
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

import { ApiError } from '@/api/client';
import { AuthHero } from '@/components/auth-hero';
import { Button } from '@/components/button';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

/** Mirrors the backend's PASSWORD_MIN_LENGTH. */
const PASSWORD_MIN_LENGTH = 8;

export interface AuthFormProps {
  title: string;
  subtitle: string;
  /** One line over the hero image. Sets the tone before the form is read. */
  strapline: string;
  submitLabel: string;
  footerText: string;
  footerLinkLabel: string;
  footerHref: '/login' | '/register';
  /** Register asks twice; login does not. */
  requireConfirmation?: boolean;
  /** Login shows a recovery link; register has nothing to recover. */
  showForgotPassword?: boolean;
  onSubmit: (email: string, password: string) => Promise<void>;
}

interface FieldErrors {
  email?: string;
  password?: string;
  confirmation?: string;
}

export function AuthForm({
  title,
  subtitle,
  strapline,
  submitLabel,
  footerText,
  footerLinkLabel,
  footerHref,
  requireConfirmation = false,
  showForgotPassword = false,
  onSubmit,
}: AuthFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const passwordRef = useRef<TextInput>(null);
  const confirmationRef = useRef<TextInput>(null);

  /**
   * Client-side validation catches the obvious mistakes without a round trip.
   * It is a convenience, never a control: the server validates everything again,
   * because anything running on the user's device can be bypassed.
   */
  function validate(): boolean {
    const errors: FieldErrors = {};

    if (!email.trim()) {
      errors.email = 'Enter your email address.';
    } else if (!email.includes('@') || !email.includes('.')) {
      errors.email = "That doesn't look like an email address.";
    }

    if (!password) {
      errors.password = 'Enter your password.';
    } else if (requireConfirmation && password.length < PASSWORD_MIN_LENGTH) {
      errors.password = `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
    }

    if (requireConfirmation && password !== confirmation) {
      errors.confirmation = "Those passwords don't match.";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit() {
    setFormError(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      await onSubmit(email, password);
      // No navigation here on purpose. The root layout redirects when auth
      // status changes, so success needs no explicit route push — and cannot
      // race with the redirect.
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.userMessage
          : 'Something went wrong. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      {/*
        Without this, the keyboard covers the password field and the submit
        button on most phones, and the user cannot see what they are typing.
        iOS and Android need different behaviours: 'padding' shrinks the view on
        iOS, while Android's window already resizes, so 'height' is correct there.
      */}
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <AuthHero strapline={strapline} />

          <View style={styles.body}>
            <Text style={text.title}>{title}</Text>
            <Text style={[text.bodyMuted, styles.subtitle]}>{subtitle}</Text>

            <View style={styles.fields}>
            <TextField
              label="Email"
              value={email}
              onChangeText={setEmail}
              error={fieldErrors.email}
              // These four together are what make a login form feel native
              // rather than fought with: no autocapitalisation, no autocorrect
              // mangling the address, the right keyboard, and the OS password
              // manager offering to fill it.
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              textContentType="emailAddress"
              autoComplete="email"
              returnKeyType="next"
              onSubmitEditing={() => passwordRef.current?.focus()}
              editable={!submitting}
            />

            <TextField
              ref={passwordRef}
              label="Password"
              value={password}
              onChangeText={setPassword}
              error={fieldErrors.password}
              hint={requireConfirmation ? `At least ${PASSWORD_MIN_LENGTH} characters` : undefined}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              // `newPassword` prompts the OS to offer a generated strong one on
              // register; `password` makes it offer the saved one on login.
              textContentType={requireConfirmation ? 'newPassword' : 'password'}
              autoComplete={requireConfirmation ? 'new-password' : 'current-password'}
              returnKeyType={requireConfirmation ? 'next' : 'go'}
              onSubmitEditing={() =>
                requireConfirmation ? confirmationRef.current?.focus() : void handleSubmit()
              }
              editable={!submitting}
            />

            {requireConfirmation && (
              <TextField
                ref={confirmationRef}
                label="Confirm password"
                value={confirmation}
                onChangeText={setConfirmation}
                error={fieldErrors.confirmation}
                secureTextEntry
                autoCapitalize="none"
                autoCorrect={false}
                textContentType="newPassword"
                autoComplete="new-password"
                returnKeyType="go"
                onSubmitEditing={() => void handleSubmit()}
                editable={!submitting}
              />
            )}
            </View>

            {showForgotPassword && (
              <Link href="/forgot-password" style={styles.forgotLink}>
                Forgot your password?
              </Link>
            )}

            {formError && (
              <View style={styles.formError} accessibilityRole="alert">
                <Text style={styles.formErrorText}>{formError}</Text>
              </View>
            )}

            <View style={styles.actions}>
              <Button
                label={submitLabel}
                onPress={() => void handleSubmit()}
                loading={submitting}
              />
            </View>

            <View style={styles.footer}>
              <Text style={text.bodyMuted}>{footerText} </Text>
              <Link href={footerHref} replace style={styles.footerLink}>
                {footerLinkLabel}
              </Link>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: {
    flexGrow: 1,
    paddingBottom: space.xxl,
  },
  // The hero bleeds to the screen edges, so the form below needs its own
  // breathing room rather than inheriting the header's flush alignment.
  body: { paddingTop: space.xl },
  subtitle: {
    marginTop: space.sm,
    marginBottom: space.xl,
    lineHeight: 21,
  },
  fields: {
    gap: space.lg,
  },
  forgotLink: {
    ...text.label,
    color: color.accent,
    marginTop: space.lg,
    // Aligned right, below the password field it relates to — the conventional
    // position, so people find it without reading.
    alignSelf: 'flex-end',
  },
  formError: {
    marginTop: space.lg,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.dangerTint,
    borderLeftWidth: 3,
    borderLeftColor: color.danger,
  },
  formErrorText: {
    ...text.body,
    fontSize: 14,
  },
  actions: {
    marginTop: space.xl,
  },
  footer: {
    marginTop: space.xl,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  footerLink: {
    ...text.label,
    color: color.accent,
  },
});
