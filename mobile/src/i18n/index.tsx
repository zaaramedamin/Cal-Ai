/**
 * Language: which one, how it is chosen, and how a screen asks for a string.
 *
 * The rule the user asked for is "the device decides", with an override in
 * Settings. So the stored preference has **three** states, not two: `en`, `fr`,
 * and `system`. That third one is the important one — storing the *resolved*
 * language at first launch would silently freeze a French phone's app in French
 * even after the owner switched their phone to English, and they would have no
 * idea why. `system` keeps following.
 *
 * SecureStore rather than AsyncStorage only because it is already a dependency
 * here; a language preference is not a secret, and this is not the reason to add
 * a second storage library.
 */

import * as Localization from 'expo-localization';
import * as SecureStore from 'expo-secure-store';
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { DICTIONARIES, type Language, type StringKey } from '@/i18n/strings';

export type LanguagePreference = Language | 'system';

const STORAGE_KEY = 'calai.language';

/**
 * What the device is set to, narrowed to a language we actually have.
 *
 * `getLocales()` returns entries like `fr-CA`; only the language part matters
 * here, because the difference between Quebec and metropolitan French is not
 * something this dictionary expresses. Anything that is not French falls to
 * English, which is the honest default for a two-language app.
 */
export function deviceLanguage(): Language {
  const [first] = Localization.getLocales();
  return first?.languageCode === 'fr' ? 'fr' : 'en';
}

export function resolveLanguage(preference: LanguagePreference): Language {
  return preference === 'system' ? deviceLanguage() : preference;
}

/**
 * Substitute `{name}` placeholders.
 *
 * Missing values are left as the literal placeholder rather than becoming
 * "undefined". A visible `{count}` on screen is a bug someone reports; the word
 * "undefined" reads as a crash and tells nobody which string broke.
 */
export function interpolate(template: string, values?: Record<string, string | number>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (whole, key: string) =>
    key in values ? String(values[key]) : whole,
  );
}

export type Translate = (key: StringKey, values?: Record<string, string | number>) => string;

interface LanguageContextValue {
  /** The language actually in use. */
  language: Language;
  /** What the user chose, which may be `system`. */
  preference: LanguagePreference;
  setPreference: (preference: LanguagePreference) => void;
  t: Translate;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<LanguagePreference>('system');

  // Read the stored preference once. Until it arrives the app renders in the
  // device language, which is the right guess and is what most users will end
  // up with anyway — so there is no flash of the wrong language to avoid, and
  // no reason to hold the UI on a storage read.
  useEffect(() => {
    void (async () => {
      try {
        const stored = await SecureStore.getItemAsync(STORAGE_KEY);
        if (stored === 'en' || stored === 'fr' || stored === 'system') {
          setPreferenceState(stored);
        }
      } catch {
        /* the device language stands */
      }
    })();
  }, []);

  const setPreference = useCallback((next: LanguagePreference) => {
    setPreferenceState(next);
    // Not awaited. The UI must switch language the instant it is tapped; a
    // failed write means the choice does not survive a restart, which is a far
    // smaller problem than a control that appears not to respond.
    void SecureStore.setItemAsync(STORAGE_KEY, next).catch(() => {});
  }, []);

  const language = resolveLanguage(preference);

  const value = useMemo<LanguageContextValue>(() => {
    const dictionary = DICTIONARIES[language];
    return {
      language,
      preference,
      setPreference,
      t: (key, values) => interpolate(dictionary[key], values),
    };
  }, [language, preference, setPreference]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (context === null) {
    throw new Error('useLanguage must be used inside <LanguageProvider>.');
  }
  return context;
}

/** The common case: a screen just wants to translate. */
export function useT(): Translate {
  return useLanguage().t;
}

/**
 * Whether to prefer French fields on catalogue documents.
 *
 * Food names live on the data, not in the dictionary, so screens rendering a
 * food need this rather than `t()`.
 */
export function useFrench(): boolean {
  return useLanguage().language === 'fr';
}
