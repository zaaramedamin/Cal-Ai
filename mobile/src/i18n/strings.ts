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
 * **Food names are not here.** They are columns on the `foods` table —
 * `name` and `name_fr` — because "Blanc de poulet" is not a translation a
 * generic dictionary produces, and a wrong food name in a nutrition app is
 * worse than a wrong button label.
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

  // First-run carousel.
  //
  // The copy is deliberately not "snap a photo and we'll do the rest", which is
  // what every competitor says. It would be a lie here: the model names foods
  // and estimates grams, and every calorie comes from USDA. Promising magic on
  // the first screen sets up the exact expectation the app then refuses to meet
  // — and "traceable to a source" is a better pitch than "trust us" anyway.
  'welcome.1Title': 'Photograph your plate',
  'welcome.1Body':
    'Snap a meal and the app identifies what is on it, then estimates how much.',
  'welcome.2Title': 'Every number has a source',
  'welcome.2Body':
    'Calories and macros come from USDA FoodData Central. Nothing is invented, and a figure nobody measured stays blank rather than becoming a zero.',
  'welcome.3Title': 'Targets from your own numbers',
  'welcome.3Body':
    'Your height, weight, age and the pace you choose set the target — not a default someone picked for an average person.',
  'welcome.next': 'Next',
  'welcome.start': 'Get started',
  'welcome.haveAccount': 'Already have an account?',

  // Email confirmation. Supabase creates the account and sends a link, but the
  // account cannot sign in until it is clicked — so a screen that just says
  // "done" would leave the user stuck on a form that appeared to work.
  'auth.confirmTitle': 'Check your email',
  'auth.confirmBody':
    'We sent a confirmation link to {email}. Open it to finish creating your account.',
  'auth.confirmHint': 'No email after a minute or two? Check your spam folder.',
  'auth.backToSignIn': 'Back to sign in',

  // Password reset.
  'auth.resetTitle': 'Reset your password',
  'auth.resetSubtitle': 'Enter your email and we will send you a link to set a new password.',
  'auth.resetSent': 'Check your email',
  'auth.resetSentBody':
    'If an account exists for {email}, a link is on its way. Open it on this device to set a new password.',
  'auth.resetSend': 'Send the link',
  'auth.newPassword': 'New password',
  'auth.setPassword': 'Set new password',
  'auth.resetDone': 'Password changed',
  'auth.resetDoneBody': 'You are signed in.',
  'auth.resetLinkInvalid': 'That link has expired or has already been used. Request a new one.',
  'auth.passwordsDiffer': 'The two passwords do not match.',
  'auth.passwordTooShort': 'Use at least 8 characters.',
  'auth.somethingWrong': 'Something went wrong. Please try again.',

  // What Supabase actually said, in words a user can act on. Every one of these
  // was previously flattened into "Something went wrong", which told the user
  // nothing and hid a configuration error from us for a whole session.
  'auth.errInvalidCredentials': "That email and password don't match.",
  'auth.errEmailNotConfirmed':
    'Confirm your email first — open the link we sent you, then sign in.',
  'auth.errUserExists': 'An account already exists for that email. Try signing in.',
  'auth.errWeakPassword': 'That password is too weak. Use at least 8 characters.',
  'auth.errRateLimited': 'Too many attempts. Wait a minute and try again.',
  'auth.errNetwork': 'Could not reach the server. Check your connection and try again.',
  'auth.errNotConfigured':
    'Sign-in is not configured in this build. EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY are missing — restart the Expo server after adding mobile/.env.',
  'auth.errProviderDisabled':
    'Email sign-in is switched off for this project. Enable it in Supabase under Authentication → Sign In / Providers → Email.',
  'auth.errSignupDisabled': 'New accounts are switched off for this project.',

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


  // --- water -----------------------------------------------------------
  'water.title': 'Water',
  'water.litres': 'litres today',
  'water.ofGoal': 'of {goal} L',
  'water.undo': 'Undo',
  'water.addLabel': 'Add {ml} millilitres',
  'water.goalTitle': 'Daily water goal',
  'water.goalNone': 'None',
  'water.goalNote':
    'Common daily references, not a figure calculated for you. With no goal set, the card simply shows what you drank.',

  'progress.weightChanges': 'Weight changes',
  'progress.notEnoughData': 'Not enough data',
  'progress.noChange': 'No change',
  'progress.gained': 'Gained',
  'progress.lost': 'Lost',
  'progress.yourBmi': 'Your BMI',
  'progress.yourWeightIs': 'Your weight is',
  'progress.bmi.underweight': 'Underweight',
  'progress.bmi.healthy': 'Healthy',
  'progress.bmi.overweight': 'Overweight',
  'progress.bmi.obese': 'Obese',

  'barcode.title': 'Scan a barcode',
  'barcode.hint': 'Line the barcode up inside the frame',
  'barcode.looking': 'Looking it up…',
  'barcode.notFound': 'Not in the database',
  'barcode.cantUse': "Can't use that one",
  'barcode.scanAgain': 'Scan another',
  'barcode.searchInstead': 'Search by name instead',
  'barcode.needCamera': 'Cal Ai needs the camera to read a barcode. Nothing is photographed or stored — the code is read on your device.',
  'barcode.cameraBlocked': 'Camera access is off. Turn it back on in your device Settings under Cal Ai, then try again.',
  'barcode.allowCamera': 'Allow camera',
  'home.scanBarcode': 'Scan barcode',

  'food.source': 'Source',
  'food.sourceOff': 'Community data — contributed by volunteers from the product label, not independently verified.',
  'food.sourceUser': 'You entered these figures from a label.',
  'food.sourceEstimate': 'Estimated by AI because no database matched. Treat it as a rough figure.',
  'food.addYourOwn': 'Add it yourself',
  'food.customTitle': 'Add a food',
  'food.customIntro': 'Copy the numbers from the nutrition label, per 100 g. Leave anything the label does not state blank — a blank stays blank rather than becoming a zero.',
  'food.per100g': 'Per 100 g',
  'food.nameLabel': 'Name',
  'food.brandLabel': 'Brand (optional)',
  'food.servingLabel': 'Serving size in grams (optional)',
  'food.saveFood': 'Save food',
  'food.privateNote': 'Saved to your account only. It will not appear in anyone else’s search.',

  'submit.title': 'Your submissions',
  'submit.empty': 'Foods you offer to the shared database appear here. Add a food, then tap “Share this food” on it.',
  'submit.statusPrivate': 'Private',
  'submit.statusPending': 'In review',
  'submit.statusApproved': 'Shared',
  'submit.statusRejected': 'Not accepted',
  'submit.pendingHint': 'Waiting for a reviewer. You can keep using it yourself in the meantime.',
  'submit.approvedHint': 'This food is now in the shared database and everyone can find it. Thank you.',
  'submit.rejectedHint': 'It stays in your own account and your diary is unaffected.',
  'submit.share': 'Share this food',
  'submit.shareBody': 'Offer this to the shared database. A reviewer checks it before anyone else can see it, and it stays yours to use either way.',
  'submit.sharing': 'Sending…',
  'submit.sent': 'Sent for review',
  'submit.mine': 'My submissions',
  'submit.mineHint': 'Foods you offered to the shared database',

  'credits.title': 'Photo credits',
  'credits.lede': 'The food photographs come from Wikimedia Commons, shared by their photographers under licences that ask for them to be named. Tap any row to see the original.',
  'credits.view': 'View the original',
  'credits.empty': 'No photographs need crediting yet.',
  'credits.link': 'Photo credits',

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
  // Goal descriptions say what the goal *is*, never what it computes. The pace
  // step below owns every number, and these used to claim percentages ("20%
  // below maintenance") that stopped being true when the pace picker took over
  // — the app was describing a calculation it no longer performed.
  'onboarding.goalCut': 'Lose fat',
  'onboarding.goalCutBody': 'Steady fat loss, keeping the muscle you have',
  'onboarding.goalMaintain': 'Maintain',
  'onboarding.goalMaintainBody': 'Hold your weight where it is',
  'onboarding.goalLeanBulk': 'Lean bulk',
  'onboarding.goalLeanBulkBody': 'Build slowly, with little fat gained',
  'onboarding.goalBulk': 'Bulk',
  'onboarding.goalBulkBody': 'Gain faster, accepting some fat with it',

  'onboarding.footnote': 'Your measurements are stored only on your own account.',
  'onboarding.next': 'Next',
  'onboarding.finish': 'Build my plan',
  'onboarding.failed': 'Something went wrong. Try again.',

  'onboarding.sexTitle': 'Which equation should we use?',
  'onboarding.sexSubtitle':
    'Mifflin-St Jeor uses a different constant for each. This is about body composition, not identity.',
  'onboarding.sexFemale': 'Female',
  'onboarding.sexFemaleBody': 'Uses the −161 constant',
  'onboarding.sexMale': 'Male',
  'onboarding.sexMaleBody': 'Uses the +5 constant',

  'onboarding.birthTitle': 'When were you born?',
  'onboarding.birthSubtitle':
    "Metabolic rate falls gradually with age, so the date matters more than you'd think.",
  'onboarding.day': 'Day',
  'onboarding.month': 'Month',
  'onboarding.year': 'Year',

  'onboarding.bodyTitle': 'Height & weight',
  'onboarding.bodySubtitle': 'Both feed the calculation.',

  'onboarding.activityTitle': 'How often do you train?',
  'onboarding.activitySubtitle':
    'Be honest — overestimating here is the single most common reason a calorie target comes out too high.',
  // The label is the session count, which is a numeral in both languages; only
  // the words around it change.
  'onboarding.sessionsPerWeek': '{count} sessions a week',
  'onboarding.activitySedentary': 'Desk job, little or no exercise',
  'onboarding.activityLight': 'Workouts now and then',
  'onboarding.activityModerate': 'A few workouts per week',
  'onboarding.activityActive': 'Hard exercise most days',
  'onboarding.activityVeryActive': 'Physical job, or training twice a day',

  'onboarding.goalTitle': 'What are you aiming for?',
  'onboarding.goalSubtitle': 'This sets how far your target sits from maintenance.',

  'onboarding.targetTitle': 'What weight are you aiming for?',
  'onboarding.targetSubtitle':
    'Used for the projection below. Your calorie target comes from your goal, not from this number.',
  'onboarding.rulerNow': 'Now',

  // The last step's heading changes with what the user just chose, so it is
  // four keys rather than one sentence assembled from fragments — "drop 8 kg"
  // and "gain 8 kg" are one verb apart in English and a different construction
  // in French.
  'onboarding.readyHold': 'Ready to hold steady?',
  'onboarding.readyStart': 'Ready to start?',
  'onboarding.readyLose': 'Ready to drop {amount} {unit}?',
  'onboarding.readyGain': 'Ready to gain {amount} {unit}?',
  'onboarding.readySubtitle':
    'People who log consistently in the first week are far more likely to still be logging in the second. The first few days are the whole game.',
  'onboarding.curveDay': 'Day {n}',
  'onboarding.curveCaveat':
    'Illustrative — it shows the habit curve, not a prediction about you.',

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
  'settings.sectionAccount': 'Account',
  'settings.sectionPreferences': 'Preferences',
  'settings.sectionAccountActions': 'Account actions',
  'settings.language': 'Language',
  'settings.languageSystem': 'Match my\ndevice',
  'settings.languageEnglish': 'English',
  'settings.languageFrench': 'Français',
  'settings.languageNote':
    'Food names come from the catalogue and are translated separately — a few may stay in English until they are filled in.',

  // --- navigation ------------------------------------------------------
  // The tab bar reads `options.title` from the tabs layout, so these are the
  // labels under the three icons and not decoration.
  'nav.home': 'Home',
  'nav.progress': 'Progress',
  'nav.settings': 'Settings',

  // --- weekday initials ------------------------------------------------
  // Seven keys rather than one 'SMTWTFS' string to slice, because French is
  // D L M M J V S and slicing a string assumes one letter per day in every
  // language it will ever be translated into.
  //
  // Not `Intl.DateTimeFormat(locale, { weekday: 'narrow' })` either: Hermes
  // ships a trimmed ICU, so what that returns depends on the engine build
  // rather than on this dictionary.
  'week.sun': 'S',
  'week.mon': 'M',
  'week.tue': 'T',
  'week.wed': 'W',
  'week.thu': 'T',
  'week.fri': 'F',
  'week.sat': 'S',
  'week.showDay': 'Show {date}',

  // --- progress --------------------------------------------------------
  'progress.title': 'Progress',
  'progress.cantLoad': "Can't load progress",
  'progress.loadFailed': 'Could not load your progress.',
  // Two keys rather than one with a conditional 's'. Appending a letter is an
  // English rule, and it is the kind of shortcut that reads fine until the day
  // a second language has to live with it.
  'progress.streakOne': '1 day streak',
  'progress.streakMany': '{count} days streak',
  'progress.streakLogged': 'Today is logged — keep it rolling.',
  'progress.streakKeepAlive': 'Log something today to keep it alive.',
  'progress.streakStart': 'Log a meal today to start one.',
  'progress.weight': 'Weight',
  'progress.goalLine': 'Goal {target} kg · {remaining} kg to go',
  'progress.todaysWeight': "Today's weight (kg)",
  'progress.logWeight': 'Log',
  'progress.thisWeek': 'This week',
  'progress.weekAverage': 'avg {kcal} kcal',
  'progress.targetCaption': 'Dashed line: your {kcal} kcal target',

  // --- the plan ---------------------------------------------------------
  'plan.building': 'Building your plan…',
  'plan.cantLoad': "Couldn't load your plan",
  'plan.loadFailed': 'Could not load your plan.',
  'plan.toDashboard': 'Go to the dashboard',
  'plan.eyebrow': 'Your personalised plan',
  // The headline is one sentence built from three pieces, because the weight
  // and the date are styled differently from the words around them. Split at
  // the seams so both languages keep the same fragment order:
  //   Reaching · 75 kg · by · 3 Mar 2027
  //   Atteindre · 75 kg · d'ici le · 3 mars 2027
  'plan.headlineLose': 'Reaching',
  'plan.headlineGain': 'Building to',
  'plan.headlineBy': 'by',
  'plan.holdingAt': 'Holding at',
  'plan.disclaimer':
    'The date assumes a steady {percent}% of bodyweight per week. The two endpoints are calculated; the curve between them is drawn to illustrate, not to predict — real progress is lumpy.',
  'plan.dailyTargets': 'Daily targets',
  'plan.kcalPerDay': 'kcal per day',
  'plan.howReached': 'How the number was reached',
  'plan.editable': 'You can change any of this later in Settings — nothing here is locked in.',
  'plan.start': 'Start tracking',

  // --- recipes ----------------------------------------------------------
  'recipes.eyebrow': 'Your recipes',
  'recipes.title': 'Custom meals',
  'recipes.loadFailed': 'Could not load your recipes.',
  'recipes.emptyTitle': 'Nothing saved yet',
  'recipes.emptyBody':
    'Build a meal once — a chilli, a smoothie, your usual breakfast — and log it in a single tap from then on.',
  'recipes.perServing': 'per serving',
  'recipes.ingredientsOne': '1 ingredient',
  'recipes.ingredientsMany': '{count} ingredients',
  'recipes.servingsOne': '1 serving',
  'recipes.servingsMany': '{count} servings',
  'recipes.new': 'New recipe',

  'recipe.edit': 'Edit recipe',
  'recipe.new': 'New recipe',
  'recipe.name': 'Name',
  'recipe.namePlaceholder': 'Sunday chilli',
  'recipe.servings': 'Servings the whole recipe makes',
  'recipe.servingsHint': "You'll log portions of this",
  'recipe.kcalPerServing': 'kcal per serving · {total} total',
  'recipe.ingredients': 'Ingredients ({count})',
  'recipe.emptyIngredients': 'Nothing added yet. Search for a food to start building.',
  'recipe.addIngredient': '+ Add ingredient',
  'recipe.remove': 'Remove {name}',
  'recipe.save': 'Save recipe',
  'recipe.saveChanges': 'Save changes',
  'recipe.delete': 'Delete recipe',
  'recipe.deleteTitle': 'Delete recipe?',
  'recipe.deleteBody': '{name} will be removed permanently.',
  'recipe.deleteFailed': 'Could not delete',
  'recipe.deleteFailedBody': 'Check your connection and try again.',
  'recipe.saveFailed': 'Could not save this recipe.',
  'recipe.loadFailed': 'Could not load this recipe.',
  'recipe.cantLoad': "Couldn't load that recipe",

  // --- charts and bars ---------------------------------------------------
  'chart.now': 'Now',
  'chart.without': 'Without Cal Ai',
  // Legend initials. They translate: French is P / G / L, for protéines,
  // glucides and lipides.
  'macro.proteinShort': 'P',
  'macro.carbsShort': 'C',
  'macro.fatShort': 'F',
  'macro.noneLogged': 'No macros logged yet',
  'macro.reading': 'Protein {protein} grams, carbohydrate {carbs} grams, fat {fat} grams',

  'a11y.goBack': 'Go back',
  'a11y.closeMenu': 'Close menu',
  'a11y.closeLogMenu': 'Close log menu',
  'a11y.logFood': 'Log food',

  // --- nutrients --------------------------------------------------------
  // Separate from `common.protein` and friends: those are the three-macro
  // shorthand used on cards, these are the full nutrition table, where
  // "Carbohydrate" is spelled out and the indented rows read as continuations
  // of the row above.
  'nutrient.full': 'Full nutrition',
  'nutrient.protein': 'Protein',
  'nutrient.carbs': 'Carbohydrate',
  'nutrient.sugars': 'of which sugars',
  'nutrient.fat': 'Fat',
  'nutrient.saturates': 'of which saturates',
  'nutrient.fibre': 'Fibre',
  'nutrient.sodium': 'Sodium',
  'nutrient.sugarsField': 'Sugars (g)',
  'nutrient.saturatesField': 'Saturated fat (g)',
  'nutrient.fibreField': 'Fibre (g)',
  'nutrient.sodiumField': 'Sodium (mg)',

  // --- settings (continued) ---------------------------------------------
  'settings.dailyTargets': 'Daily targets',
  'settings.gramsProtein': '{grams}g protein',
  'settings.gramsCarbs': '{grams}g carbs',
  'settings.gramsFat': '{grams}g fat',
  'settings.editDetails': 'Edit my details',
  'settings.editDetailsHint': 'Body stats, activity, goal',
  'settings.myRecipes': 'My recipes',
  'settings.myRecipesHint': 'Build meals you log often',
  'settings.signOut': 'Sign out',

  // Deleting an account. The copy is deliberately plain about what does and
  // does not survive — a vague "this cannot be undone" invites the reasonable
  // assumption that something, somewhere, is recoverable.
  'settings.sectionDanger': 'Delete account',
  'settings.deleteAccount': 'Delete my account',
  'settings.deleteAccountHint': 'Permanent. Everything goes.',
  'settings.deleteTitle': 'Delete your account?',
  'settings.deleteBody':
    'Your diary, weights, profile, saved meals, recipes and private foods are erased. There is no undo and no way to get them back.',
  'settings.deleteShared':
    'Foods you shared and had approved stay in the database with your name removed — other people have already logged them.',
  'settings.deleteConfirmLabel': 'Type {email} to confirm',
  'settings.deleteConfirm': 'Delete everything',
  'settings.deleting': 'Deleting…',
  'settings.deleteMismatch': 'That does not match your email address.',
  'settings.deleteFailed': 'Could not delete the account. Try again in a moment.',

  // --- a food -----------------------------------------------------------
  'food.cantLoad': "Couldn't load this food",
  'food.loadFailed': 'Could not load this food.',
  'food.logFailed': 'Could not log this food.',
  'food.amountPositive': 'Enter an amount greater than zero.',

  'catalogue.loadFailed': 'Could not load the catalogue.',
  'catalogue.logFailed': 'Could not log that.',

  // --- search -----------------------------------------------------------
  'search.label': 'Search',
  'search.placeholder': 'Chicken breast, oats, banana…',
  'search.noMatches': 'No matches',
  'search.failed': 'Search failed.',

  // --- photo scanning ----------------------------------------------------
  'scan.eyebrow': 'Scan a meal',
  'scan.title': 'Photograph your meal',
  'scan.intro':
    'Cal Ai identifies the foods and estimates portion sizes. You confirm both before anything is logged — and the nutrition itself always comes from USDA, never from the photo.',
  'scan.takePhoto': 'Take a photo',
  'scan.takePhotoHint': 'Fill the frame with the plate',
  'scan.fromLibrary': 'Choose from library',
  'scan.fromLibraryHint': 'A photo you already took',
  'scan.orDescribe': 'Or describe it',
  'scan.describePlaceholder': 'two boiled eggs and a slice of rye toast',
  'scan.identify': 'Identify foods',
  'scan.opening': 'Opening…',
  'scan.lookingPhoto': 'Looking at your plate…',
  'scan.lookingText': 'Reading your description…',
  'scan.takesSeconds': 'This usually takes a few seconds.',
  'scan.detected': 'Detected',
  'scan.noMatchInDb': 'No match in the food database',
  'scan.lowConfidence': 'Low confidence — worth a check',
  'scan.searchManually': 'Search for it manually',
  'scan.grams': 'Grams',
  'scan.selectedCount': '{selected} of {total} selected',
  'scan.nothingSelected': 'Nothing selected',
  'scan.logCount': 'Log {count}',
  'scan.tryAnother': 'Try another photo',

  'scan.noFoodPhoto': 'No food in this photo',
  'scan.noFoodText': 'No food in that description',
  'scan.noFoodPhotoBody':
    'Try again with the plate filling more of the frame, in decent light.',
  'scan.noFoodTextBody': 'Try naming the foods plainly — "chicken breast, rice, broccoli".',

  'scan.cameraOff': 'Camera access is off',
  'scan.photosOff': 'Photo access is off',
  'scan.permissionAsk':
    'Cal Ai needs permission to read the photo so it can identify the food in it.',
  'scan.permissionBlocked':
    'Turn it back on in your device Settings under Cal Ai, then try again.',
  'scan.badPhoto': 'Could not read that photo',
  'scan.badPhotoBody': 'Try taking it again, or pick a different one from your library.',
  'scan.logPartial': 'Could not log everything',
  'scan.logPartialBody': 'Some items may have been saved. Check your diary before retrying.',

  // Failure titles. Which input was used decides the wording — telling someone
  // who typed a sentence to improve their lighting is the kind of stock message
  // that makes an app feel like it is not listening.
  'scan.failedPhoto': 'Scan failed',
  'scan.failedText': 'Couldn’t read that',
  'scan.failedBody': 'Something unexpected went wrong. Try again in a moment.',
  'scan.notEnabled': 'Scanning isn’t switched on',
  'scan.noKey': 'The server has no AI key configured.',
  'scan.busy': 'The AI is busy right now',
  'scan.cantAnalysePhoto': 'Couldn’t analyse the photo',
  'scan.cantIdentify': 'Couldn’t identify those foods',

  // --- transport errors --------------------------------------------------
  // Used by `apiErrorMessage`, which is what every screen calls instead of
  // reading `ApiError.userMessage` directly. These are the cases where the
  // failure never reached the server, so there is no server text to show.
  'error.timeout': 'The server took too long to respond. Check your connection and try again.',
  'error.network': 'Could not reach the server. Check your connection and try again.',
  'error.parse': 'The server sent something unexpected. Try again in a moment.',
  'error.server': 'Something went wrong on the server. Try again in a moment.',
  // A rate-limit message without a duration is actively unhelpful: the user has
  // no idea whether to wait ten seconds or an hour, so they retry immediately
  // and stay blocked.
  'error.rateLimited': 'Too many attempts. Try again in {wait}.',
  'error.waitSecond': '1 second',
  'error.waitSeconds': '{count} seconds',
  'error.waitMinute': '1 minute',
  'error.waitMinutes': '{count} minutes',
  'error.tryAgain': 'Check your connection and try again.',
  'error.pleaseRetry': 'Please try again.',

  // --- the dashboard (continued) -----------------------------------------
  'home.loadFailed': 'Could not load your day.',
  'home.logFailed': 'Could not log that',
  'home.deleteEntryTitle': 'Delete entry?',
  'home.deleteEntryBody': 'Remove {name}?',
  'home.deleteEntryFailed': 'Could not delete that entry',
  'home.emptyUsuals': 'Tap one of your usuals above, or use + to scan a meal.',
  'home.emptyFresh': 'Tap + to photograph a meal or search for a food.',
  'home.longPressDelete': 'Long press to delete',

  'settings.showWorking': 'How was this calculated?',
  'settings.hideWorking': 'Hide the working',

  'meals.loadFailed': 'Could not load your meals.',
  'meals.saveFailed': 'Could not save that meal.',
  'meals.deleteFailed': 'Could not delete that meal.',

  'search.searching': 'Searching…',
  'search.failedTitle': 'Search didn’t work',
  'search.cachedOnly': 'USDA is unreachable, so these are previously cached foods only.',
  'search.per100': 'per 100 g',
  'search.hint':
    'Type at least {count} characters. Tunisian and curated foods come first — every number is traceable to its source.',
  // Shown only when nothing curated matched and the results are raw database
  // rows. Saying so is the difference between a short list the app stands
  // behind and one it is merely passing on.
  'search.fallbackNotice':
    'None of our foods matched, so these come from the USDA database. The names are theirs.',
  'search.noMatchesBody':
    'Try a simpler term — “oats” rather than “organic jumbo oats”. Brand names often only match packaged products.',

  'trend.empty': 'Log your weight a few times and the trend appears here.',
  'trend.noChange': 'No change yet',
  'trend.soFar': '{arrow} {amount} {unit} so far',

  'auth.badEmail': 'That doesn’t look like an email address.',
  'auth.useAtLeast': 'Use at least {count} characters.',

  // --- reporting a wrong food -------------------------------------------
  // The counterpart to submission. Submission is how a food gets in; this is
  // how one already in gets challenged — including the USDA and Open Food Facts
  // rows nobody here typed and nobody here has ever checked.
  'report.link': 'Report a problem',
  'report.title': 'What’s wrong with this food?',
  'report.lede':
    'Reporting changes nothing on its own — a person checks it. Tell us what you see and we can compare it against the source.',
  'report.wrongNumbers': 'The numbers are wrong',
  'report.wrongNumbersHint': 'Calories or macros don’t match the label',
  'report.wrongName': 'The name or brand is wrong',
  'report.wrongNameHint': 'Right food, wrong label on it',
  'report.duplicate': 'It’s already in here twice',
  'report.duplicateHint': 'The same food under another entry',
  'report.notFood': 'This isn’t a food',
  'report.notFoodHint': 'Spam, or something that shouldn’t be here',
  'report.other': 'Something else',
  'report.otherHint': 'Tell us below',
  'report.noteLabel': 'What does the label say? (optional)',
  'report.notePlaceholder': 'e.g. the pack says 250 kcal per 100 g, not 180',
  'report.send': 'Send the report',
  'report.sending': 'Sending…',
  'report.sent': 'Thank you',
  'report.sentBody':
    'Someone will compare this against the source. You can see what came of it under Settings → My reports.',
  'report.already': 'You have already reported this food. It is waiting to be checked.',
  'report.failed': 'Could not send that report.',

  'report.mine': 'My reports',
  'report.mineHint': 'Foods you said were wrong',
  'report.empty':
    'Nothing reported yet. If a food’s numbers don’t match the label, open it and tap “Report a problem”.',
  'report.statusOpen': 'Being checked',
  'report.statusAccepted': 'You were right',
  'report.statusDismissed': 'No change made',
  'report.resolvedCorrected': 'The numbers were corrected.',
  'report.resolvedWithdrawn': 'The food was removed from search.',
  'report.dismissedHint': 'Checked against the source, and it matches.',

  // Shown on a food that was withdrawn. Not hidden outright: it is still
  // reachable from a diary entry logged before the withdrawal, and that entry
  // is a record of what was eaten rather than a number still being claimed.
  'food.withdrawn': 'Withdrawn',
  'food.withdrawnBody':
    'A report about this food was upheld, so it no longer appears in search. Anything you already logged is unchanged — but treat the figures below with caution.',

  'food.kcalFor': 'kcal for {amount} {unit}',
  'food.mealSection': 'Meal',
  'food.quantitySection': 'Quantity',
  'food.amountIn': 'Amount in {unit}',
  'food.logAmount': 'Log {amount} {unit}',
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

  'welcome.1Title': 'Photographiez votre assiette',
  'welcome.1Body':
    'Prenez un repas en photo : l’app identifie ce qu’il contient, puis estime les quantités.',
  'welcome.2Title': 'Chaque chiffre a une source',
  'welcome.2Body':
    'Les calories et les macros viennent de l’USDA FoodData Central. Rien n’est inventé, et une valeur que personne n’a mesurée reste vide plutôt que de devenir un zéro.',
  'welcome.3Title': 'Des objectifs tirés de vos chiffres',
  'welcome.3Body':
    'Votre taille, votre poids, votre âge et le rythme que vous choisissez définissent l’objectif — pas une valeur par défaut pensée pour une personne moyenne.',
  'welcome.next': 'Suivant',
  'welcome.start': 'Commencer',
  'welcome.haveAccount': 'Vous avez déjà un compte ?',

  'auth.confirmTitle': 'Vérifiez vos e-mails',
  'auth.confirmBody':
    'Nous avons envoyé un lien de confirmation à {email}. Ouvrez-le pour terminer la création de votre compte.',
  'auth.confirmHint': "Rien après une minute ou deux ? Regardez dans vos courriers indésirables.",
  'auth.backToSignIn': 'Retour à la connexion',

  'auth.resetTitle': 'Réinitialiser votre mot de passe',
  'auth.resetSubtitle':
    'Saisissez votre e-mail et nous vous enverrons un lien pour définir un nouveau mot de passe.',
  'auth.resetSent': 'Vérifiez vos e-mails',
  'auth.resetSentBody':
    'Si un compte existe pour {email}, un lien est en route. Ouvrez-le sur cet appareil pour définir un nouveau mot de passe.',
  'auth.resetSend': 'Envoyer le lien',
  'auth.newPassword': 'Nouveau mot de passe',
  'auth.setPassword': 'Définir le mot de passe',
  'auth.resetDone': 'Mot de passe modifié',
  'auth.resetDoneBody': 'Vous êtes connecté.',
  'auth.resetLinkInvalid':
    'Ce lien a expiré ou a déjà été utilisé. Demandez-en un nouveau.',
  'auth.passwordsDiffer': 'Les deux mots de passe ne correspondent pas.',
  'auth.passwordTooShort': 'Utilisez au moins 8 caractères.',
  'auth.somethingWrong': 'Une erreur est survenue. Veuillez réessayer.',

  'auth.errInvalidCredentials': 'Cet e-mail et ce mot de passe ne correspondent pas.',
  'auth.errEmailNotConfirmed':
    'Confirmez d’abord votre e-mail : ouvrez le lien que nous vous avons envoyé, puis connectez-vous.',
  'auth.errUserExists': 'Un compte existe déjà pour cet e-mail. Essayez de vous connecter.',
  'auth.errWeakPassword': 'Ce mot de passe est trop faible. Utilisez au moins 8 caractères.',
  'auth.errRateLimited': 'Trop de tentatives. Attendez une minute et réessayez.',
  'auth.errNetwork': 'Impossible de joindre le serveur. Vérifiez votre connexion et réessayez.',
  'auth.errNotConfigured':
    'La connexion n’est pas configurée dans cette version. EXPO_PUBLIC_SUPABASE_URL et EXPO_PUBLIC_SUPABASE_ANON_KEY sont absents — redémarrez le serveur Expo après avoir ajouté mobile/.env.',
  'auth.errProviderDisabled':
    'La connexion par e-mail est désactivée pour ce projet. Activez-la dans Supabase sous Authentication → Sign In / Providers → Email.',
  'auth.errSignupDisabled': 'Les nouveaux comptes sont désactivés pour ce projet.',

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

  'water.title': 'Eau',
  'water.litres': 'litres aujourd’hui',
  'water.ofGoal': 'sur {goal} L',
  'water.undo': 'Annuler',
  'water.addLabel': 'Ajouter {ml} millilitres',
  'water.goalTitle': 'Objectif d’eau quotidien',
  'water.goalNone': 'Aucun',
  'water.goalNote':
    'Des références courantes, pas un chiffre calculé pour vous. Sans objectif, la carte affiche simplement ce que vous avez bu.',

  'progress.weightChanges': 'Évolution du poids',
  'progress.notEnoughData': 'Pas assez de données',
  'progress.noChange': 'Stable',
  'progress.gained': 'Pris',
  'progress.lost': 'Perdu',
  'progress.yourBmi': 'Votre IMC',
  'progress.yourWeightIs': 'Votre poids est',
  'progress.bmi.underweight': 'Insuffisant',
  'progress.bmi.healthy': 'Normal',
  'progress.bmi.overweight': 'Surpoids',
  'progress.bmi.obese': 'Obésité',

  'barcode.title': 'Scanner un code-barres',
  'barcode.hint': 'Alignez le code-barres dans le cadre',
  'barcode.looking': 'Recherche en cours…',
  'barcode.notFound': 'Absent de la base',
  'barcode.cantUse': 'Impossible d’utiliser celui-ci',
  'barcode.scanAgain': 'Scanner un autre',
  'barcode.searchInstead': 'Rechercher par nom',
  'barcode.needCamera': 'Cal Ai a besoin de l’appareil photo pour lire un code-barres. Rien n’est photographié ni conservé : le code est lu sur votre appareil.',
  'barcode.cameraBlocked': 'L’accès à l’appareil photo est désactivé. Réactivez-le dans les Réglages de votre appareil, puis réessayez.',
  'barcode.allowCamera': 'Autoriser l’appareil photo',
  'home.scanBarcode': 'Scanner un code-barres',

  'food.source': 'Source',
  'food.sourceOff': 'Données communautaires — saisies par des bénévoles depuis l’étiquette, sans vérification indépendante.',
  'food.sourceUser': 'Vous avez saisi ces chiffres depuis une étiquette.',
  'food.sourceEstimate': 'Estimé par l’IA faute de correspondance en base. À considérer comme un ordre de grandeur.',
  'food.addYourOwn': 'L’ajouter vous-même',
  'food.customTitle': 'Ajouter un aliment',
  'food.customIntro': 'Recopiez les chiffres de l’étiquette, pour 100 g. Laissez vide ce que l’étiquette n’indique pas : un champ vide reste vide plutôt que de devenir zéro.',
  'food.per100g': 'Pour 100 g',
  'food.nameLabel': 'Nom',
  'food.brandLabel': 'Marque (facultatif)',
  'food.servingLabel': 'Portion en grammes (facultatif)',
  'food.saveFood': 'Enregistrer',
  'food.privateNote': 'Enregistré sur votre compte uniquement. Il n’apparaîtra dans la recherche de personne d’autre.',

  'submit.title': 'Vos propositions',
  'submit.empty': 'Les aliments que vous proposez à la base partagée apparaissent ici. Ajoutez un aliment, puis touchez « Partager cet aliment ».',
  'submit.statusPrivate': 'Privé',
  'submit.statusPending': 'En cours d’examen',
  'submit.statusApproved': 'Partagé',
  'submit.statusRejected': 'Non retenu',
  'submit.pendingHint': 'En attente d’un relecteur. Vous pouvez continuer à l’utiliser entre-temps.',
  'submit.approvedHint': 'Cet aliment est maintenant dans la base partagée et tout le monde peut le trouver. Merci.',
  'submit.rejectedHint': 'Il reste sur votre compte et votre journal n’est pas affecté.',
  'submit.share': 'Partager cet aliment',
  'submit.shareBody': 'Proposez-le à la base partagée. Un relecteur le vérifie avant que quiconque puisse le voir, et il reste à vous dans tous les cas.',
  'submit.sharing': 'Envoi…',
  'submit.sent': 'Envoyé pour examen',
  'submit.mine': 'Mes propositions',
  'submit.mineHint': 'Les aliments que vous avez proposés à la base partagée',

  'credits.title': 'Crédits photo',
  'credits.lede': 'Les photos des aliments proviennent de Wikimedia Commons, partagées par leurs auteurs sous des licences qui demandent de les citer. Touchez une ligne pour voir l’original.',
  'credits.view': 'Voir l’original',
  'credits.empty': 'Aucune photo à créditer pour l’instant.',
  'credits.link': 'Crédits photo',

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

  'onboarding.goalCut': 'Perdre du gras',
  'onboarding.goalCutBody': 'Une perte de gras régulière, en gardant vos muscles',
  'onboarding.goalMaintain': 'Maintenir',
  'onboarding.goalMaintainBody': 'Garder votre poids actuel',
  'onboarding.goalLeanBulk': 'Prise de masse sèche',
  'onboarding.goalLeanBulkBody': 'Construire lentement, avec peu de gras pris',
  'onboarding.goalBulk': 'Prise de masse',
  'onboarding.goalBulkBody': 'Prendre plus vite, en acceptant un peu de gras',

  'onboarding.footnote': 'Vos mesures sont conservées sur votre compte uniquement.',
  'onboarding.next': 'Suivant',
  'onboarding.finish': 'Construire mon plan',
  'onboarding.failed': 'Une erreur est survenue. Réessayez.',

  'onboarding.sexTitle': 'Quelle équation utiliser ?',
  'onboarding.sexSubtitle':
    'Mifflin-St Jeor emploie une constante différente pour chacune. Il s’agit de composition corporelle, pas d’identité.',
  'onboarding.sexFemale': 'Femme',
  'onboarding.sexFemaleBody': 'Utilise la constante −161',
  'onboarding.sexMale': 'Homme',
  'onboarding.sexMaleBody': 'Utilise la constante +5',

  'onboarding.birthTitle': 'Quelle est votre date de naissance ?',
  'onboarding.birthSubtitle':
    'Le métabolisme baisse progressivement avec l’âge : la date compte plus qu’on ne le croit.',
  'onboarding.day': 'Jour',
  'onboarding.month': 'Mois',
  'onboarding.year': 'Année',

  'onboarding.bodyTitle': 'Taille et poids',
  'onboarding.bodySubtitle': 'Les deux entrent dans le calcul.',

  'onboarding.activityTitle': 'À quelle fréquence vous entraînez-vous ?',
  'onboarding.activitySubtitle':
    'Soyez honnête — surestimer ici est de loin la raison la plus fréquente d’un objectif calorique trop élevé.',
  'onboarding.sessionsPerWeek': '{count} séances par semaine',
  'onboarding.activitySedentary': 'Travail de bureau, peu ou pas d’exercice',
  'onboarding.activityLight': 'Des séances de temps en temps',
  'onboarding.activityModerate': 'Quelques séances par semaine',
  'onboarding.activityActive': 'Exercice intense presque tous les jours',
  'onboarding.activityVeryActive': 'Travail physique, ou deux séances par jour',

  'onboarding.goalTitle': 'Quel est votre objectif ?',
  'onboarding.goalSubtitle':
    'Cela détermine l’écart entre votre objectif et votre maintien.',

  'onboarding.targetTitle': 'Quel poids visez-vous ?',
  'onboarding.targetSubtitle':
    'Sert à la projection ci-dessous. Votre objectif calorique vient de votre but, pas de ce chiffre.',
  'onboarding.rulerNow': 'Actuel',

  'onboarding.readyHold': 'Prêt à vous maintenir ?',
  'onboarding.readyStart': 'Prêt à commencer ?',
  'onboarding.readyLose': 'Prêt à perdre {amount} {unit} ?',
  'onboarding.readyGain': 'Prêt à prendre {amount} {unit} ?',
  'onboarding.readySubtitle':
    'Ceux qui enregistrent régulièrement la première semaine sont bien plus nombreux à le faire encore la deuxième. Les premiers jours font tout.',
  'onboarding.curveDay': 'Jour {n}',
  'onboarding.curveCaveat':
    'À titre indicatif — la courbe illustre l’habitude, elle ne prédit rien vous concernant.',

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
  'settings.sectionAccount': 'Compte',
  'settings.sectionPreferences': 'Préférences',
  'settings.sectionAccountActions': 'Actions du compte',
  'settings.language': 'Langue',
  'settings.languageSystem': 'Suivre mon\nappareil',
  'settings.languageEnglish': 'English',
  'settings.languageFrench': 'Français',
  'settings.languageNote':
    'Les noms d’aliments viennent du catalogue et sont traduits séparément — quelques-uns peuvent rester en anglais tant qu’ils ne sont pas renseignés.',

  'nav.home': 'Accueil',
  'nav.progress': 'Progrès',
  'nav.settings': 'Paramètres',

  // Dimanche, Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi.
  'week.sun': 'D',
  'week.mon': 'L',
  'week.tue': 'M',
  'week.wed': 'M',
  'week.thu': 'J',
  'week.fri': 'V',
  'week.sat': 'S',
  'week.showDay': 'Afficher le {date}',

  'progress.title': 'Progrès',
  'progress.cantLoad': 'Impossible d’afficher vos progrès',
  'progress.loadFailed': 'Impossible de charger vos progrès.',
  'progress.streakOne': '1 jour d’affilée',
  'progress.streakMany': '{count} jours d’affilée',
  'progress.streakLogged': 'La journée est enregistrée — continuez.',
  'progress.streakKeepAlive': 'Enregistrez quelque chose aujourd’hui pour ne pas la perdre.',
  'progress.streakStart': 'Enregistrez un repas aujourd’hui pour en commencer une.',
  'progress.weight': 'Poids',
  'progress.goalLine': 'Objectif {target} kg · encore {remaining} kg',
  'progress.todaysWeight': 'Poids du jour (kg)',
  'progress.logWeight': 'Enregistrer',
  'progress.thisWeek': 'Cette semaine',
  'progress.weekAverage': 'moy. {kcal} kcal',
  'progress.targetCaption': 'Ligne pointillée : votre objectif de {kcal} kcal',

  'plan.building': 'Construction de votre plan…',
  'plan.cantLoad': 'Impossible de charger votre plan',
  'plan.loadFailed': 'Impossible de charger votre plan.',
  'plan.toDashboard': 'Aller au tableau de bord',
  'plan.eyebrow': 'Votre plan personnalisé',
  'plan.headlineLose': 'Atteindre',
  'plan.headlineGain': 'Aller vers',
  'plan.headlineBy': 'd’ici le',
  'plan.holdingAt': 'Se maintenir à',
  'plan.disclaimer':
    'La date suppose un rythme constant de {percent} % du poids corporel par semaine. Les deux extrémités sont calculées ; la courbe entre elles illustre, elle ne prédit pas — la progression réelle est irrégulière.',
  'plan.dailyTargets': 'Objectifs quotidiens',
  'plan.kcalPerDay': 'kcal par jour',
  'plan.howReached': 'Comment ce chiffre est obtenu',
  'plan.editable':
    'Vous pourrez tout modifier plus tard dans les Paramètres — rien n’est figé ici.',
  'plan.start': 'Commencer le suivi',

  'recipes.eyebrow': 'Vos recettes',
  'recipes.title': 'Repas personnalisés',
  'recipes.loadFailed': 'Impossible de charger vos recettes.',
  'recipes.emptyTitle': 'Rien d’enregistré',
  'recipes.emptyBody':
    'Composez un repas une fois — un chili, un smoothie, votre petit-déjeuner habituel — et enregistrez-le ensuite d’un seul geste.',
  'recipes.perServing': 'par portion',
  'recipes.ingredientsOne': '1 ingrédient',
  'recipes.ingredientsMany': '{count} ingrédients',
  'recipes.servingsOne': '1 portion',
  'recipes.servingsMany': '{count} portions',
  'recipes.new': 'Nouvelle recette',

  'recipe.edit': 'Modifier la recette',
  'recipe.new': 'Nouvelle recette',
  'recipe.name': 'Nom',
  'recipe.namePlaceholder': 'Chili du dimanche',
  'recipe.servings': 'Portions que donne la recette entière',
  'recipe.servingsHint': 'Vous enregistrerez des portions de celle-ci',
  'recipe.kcalPerServing': 'kcal par portion · {total} au total',
  'recipe.ingredients': 'Ingrédients ({count})',
  'recipe.emptyIngredients':
    'Rien pour l’instant. Recherchez un aliment pour commencer à composer.',
  'recipe.addIngredient': '+ Ajouter un ingrédient',
  'recipe.remove': 'Retirer {name}',
  'recipe.save': 'Enregistrer la recette',
  'recipe.saveChanges': 'Enregistrer les modifications',
  'recipe.delete': 'Supprimer la recette',
  'recipe.deleteTitle': 'Supprimer la recette ?',
  'recipe.deleteBody': '« {name} » sera supprimée définitivement.',
  'recipe.deleteFailed': 'Suppression impossible',
  'recipe.deleteFailedBody': 'Vérifiez votre connexion et réessayez.',
  'recipe.saveFailed': 'Impossible d’enregistrer cette recette.',
  'recipe.loadFailed': 'Impossible de charger cette recette.',
  'recipe.cantLoad': 'Impossible de charger cette recette',

  'chart.now': 'Maintenant',
  'chart.without': 'Sans Cal Ai',
  'macro.proteinShort': 'P',
  'macro.carbsShort': 'G',
  'macro.fatShort': 'L',
  'macro.noneLogged': 'Aucune macro enregistrée',
  'macro.reading':
    '{protein} grammes de protéines, {carbs} grammes de glucides, {fat} grammes de lipides',

  'a11y.goBack': 'Retour',
  'a11y.closeMenu': 'Fermer le menu',
  'a11y.closeLogMenu': 'Fermer le menu d’enregistrement',
  'a11y.logFood': 'Enregistrer un aliment',

  'nutrient.full': 'Nutrition complète',
  'nutrient.protein': 'Protéines',
  'nutrient.carbs': 'Glucides',
  'nutrient.sugars': 'dont sucres',
  'nutrient.fat': 'Lipides',
  'nutrient.saturates': 'dont acides gras saturés',
  'nutrient.fibre': 'Fibres',
  'nutrient.sodium': 'Sodium',
  'nutrient.sugarsField': 'Sucres (g)',
  'nutrient.saturatesField': 'Acides gras saturés (g)',
  'nutrient.fibreField': 'Fibres (g)',
  'nutrient.sodiumField': 'Sodium (mg)',

  'settings.dailyTargets': 'Objectifs quotidiens',
  'settings.gramsProtein': '{grams} g de protéines',
  'settings.gramsCarbs': '{grams} g de glucides',
  'settings.gramsFat': '{grams} g de lipides',
  'settings.editDetails': 'Modifier mes informations',
  'settings.editDetailsHint': 'Mensurations, activité, objectif',
  'settings.myRecipes': 'Mes recettes',
  'settings.myRecipesHint': 'Composez les repas que vous enregistrez souvent',
  'settings.signOut': 'Se déconnecter',

  'settings.sectionDanger': 'Supprimer le compte',
  'settings.deleteAccount': 'Supprimer mon compte',
  'settings.deleteAccountHint': 'Définitif. Tout est effacé.',
  'settings.deleteTitle': 'Supprimer votre compte ?',
  'settings.deleteBody':
    'Votre journal, vos poids, votre profil, vos repas, vos recettes et vos aliments privés seront effacés. Aucun retour en arrière n’est possible.',
  'settings.deleteShared':
    'Les aliments que vous avez partagés et qui ont été validés restent dans la base, sans votre nom — d’autres personnes les ont déjà enregistrés.',
  'settings.deleteConfirmLabel': 'Saisissez {email} pour confirmer',
  'settings.deleteConfirm': 'Tout supprimer',
  'settings.deleting': 'Suppression…',
  'settings.deleteMismatch': 'Cela ne correspond pas à votre adresse e-mail.',
  'settings.deleteFailed': 'Impossible de supprimer le compte. Réessayez dans un instant.',

  'food.cantLoad': 'Impossible de charger cet aliment',
  'food.loadFailed': 'Impossible de charger cet aliment.',
  'food.logFailed': 'Impossible d’enregistrer cet aliment.',
  'food.amountPositive': 'Saisissez une quantité supérieure à zéro.',

  'catalogue.loadFailed': 'Impossible de charger le catalogue.',
  'catalogue.logFailed': 'Enregistrement impossible.',

  'search.label': 'Rechercher',
  'search.placeholder': 'Blanc de poulet, avoine, banane…',
  'search.noMatches': 'Aucun résultat',
  'search.failed': 'La recherche a échoué.',

  'scan.eyebrow': 'Photographier un repas',
  'scan.title': 'Photographiez votre repas',
  'scan.intro':
    'Cal Ai identifie les aliments et estime les portions. Vous confirmez les deux avant tout enregistrement — et les valeurs nutritionnelles viennent toujours de l’USDA, jamais de la photo.',
  'scan.takePhoto': 'Prendre une photo',
  'scan.takePhotoHint': 'Remplissez le cadre avec l’assiette',
  'scan.fromLibrary': 'Choisir dans la galerie',
  'scan.fromLibraryHint': 'Une photo déjà prise',
  'scan.orDescribe': 'Ou décrivez-le',
  'scan.describePlaceholder': 'deux œufs durs et une tranche de pain de seigle',
  'scan.identify': 'Identifier les aliments',
  'scan.opening': 'Ouverture…',
  'scan.lookingPhoto': 'Analyse de votre assiette…',
  'scan.lookingText': 'Lecture de votre description…',
  'scan.takesSeconds': 'Cela prend généralement quelques secondes.',
  'scan.detected': 'Détecté',
  'scan.noMatchInDb': 'Aucune correspondance dans la base',
  'scan.lowConfidence': 'Faible confiance — à vérifier',
  'scan.searchManually': 'Le rechercher manuellement',
  'scan.grams': 'Grammes',
  'scan.selectedCount': '{selected} sur {total} sélectionnés',
  'scan.nothingSelected': 'Rien de sélectionné',
  'scan.logCount': 'Enregistrer {count}',
  'scan.tryAnother': 'Essayer une autre photo',

  'scan.noFoodPhoto': 'Aucun aliment sur cette photo',
  'scan.noFoodText': 'Aucun aliment dans cette description',
  'scan.noFoodPhotoBody':
    'Réessayez avec l’assiette occupant davantage le cadre, sous une bonne lumière.',
  'scan.noFoodTextBody':
    'Nommez les aliments simplement — « blanc de poulet, riz, brocoli ».',

  'scan.cameraOff': 'L’accès à l’appareil photo est désactivé',
  'scan.photosOff': 'L’accès aux photos est désactivé',
  'scan.permissionAsk':
    'Cal Ai a besoin de l’autorisation de lire la photo pour identifier ce qu’elle contient.',
  'scan.permissionBlocked':
    'Réactivez-le dans les Réglages de votre appareil, sous Cal Ai, puis réessayez.',
  'scan.badPhoto': 'Impossible de lire cette photo',
  'scan.badPhotoBody': 'Reprenez-la, ou choisissez-en une autre dans votre galerie.',
  'scan.logPartial': 'Enregistrement incomplet',
  'scan.logPartialBody':
    'Certains éléments ont peut-être été enregistrés. Vérifiez votre journal avant de réessayer.',

  'scan.failedPhoto': 'Échec de l’analyse',
  'scan.failedText': 'Lecture impossible',
  'scan.failedBody': 'Une erreur inattendue est survenue. Réessayez dans un instant.',
  'scan.notEnabled': 'L’analyse n’est pas activée',
  'scan.noKey': 'Le serveur n’a aucune clé IA configurée.',
  'scan.busy': 'L’IA est très sollicitée en ce moment',
  'scan.cantAnalysePhoto': 'Impossible d’analyser la photo',
  'scan.cantIdentify': 'Impossible d’identifier ces aliments',

  'error.timeout':
    'Le serveur a mis trop de temps à répondre. Vérifiez votre connexion et réessayez.',
  'error.network': 'Impossible de joindre le serveur. Vérifiez votre connexion et réessayez.',
  'error.parse': 'Le serveur a renvoyé une réponse inattendue. Réessayez dans un instant.',
  'error.server': 'Une erreur est survenue sur le serveur. Réessayez dans un instant.',
  'error.rateLimited': 'Trop de tentatives. Réessayez dans {wait}.',
  'error.waitSecond': '1 seconde',
  'error.waitSeconds': '{count} secondes',
  'error.waitMinute': '1 minute',
  'error.waitMinutes': '{count} minutes',
  'error.tryAgain': 'Vérifiez votre connexion et réessayez.',
  'error.pleaseRetry': 'Veuillez réessayer.',

  'home.loadFailed': 'Impossible de charger votre journée.',
  'home.logFailed': 'Enregistrement impossible',
  'home.deleteEntryTitle': 'Supprimer cette entrée ?',
  'home.deleteEntryBody': 'Retirer {name} ?',
  'home.deleteEntryFailed': 'Impossible de supprimer cette entrée',
  'home.emptyUsuals':
    'Touchez une de vos habitudes ci-dessus, ou utilisez + pour photographier un repas.',
  'home.emptyFresh': 'Touchez + pour photographier un repas ou rechercher un aliment.',
  'home.longPressDelete': 'Appui long pour supprimer',

  'settings.showWorking': 'Comment ce chiffre est-il calculé ?',
  'settings.hideWorking': 'Masquer le détail',

  'meals.loadFailed': 'Impossible de charger vos repas.',
  'meals.saveFailed': 'Impossible d’enregistrer ce repas.',
  'meals.deleteFailed': 'Impossible de supprimer ce repas.',

  'search.searching': 'Recherche…',
  'search.failedTitle': 'La recherche a échoué',
  'search.cachedOnly':
    'L’USDA est injoignable : seuls des aliments déjà mis en cache sont affichés.',
  'search.per100': 'pour 100 g',
  'search.hint':
    'Saisissez au moins {count} caractères. Les aliments tunisiens et sélectionnés viennent en premier — chaque chiffre remonte à sa source.',
  'search.fallbackNotice':
    'Aucun de nos aliments ne correspond : ceux-ci viennent de la base USDA. Les noms sont les leurs.',
  'search.noMatchesBody':
    'Essayez un terme plus simple — « avoine » plutôt que « flocons d’avoine bio ». Les marques ne correspondent souvent qu’à des produits emballés.',

  'trend.empty': 'Pesez-vous quelques fois et la tendance apparaîtra ici.',
  'trend.noChange': 'Aucun changement',
  'trend.soFar': '{arrow} {amount} {unit} jusqu’ici',

  'auth.badEmail': 'Cela ne ressemble pas à une adresse e-mail.',
  'auth.useAtLeast': 'Utilisez au moins {count} caractères.',

  'report.link': 'Signaler un problème',
  'report.title': 'Qu’est-ce qui ne va pas ?',
  'report.lede':
    'Un signalement ne change rien à lui seul — une personne le vérifie. Dites-nous ce que vous voyez et nous comparerons avec la source.',
  'report.wrongNumbers': 'Les chiffres sont faux',
  'report.wrongNumbersHint': 'Les calories ou les macros ne correspondent pas à l’étiquette',
  'report.wrongName': 'Le nom ou la marque est faux',
  'report.wrongNameHint': 'Le bon aliment, mais mal nommé',
  'report.duplicate': 'Il y est déjà en double',
  'report.duplicateHint': 'Le même aliment sous une autre entrée',
  'report.notFood': 'Ce n’est pas un aliment',
  'report.notFoodHint': 'Spam, ou quelque chose qui n’a rien à faire ici',
  'report.other': 'Autre chose',
  'report.otherHint': 'Précisez ci-dessous',
  'report.noteLabel': 'Que dit l’étiquette ? (facultatif)',
  'report.notePlaceholder': 'ex. le paquet indique 250 kcal pour 100 g, pas 180',
  'report.send': 'Envoyer le signalement',
  'report.sending': 'Envoi…',
  'report.sent': 'Merci',
  'report.sentBody':
    'Quelqu’un va comparer avec la source. Vous verrez la suite dans Paramètres → Mes signalements.',
  'report.already': 'Vous avez déjà signalé cet aliment. Il est en attente de vérification.',
  'report.failed': 'Impossible d’envoyer ce signalement.',

  'report.mine': 'Mes signalements',
  'report.mineHint': 'Les aliments que vous avez signalés',
  'report.empty':
    'Aucun signalement. Si les chiffres d’un aliment ne correspondent pas à l’étiquette, ouvrez-le et touchez « Signaler un problème ».',
  'report.statusOpen': 'En cours de vérification',
  'report.statusAccepted': 'Vous aviez raison',
  'report.statusDismissed': 'Aucun changement',
  'report.resolvedCorrected': 'Les chiffres ont été corrigés.',
  'report.resolvedWithdrawn': 'L’aliment a été retiré de la recherche.',
  'report.dismissedHint': 'Vérifié auprès de la source : cela correspond.',

  'food.withdrawn': 'Retiré',
  'food.withdrawnBody':
    'Un signalement concernant cet aliment a été retenu : il n’apparaît plus dans la recherche. Ce que vous avez déjà enregistré reste inchangé — mais considérez les chiffres ci-dessous avec prudence.',

  'food.kcalFor': 'kcal pour {amount} {unit}',
  'food.mealSection': 'Repas',
  'food.quantitySection': 'Quantité',
  'food.amountIn': 'Quantité en {unit}',
  'food.logAmount': 'Enregistrer {amount} {unit}',
};

export type Language = 'en' | 'fr';

export const DICTIONARIES: Record<Language, Dictionary> = { en, fr };

/**
 * Weekday initial keys, indexed the way `Date.getDay()` counts — Sunday first.
 *
 * Exported so the week strip and the progress chart index the same array. They
 * each had their own `['S','M','T','W','T','F','S']` literal, which is one
 * definition too many for something whose ordering is easy to get subtly wrong
 * and whose bug (every day labelled one place off) is easy to miss.
 */
export const WEEKDAY_KEYS = [
  'week.sun',
  'week.mon',
  'week.tue',
  'week.wed',
  'week.thu',
  'week.fri',
  'week.sat',
] as const satisfies readonly StringKey[];
