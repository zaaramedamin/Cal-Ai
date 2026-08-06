/**
 * Scan a meal from a photo.
 *
 * One route, four phases: choose a photo, wait, review, log. They live together
 * because they are one task — splitting them across routes would let the back
 * button strand a user on a review screen whose photo state lives elsewhere.
 *
 * **The honesty rule this screen exists to keep.** The AI contributes two things
 * and only two: which foods it thinks are on the plate, and roughly how many
 * grams of each. Every calorie and macro shown comes from the USDA-backed
 * database via the backend. So the review step is not a formality — it is where
 * a guess becomes something the user has agreed to. Nothing is logged until they
 * press the button, grams are editable, and low-confidence items are flagged
 * rather than quietly averaged in.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ApiError } from '@/api/client';
import { apiErrorMessage } from '@/api/errors';
import {
  type FoodSearchResult,

  MEAL_SLOTS,
  type MealSlot,
  logFood,
} from '@/api/diary';
import { type ScannedItem, describeMeal, isEstimate, scanMeal } from '@/api/scan';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { HOME } from '@/routes';
import { HIT_SLOP_MIN, cardShadow, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';
import { type Translate, useT } from '@/i18n';

/**
 * Longest edge of the uploaded image.
 *
 * A modern phone camera produces roughly 4000px and 4 MB. Gemini gains nothing
 * from that for "what food is this" — but the user pays for it twice, in upload
 * time on a mobile connection and in image tokens against a shared free-tier
 * budget. 1024px at quality 0.7 lands around 150–250 KB and identifies food
 * just as well.
 */
const MAX_EDGE_PX = 1024;
const JPEG_QUALITY = 0.7;

/** Below this the model is guessing, and the user should know before logging. */
const LOW_CONFIDENCE = 0.5;

interface ReviewItem {
  key: string;
  detectedName: string;
  /** Held as text, not a number: an input mid-edit is legitimately "" or "12.". */
  grams: string;
  confidence: number;
  match: FoodSearchResult | null;
  selected: boolean;
}

type State =
  | { kind: 'idle' }
  | { kind: 'preparing' }
  | { kind: 'analyzing'; preview?: string }
  | {
      kind: 'review';
      preview?: string;
      items: ReviewItem[];
      notes: string;
      estimatedCount: number;
    }
  | { kind: 'nothing'; preview?: string; notes: string }
  | { kind: 'error'; title: string; message: string };

function toReviewItems(items: ScannedItem[]): ReviewItem[] {
  return items.map((item, index) => ({
    key: `${index}-${item.detected_name}`,
    detectedName: item.detected_name,
    grams: String(Math.round(item.estimated_grams)),
    confidence: item.confidence,
    match: item.match,
    // Unmatched items cannot be logged — there is no food to attach them to —
    // so they start off and stay off.
    selected: item.match !== null,
  }));
}

/** Which meal to log into, by hour. Overridable with the chips on the review step. */
function slotForNow(): MealSlot {
  const hour = new Date().getHours();
  if (hour < 11) return 'breakfast';
  if (hour < 15) return 'lunch';
  if (hour < 18) return 'snack';
  return 'dinner';
}

