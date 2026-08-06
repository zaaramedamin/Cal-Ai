/**
 * Scan a packaged food's barcode.
 *
 * **Why the camera stays open on a failure.** Most barcodes on a shelf are not
 * in Open Food Facts, and a scanner that drops back to a menu on every miss
 * makes trying the next product a four-tap job. A miss shows a card over the
 * live view with a way out; the camera keeps running behind it, so scanning
 * again is one tap.
 *
 * **Why a scan is not a log.** The barcode identifies the product, not the
 * portion — nobody eats exactly 100 g of a tub of yoghurt. The scan resolves to
 * a food and hands off to the normal food screen, where the amount is chosen and
 * confirmed. Logging straight from a scan would be fast and routinely wrong.
 */

import Ionicons from '@expo/vector-icons/Ionicons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError } from '@/api/client';
import { apiErrorMessage } from '@/api/errors';
import { type MealSlot, getFoodByBarcode } from '@/api/diary';
import { Button } from '@/components/button';
import { useT } from '@/i18n';
import { color, radius, space } from '@/theme/tokens';
import { text } from '@/theme/typography';

/**
 * The symbologies actually printed on food packaging.
 *
 * Listed rather than left to default, because scanning everything means the
 * camera happily reads a QR code on the back of the box and sends its URL to a
 * lookup endpoint that expects digits.
 */
const BARCODE_TYPES = ['ean13', 'ean8', 'upc_a', 'upc_e'] as const;

type Status =
  | { kind: 'scanning' }
  | { kind: 'looking'; code: string }
  | { kind: 'missing'; title: string; body: string };

export default function BarcodeScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const t = useT();
  const params = useLocalSearchParams<{ day?: string; slot?: MealSlot }>();

  const [permission, requestPermission] = useCameraPermissions();
  const [status, setStatus] = useState<Status>({ kind: 'scanning' });

  // A ref, not state: the camera fires this callback many times a second while
  // a barcode is in frame, and a state update does not land before the next
  // frame arrives. Without the guard one tin produces a dozen lookups.
  const busy = useRef(false);
  /** Kept so the 'add it yourself' route can carry the code that missed. */
  const lastCode = useRef<string | undefined>(undefined);

  const onScanned = useCallback(
    async ({ data }: { data: string }) => {
      if (busy.current) return;
      busy.current = true;

      const code = data.trim();
      lastCode.current = code;
      setStatus({ kind: 'looking', code });

      try {
        const food = await getFoodByBarcode(code);
        // Replace, not push: coming back from the food screen should return to
        // wherever the user opened the scanner from, not to a live camera they
        // have already finished with.
        router.replace({
          pathname: '/food/[id]',
          params: { id: food.id, day: params.day, slot: params.slot },
        });
      } catch (caught) {
        setStatus({
          kind: 'missing',
          title:
            caught instanceof ApiError && caught.status === 404
              ? t('barcode.notFound')
              : t('barcode.cantUse'),
          // The server's `detail` is the actionable part — it distinguishes "not
          // in the database" from "in the database with no nutrition", which
          // need different next steps.
          body: apiErrorMessage(t, caught, 'auth.somethingWrong'),
        });
        busy.current = false;
      }
    },
    [params.day, params.slot, router, t],
  );

  /* ---- permission ------------------------------------------------------ */

  if (!permission) {
    return <View style={styles.black} />;
  }

  if (!permission.granted) {
    return (
      <View style={[styles.explain, { paddingTop: insets.top + space.xxl }]}>
        <Ionicons name="barcode-outline" size={40} color={color.ink} />
        <Text style={text.title}>{t('barcode.title')}</Text>
        <Text style={[text.bodyMuted, styles.explainBody]}>
          {permission.canAskAgain ? t('barcode.needCamera') : t('barcode.cameraBlocked')}
        </Text>
        {permission.canAskAgain && (
          <Button label={t('barcode.allowCamera')} onPress={() => void requestPermission()} />
        )}
        <Pressable onPress={() => router.back()} hitSlop={8}>
          <Text style={styles.link}>{t('common.back')}</Text>
        </Pressable>
      </View>
    );
  }

  /* ---- camera ---------------------------------------------------------- */

  return (
    <View style={styles.black}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: [...BARCODE_TYPES] }}
        // Stopped while a lookup is in flight or a result card is showing, so
        // the camera is not still firing callbacks behind the overlay.
        onBarcodeScanned={status.kind === 'scanning' ? onScanned : undefined}
      />

      {/* The reticle. Corners rather than a full rectangle: a closed box invites
          people to fit the whole package inside it, when the barcode alone is
          what needs to be in frame. */}
      <View style={styles.reticleWrap} pointerEvents="none">
        <View style={styles.reticle}>
          <View style={[styles.corner, styles.tl]} />
          <View style={[styles.corner, styles.tr]} />
          <View style={[styles.corner, styles.bl]} />
          <View style={[styles.corner, styles.br]} />
        </View>
        <Text style={styles.hint}>{t('barcode.hint')}</Text>
      </View>

      <Pressable
        onPress={() => router.back()}
        hitSlop={12}
        accessibilityRole="button"
        accessibilityLabel={t('common.close')}
        style={[styles.close, { top: insets.top + space.md }]}
      >
        <Ionicons name="close" size={24} color={color.onDark} />
      </Pressable>

      {status.kind === 'looking' && (
        <View style={styles.overlay}>
          <View style={styles.sheet}>
            <ActivityIndicator color={color.ink} />
            <Text style={text.bodyMuted}>{t('barcode.looking')}</Text>
          </View>
        </View>
      )}

      {status.kind === 'missing' && (
        <View style={styles.overlay}>
          <View style={styles.sheet}>
            <Text style={text.heading}>{status.title}</Text>
            <Text style={[text.bodyMuted, styles.sheetBody]}>{status.body}</Text>

            <Button
              label={t('barcode.scanAgain')}
              onPress={() => setStatus({ kind: 'scanning' })}
            />
            {/* The barcode travels with it, so the food the user types is
                findable by scanning the same pack again. That is what turns a
                dead end into a two-minute contribution. */}
            <Pressable
              onPress={() =>
                router.replace({
                  pathname: '/food/new',
                  params: {
                    barcode: status.kind === 'missing' ? lastCode.current : undefined,
                    day: params.day,
                    slot: params.slot,
                  },
                })
              }
              hitSlop={8}
            >
              <Text style={styles.link}>{t('food.addYourOwn')}</Text>
            </Pressable>
            <Pressable
              onPress={() =>
                router.replace({
                  pathname: '/search',
                  params: { day: params.day, slot: params.slot },
                })
              }
              hitSlop={8}
            >
              <Text style={styles.link}>{t('barcode.searchInstead')}</Text>
            </Pressable>
          </View>
        </View>
      )}
    </View>
  );
}

