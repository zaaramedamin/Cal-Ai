/**
 * Food search.
 *
 * The input is debounced at 350ms. Without it, "chicken" fires seven requests —
 * six of which are thrown away — and each one that reaches USDA spends part of a
 * shared hourly budget. 350ms is long enough to swallow mid-word typing and
 * short enough that a deliberate pause feels immediate.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ApiError } from '@/api/client';
import { MEAL_LABELS, type FoodSearchResult, type MealSlot, searchFoods } from '@/api/diary';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { draftActions } from '@/features/recipes/draft-store';
import { HIT_SLOP_MIN, color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;

type State =
  | { kind: 'idle' }
  | { kind: 'searching' }
  | { kind: 'results'; results: FoodSearchResult[]; cachedOnly: boolean }
  | { kind: 'error'; message: string };

export default function SearchScreen() {
  const router = useRouter();
  const { slot, day, mode } = useLocalSearchParams<{
    slot?: MealSlot;
    day?: string;
    /** 'recipe' adds the chosen food to the recipe draft instead of the diary. */
    mode?: string;
  }>();
  const pickingIngredient = mode === 'recipe';

  const [query, setQuery] = useState('');
  const [state, setState] = useState<State>({ kind: 'idle' });

  // Tracks the most recent query so a slow response for an earlier one cannot
  // overwrite results for a later one — the classic out-of-order race that makes
  // a search box show results for something you already stopped typing.
  const latestQuery = useRef('');

  useEffect(() => {
    const trimmed = query.trim();
    latestQuery.current = trimmed;

    if (trimmed.length < MIN_QUERY_LENGTH) {
      setState({ kind: 'idle' });
      return;
    }

    setState({ kind: 'searching' });
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const response = await searchFoods(trimmed);
          if (latestQuery.current !== trimmed) return;
          setState({
            kind: 'results',
            results: response.results,
            cachedOnly: response.upstream_unavailable,
          });
        } catch (caught) {
          if (latestQuery.current !== trimmed) return;
          setState({
            kind: 'error',
            message: caught instanceof ApiError ? caught.userMessage : 'Search failed.',
          });
        }
      })();
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [query]);

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>
          {pickingIngredient
            ? 'Add ingredient'
            : slot
              ? `Add to ${MEAL_LABELS[slot]}`
              : 'Search foods'}
        </Text>
        <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>Cancel</Text>
        </Pressable>
      </View>

      <TextField
        label="Search"
        value={query}
        onChangeText={setQuery}
        placeholder="Chicken breast, oats, banana…"
        autoCapitalize="none"
        autoCorrect={false}
        autoFocus
        returnKeyType="search"
      />

      {state.kind === 'idle' && (
        <View style={styles.centered}>
          <Text style={text.bodyMuted}>
            Type at least {MIN_QUERY_LENGTH} characters. Results come from USDA FoodData
            Central — every number is traceable to its source.
          </Text>
        </View>
      )}

      {state.kind === 'searching' && (
        <View style={styles.centered}>
          <ActivityIndicator color={color.clay} />
          <Text style={[text.bodyMuted, styles.searchingLabel]}>Searching…</Text>
        </View>
      )}

      {state.kind === 'error' && (
        <View style={styles.callout} accessibilityRole="alert">
          <Text style={styles.calloutTitle}>Search didn&apos;t work</Text>
          <Text style={styles.calloutText}>{state.message}</Text>
        </View>
      )}

      {state.kind === 'results' && (
        <>
          {state.cachedOnly && (
            <View style={styles.notice}>
              <Text style={styles.noticeText}>
                USDA is unreachable, so these are previously cached foods only.
              </Text>
            </View>
          )}

          {state.results.length === 0 ? (
            <View style={styles.centered}>
              <Text style={text.title}>No matches</Text>
              <Text style={[text.bodyMuted, styles.emptyBody]}>
                Try a simpler term — &ldquo;oats&rdquo; rather than &ldquo;organic jumbo
                oats&rdquo;. Brand names often only match packaged products.
              </Text>
            </View>
          ) : (
            <FlatList
              data={state.results}
              keyExtractor={(item) => item.id}
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={styles.list}
              renderItem={({ item }) => (
                <Pressable
                  onPress={() => {
                    if (pickingIngredient) {
                      // Straight into the draft at a sensible default, and back.
                      // Sending the cook through the portion screen for every
                      // ingredient would make building a ten-item recipe twenty
                      // taps; the quantity is editable inline in the builder.
                      draftActions.addIngredient({
                        foodId: item.id,
                        name: item.name,
                        brand: item.brand,
                        grams: 100,
                        kcal: item.kcal,
                        protein_g: item.protein_g,
                        carbs_g: item.carbs_g,
                        fat_g: item.fat_g,
                      });
                      router.back();
                      return;
                    }
                    router.push({
                      pathname: '/food/[id]',
                      params: { id: item.id, slot: slot ?? 'snack', day: day ?? '' },
                    });
                  }}
                  accessibilityRole="button"
                  style={styles.row}
                >
                  <View style={styles.rowText}>
                    <Text style={text.label} numberOfLines={1}>
                      {item.name}
                    </Text>
                    <Text style={styles.rowMeta} numberOfLines={1}>
                      {item.brand ? `${item.brand} · ` : ''}per 100 g
                    </Text>
                    <View style={styles.rowBar}>
                      <MacroBar macros={item} scale="row" />
                    </View>
                  </View>
                  <Text style={styles.rowKcal}>{Math.round(item.kcal)}</Text>
                </Pressable>
              )}
            />
          )}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  cancel: { minHeight: HIT_SLOP_MIN, justifyContent: 'center', paddingLeft: space.md },
  cancelLabel: { ...text.label, color: color.clay },
  centered: { flex: 1, justifyContent: 'center', gap: space.sm, paddingBottom: space.xxl },
  searchingLabel: { textAlign: 'center' },
  emptyBody: { lineHeight: 21 },
  list: { paddingVertical: space.md },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: color.hairline,
  },
  rowText: { flex: 1, gap: 3 },
  rowMeta: { ...text.bodyMuted, fontSize: 12 },
  rowBar: { marginTop: space.xs },
  rowKcal: { ...text.numeric },
  callout: {
    marginTop: space.lg,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.clayDeep,
    gap: space.xs,
  },
  calloutTitle: { ...text.label },
  calloutText: { ...text.bodyMuted, fontSize: 14 },
  notice: {
    marginTop: space.md,
    padding: space.md,
    borderRadius: radius.md,
    backgroundColor: color.inkWash,
    borderLeftWidth: 3,
    borderLeftColor: color.wheat,
  },
  noticeText: { ...text.bodyMuted, fontSize: 13 },
});
