"""A short, curated list of foods people actually log.

**Why a curated list exists at all when USDA has 300,000 entries.**

USDA is authoritative and unusable as a browsing surface. Searching "chicken"
returns "Chicken, broilers or fryers, dark meat, meat only, cooked, stewed"
alongside forty near-identical variants, and a user who wants to log a chicken
breast has to read taxonomy to find one. The database is the right source of
*numbers* and the wrong source of *names*.

So this list is a menu, not a database. Each entry is a short human name, an
emoji, and the search term that finds the right USDA row. Nutrition still comes
entirely from USDA — nothing here carries a calorie — but the user meets
"Chicken breast 🍗" instead of a taxonomic string.

**On the emoji.** They stand in for photographs deliberately. Food photos would
mean either bundling megabytes of images or loading them from a third party on
every render — one bloats the app, the other leaks what the user is browsing and
breaks offline. Emoji render instantly from the system font at any size, cost
nothing, and are legible at chip scale where a 40px photo is a smear.

Kept deliberately short. A curated list that grows to a thousand entries has
become the thing it was meant to replace.
"""

from typing import NamedTuple


class PopularFood(NamedTuple):
    #: What the user reads. Short enough to fit a chip.
    name: str
    emoji: str
    #: What we search USDA with. Not shown — this is the bridge from the
    #: friendly name to the authoritative row.
    search_term: str
    category: str


#: Grouped so the browse screen has sections rather than one long grid.
POPULAR_FOODS: tuple[PopularFood, ...] = (
    # --- Protein ---------------------------------------------------------
    PopularFood("Chicken breast", "🍗", "chicken breast", "Protein"),
    PopularFood("Eggs", "🥚", "egg whole raw", "Protein"),
    PopularFood("Salmon", "🐟", "salmon atlantic", "Protein"),
    PopularFood("Tuna", "🐠", "tuna light canned water", "Protein"),
    PopularFood("Beef mince", "🥩", "ground beef", "Protein"),
    PopularFood("Turkey", "🦃", "turkey breast", "Protein"),
    PopularFood("Prawns", "🍤", "shrimp cooked", "Protein"),
    PopularFood("Tofu", "🧊", "tofu firm", "Protein"),
    PopularFood("Lentils", "🫘", "lentils cooked", "Protein"),
    PopularFood("Chickpeas", "🫛", "chickpeas cooked", "Protein"),
    # --- Carbs -----------------------------------------------------------
    PopularFood("White rice", "🍚", "rice white cooked", "Carbs"),
    PopularFood("Brown rice", "🌾", "rice brown cooked", "Carbs"),
    PopularFood("Pasta", "🍝", "pasta cooked", "Carbs"),
    PopularFood("Bread", "🍞", "bread whole wheat", "Carbs"),
    PopularFood("Oats", "🥣", "oats rolled", "Carbs"),
    PopularFood("Potato", "🥔", "potato baked flesh", "Carbs"),
    PopularFood("Sweet potato", "🍠", "sweet potato cooked", "Carbs"),
    PopularFood("Couscous", "🍲", "couscous cooked", "Carbs"),
    PopularFood("Tortilla", "🌯", "tortilla flour", "Carbs"),
    PopularFood("Quinoa", "🌱", "quinoa cooked", "Carbs"),
    # --- Fruit -----------------------------------------------------------
    PopularFood("Banana", "🍌", "banana raw", "Fruit"),
    PopularFood("Apple", "🍎", "apple raw with skin", "Fruit"),
    PopularFood("Orange", "🍊", "orange raw", "Fruit"),
    PopularFood("Strawberries", "🍓", "strawberries raw", "Fruit"),
    PopularFood("Blueberries", "🫐", "blueberries raw", "Fruit"),
    PopularFood("Grapes", "🍇", "grapes raw", "Fruit"),
    PopularFood("Watermelon", "🍉", "watermelon raw", "Fruit"),
    PopularFood("Mango", "🥭", "mango raw", "Fruit"),
    PopularFood("Pineapple", "🍍", "pineapple raw", "Fruit"),
    PopularFood("Avocado", "🥑", "avocado raw", "Fruit"),
    # --- Vegetables ------------------------------------------------------
    PopularFood("Broccoli", "🥦", "broccoli raw", "Vegetables"),
    PopularFood("Tomato", "🍅", "tomato red raw", "Vegetables"),
    PopularFood("Carrot", "🥕", "carrots raw", "Vegetables"),
    PopularFood("Spinach", "🥬", "spinach raw", "Vegetables"),
    PopularFood("Cucumber", "🥒", "cucumber raw", "Vegetables"),
    PopularFood("Onion", "🧅", "onions raw", "Vegetables"),
    PopularFood("Bell pepper", "🫑", "peppers sweet red raw", "Vegetables"),
    PopularFood("Sweetcorn", "🌽", "corn sweet yellow", "Vegetables"),
    PopularFood("Mushrooms", "🍄", "mushrooms white raw", "Vegetables"),
    PopularFood("Aubergine", "🍆", "eggplant raw", "Vegetables"),
    # --- Dairy -----------------------------------------------------------
    PopularFood("Milk", "🥛", "milk whole", "Dairy"),
    PopularFood("Greek yoghurt", "🍶", "yogurt greek plain", "Dairy"),
    PopularFood("Cheddar", "🧀", "cheese cheddar", "Dairy"),
    PopularFood("Butter", "🧈", "butter salted", "Dairy"),
    PopularFood("Cottage cheese", "🥣", "cheese cottage", "Dairy"),
    # --- Nuts, fats and extras ------------------------------------------
    PopularFood("Peanut butter", "🥜", "peanut butter", "Nuts & fats"),
    PopularFood("Almonds", "🌰", "almonds raw", "Nuts & fats"),
    PopularFood("Olive oil", "🫒", "oil olive", "Nuts & fats"),
    PopularFood("Walnuts", "🥥", "walnuts english", "Nuts & fats"),
    PopularFood("Honey", "🍯", "honey", "Nuts & fats"),
    # --- Meals people log as one thing ----------------------------------
    PopularFood("Pizza", "🍕", "pizza cheese", "Common meals"),
    PopularFood("Burger", "🍔", "hamburger single patty", "Common meals"),
    PopularFood("Sandwich", "🥪", "sandwich ham cheese", "Common meals"),
    PopularFood("Salad", "🥗", "salad vegetable tossed", "Common meals"),
    PopularFood("Sushi", "🍣", "sushi", "Common meals"),
    PopularFood("Soup", "🍜", "soup chicken noodle", "Common meals"),
    PopularFood("Fries", "🍟", "potatoes french fried", "Common meals"),
    PopularFood("Chocolate", "🍫", "chocolate milk candy", "Common meals"),
    PopularFood("Coffee", "☕", "coffee brewed", "Drinks"),
    PopularFood("Orange juice", "🧃", "orange juice raw", "Drinks"),
)

#: Section order for the browse screen, so it is stable rather than dict-order.
CATEGORIES: tuple[str, ...] = (
    "Protein",
    "Carbs",
    "Fruit",
    "Vegetables",
    "Dairy",
    "Nuts & fats",
    "Common meals",
    "Drinks",
)