export default function ScanScreen() {
  const router = useRouter();
  const t = useT();
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [slot, setSlot] = useState<MealSlot>(slotForNow);
  const [logging, setLogging] = useState(false);

  async function choosePhoto(source: 'camera' | 'library') {
    const permission =
      source === 'camera'
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();

    if (!permission.granted) {
      setState({
        kind: 'error',
        title: source === 'camera' ? t('scan.cameraOff') : t('scan.photosOff'),
        // `canAskAgain: false` means the OS will no longer show the dialog, so
        // telling the user to "allow it next time" would be a dead end.
        message: permission.canAskAgain
          ? t('scan.permissionAsk')
          : t('scan.permissionBlocked'),
      });
      return;
    }

    setState({ kind: 'preparing' });

    const picked =
      source === 'camera'
        ? await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 1 })
        : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1 });

    if (picked.canceled || !picked.assets[0]) {
      setState({ kind: 'idle' });
      return;
    }

    const original = picked.assets[0].uri;

    let base64: string;
    try {
      // Only the width is given; the height follows to preserve the aspect
      // ratio. Forcing a square would crop food out of the frame.
      const rendered = await ImageManipulator.manipulate(original)
        .resize({ width: MAX_EDGE_PX })
        .renderAsync();
      const saved = await rendered.saveAsync({
        format: SaveFormat.JPEG,
        compress: JPEG_QUALITY,
        base64: true,
      });
      if (!saved.base64) throw new Error('no base64 in manipulator result');
      base64 = saved.base64;
    } catch {
      setState({
        kind: 'error',
        title: t('scan.badPhoto'),
        message: t('scan.badPhotoBody'),
      });
      return;
    }

    setState({ kind: 'analyzing', preview: original });

    try {
      const response = await scanMeal({ imageBase64: base64 });
      if (response.items.length === 0) {
        setState({
          kind: 'nothing',
          preview: original,
          notes: response.notes,
        });
        return;
      }
      setState({
        kind: 'review',
        preview: original,
        items: toReviewItems(response.items),
        notes: response.notes,
        estimatedCount: response.estimated_count,
      });
    } catch (caught) {
      setState({ kind: 'error', ...describeScanFailure(t, caught) });
    }
  }

  async function describe(description: string) {
    setState({ kind: 'analyzing' });

    try {
      const response = await describeMeal(description);
      if (response.items.length === 0) {
        setState({ kind: 'nothing', notes: response.notes });
        return;
      }
      setState({
        kind: 'review',
        items: toReviewItems(response.items),
        notes: response.notes,
        estimatedCount: response.estimated_count,
      });
    } catch (caught) {
      // The same mapper as the photo path — both spend the same Gemini budget,
      // so both need the same quota message — but told which input it was, so
      // the wording matches what the user actually did.
      setState({ kind: 'error', ...describeScanFailure(t, caught, 'text') });
    }
  }

  function updateItem(key: string, patch: Partial<ReviewItem>) {
    setState((current) =>
      current.kind === 'review'
        ? {
            ...current,
            items: current.items.map((item) =>
              item.key === key ? { ...item, ...patch } : item,
            ),
          }
        : current,
    );
  }

  async function logSelected() {
    if (state.kind !== 'review') return;
    const chosen = state.items.filter((item) => item.selected && item.match && gramsOf(item) > 0);
    if (chosen.length === 0) return;

    setLogging(true);
    try {
      // Sequential, so a partial failure leaves a known state: everything before
      // the failure is logged and the error names what stopped. Firing them all
      // at once and catching one rejection would leave the user unsure which of
      // five items actually made it into the diary.
      for (const item of chosen) {
        await logFood({
          foodId: item.match!.id,
          mealSlot: slot,
          quantityGrams: gramsOf(item),
        });
      }
      router.dismissAll();
      router.replace(HOME);
    } catch (caught) {
      setState({
        kind: 'error',
        title: t('scan.logPartial'),
        message:
          apiErrorMessage(t, caught, 'scan.logPartialBody'),
      });
    } finally {
      setLogging(false);
    }
  }

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>{t('scan.eyebrow')}</Text>
        <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>{t('common.cancel')}</Text>
        </Pressable>
      </View>

      {state.kind === 'idle' && (
        <ChoosePhoto
          onChoose={(source) => void choosePhoto(source)}
          onDescribe={(value) => void describe(value)}
        />
      )}

      {state.kind === 'preparing' && <Waiting caption={t('scan.opening')} />}

      {state.kind === 'analyzing' && (
        <Waiting
          caption={state.preview ? t('scan.lookingPhoto') : t('scan.lookingText')}
          preview={state.preview}
        />
      )}

      {state.kind === 'nothing' && (
        <Outcome
          // Which input was used decides which advice is useful. Telling someone
          // who typed a sentence to improve their lighting is the kind of stock
          // message that makes an app feel like it is not listening.
          title={state.preview ? t('scan.noFoodPhoto') : t('scan.noFoodText')}
          body={
            state.notes ||
            (state.preview ? t('scan.noFoodPhotoBody') : t('scan.noFoodTextBody'))
          }
          preview={state.preview}
          onRetry={() => setState({ kind: 'idle' })}
        />
      )}

      {state.kind === 'error' && (
        <Outcome
          title={state.title}
          body={state.message}
          onRetry={() => setState({ kind: 'idle' })}
        />
      )}

      {state.kind === 'review' && (
        <Review
          state={state}
          slot={slot}
          onSlot={setSlot}
          onUpdate={updateItem}
          onRetake={() => setState({ kind: 'idle' })}
          onLog={() => void logSelected()}
          logging={logging}
        />
      )}
    </Screen>
  );
}

