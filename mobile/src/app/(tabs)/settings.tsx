/**
 * Settings — your plan, your details, your account.
 *
 * The "how was this calculated" derivation lives here now. It is rendered from
 * the server's derivation list, never re-described in the UI, so the
 * explanation cannot drift from the calculation that produced it.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { apiErrorMessage } from '@/api/errors';
import { type ProfileWithTargets, deleteAccount, getProfile } from '@/api/profile';
import { getWaterDay, setWaterGoal } from '@/api/water';
import { useAuth } from '@/auth/context';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { TAB_DOCK_HEIGHT } from '@/components/tab-bar';
import { type LanguagePreference, useLanguage, useT } from '@/i18n';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

export default function SettingsScreen() {
  const t = useT();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [data, setData] = useState<ProfileWithTargets | null>(null);
  const [showWorking, setShowWorking] = useState(false);

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        try {
          const loaded = await getProfile();
          if (!cancelled) setData(loaded);
        } catch (caught) {
          if (!cancelled && caught instanceof ApiError && caught.status === 404) {
            router.replace('/onboarding');
          }
        }
      })();
      return () => {
        cancelled = true;
      };
    }, [router]),
  );

  return (
    <Screen>
      <Text style={text.title}>{t('settings.title')}</Text>

      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
        // The delete-account confirmation is a text field at the very bottom of
        // this list. Without these the keyboard covered it, and the first tap on
        // "Delete" only dismissed the keyboard rather than pressing the button.
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets
      >
        {data && (
          <Card>
            <Text style={text.overline}>{t('settings.dailyTargets')}</Text>
            <View style={styles.targetRow}>
              <Text style={text.hero}>{data.targets.calories.toLocaleString()}</Text>
              <Text style={styles.targetUnit}>kcal</Text>
            </View>
            <View style={styles.macroLine}>
              <MacroDot tint={color.protein} label={t('settings.gramsProtein', { grams: data.targets.macros.protein_g })} />
              <MacroDot tint={color.carbs} label={t('settings.gramsCarbs', { grams: data.targets.macros.carbs_g })} />
              <MacroDot tint={color.fat} label={t('settings.gramsFat', { grams: data.targets.macros.fat_g })} />
            </View>

            {data.targets.warnings.map((warning) => (
              <View key={warning} style={styles.warning}>
                <Text style={styles.warningText}>{warning}</Text>
              </View>
            ))}

            <Pressable
              onPress={() => setShowWorking((open) => !open)}
              accessibilityRole="button"
              accessibilityState={{ expanded: showWorking }}
              style={styles.disclosure}
            >
              <Text style={styles.disclosureLabel}>
                {showWorking ? t('settings.hideWorking') : t('settings.showWorking')}
              </Text>
              <Ionicons
                name={showWorking ? 'chevron-up' : 'chevron-down'}
                size={16}
                color={color.inkMuted}
              />
            </Pressable>

            {showWorking &&
              data.targets.derivation.map((step) => (
                <View key={step.label} style={styles.step}>
                  <View style={styles.stepHeader}>
                    <Text style={text.label}>{step.label}</Text>
                    <Text style={text.numeric}>{step.value}</Text>
                  </View>
                  <Text style={styles.stepDetail}>{step.detail}</Text>
                </View>
              ))}
          </Card>
        )}

        <SectionLabel>{t('settings.sectionAccount')}</SectionLabel>
        <Card style={styles.menuCard}>
          <MenuRow
            icon="person-circle-outline"
            label={t('settings.editDetails')}
            hint={t('settings.editDetailsHint')}
            onPress={() => router.push('/onboarding')}
          />
          <MenuRow
            divided
            icon="restaurant-outline"
            label={t('meals.title')}
            hint={t('meals.compose')}
            onPress={() => router.push('/meals')}
          />
          <MenuRow
            divided
            icon="book-outline"
            label={t('settings.myRecipes')}
            hint={t('settings.myRecipesHint')}
            onPress={() => router.push('/recipes')}
          />
          <MenuRow
            divided
            icon="cloud-upload-outline"
            label={t('submit.mine')}
            hint={t('submit.mineHint')}
            onPress={() => router.push('/submissions')}
          />
          <MenuRow
            divided
            icon="flag-outline"
            label={t('report.mine')}
            hint={t('report.mineHint')}
            onPress={() => router.push('/reports')}
          />
          <MenuRow
            divided
            icon="camera-outline"
            label={t('credits.link')}
            hint={t('credits.title')}
            onPress={() => router.push('/photo-credits')}
          />
        </Card>

        <SectionLabel>{t('settings.sectionPreferences')}</SectionLabel>
        <LanguagePicker />
        <WaterGoalPicker />

        <SectionLabel>{t('settings.sectionAccountActions')}</SectionLabel>
        <Card style={styles.menuCard}>
          {/* Not `destructive`. Signing out loses nothing and is undone by
              signing in; painting it the same red as deleting the account
              teaches people to ignore the red, which is the one thing the red
              below must never be. */}
          <MenuRow
            icon="log-out-outline"
            label={t('settings.signOut')}
            hint={user?.email}
            onPress={() => void signOut()}
          />
        </Card>

        {/* Its own section, below sign-out, because the two are not peers: one
            is reversible in a tap and the other is not reversible at all. */}
        <SectionLabel>{t('settings.sectionDanger')}</SectionLabel>
        <DeleteAccount />
      </ScrollView>
    </Screen>
  );
}

