import { useAuth } from '@/auth/context';
import { AuthForm } from '@/features/auth/auth-form';

export default function LoginScreen() {
  const { signIn } = useAuth();

  return (
    <AuthForm
      strapline="Photograph a meal. Every calorie traced back to USDA."
      title="Welcome back"
      subtitle="Sign in to pick up where you left off."
      submitLabel="Sign in"
      footerText="No account yet?"
      footerLinkLabel="Create one"
      footerHref="/register"
      showForgotPassword
      onSubmit={signIn}
    />
  );
}
