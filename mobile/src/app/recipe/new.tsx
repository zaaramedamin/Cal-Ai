import { useFocusEffect } from 'expo-router';
import { useCallback, useRef } from 'react';

import { draftActions } from '@/features/recipes/draft-store';
import { RecipeBuilder } from '@/features/recipes/recipe-builder';

export default function NewRecipeScreen() {
  // Reset only on first focus, not on every focus. Returning from the food
  // search re-focuses this screen, and clearing the draft there would throw away
  // the ingredient the user just added.
  const initialised = useRef(false);

  useFocusEffect(
    useCallback(() => {
      if (!initialised.current) {
        draftActions.reset();
        initialised.current = true;
      }
    }, []),
  );

  return <RecipeBuilder />;
}