/**
 * Deleting the account, behind a confirmation you cannot fumble.
 *
 * Typing your own email rather than tapping OK. This is the only irreversible
 * action in the app — no undo, no grace period, no export — and a destructive
 * button that a thumb can reach by accident on a scrolling screen is not a
 * confirmation.
 *
 * The copy says plainly what survives. "This cannot be undone" invites the
 * reasonable assumption that something, somewhere, is recoverable.
 */
function DeleteAccount() {
  const t = useT();
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const email = user?.email ?? '';
  const matches = typed.trim().toLowerCase() === email.toLowerCase() && email !== '';

  async function confirm() {
    if (!matches || busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteAccount(typed.trim());
      // Sign out locally afterwards. The token is already dead server-side, so
      // this only clears the device — without it the app sits on a session for
      // an account that no longer exists and every request 401s.
      await signOut();
    } catch (caught) {
      setError(apiErrorMessage(t, caught, 'settings.deleteFailed'));
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Card style={styles.menuCard}>
        <MenuRow
          icon="trash-outline"
          label={t('settings.deleteAccount')}
          hint={t('settings.deleteAccountHint')}
          destructive
          onPress={() => setOpen(true)}
        />
      </Card>
    );
  }

  return (
    <Card style={styles.deleteCard}>
      <Text style={text.label}>{t('settings.deleteTitle')}</Text>
      <Text style={styles.deleteBody}>{t('settings.deleteBody')}</Text>
      <Text style={styles.deleteBody}>{t('settings.deleteShared')}</Text>

      <TextField
        label={t('settings.deleteConfirmLabel', { email })}
        value={typed}
        onChangeText={setTyped}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        error={typed.length > 0 && !matches ? t('settings.deleteMismatch') : null}
      />

      {error && (
        <View style={styles.deleteError} accessibilityRole="alert">
          <Text style={styles.deleteErrorText}>{error}</Text>
        </View>
      )}

      <View style={styles.deleteActions}>
        <Pressable
          onPress={() => {
            setOpen(false);
            setTyped('');
            setError(null);
          }}
          accessibilityRole="button"
          style={styles.deleteCancel}
        >
          <Text style={text.label}>{t('common.cancel')}</Text>
        </Pressable>
        <Button
          label={busy ? t('settings.deleting') : t('settings.deleteConfirm')}
          onPress={() => void confirm()}
          disabled={!matches}
          loading={busy}
          variant="danger"
        />
      </View>
    </Card>
  );
}

function MacroDot({ tint, label }: { tint: string; label: string }) {
  return (
    <View style={styles.macroDotWrap}>
      <View style={[styles.macroDot, { backgroundColor: tint }]} />
      <Text style={styles.macroDotLabel}>{label}</Text>
    </View>
  );
}

/**
 * Language, with "match my device" as a real option rather than a first-launch
 * guess.
 *
 * That third choice is the one that matters. Storing the resolved language at
 * first launch would freeze a French phone's app in French even after its owner
 * switched the phone to English, with nothing on screen explaining why.
 */

/**
 * The daily water target.
 *
 * Presets rather than a number field, and "None" as a real option sitting first
 * among equals. Clearing the goal is a choice — the card then shows intake with
 * no denominator — not a failure to configure something, and a text input would
 * have implied that leaving it blank was incomplete.
 *
 * The figures are the common daily-intake references rather than anything
 * derived from the user's body. Nothing here claims to know what *they* need.
 */
