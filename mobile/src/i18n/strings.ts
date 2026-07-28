/**
 * Every user-facing string, in English and French.
 *
 * **The type is the safety net.** `en` is declared first and `fr` is typed as
 * `Record<keyof typeof en, string>`, so a key added to English without a French
 * translation is a compile error rather than a screen that silently reads half
 * in one language. That mattered more than any runtime fallback: a fallback
 * hides the gap, and a hidden gap in a French app ships. Verified by deliberately
 * adding an English-only key and watching the build fail.
 *
 * Flat, dotted keys rather than nested objects. Nesting groups nicely and makes
 * every lookup a chain of optional accesses; a flat map is one indexed read, and
 * the dots still group it for a reader.
 *
 * Interpolation is `{name}` and is done by `t()`. Deliberately not a template
 * literal: a translated string has to be data, and data cannot carry code.
 *
 * **Food names are not here.** They live on the catalogue documents in
 * MongoDB with `name_en` and `name_fr`, because "Blanc de poulet" is not a
 * translation a generic dictionary produces, and a wrong food name in a
 * nutrition app is worse than a wrong button label.
 */

export const en = {
  // --- generic ---------------------------------------------------------
  'common.cancel': 'Cancel',
  'common.close': 'Close',
  'common.done': 'Done',
  'common.save': 'Save',
  'common.delete': 'Delete',
  'common.edit': 'Edit',
  'common.back': 'Back',
  'common.next': 'Next',
  'common.retry': 'Try again',
  'common.loading': 'Loading…',
  'common.error': 'Something went wrong.',
  'common.kcal': 'kcal',
  'common.grams': 'g',
  'common.protein': 'Protein',
  'common.carbs': 'Carbs',
  'common.fat': 'Fat',

  // --- meal slots ------------------------------------------------------
  'slot.breakfast': 'Breakfast',
  'slot.lunch': 'Lunch',
  'slot.dinner': 'Dinner',
  'slot.snack': 'Snacks',

  // --- auth ------------------------------------------------------------
  'auth.strapline': 'Every number traceable to its source.',
  'auth.signIn': 'Sign in',
  'auth.signUp': 'Create account',
  'auth.email': 'Email',
  'auth.password': 'Password',
  'auth.forgot': 'Forgotten your password?',
  'auth.loginTitle': 'Welcome back',
  'auth.loginSubtitle': 'Sign in to pick up where you left off.',
  'auth.loginStrapline': 'Photograph a meal. Every calorie traced back to USDA.',
  'auth.registerTitle': 'Create your account',
  'auth.registerSubtitle':
    'Track calories and macros against targets built from your own numbers.',
  'auth.registerStrapline': 'Real numbers from real data. Nothing invented, ever.',
  'auth.confirmPassword': 'Confirm password',
  'auth.needEmail': 'Enter your email address.',
  'auth.needPassword': 'Enter your password.',
  'auth.createOne': 'Create one',
  'auth.noAccount': 'No account yet? Create one',
  'auth.haveAccount': 'Already have an account? Sign in',

  // --- dashboard -------------------------------------------------------
  'home.goodMorning': 'Good morning',
  'home.goodAfternoon': 'Good afternoon',
  'home.goodEvening': 'Good evening',
  'home.caloriesLeft': 'Calories left',
  'home.caloriesOver': 'Calories over',
  'home.eatenOf': '{eaten} of {target} eaten',
  'home.yourUsuals': 'Your usuals',
  'home.whatToEat': 'What to eat next',
  'home.loggedToday': 'Logged today',
  'home.nothingYet': 'Nothing logged yet',
  'home.cantLoadDay': "Can't load your day",
  'home.scanMeal': 'Scan a meal',
  'home.myMeals': 'My meals',
  'home.ingredients': 'Ingredients',
  'home.searchFood': 'Search food',

  // --- body figure -----------------------------------------------------
  'body.title': 'You, right now',
  'body.height': 'Height',
  'body.weight': 'Weight',
  'body.bmi': 'BMI',
  'body.bmiCaveat':
    'A population average. It cannot tell muscle from fat, so read it as one number among several rather than a verdict.',
  'body.toGoal': '{remaining} kg to your goal of {target} kg',
  'body.atGoal': "You're at your goal weight.",

  // --- catalogue -------------------------------------------------------
  'catalogue.title': 'Ingredients',
  'catalogue.addTo': 'Add to {slot}',
  'catalogue.addIngredient': 'Add ingredient',
  'catalogue.footnote':
    '{count} ingredients. Every number is verified against USDA FoodData Central.',
  'catalogue.emptyTitle': 'The catalogue is empty',
  'catalogue.emptyBody':
    'Its numbers come from USDA FoodData Central, and filling it needs an API key. Run the seed command on the server once USDA_API_KEY is set.',
  'catalogue.cantLoad': "Couldn't load",
  'catalogue.logTo': 'Log to {slot}',
  'catalogue.addToMeal': 'Add to meal',
  'catalogue.backToMeal': 'Back to meal →',
  'catalogue.less': 'Less',
  'catalogue.more': 'More',

  // --- meals -----------------------------------------------------------
  'meals.title': 'My meals',
  'meals.emptyTitle': 'No meals yet',
  'meals.emptyBody':
    'Build the plates you eat often — a breakfast, a usual lunch — and logging one becomes two taps instead of six.',
  'meals.compose': 'Compose a meal',
  'meals.new': 'New meal',
  'meals.edit': 'Edit meal',
  'meals.name': 'Name',
  'meals.namePlaceholder': 'Breakfast, usual lunch…',
  'meals.ingredientCount': '{count} ingredients · {grams} g',
  'meals.totalGrams': '{grams} g total',
  'meals.tapToLog': 'Tap to log · hold to delete',
  'meals.logging': 'Logging…',
  'meals.whichMeal': 'Which meal?',
  'meals.save': 'Save meal',
  'meals.saveChanges': 'Save changes',
  'meals.needsName': 'Give the meal a name to save it.',
  'meals.noIngredients':
    "No ingredients yet. Add the things you put on the plate — the amounts stay in each food's own unit.",
  'meals.discardTitle': 'Discard this meal?',
  'meals.discardBody': 'Nothing will be saved.',
  'meals.keepEditing': 'Keep editing',
  'meals.discard': 'Discard',
  'meals.deleteTitle': 'Delete this meal?',
  'meals.deleteBody': '"{name}" will be removed.',
  'meals.missingOne': '1 ingredient is no longer in the catalogue and is not counted above.',
  'meals.missingMany':
    '{count} ingredients are no longer in the catalogue and are not counted above.',

  // --- onboarding ------------------------------------------------------
  'onboarding.paceTitle': 'How fast do you want to get there?',
  'onboarding.paceSubtitle':
    'This is what actually sets your daily calories. Slower is easier to keep up, and keeping it up is the whole thing.',
  'onboarding.paceRate': '{rate} kg per week',
  'onboarding.paceDaily': '{sign}{kcal} kcal a day',
  'onboarding.paceWeeks': 'about {weeks} weeks',
  'onboarding.paceAggressive': 'faster than 1% of your bodyweight',
  'onboarding.paceCaveat':
    'Projections assume a steady pace and about 7,700 kcal per kilogram. Real bodies are less tidy — treat the scale over a few weeks as the real answer.',

  // --- settings --------------------------------------------------------
  'settings.title': 'Settings',
  'settings.language': 'Language',
  'settings.languageSystem': 'Match my device',
  'settings.languageEnglish': 'English',
  'settings.languageFrench': 'Français',
  'settings.languageNote':
    'Food names come from the catalogue and are translated separately — a few may stay in English until they are filled in.',
} as const;