const RETICLE = 240;

const styles = StyleSheet.create({
  black: { flex: 1, backgroundColor: '#000' },

  explain: {
    flex: 1,
    paddingHorizontal: space.lg,
    gap: space.lg,
    backgroundColor: color.canvas,
  },
  explainBody: { lineHeight: 22 },
  link: { ...text.label, color: color.accent, textAlign: 'center' },

  reticleWrap: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
  reticle: { width: RETICLE, height: RETICLE * 0.62 },
  corner: {
    position: 'absolute',
    width: 34,
    height: 34,
    borderColor: '#FFFFFF',
  },
  tl: { top: 0, left: 0, borderTopWidth: 4, borderLeftWidth: 4, borderTopLeftRadius: radius.md },
  tr: { top: 0, right: 0, borderTopWidth: 4, borderRightWidth: 4, borderTopRightRadius: radius.md },
  bl: {
    bottom: 0,
    left: 0,
    borderBottomWidth: 4,
    borderLeftWidth: 4,
    borderBottomLeftRadius: radius.md,
  },
  br: {
    bottom: 0,
    right: 0,
    borderBottomWidth: 4,
    borderRightWidth: 4,
    borderBottomRightRadius: radius.md,
  },
  hint: {
    ...text.label,
    color: '#FFFFFF',
    marginTop: space.xl,
    textAlign: 'center',
    paddingHorizontal: space.xl,
  },

  close: {
    position: 'absolute',
    left: space.lg,
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.45)',
  },

  overlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  sheet: {
    backgroundColor: color.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: space.xl,
    paddingBottom: space.xxl,
    gap: space.md,
    alignItems: 'center',
  },
  sheetBody: { textAlign: 'center', lineHeight: 21 },
});
