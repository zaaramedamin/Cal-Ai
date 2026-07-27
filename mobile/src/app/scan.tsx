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
  View,
} from 'react-native';

import { ApiError } from '@/api/client';
import {
  type FoodSearchResult,
  MEAL_LABELS,
  type MealSlot,
  logFood,
} from '@/api/diary';
import { type ScannedItem, scanMeal } from '@/api/scan';
import { Button } from '@/components/button';
import { Card } from '@/components/card';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { HOME } from '@/routes';
import { HIT_SLOP_MIN, cardShadow, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

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
  | { kind: 'analyzing'; preview: string }
  | { kind: 'review'; preview: string; items: ReviewItem[]; notes: string }
  | { kind: 'nothing'; preview: string; notes: string }
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
        title: source === 'camera' ? 'Camera access is off' : 'Photo access is off',
        // `canAskAgain: false` means the OS will no longer show the dialog, so
        // telling the user to "allow it next time" would be a dead end.
        message: permission.canAskAgain
          ? 'CalAi needs permission to read the photo so it can identify the food in it.'
          : 'Turn it back on in your device Settings under CalAi, then try again.',
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
        title: 'Could not read that photo',
        message: 'Try taking it again, or pick a different one from your library.',
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
      });
    } catch (caught) {
      setState({ kind: 'error', ...describeScanFailure(caught) });
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
        title: 'Could not log everything',
        message:
          caught instanceof ApiError
            ? caught.userMessage
            : 'Some items may have been saved. Check your diary before retrying.',
      });
    } finally {
      setLogging(false);
    }
  }

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>Scan a meal</Text>
        <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>Cancel</Text>
        </Pressable>
      </View>

      {state.kind === 'idle' && <ChoosePhoto onChoose={(source) => void choosePhoto(source)} />}

      {state.kind === 'preparing' && <Waiting caption="Opening…" />}

      {state.kind === 'analyzing' && (
        <Waiting caption="Looking at your plate…" preview={state.preview} />
      )}

      {state.kind === 'nothing' && (
        <Outcome
          title="No food in this photo"
          body={
            state.notes ||
            'Try again with the plate filling more of the frame, in decent light.'
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

function ChoosePhoto({ onChoose }: { onChoose: (source: 'camera' | 'library') => void }) {
  return (
    <ScrollView contentContainerStyle={styles.choose} showsVerticalScrollIndicator={false}>
      <View style={styles.chooseIntro}>
        <Text style={text.title}>Photograph your meal</Text>
        <Text style={[text.bodyMuted, styles.chooseBody]}>
          CalAi identifies the foods and estimates portion sizes. You confirm both before
          anything is logged — and the nutrition itself always comes from USDA, never from
          the photo.
        </Text>
      </View>

      <Pressable
        onPress={() => onChoose('camera')}
        accessibilityRole="button"
        style={({ pressed }) => [styles.sourceCard, styles.sourcePrimary, pressed && styles.pressed]}
      >
        <Ionicons name="camera" size={26} color={color.onDark} />
        <View style={styles.sourceText}>
          <Text style={styles.sourceTitleOnDark}>Take a photo</Text>
          <Text style={styles.sourceHintOnDark}>Fill the frame with the plate</Text>
        </View>
      </Pressable>

      <Pressable
        onPress={() => onChoose('library')}
        accessibilityRole="button"
        style={({ pressed }) => [styles.sourceCard, styles.sourceSecondary, pressed && styles.pressed]}
      >
        <Ionicons name="images-outline" size={26} color={color.ink} />
        <View style={styles.sourceText}>
          <Text style={styles.sourceTitle}>Choose from library</Text>
          <Text style={styles.sourceHint}>A photo you already took</Text>
        </View>
      </Pressable>
    </ScrollView>
  );
}

function Waiting({ caption, preview }: { caption: string; preview?: string }) {
  return (
    <View style={styles.centered}>
      {preview && <Image source={{ uri: preview }} style={styles.previewLarge} />}
      <ActivityIndicator color={color.ink} />
      <Text style={[text.bodyMuted, styles.waitingCaption]}>{caption}</Text>
      {preview && (
        <Text style={styles.waitingSub}>This usually takes a few seconds.</Text>
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
  return (
    <View style={styles.centered}>
      {preview && <Image source={{ uri: preview }} style={styles.previewLarge} />}
      <Text style={text.title}>{title}</Text>
      <Text style={[text.bodyMuted, styles.outcomeBody]}>{body}</Text>
      <View style={styles.outcomeAction}>
        <Button label="Try another photo" onPress={onRetry} />
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
          <Image source={{ uri: state.preview }} style={styles.previewThumb} />
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

        {state.notes.length > 0 && <Text style={styles.notes}>{state.notes}</Text>}

        <Text style={[text.overline, styles.sectionLabel]}>Meal</Text>
        <View style={styles.slotRow}>
          {(Object.keys(MEAL_LABELS) as MealSlot[]).map((option) => {
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
                  {MEAL_LABELS[option]}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text style={[text.overline, styles.sectionLabel]}>Detected</Text>

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
            Rather than invent numbers for {unmatched === 1 ? 'it' : 'them'}, CalAi leaves{' '}
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
            {loggable.length} of {state.items.length} selected
          </Text>
        </View>
        <View style={styles.footerButton}>
          <Button
            label={loggable.length === 0 ? 'Nothing selected' : `Log ${loggable.length}`}
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
  const grams = gramsOf(item);
  const validGrams = grams > 0;
  const kcal = item.match ? (item.match.kcal * grams) / 100 : null;

  return (
    <Card style={styles.itemCard}>
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
            <Text style={styles.itemNoMatch}>No match in the food database</Text>
          )}
          {item.confidence < LOW_CONFIDENCE && (
            <View style={styles.lowConfidence}>
              <Ionicons name="alert-circle-outline" size={13} color={color.carbs} />
              <Text style={styles.lowConfidenceText}>Low confidence — worth a check</Text>
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
            label="Grams"
            value={item.grams}
            onChangeText={(grams) => onUpdate({ grams })}
            keyboardType="decimal-pad"
            error={validGrams ? null : 'Enter an amount greater than zero.'}
          />
        </View>
      ) : (
        <Pressable onPress={onSearch} accessibilityRole="button" style={styles.searchLink}>
          <Ionicons name="search" size={15} color={color.ink} />
          <Text style={styles.searchLinkLabel}>Search for it manually</Text>
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
function describeScanFailure(caught: unknown): { title: string; message: string } {
  if (!(caught instanceof ApiError)) {
    return {
      title: 'Scan failed',
      message: 'Something unexpected went wrong. Try again in a moment.',
    };
  }

  if (caught.status === 503) {
    return {
      title: 'Scanning isn’t switched on',
      // The backend's 503 detail carries the aistudio.google.com link, which is
      // exactly the actionable part.
      message: caught.detail ?? 'The server has no AI key configured.',
    };
  }

  if (caught.status === 429) {
    return {
      title: 'Scanning limit reached',
      message: caught.userMessage,
    };
  }

  return { title: 'Couldn’t analyse the photo', message: caught.userMessage };
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
  sourcePrimary: { backgroundColor: color.ink },
  sourceSecondary: { backgroundColor: color.surface },
  sourceText: { flex: 1, gap: 2 },
  sourceTitle: { ...text.label, fontSize: 16 },
  sourceHint: { ...text.bodyMuted, fontSize: 12 },
  sourceTitleOnDark: { ...text.label, fontSize: 16, color: color.onDark },
  sourceHintOnDark: { ...text.bodyMuted, fontSize: 12, color: 'rgba(255, 255, 255, 0.65)' },
  pressed: { opacity: 0.85 },

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
  slotChipSelected: { backgroundColor: color.ink, borderColor: color.ink },
  slotChipLabel: { ...text.label, fontSize: 13 },
  slotChipLabelSelected: { color: color.onDark },

  itemCard: { gap: space.md },
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
  checkboxOn: { backgroundColor: color.ink, borderColor: color.ink },
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