function WaterGoalPicker() {
  const t = useT();
  const [goal, setGoal] = useState<number | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    void getWaterDay()
      .then((day) => {
        if (!cancelled) setGoal(day.goal_ml);
      })
      .catch(() => {
        // Leave it undefined: the card renders nothing rather than showing
        // "None" selected, which would be a claim we cannot support.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (goal === undefined) return null;

  const options: { value: number | null; label: string }[] = [
    { value: null, label: t('water.goalNone') },
    { value: 1500, label: '1.5 L' },
    { value: 2000, label: '2 L' },
    { value: 2500, label: '2.5 L' },
    { value: 3000, label: '3 L' },
  ];

  async function choose(value: number | null) {
    const previous = goal;
    setGoal(value);
    try {
      await setWaterGoal(value);
    } catch {
      setGoal(previous);
    }
  }

  return (
    <Card style={styles.languageCard}>
      <Text style={text.overline}>{t('water.goalTitle')}</Text>
      <View style={styles.languageRow}>
        {options.map((option) => {
          const selected = goal === option.value;
          return (
            <Pressable
              key={String(option.value)}
              onPress={() => void choose(option.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              style={[styles.languageChip, selected && styles.languageChipOn]}
            >
              <Text style={[styles.languageLabel, selected && styles.languageLabelOn]}>
                {option.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.languageNote}>{t('water.goalNote')}</Text>
    </Card>
  );
}

function LanguagePicker() {
  const { preference, setPreference, t } = useLanguage();

  const options: { value: LanguagePreference; label: string }[] = [
    { value: 'system', label: t('settings.languageSystem') },
    { value: 'en', label: t('settings.languageEnglish') },
    { value: 'fr', label: t('settings.languageFrench') },
  ];

  return (
    <Card style={styles.languageCard}>
      <Text style={text.overline}>{t('settings.language')}</Text>
      <View style={styles.languageRow}>
        {options.map((option) => {
          const selected = preference === option.value;
          return (
            <Pressable
              key={option.value}
              onPress={() => setPreference(option.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              style={[styles.languageChip, selected && styles.languageChipOn]}
            >
              <Text style={[styles.languageLabel, selected && styles.languageLabelOn]}>
                {option.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.languageNote}>{t('settings.languageNote')}</Text>
    </Card>
  );
}

/**
 * A small label above a group of rows.
 *
 * Cards alone give you separation but not meaning — a reader sees five white
 * rectangles and has to open each to learn what it holds. A word above each one
 * turns the screen into a table of contents, which is what a settings screen is.
 */
function SectionLabel({ children }: { children: string }) {
  return <Text style={styles.sectionLabel}>{children}</Text>;
}

function MenuRow({
  icon,
  label,
  hint,
  onPress,
  destructive = false,
  divided = false,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  hint?: string;
  onPress: () => void;
  destructive?: boolean;
  /** Draws a hairline above. Set on every row but the first in a card. */
  divided?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [
        styles.menuRow,
        divided && styles.menuRowDivided,
        pressed && styles.menuRowPressed,
      ]}
    >
      <Ionicons
        name={icon}
        size={22}
        color={destructive ? color.danger : color.ink}
      />
      <View style={styles.menuText}>
        <Text style={[text.label, destructive && styles.destructiveLabel]}>{label}</Text>
        {hint && (
          <Text style={styles.menuHint} numberOfLines={1}>
            {hint}
          </Text>
        )}
      </View>
      <Ionicons name="chevron-forward" size={18} color={color.inkFaint} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // Clears the floating tab bar, which overlays the content.
  scroll: { paddingTop: space.lg, paddingBottom: TAB_DOCK_HEIGHT + space.xl, gap: space.md },

  targetRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: space.sm,
    marginTop: space.xs,
  },
  targetUnit: { ...text.bodyMuted, fontSize: 15 },
  macroLine: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.md,
    marginTop: space.sm,
  },
  macroDotWrap: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  macroDot: { width: 8, height: 8, borderRadius: radius.pill },
  macroDotLabel: { ...text.numeric, fontSize: 13, color: color.inkMuted },

  warning: {
    marginTop: space.md,
    padding: space.md,
    borderRadius: radius.sm,
    backgroundColor: color.warningTint,
    borderLeftWidth: 3,
    borderLeftColor: color.warning,
  },
  warningText: { ...text.body, fontSize: 13, lineHeight: 19 },

  disclosure: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    marginTop: space.md,
    minHeight: HIT_SLOP_MIN,
  },
  disclosureLabel: { ...text.label, color: color.inkMuted },
  step: { marginTop: space.md, gap: 2 },
  stepHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    gap: space.sm,
  },
  stepDetail: { ...text.bodyMuted, fontSize: 12, lineHeight: 17 },

  menuCard: { padding: space.xs },
  menuRowDivided: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: color.hairline },
  sectionLabel: {
    ...text.overline,
    color: color.inkMuted,
    marginTop: space.md,
    marginLeft: space.sm,
    marginBottom: -space.xs,
  },
  languageCard: { gap: space.sm, paddingVertical: space.md },
  languageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  languageChip: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 40,
    paddingVertical: space.xs + 2,
    paddingHorizontal: 4,
    borderRadius: radius.pill,
    backgroundColor: color.wash,
  },
  languageChipOn: { backgroundColor: color.accent },
  languageLabel: { ...text.label, fontSize: 12, lineHeight: 16, textAlign: 'center' },
  languageLabelOn: { color: color.onDark },
  languageNote: { ...text.bodyMuted, fontSize: 11, lineHeight: 15 },

  deleteCard: { gap: space.md, borderWidth: 1, borderColor: color.danger },
  deleteBody: { ...text.bodyMuted, fontSize: 13, lineHeight: 19 },
  deleteActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: space.sm },
  deleteCancel: { minHeight: 44, justifyContent: 'center', paddingHorizontal: space.md },
  deleteError: {
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.dangerTint,
  },
  deleteErrorText: { ...text.body, fontSize: 13 },
  menuRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.md,
    minHeight: HIT_SLOP_MIN + 8,
    borderRadius: radius.md,
  },
  menuRowPressed: { backgroundColor: color.wash },
  menuText: { flex: 1, gap: 1 },
  menuHint: { ...text.bodyMuted, fontSize: 12 },
  destructiveLabel: { color: color.dangerText },
});
