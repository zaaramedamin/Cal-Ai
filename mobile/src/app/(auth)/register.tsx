import { useAuth } from '@/auth/context';
import { AuthForm } from '@/features/auth/auth-form';

export default function RegisterScreen() {
  const { signUp } = useAuth();

  return (
    <AuthForm
      strapline="Real numbers from real data. Nothing invented, ever."
      title="Create your account"
      subtitle="Track calories and macros against targets built from your own numbers."
      submitLabel="Create account"
      footerText="Already have an account?"
      footerLinkLabel="Sign in"
      footerHref="/login"
      requireConfirmation
      onSubmit={signUp}
    />
  );
}
