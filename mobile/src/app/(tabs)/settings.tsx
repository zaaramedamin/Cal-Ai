/**
 * Settings — your plan, your details, your account.
 *
 * The "how was this calculated" derivation lives here now. It is rendered from
 * the server's derivation list, never re-described in the UI, so the
 * explanation cannot drift from the calculation that produced it.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { type ProfileWithTargets, getProfile } from '@/api/profile';
import { useAuth } from '@/auth/context';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
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

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {data && (
          <Card>
            <Text style={text.overline}>Daily targets</Text>
            <View style={styles.targetRow}>
              <Text style={text.hero}>{data.targets.calories.toLocaleString()}</Text>
              <Text style={styles.targetUnit}>kcal</Text>
            </View>
            <View style={styles.macroLine}>
              <MacroDot tint={color.protein} label={`${data.targets.macros.protein_g}g protein`} />
              <MacroDot tint={color.carbs} label={`${data.targets.macros.carbs_g}g carbs`} />
              <MacroDot tint={color.fat} label={`${data.targets.macros.fat_g}g fat`} />
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
                {showWorking ? 'Hide the working' : 'How was this calculated?'}
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

        <Card style={styles.menuCard}>
          <MenuRow
            icon="person-circle-outline"
            label="Edit my details"
            hint="Body stats, activity, goal"
            onPress={() => router.push('/onboarding')}
          />
          <MenuRow
            icon="restaurant-outline"
            label={t('meals.title')}
            hint={t('meals.compose')}
            onPress={() => router.push('/meals')}
          />
          <MenuRow
            icon="book-outline"
            label="My recipes"
            hint="Build meals you log often"
            onPress={() => router.push('/recipes')}
          />
        </Card>

        <LanguagePicker />

        <Card style={styles.menuCard}>
          <MenuRow icon="log-out-outline" label="Sign out" hint={user?.email} destructive
            onPress={() => void signOut()}
          />
        </Card>
      </ScrollView>
    </Screen>
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

function MenuRow({
  icon,
  label,
  hint,
  onPress,
  destructive = false,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  hint?: string;
  onPress: () => void;
  destructive?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.menuRow, pressed && styles.menuRowPressed]}
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
  scroll: { paddingTop: space.lg, paddingBottom: space.xxl, gap: space.md },

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
    backgroundColor: color.wash,
    borderLeftWidth: 3,
    borderLeftColor: color.carbs,
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
  languageCard: { gap: space.md },
  languageRow: { flexDirection: 'row', gap: space.sm },
  languageChip: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: space.sm,
    borderRadius: radius.pill,
    backgroundColor: color.wash,
  },
  languageChipOn: { backgroundColor: color.accent },
  languageLabel: { ...text.label, fontSize: 13 },
  languageLabelOn: { color: color.onDark },
  languageNote: { ...text.bodyMuted, fontSize: 11, lineHeight: 15 },
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
  destructiveLabel: { color: color.danger },
});