export type StringKey = keyof typeof en;

/**
 * The shape every dictionary must have.
 *
 * `Record<StringKey, string>` rather than `typeof en`. The `as const` above
 * makes each English value its own literal type, so `typeof en` would demand
 * that the French for "Cancel" be the string "Cancel" — the constraint we want
 * is on the *keys*, not the values.
 */
export type Dictionary = Record<StringKey, string>;

/**
 * French.
 *
 * Typed as `Dictionary`, so this object cannot be missing a key or invent one.
 * A key added to English without a French translation fails the typecheck
 * rather than silently rendering English inside a French screen.
 */
export const fr: Dictionary = {
  'common.cancel': 'Annuler',
  'common.close': 'Fermer',
  'common.done': 'Terminé',
  'common.save': 'Enregistrer',
  'common.delete': 'Supprimer',
  'common.edit': 'Modifier',
  'common.back': 'Retour',
  'common.next': 'Suivant',
  'common.retry': 'Réessayer',
  'common.loading': 'Chargement…',
  'common.error': "Une erreur s'est produite.",
  'common.kcal': 'kcal',
  'common.grams': 'g',
  'common.protein': 'Protéines',
  'common.carbs': 'Glucides',
  'common.fat': 'Lipides',

  'slot.breakfast': 'Petit-déjeuner',
  'slot.lunch': 'Déjeuner',
  'slot.dinner': 'Dîner',
  'slot.snack': 'Collations',

  'auth.strapline': 'Chaque chiffre remonte à sa source.',
  'auth.signIn': 'Se connecter',
  'auth.signUp': 'Créer un compte',
  'auth.email': 'E-mail',
  'auth.password': 'Mot de passe',
  'auth.forgot': 'Mot de passe oublié ?',
  'auth.loginTitle': 'Bon retour',
  'auth.loginSubtitle': 'Connectez-vous pour reprendre où vous en étiez.',
  'auth.loginStrapline': 'Photographiez un repas. Chaque calorie remonte à l’USDA.',
  'auth.registerTitle': 'Créez votre compte',
  'auth.registerSubtitle':
    'Suivez vos calories et vos macros par rapport à des objectifs calculés sur vos propres chiffres.',
  'auth.registerStrapline': 'De vrais chiffres, issus de vraies données. Rien d’inventé, jamais.',
  'auth.confirmPassword': 'Confirmez le mot de passe',
  'auth.needEmail': 'Saisissez votre adresse e-mail.',
  'auth.needPassword': 'Saisissez votre mot de passe.',
  'auth.createOne': 'Créez-en un',
  'auth.noAccount': 'Pas encore de compte ? Créez-en un',
  'auth.haveAccount': 'Vous avez déjà un compte ? Connectez-vous',

  'home.goodMorning': 'Bonjour',
  'home.goodAfternoon': 'Bon après-midi',
  'home.goodEvening': 'Bonsoir',
  'home.caloriesLeft': 'Calories restantes',
  'home.caloriesOver': 'Calories dépassées',
  'home.eatenOf': '{eaten} sur {target} consommées',
  'home.yourUsuals': 'Vos habitudes',
  'home.whatToEat': 'Quoi manger ensuite',
  'home.loggedToday': "Enregistré aujourd'hui",
  'home.nothingYet': 'Rien enregistré pour le moment',
  'home.cantLoadDay': 'Impossible de charger votre journée',
  'home.scanMeal': 'Photographier un repas',
  'home.myMeals': 'Mes repas',
  'home.ingredients': 'Ingrédients',
  'home.searchFood': 'Rechercher un aliment',

  'body.title': 'Vous, maintenant',
  'body.height': 'Taille',
  'body.weight': 'Poids',
  'body.bmi': 'IMC',
  'body.bmiCaveat':
    'Une moyenne de population. Il ne distingue pas le muscle de la graisse : à lire comme un chiffre parmi d’autres, pas comme un verdict.',
  'body.toGoal': '{remaining} kg avant votre objectif de {target} kg',
  'body.atGoal': 'Vous êtes à votre poids objectif.',

  'catalogue.title': 'Ingrédients',
  'catalogue.addTo': 'Ajouter au {slot}',
  'catalogue.addIngredient': 'Ajouter un ingrédient',
  'catalogue.footnote':
    '{count} ingrédients. Chaque chiffre est vérifié auprès de l’USDA FoodData Central.',
  'catalogue.emptyTitle': 'Le catalogue est vide',
  'catalogue.emptyBody':
    'Ses chiffres viennent de l’USDA FoodData Central, et le remplir demande une clé API. Lancez la commande de remplissage sur le serveur une fois USDA_API_KEY définie.',
  'catalogue.cantLoad': 'Chargement impossible',
  'catalogue.logTo': 'Ajouter au {slot}',
  'catalogue.addToMeal': 'Ajouter au repas',
  'catalogue.backToMeal': 'Retour au repas →',
  'catalogue.less': 'Moins',
  'catalogue.more': 'Plus',

  'meals.title': 'Mes repas',
  'meals.emptyTitle': 'Aucun repas',
  'meals.emptyBody':
    'Composez les assiettes que vous mangez souvent — un petit-déjeuner, un déjeuner habituel — et les enregistrer ne prendra plus que deux gestes au lieu de six.',
  'meals.compose': 'Composer un repas',
  'meals.new': 'Nouveau repas',
  'meals.edit': 'Modifier le repas',
  'meals.name': 'Nom',
  'meals.namePlaceholder': 'Petit-déjeuner, déjeuner habituel…',
  'meals.ingredientCount': '{count} ingrédients · {grams} g',
  'meals.totalGrams': '{grams} g au total',
  'meals.tapToLog': 'Touchez pour enregistrer · maintenez pour supprimer',
  'meals.logging': 'Enregistrement…',
  'meals.whichMeal': 'Quel repas ?',
  'meals.save': 'Enregistrer le repas',
  'meals.saveChanges': 'Enregistrer les modifications',
  'meals.needsName': 'Donnez un nom au repas pour l’enregistrer.',
  'meals.noIngredients':
    'Aucun ingrédient. Ajoutez ce que vous mettez dans l’assiette — les quantités restent dans l’unité propre à chaque aliment.',
  'meals.discardTitle': 'Abandonner ce repas ?',
  'meals.discardBody': 'Rien ne sera enregistré.',
  'meals.keepEditing': 'Continuer',
  'meals.discard': 'Abandonner',
  'meals.deleteTitle': 'Supprimer ce repas ?',
  'meals.deleteBody': '« {name} » sera supprimé.',
  'meals.missingOne':
    "1 ingrédient ne figure plus au catalogue et n'est pas compté ci-dessus.",
  'meals.missingMany':
    '{count} ingrédients ne figurent plus au catalogue et ne sont pas comptés ci-dessus.',

  'onboarding.paceTitle': 'À quelle vitesse voulez-vous y arriver ?',
  'onboarding.paceSubtitle':
    'C’est ce qui détermine réellement vos calories quotidiennes. Plus lent est plus facile à tenir, et tenir dans la durée est tout ce qui compte.',
  'onboarding.paceRate': '{rate} kg par semaine',
  'onboarding.paceDaily': '{sign}{kcal} kcal par jour',
  'onboarding.paceWeeks': 'environ {weeks} semaines',
  'onboarding.paceAggressive': 'plus rapide que 1 % de votre poids',
  'onboarding.paceCaveat':
    'Les projections supposent un rythme constant et environ 7 700 kcal par kilogramme. Les corps réels sont moins réguliers — la balance sur quelques semaines reste la vraie réponse.',

  'settings.title': 'Paramètres',
  'settings.language': 'Langue',
  'settings.languageSystem': 'Suivre mon appareil',
  'settings.languageEnglish': 'English',
  'settings.languageFrench': 'Français',
  'settings.languageNote':
    'Les noms d’aliments viennent du catalogue et sont traduits séparément — quelques-uns peuvent rester en anglais tant qu’ils ne sont pas renseignés.',
};

export type Language = 'en' | 'fr';

export const DICTIONARIES: Record<Language, Dictionary> = { en, fr };
