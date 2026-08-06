/**
 * Food search.
 *
 * The input is debounced at 350ms. Without it, "chicken" fires seven requests —
 * six of which are thrown away — and each one that reaches USDA spends part of a
 * shared hourly budget. 350ms is long enough to swallow mid-word typing and
 * short enough that a deliberate pause feels immediate.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { apiErrorMessage } from '@/api/errors';
import {
  type FoodSearchResult,
  type MealSlot,
  type PopularFood,
  getPopularFoods,
  searchFoods,
} from '@/api/diary';
import { MacroBar } from '@/components/macro-bar';
import { Screen } from '@/components/screen';
import { TextField } from '@/components/text-field';
import { PressableScale } from '@/components/motion';
import { draftActions } from '@/features/recipes/draft-store';
import { useT } from '@/i18n';
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
  const t = useT();
  const { slot, day, mode, q } = useLocalSearchParams<{
    slot?: MealSlot;
    day?: string;
    /** 'recipe' adds the chosen food to the recipe draft instead of the diary. */
    mode?: string;
    /** Pre-filled search text. The scan screen sends the name it detected but
        could not match, so the user resumes from that word instead of retyping
        something they just watched the app fail to find. */
    q?: string;
  }>();
  const pickingIngredient = mode === 'recipe';

  const [query, setQuery] = useState(q ?? '');
  const [state, setState] = useState<State>({ kind: 'idle' });
  // The curated menu, shown while the box is empty. Fetched once and cached in
  // state: it is a static list, so refetching it on every keystroke-clear would
  // be pure waste.
  const [popular, setPopular] = useState<PopularFood[]>([]);
  /**
   * What to search with, when it differs from what the box shows.
   *
   * Tapping "Eggs" should search the term USDA files eggs under
   * ("egg whole raw") while the box still reads "Eggs" — putting the lookup
   * string in the field works but reads like a leaked implementation detail.
   * Cleared the moment the user types, so their own words always win.
   */
  const [searchOverride, setSearchOverride] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const foods = await getPopularFoods();
        if (!cancelled) setPopular(foods);
      } catch {
        /* the grid simply doesn't render; typing still works */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Tracks the most recent query so a slow response for an earlier one cannot
  // overwrite results for a later one — the classic out-of-order race that makes
  // a search box show results for something you already stopped typing.
  const latestQuery = useRef('');

  /**
   * One search, shared by the debounce and by the keyboard's Search key.
   *
   * Pulled out of the effect because the Search key had nothing to call: the
   * field declared `returnKeyType="search"` and no `onSubmitEditing`, so
   * pressing it did nothing whatsoever — not even dismiss the keyboard. It
   * looked broken because it was.
   */
  const runSearch = useCallback(
    async (term: string) => {
      latestQuery.current = term;
      if (term.length < MIN_QUERY_LENGTH) {
        setState({ kind: 'idle' });
        return;
      }
      setState({ kind: 'searching' });
      try {
        const response = await searchFoods(term);
        if (latestQuery.current !== term) return;
        setState({
          kind: 'results',
          results: response.results,
          cachedOnly: response.upstream_unavailable,
        });
      } catch (caught) {
        if (latestQuery.current !== term) return;
        setState({ kind: 'error', message: apiErrorMessage(t, caught, 'search.failed') });
      }
    },
    [t],
  );

  useEffect(() => {
    const trimmed = (searchOverride ?? query).trim();
    latestQuery.current = trimmed;

    if (trimmed.length < MIN_QUERY_LENGTH) {
      setState({ kind: 'idle' });
      return;
    }

    setState({ kind: 'searching' });
    const timer = setTimeout(() => void runSearch(trimmed), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, searchOverride, runSearch]);

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={text.overline}>
          {pickingIngredient
            ? t('catalogue.addIngredient')
            : slot
              ? t('catalogue.addTo', { slot: t(`slot.${slot}`) })
              : t('home.searchFood')}
        </Text>
        <Pressable onPress={() => router.back()} accessibilityRole="button" style={styles.cancel}>
          <Text style={styles.cancelLabel}>{t('common.cancel')}</Text>
        </Pressable>
      </View>

      <TextField
        label={t('search.label')}
        value={query}
        onChangeText={(next) => {
          setSearchOverride(null);
          setQuery(next);
        }}
        placeholder={t('search.placeholder')}
        autoCapitalize="none"
        autoCorrect={false}
        autoFocus
        returnKeyType="search"
        // Searches now rather than waiting out the debounce, and closes the
        // keyboard so the results are not hidden behind it.
        onSubmitEditing={() => {
          Keyboard.dismiss();
          void runSearch((searchOverride ?? query).trim());
        }}
      />

      {state.kind === 'idle' &&
        (popular.length > 0 ? (
          // A menu beats a blank box. USDA has 300,000 entries and searching it
          // cold means guessing which of forty chicken variants you meant; this
          // is the short list of things people actually log, with the emoji
          // doing the work a thumbnail would in an app that could afford one.
          <PopularGrid
            foods={popular}
            onPick={(food) => {
              setQuery(food.name);
              setSearchOverride(food.search_term);
            }}
          />
        ) : (
          <View style={styles.centered}>
            <Text style={text.bodyMuted}>{t('search.hint', { count: MIN_QUERY_LENGTH })}</Text>
          </View>
        ))}

      {state.kind === 'searching' && (
        <View style={styles.centered}>
          <ActivityIndicator color={color.clay} />
          <Text style={[text.bodyMuted, styles.searchingLabel]}>{t('search.searching')}</Text>
        </View>
      )}

      {state.kind === 'error' && (
        <View style={styles.callout} accessibilityRole="alert">
          <Text style={styles.calloutTitle}>{t('search.failedTitle')}</Text>
          <Text style={styles.calloutText}>{state.message}</Text>
        </View>
      )}

      {state.kind === 'results' && (
        <>
          {state.cachedOnly && (
            <View style={styles.notice}>
              <Text style={styles.noticeText}>{t('search.cachedOnly')}</Text>
            </View>
          )}

          {/* Only when *every* result is a raw database row, which the API only
              returns when nothing curated matched. Saying so is the difference
              between a list the app stands behind and one it is passing on. */}
          {state.results.length > 0 &&
            state.results.every((r) => r.source === 'usda' || r.source === 'off') && (
              <View style={styles.notice}>
                <Text style={styles.noticeText}>{t('search.fallbackNotice')}</Text>
              </View>
            )}

          {state.results.length === 0 ? (
            <View style={styles.centered}>
              <Text style={text.title}>{t('search.noMatches')}</Text>
              <Text style={[text.bodyMuted, styles.emptyBody]}>
                {t('search.noMatchesBody')}
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
                      {item.brand ? `${item.brand} · ` : ''}{t('search.per100')}
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

/**
 * The curated browse grid, grouped into sections.
 *
 * Tapping fills the search box rather than navigating straight to a food. That
 * is deliberate: it keeps one path to the food detail screen, so a tap here and
 * a typed search behave identically and the user can see and adjust the term
 * that produced the results.
 */
function PopularGrid({
  foods,
  onPick,
}: {
  foods: PopularFood[];
  onPick: (food: PopularFood) => void;
}) {
  const categories = foods.reduce<Record<string, PopularFood[]>>((groups, food) => {
    (groups[food.category] ??= []).push(food);
    return groups;
  }, {});

  return (
    <ScrollView
      contentContainerStyle={styles.gridScroll}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      {Object.entries(categories).map(([category, items]) => (
        <View key={category} style={styles.gridSection}>
          <Text style={styles.gridHeading}>{category}</Text>
          <View style={styles.grid}>
            {items.map((food) => (
              <PressableScale
                key={food.name}
                onPress={() => onPick(food)}
                accessibilityRole="button"
                accessibilityLabel={food.name}
                style={styles.tile}
              >
                <Text style={styles.tileEmoji}>{food.emoji}</Text>
                <Text style={styles.tileName} numberOfLines={2}>
                  {food.name}
                </Text>
              </PressableScale>
            ))}
          </View>
        </View>
      ))}
      <Text style={styles.gridFootnote}>
        Tap one to look it up. Every number still comes from USDA FoodData Central.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  gridScroll: { paddingTop: space.lg, paddingBottom: space.xxl, gap: space.lg },
  gridSection: { gap: space.sm },
  gridHeading: { ...text.overline, color: color.inkMuted },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  tile: {
    width: '23%',
    aspectRatio: 0.86,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    paddingHorizontal: 2,
    borderRadius: radius.md,
    backgroundColor: color.surface,
  },
  tileEmoji: { fontSize: 26 },
  tileName: { ...text.bodyMuted, fontSize: 10, textAlign: 'center', lineHeight: 12 },
  gridFootnote: { ...text.bodyMuted, fontSize: 11, textAlign: 'center' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  cancel: { minHeight: HIT_SLOP_MIN, justifyContent: 'center', paddingLeft: space.md },
  cancelLabel: { ...text.label, color: color.clay },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    paddingBottom: space.xxl,
  },
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
    borderLeftColor: color.carbs,
  },
  noticeText: { ...text.bodyMuted, fontSize: 13 },
});
