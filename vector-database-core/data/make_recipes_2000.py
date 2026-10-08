"""Make data/recipes_2000.csv: the course's 50 recipes plus 1,950 generated ones (lesson 14).

Deterministic: the same file every run. Run from this folder:  python make_recipes_2000.py
Columns: slug,title,description,cuisine,vegetarian,minutes
The slug is the recipe's permanent key (lesson 14 turns it into a point id with uuid5).
"""
import re

import numpy as np
import pandas as pd

rng = np.random.default_rng(14)

# main ingredient -> (vegetarian?, short phrase used in descriptions)
MAINS = {
    "chicken": (False, "tender chicken thighs"), "beef": (False, "strips of beef"),
    "pork": (False, "pork shoulder"), "lamb": (False, "lamb"), "salmon": (False, "salmon fillets"),
    "shrimp": (False, "juicy shrimp"), "cod": (False, "flaky cod"), "turkey": (False, "turkey mince"),
    "duck": (False, "duck breast"), "tuna": (False, "seared tuna"),
    "tofu": (True, "crispy tofu"), "chickpea": (True, "chickpeas"), "mushroom": (True, "mushrooms"),
    "lentil": (True, "lentils"), "halloumi": (True, "grilled halloumi"), "paneer": (True, "paneer"),
    "black bean": (True, "black beans"), "cauliflower": (True, "roasted cauliflower"),
    "sweet potato": (True, "sweet potato"), "eggplant": (True, "eggplant"),
    "spinach": (True, "spinach"), "tempeh": (True, "tempeh"),
}
# dish -> (cuisine, typical minutes, description template)
DISHES = {
    "curry": ("Indian", 40, "{main} simmered in a {flavour} curry sauce with onion, ginger and garam masala, served with rice."),
    "tacos": ("Mexican", 25, "Soft tortillas filled with {flavour} {main}, salsa, lime and shredded cabbage."),
    "stir-fry": ("Chinese", 20, "{main} tossed in a hot wok with vegetables and a {flavour} sauce, served over noodles."),
    "risotto": ("Italian", 45, "Creamy arborio rice stirred slowly with {main}, parmesan and a {flavour} finish."),
    "salad": ("Mediterranean", 15, "A fresh bowl of leaves, cucumber and {main} with a {flavour} dressing."),
    "soup": ("French", 50, "A warming pot of {main} and root vegetables in a {flavour} broth, served hot."),
    "pasta": ("Italian", 25, "Pasta tossed with {main}, garlic and a {flavour} sauce, topped with herbs."),
    "burger": ("American", 30, "A toasted bun with a {flavour} {main} patty, pickles and crunchy lettuce."),
    "skewers": ("Greek", 35, "{main} threaded on skewers, grilled over high heat and brushed with a {flavour} glaze."),
    "stew": ("British", 120, "{main} braised slowly with carrots, potatoes and a {flavour} gravy until thick."),
    "noodle bowl": ("Japanese", 30, "Noodles in a steaming broth with {main}, spring onions and a {flavour} kick."),
    "wrap": ("Middle Eastern", 20, "Warm flatbread rolled around {main}, hummus, salad and a {flavour} sauce."),
    "traybake": ("British", 55, "{main} and vegetables roasted together on one tray with a {flavour} seasoning."),
    "fried rice": ("Chinese", 20, "Day-old rice fried with egg, peas and {main} in a {flavour} sauce."),
    "pie": ("British", 75, "{main} in a {flavour} filling under a golden, flaky pastry lid."),
    "green curry": ("Thai", 35, "{main} cooked in coconut milk with green curry paste and a {flavour} edge."),
    "enchiladas": ("Mexican", 50, "Tortillas rolled around {main}, covered with a {flavour} sauce and cheese, then baked."),
    "flatbread": ("Middle Eastern", 25, "Crisp flatbread topped with {main}, yogurt and a {flavour} drizzle."),
}
# modifier in the title -> flavour words in the description
MODIFIERS = {
    "Spicy": "fiery chili", "Smoky": "smoky paprika", "Lemon garlic": "bright lemon and garlic",
    "Creamy": "rich, creamy", "Honey ginger": "sweet honey and ginger", "Herby": "fresh herb",
}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


base = pd.read_csv("recipes_50.csv").drop(columns="id")
base.insert(0, "slug", base.title.map(slugify))

combos = [(m, d, f) for m in MAINS for d in DISHES for f in MODIFIERS
          if slugify(f"{f} {m} {d}") not in set(base.slug)]   # e.g. "Spicy tofu stir-fry" exists
picked = rng.choice(len(combos), size=2000 - len(base), replace=False)
rows = []
for i in sorted(picked):
    main, dish, mod = combos[i]
    veg, phrase = MAINS[main]
    cuisine, minutes, template = DISHES[dish]
    title = f"{mod} {main} {dish}"
    text = template.format(main=phrase, flavour=MODIFIERS[mod])
    rows.append({"slug": slugify(title), "title": title, "description": text[0].upper() + text[1:],
                 "cuisine": cuisine, "vegetarian": veg,
                 "minutes": int(max(5, minutes + rng.integers(-2, 3) * 5))})

recipes = pd.concat([base, pd.DataFrame(rows)], ignore_index=True)
assert recipes.slug.is_unique and len(recipes) == 2000
recipes.to_csv("recipes_2000.csv", index=False)
print(recipes.shape, recipes.vegetarian.mean().round(2), recipes.cuisine.nunique())
