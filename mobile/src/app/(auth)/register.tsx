/**
 * Create an account.
 *
 * **Why this screen has two states.** Supabase creates the account and emails a
 * confirmation link, but the account cannot sign in until that link is clicked.
 * `signUp` therefore succeeds without producing a session — and a screen that
 * treated success as "you are in" would leave the user staring at a form that
 * appeared to work and did nothing. The second state exists to say what actually
 * happened.
 *
 * If the project ever switches email confirmation off, `signUp` returns a
 * session, the router moves the user on, and this state is simply never shown —
 * no code change needed.
 */

import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useAuth } from '@/auth/context';
import { Screen } from '@/components/screen';
import { Wordmark } from '@/components/wordmark';
import { AuthForm } from '@/features/auth/auth-form';
import { useT } from '@/i18n';
import { color, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function RegisterScreen() {
  const { signUp } = useAuth();
  const t = useT();
  const [awaiting, setAwaiting] = useState<string | null>(null);

  if (awaiting !== null) {
    return (
      <Screen>
        <View style={styles.confirm}>
          <Wordmark size={18} />
          <Text style={text.title}>{t('auth.confirmTitle')}</Text>
          <Text style={[text.bodyMuted, styles.line]}>
            {t('auth.confirmBody', { email: awaiting })}
          </Text>
          <Text style={[text.bodyMuted, styles.line]}>{t('auth.confirmHint')}</Text>
          <Link href="/login" replace style={styles.link}>
            {t('auth.backToSignIn')}
          </Link>
        </View>
      </Screen>
    );
  }

  return (
    <AuthForm
      strapline={t('auth.registerStrapline')}
      title={t('auth.registerTitle')}
      subtitle={t('auth.registerSubtitle')}
      submitLabel={t('auth.signUp')}
      footerText={t('auth.haveAccount')}
      footerLinkLabel={t('auth.signIn')}
      footerHref="/login"
      requireConfirmation
      onSubmit={async (email, password) => {
        const outcome = await signUp(email, password);
        // Only switch screens when there is genuinely nothing more to do here.
        if (outcome.kind === 'confirm-email') setAwaiting(outcome.email);
      }}
    />
  );
}

const styles = StyleSheet.create({
  confirm: { flex: 1, justifyContent: 'center', gap: space.md, paddingHorizontal: space.lg },
  line: { lineHeight: 22 },
  link: { ...text.label, color: color.accent, marginTop: space.md },
});