/* -------------------------------------------------------------------------- */
/* Phases                                                                     */
/* -------------------------------------------------------------------------- */

function ChoosePhoto({
  onChoose,
  onDescribe,
}: {
  onChoose: (source: 'camera' | 'library') => void;
  onDescribe: (description: string) => void;
}) {
  const t = useT();
  const [description, setDescription] = useState('');
  const ready = description.trim().length >= 3;

  return (
    <ScrollView contentContainerStyle={styles.choose} showsVerticalScrollIndicator={false}>
      <View style={styles.chooseIntro}>
        <Text style={text.title}>{t('scan.title')}</Text>
        <Text style={[text.bodyMuted, styles.chooseBody]}>{t('scan.intro')}</Text>
      </View>

      <Pressable
        onPress={() => onChoose('camera')}
        accessibilityRole="button"
        style={({ pressed }) => [styles.sourceCard, styles.sourcePrimary, pressed && styles.pressed]}
      >
        <Ionicons name="camera" size={26} color={color.onDark} />
        <View style={styles.sourceText}>
          <Text style={styles.sourceTitleOnDark}>{t('scan.takePhoto')}</Text>
          <Text style={styles.sourceHintOnDark}>{t('scan.takePhotoHint')}</Text>
        </View>
      </Pressable>

      <Pressable
        onPress={() => onChoose('library')}
        accessibilityRole="button"
        style={({ pressed }) => [styles.sourceCard, styles.sourceSecondary, pressed && styles.pressed]}
      >
        <Ionicons name="images-outline" size={26} color={color.ink} />
        <View style={styles.sourceText}>
          <Text style={styles.sourceTitle}>{t('scan.fromLibrary')}</Text>
          <Text style={styles.sourceHint}>{t('scan.fromLibraryHint')}</Text>
        </View>
      </Pressable>

      {/* The written route. Not hidden behind a tab: a photograph is the better
          input when there is a plate in front of you, and typing is the better
          one when there is not — a sandwich already eaten, a meal out, a recipe
          you know by heart. Neither is the fallback. */}
      <View style={styles.describeBlock}>
        <Text style={styles.describeLabel}>{t('scan.orDescribe')}</Text>
        <TextInput
          value={description}
          onChangeText={setDescription}
          placeholder={t('scan.describePlaceholder')}
          placeholderTextColor={color.inkFaint}
          style={styles.describeInput}
          multiline
          maxLength={500}
          returnKeyType="go"
          onSubmitEditing={() => ready && onDescribe(description.trim())}
        />
        <Pressable
          onPress={() => ready && onDescribe(description.trim())}
          disabled={!ready}
          accessibilityRole="button"
          style={({ pressed }) => [
            styles.describeButton,
            !ready && styles.describeButtonOff,
            pressed && styles.pressed,
          ]}
        >
          <Ionicons
            name="sparkles-outline"
            size={18}
            color={ready ? color.onDark : color.inkFaint}
          />
          <Text style={[styles.describeButtonText, !ready && styles.describeButtonTextOff]}>
            {t('scan.identify')}
          </Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

function Waiting({ caption, preview }: { caption: string; preview?: string }) {
  const t = useT();

  return (
    <View style={styles.centered}>
      {preview && <Image source={{ uri: preview }} style={styles.previewLarge} />}
      <ActivityIndicator color={color.ink} />
      <Text style={[text.bodyMuted, styles.waitingCaption]}>{caption}</Text>
      {preview && (
        <Text style={styles.waitingSub}>{t('scan.takesSeconds')}</Text>
      )}
    </View>
  );
}

function Outcome({
  title,
  body,
  preview,
  onRetry,
}: {
  title: string;
  body: string;
  preview?: string;
  onRetry: () => void;
}) {
  const t = useT();

  return (
    <View style={styles.centered}>
      {preview && <Image source={{ uri: preview }} style={styles.previewLarge} />}
      <Text style={text.title}>{title}</Text>
      <Text style={[text.bodyMuted, styles.outcomeBody]}>{body}</Text>
      <View style={styles.outcomeAction}>
        <Button label={t('scan.tryAnother')} onPress={onRetry} />
      </View>
    </View>
  );
}

function Review({
  state,
  slot,
  onSlot,
  onUpdate,
  onRetake,
  onLog,
  logging,
}: {
  state: Extract<State, { kind: 'review' }>;
  slot: MealSlot;
  onSlot: (slot: MealSlot) => void;
  onUpdate: (key: string, patch: Partial<ReviewItem>) => void;
  onRetake: () => void;
  onLog: () => void;
  logging: boolean;
}) {
  const router = useRouter();
  const t = useT();

  const loggable = state.items.filter(
    (item) => item.selected && item.match && gramsOf(item) > 0,
  );
  const totalKcal = loggable.reduce(
    (sum, item) => sum + (item.match!.kcal * gramsOf(item)) / 100,
    0,
  );
  const unmatched = state.items.filter((item) => !item.match).length;

  return (
    <>
      <ScrollView contentContainerStyle={styles.reviewScroll} showsVerticalScrollIndicator={false}>
        <View style={styles.reviewHead}>
          {state.preview && (
            <Image source={{ uri: state.preview }} style={styles.previewThumb} />
          )}
          <View style={styles.reviewHeadText}>
            <Text style={text.heading}>
              {state.items.length} item{state.items.length === 1 ? '' : 's'} found
            </Text>
            <Pressable onPress={onRetake} accessibilityRole="button" hitSlop={8}>
              <Text style={styles.retake}>Retake</Text>
            </Pressable>
          </View>
        </View>

        {/* Stated plainly and above the list, not buried in a footnote. The user
            is about to accept a machine's guess about their food; they should
            know exactly which part of it is a guess. */}
        <View style={styles.honesty}>
          <Ionicons name="information-circle-outline" size={16} color={color.inkMuted} />
          <Text style={styles.honestyText}>
            Portions are AI estimates — check them before logging. Nutrition comes from USDA.
          </Text>
        </View>

        {state.estimatedCount > 0 && (
          // A second, stronger warning, because these items break the promise
          // the line above makes. Saying "nutrition comes from USDA" and then
          // silently including numbers that do not would be the dishonest way
          // to ship this feature.
          <View style={styles.estimateNotice}>
            <Ionicons name="sparkles-outline" size={16} color={color.carbs} />
            <Text style={styles.estimateNoticeText}>
              {state.estimatedCount === 1 ? '1 food is' : `${state.estimatedCount} foods are`} not
              in the USDA database, so the numbers below are the AI&apos;s own estimate. Treat
              them as approximate.
            </Text>
          </View>
        )}

        {state.notes.length > 0 && <Text style={styles.notes}>{state.notes}</Text>}

        <Text style={[text.overline, styles.sectionLabel]}>Meal</Text>
        <View style={styles.slotRow}>
          {MEAL_SLOTS.map((option) => {
            const selected = option === slot;
            return (
              <Pressable
                key={option}
                onPress={() => onSlot(option)}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                style={[styles.slotChip, selected && styles.slotChipSelected]}
              >
                <Text style={[styles.slotChipLabel, selected && styles.slotChipLabelSelected]}>
                  {t(`slot.${option}`)}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={[text.overline, styles.sectionLabel]}>{t('scan.detected')}</Text>

        {state.items.map((item) => (
          <ReviewCard
            key={item.key}
            item={item}
            onUpdate={(patch) => onUpdate(item.key, patch)}
            onSearch={() =>
              router.push({
                pathname: '/search',
                params: { slot, q: item.detectedName },
              })
            }
          />
        ))}

        {unmatched > 0 && (
          <Text style={styles.unmatchedNote}>
            {unmatched} item{unmatched === 1 ? '' : 's'} had no match in the food database.
            Rather than invent numbers for {unmatched === 1 ? 'it' : 'them'}, Cal Ai leaves{' '}
            {unmatched === 1 ? 'it' : 'them'} out — search manually to add{' '}
            {unmatched === 1 ? 'it' : 'them'}.
          </Text>
        )}
      </ScrollView>

      {/* Pinned, so the total and the action stay visible while editing grams. */}
      <View style={styles.footer}>
        <View>
          <Text style={styles.footerTotal}>{Math.round(totalKcal).toLocaleString()} kcal</Text>
          <Text style={styles.footerSub}>
            {t('scan.selectedCount', {
              selected: loggable.length,
              total: state.items.length,
            })}
          </Text>
        </View>
        <View style={styles.footerButton}>
          <Button
            label={
              loggable.length === 0
                ? t('scan.nothingSelected')
                : t('scan.logCount', { count: loggable.length })
            }
            disabled={loggable.length === 0}
            loading={logging}
            onPress={onLog}
          />
        </View>
      </View>
    </>
  );
}

function ReviewCard({
  item,
  onUpdate,
  onSearch,
}: {
  item: ReviewItem;
  onUpdate: (patch: Partial<ReviewItem>) => void;
  onSearch: () => void;
}) {
  const t = useT();
  const grams = gramsOf(item);
  const validGrams = grams > 0;
  const kcal = item.match ? (item.match.kcal * grams) / 100 : null;
  const estimated = isEstimate(item.match);

  return (
    <Card style={[styles.itemCard, estimated && styles.itemCardEstimated]}>
      <View style={styles.itemTop}>
        <Pressable
          onPress={() => item.match && onUpdate({ selected: !item.selected })}
          disabled={!item.match}
          accessibilityRole="checkbox"
          accessibilityState={{ checked: item.selected, disabled: !item.match }}
          accessibilityLabel={item.detectedName}
          hitSlop={8}
          style={[
            styles.checkbox,
            item.selected && styles.checkboxOn,
            !item.match && styles.checkboxDisabled,
          ]}
        >
          {item.selected && <Ionicons name="checkmark" size={16} color={color.onDark} />}
        </Pressable>

        <View style={styles.itemText}>
          {/* The model's word first — it is what the user recognises from their
              own plate — then what we matched it to underneath. Showing only the
              matched name would hide a mismatch worth catching. */}
          <Text style={text.label} numberOfLines={1}>
            {item.detectedName}
          </Text>
          {item.match ? (
            <Text style={styles.itemMatch} numberOfLines={1}>
              {item.match.name}
            </Text>
          ) : (
            <Text style={styles.itemNoMatch}>{t('scan.noMatchInDb')}</Text>
          )}
          {estimated && (
            // Deliberately loud, and deliberately attached to the item rather
            // than only summarised at the top. A user scrolling a list of five
            // foods should not have to remember which of them were guessed.
            <View style={styles.estimateBadge}>
              <Ionicons name="sparkles-outline" size={12} color={color.carbs} />
              <Text style={styles.estimateBadgeText}>AI estimate — not from USDA</Text>
            </View>
          )}
          {item.confidence < LOW_CONFIDENCE && (
            <View style={styles.lowConfidence}>
              <Ionicons name="alert-circle-outline" size={13} color={color.carbs} />
              <Text style={styles.lowConfidenceText}>{t('scan.lowConfidence')}</Text>
            </View>
          )}
        </View>

        {kcal !== null && validGrams && (
          <View style={styles.itemKcalBlock}>
            <Text style={text.heading}>{Math.round(kcal)}</Text>
            <Text style={styles.itemKcalUnit}>kcal</Text>
          </View>
        )}
      </View>

      {item.match ? (
        <View style={styles.gramsRow}>
          <TextField
            label={t('scan.grams')}
            value={item.grams}
            onChangeText={(grams) => onUpdate({ grams })}
            keyboardType="decimal-pad"
            error={validGrams ? null : t('food.amountPositive')}
          />
        </View>
      ) : (
        <Pressable onPress={onSearch} accessibilityRole="button" style={styles.searchLink}>
          <Ionicons name="search" size={15} color={color.ink} />
          <Text style={styles.searchLinkLabel}>{t('scan.searchManually')}</Text>
        </Pressable>
      )}
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function gramsOf(item: ReviewItem): number {
  const value = Number(item.grams);
  return Number.isFinite(value) ? value : 0;
}

/**
 * Turn a failure into copy that tells the user what to do next.
 *
 * The three cases below are genuinely different situations and a single "scan
 * failed" message would leave every one of them stuck: one is the operator's
 * job, one just needs waiting out, one is worth retrying immediately.
 */
function describeScanFailure(
  t: Translate,
  caught: unknown,
  input: 'photo' | 'text' = 'photo',
): { title: string; message: string } {
  if (!(caught instanceof ApiError)) {
    return {
      title: input === 'photo' ? t('scan.failedPhoto') : t('scan.failedText'),
      message: t('scan.failedBody'),
    };
  }

  if (caught.status === 503) {
    return {
      title: t('scan.notEnabled'),
      // The backend's 503 detail carries the aistudio.google.com link, which is
      // exactly the actionable part.
      message: caught.detail ?? t('scan.noKey'),
    };
  }

  if (caught.status === 429) {
    return {
      // Not "limit reached", which reads as a punishment for something the user
      // did. On a shared free-tier key the cap is usually spent by someone else
      // — or by a test run — and the wait is seconds, so the title says so and
      // the server's message carries the actual number.
      title: t('scan.busy'),
      // `detail` rather than `userMessage`: the client's generic rate-limit copy
      // would overwrite the server's specific explanation of which cap was hit
      // and how long it lasts.
      message: caught.detail ?? apiErrorMessage(t, caught, 'error.server'),
    };
  }

  // Which input was used decides the wording. "Couldn't analyse the photo" for
  // someone who typed a sentence is the kind of stock message that makes an app
  // feel like it is not listening.
  return {
    title:
      input === 'photo' ? t('scan.cantAnalysePhoto') : t('scan.cantIdentify'),
    message: apiErrorMessage(t, caught, 'error.server'),
  };
}

/* -------------------------------------------------------------------------- */

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  cancel: { minHeight: HIT_SLOP_MIN, justifyContent: 'center', paddingLeft: space.md },
  cancelLabel: { ...text.label, color: color.clay },

  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: space.sm },
  waitingCaption: { marginTop: space.xs },
  waitingSub: { ...text.bodyMuted, fontSize: 12 },
  outcomeBody: { textAlign: 'center', lineHeight: 21, paddingHorizontal: space.lg },
  outcomeAction: { alignSelf: 'stretch', marginTop: space.lg },

  choose: { flexGrow: 1, justifyContent: 'center', gap: space.md, paddingBottom: space.xxl },
  chooseIntro: { gap: space.sm, marginBottom: space.lg },
  chooseBody: { lineHeight: 21 },
  sourceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.lg,
    padding: space.xl,
    borderRadius: radius.lg,
    ...cardShadow,
  },
  sourcePrimary: { backgroundColor: color.accent },
  sourceSecondary: { backgroundColor: color.surface },
  sourceText: { flex: 1, gap: 2 },
  sourceTitle: { ...text.label, fontSize: 16 },
  sourceHint: { ...text.bodyMuted, fontSize: 12 },
  sourceTitleOnDark: { ...text.label, fontSize: 16, color: color.onDark },
  sourceHintOnDark: { ...text.bodyMuted, fontSize: 12, color: 'rgba(255, 255, 255, 0.65)' },
  pressed: { opacity: 0.85 },

  describeBlock: { marginTop: space.lg, gap: space.sm },
  describeLabel: { ...text.overline, color: color.inkMuted },
  describeInput: {
    ...text.body,
    minHeight: 84,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
    textAlignVertical: 'top',
  },
  describeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingVertical: space.md,
    borderRadius: radius.md,
    backgroundColor: color.ink,
  },
  describeButtonOff: { backgroundColor: color.wash },
  describeButtonText: { ...text.label, color: color.onDark },
  describeButtonTextOff: { color: color.inkFaint },
  previewLarge: {
    width: 200,
    height: 200,
    borderRadius: radius.lg,
    marginBottom: space.lg,
    backgroundColor: color.wash,
  },
  previewThumb: {
    width: 56,
    height: 56,
    borderRadius: radius.md,
    backgroundColor: color.wash,
  },

  reviewScroll: { paddingBottom: 120, gap: space.md },
  reviewHead: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  reviewHeadText: { flex: 1, gap: 2 },
  retake: { ...text.label, fontSize: 13, color: color.inkMuted },

  honesty: {
    flexDirection: 'row',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
  },
  honestyText: { ...text.bodyMuted, fontSize: 12, flex: 1, lineHeight: 17 },
  notes: { ...text.bodyMuted, fontSize: 12, fontStyle: 'italic' },

  estimateNotice: {
    flexDirection: 'row',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: 'rgba(239, 160, 54, 0.10)',
    borderLeftWidth: 3,
    borderLeftColor: color.carbs,
  },
  estimateNoticeText: { ...text.body, fontSize: 12, flex: 1, lineHeight: 17 },
  estimateBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 3 },
  estimateBadgeText: { ...text.label, fontSize: 11, color: color.carbs },

  sectionLabel: { marginTop: space.sm },
  slotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  slotChip: {
    minHeight: HIT_SLOP_MIN - 8,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: color.surface,
    borderWidth: 1,
    borderColor: color.hairline,
  },
  slotChipSelected: { backgroundColor: color.accent, borderColor: color.accent },
  slotChipLabel: { ...text.label, fontSize: 13 },
  slotChipLabelSelected: { color: color.onDark },

  itemCard: { gap: space.md },
  // A left edge in the carbs amber, matching the badge and the banner, so an
  // estimated row is identifiable at a glance while scrolling.
  itemCardEstimated: { borderLeftWidth: 3, borderLeftColor: color.carbs },
  itemTop: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  checkbox: {
    width: 24,
    height: 24,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    borderColor: color.inkFaint,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  checkboxOn: { backgroundColor: color.accent, borderColor: color.accent },
  checkboxDisabled: { opacity: 0.35 },
  itemText: { flex: 1, gap: 3 },
  itemMatch: { ...text.bodyMuted, fontSize: 12 },
  itemNoMatch: { ...text.bodyMuted, fontSize: 12, color: color.danger },
  lowConfidence: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  lowConfidenceText: { ...text.bodyMuted, fontSize: 11 },
  itemKcalBlock: { alignItems: 'flex-end' },
  itemKcalUnit: { ...text.bodyMuted, fontSize: 11 },
  gramsRow: { marginTop: -space.sm },
  searchLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: HIT_SLOP_MIN - 8,
  },
  searchLinkLabel: { ...text.label, fontSize: 13 },

  unmatchedNote: { ...text.bodyMuted, fontSize: 12, lineHeight: 17 },

  footer: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.lg,
    paddingTop: space.md,
    paddingBottom: space.lg,
    backgroundColor: color.canvas,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: color.hairline,
  },
  footerTotal: { ...text.heading },
  footerSub: { ...text.bodyMuted, fontSize: 12 },
  footerButton: { flex: 1, maxWidth: 180 },
});
