import { useAuth } from '@/auth/context';
import { AuthForm } from '@/features/auth/auth-form';
import { useT } from '@/i18n';

export default function RegisterScreen() {
  const { signUp } = useAuth();
  const t = useT();

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
      onSubmit={signUp}
    />
  );
}
