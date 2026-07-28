import { useAuth } from '@/auth/context';
import { AuthForm } from '@/features/auth/auth-form';
import { useT } from '@/i18n';

export default function LoginScreen() {
  const { signIn } = useAuth();
  const t = useT();

  return (
    <AuthForm
      strapline={t('auth.loginStrapline')}
      title={t('auth.loginTitle')}
      subtitle={t('auth.loginSubtitle')}
      submitLabel={t('auth.signIn')}
      footerText={t('auth.noAccount')}
      footerLinkLabel={t('auth.createOne')}
      footerHref="/register"
      showForgotPassword
      onSubmit={signIn}
    />
  );
}
