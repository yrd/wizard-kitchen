import json
import logging
import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

import requests
from django.core.cache import caches
from django.core.management.base import BaseCommand, CommandParser
from django.db import models, transaction
from django.db.models import functions

from cookpot.ingredients.models import (
    Ingredient,
    IngredientMolecule,
    IngredientName,
    Molecule,
)

FLAVORDB_CATEGORY_MAPPINGS = {
    "cereal": Ingredient.Category.CEREALS_CEREAL,
    "seed": Ingredient.Category.NUTSEED_SEED,
    "Plant": Ingredient.Category.PLANT,
    "Vegetable": Ingredient.Category.VEGETABLE,
    "fishseafood-fish": Ingredient.Category.AQUATIC_FISH,
    "fishseafood-seafood": Ingredient.Category.AQUATIC_SEAFOOD,
    "cerealcrop": Ingredient.Category.CEREALS,
    "cerealcrop-cereal": Ingredient.Category.CEREALS_CEREAL,
    "cerealcrop-maize": Ingredient.Category.CEREALS_MAIZE,
    "plantderivative": Ingredient.Category.PLANT_DERIVATIVE,
}

FOODB_GROUP_MAPPINGS = {
    ("Animal foods", "Caprae"): Ingredient.Category.MEAT,
    ("Animal foods", "Poultry"): Ingredient.Category.MEAT,
    ("Animal foods", "Swine"): Ingredient.Category.MEAT,
    ("Aquatic foods", "Crustaceans"): Ingredient.Category.AQUATIC_SEAFOOD,
    ("Aquatic foods", "Fishes"): Ingredient.Category.AQUATIC_FISH,
    ("Aquatic foods", "Mollusks"): Ingredient.Category.AQUATIC_SEAFOOD,
    ("Aquatic foods", "Other aquatic foods"): Ingredient.Category.AQUATIC,
    ("Aquatic foods", "Seaweed"): Ingredient.Category.AQUATIC_SEAWEED,
    ("Baking goods", "Substitutes"): Ingredient.Category.ADDITIVE,
    ("Beverages", "Alcoholic beverages"): Ingredient.Category.BEVERAGE_ALCOHOLIC,
    ("Beverages", "Beverages"): Ingredient.Category.BEVERAGE,
    ("Beverages", "Fermented beverages"): Ingredient.Category.BEVERAGE_ALCOHOLIC,
    ("Cereals and cereal products", "Cereals"): Ingredient.Category.CEREALS_CEREAL,
    ("Cereals and cereal products", "Leavened breads"): Ingredient.Category.CEREALS,
    (
        "Cocoa and cocoa products",
        "Cocoa products",
    ): Ingredient.Category.PLANT_DERIVATIVE,
    ("Cocoa and cocoa products", "Cocoa"): Ingredient.Category.PLANT_DERIVATIVE,
    ("Coffee and coffee products", "Coffee"): Ingredient.Category.BEVERAGE_CAFFEINATED,
    ("Confectioneries", "Candies"): Ingredient.Category.BAKERY_CANDIES,
    ("Eggs", "Eggs"): Ingredient.Category.ANIMAL_PRODUCT,
    ("Fats and oils", "Animal fats"): Ingredient.Category.ANIMAL_PRODUCT,
    ("Fruits", "Berries"): Ingredient.Category.FRUIT_BERRY,
    ("Fruits", "Citrus"): Ingredient.Category.FRUIT_CITRUS,
    ("Fruits", "Drupes"): Ingredient.Category.FRUIT,
    ("Fruits", "Other fruits"): Ingredient.Category.FRUIT,
    ("Fruits", "Pomes"): Ingredient.Category.FRUIT,
    ("Fruits", "Tropical fruits"): Ingredient.Category.FRUIT,
    ("Gourds", "Gourds"): Ingredient.Category.VEGETABLE_GOURD,
    ("Herbs and Spices", "Herb and spice mixtures"): Ingredient.Category.ADDITIVE,
    ("Herbs and Spices", "Herbs"): Ingredient.Category.HERB,
    ("Herbs and Spices", "Oilseed crops"): Ingredient.Category.FLOWER,
    ("Herbs and Spices", "Spices"): Ingredient.Category.SPICE,
    ("Herbs and spices", "Oilseed crops"): Ingredient.Category.FLOWER,
    ("Milk and milk products", "Fermented milk products"): Ingredient.Category.DAIRY,
    ("Milk and milk products", "Other milk products"): Ingredient.Category.DAIRY,
    ("Milk and milk products", "Unfermented milks"): Ingredient.Category.DAIRY,
    ("Nuts", "Nuts"): Ingredient.Category.NUTSEED_NUT,
    ("Pulses", "Beans"): Ingredient.Category.NUTSEED_LEGUME,
    ("Pulses", "Peas"): Ingredient.Category.NUTSEED_LEGUME,
    ("Pulses", "Pulses"): Ingredient.Category.NUTSEED_LEGUME,
    # This is only soy sauce.
    ("Soy", "Soy products"): Ingredient.Category.ADDITIVE,
    ("Teas", "Teas"): Ingredient.Category.BEVERAGE,
    ("Vegetables", ""): Ingredient.Category.VEGETABLE,
    ("Vegetables", "Cabbages"): Ingredient.Category.VEGETABLE_CABBAGE,
    ("Vegetables", "Fruit vegetables"): Ingredient.Category.VEGETABLE_FRUIT,
    ("Vegetables", "Leaf vegetables"): Ingredient.Category.VEGETABLE,
    ("Vegetables", "Mushrooms"): Ingredient.Category.FUNGUS,
    ("Vegetables", "Onion-family vegetables"): Ingredient.Category.VEGETABLE,
    ("Vegetables", "Other vegetables"): Ingredient.Category.VEGETABLE,
    ("Vegetables", "Root vegetables"): Ingredient.Category.VEGETABLE_ROOT,
    ("Vegetables", "Stalk vegetables"): Ingredient.Category.VEGETABLE,
}


class Command(BaseCommand):
    help = "Fetch ingredient information from upstream databases."

    @transaction.atomic
    def _handle_flavordb_entity(self, entity_id: int, data: Any) -> bool:
        assert isinstance(data, Mapping), "Response was not a JSON object."

        assert isinstance(
            category := data.get("category"), str
        ), f"Category must be a string, got {type(category)}."
        # See if we have a remapping for the category. This is because some of the
        # categories are still present twice upstream.
        category = FLAVORDB_CATEGORY_MAPPINGS.get(category, category)
        if category not in Ingredient.Category.values:
            logging.warning(f"Entity {entity_id}: got unknown category {category}.")
            category = Ingredient.Category.UNCATEGORIZED

        assert isinstance(
            wikipedia_url := data.get("entity_alias_url"), str
        ), f"Alias URL must be a string, got {type(wikipedia_url)}"
        if wikipedia_url.startswith("https://en.wikipedia.org/wiki/"):
            wikipedia_title = wikipedia_url[30:]
        else:
            wikipedia_title = ""

        ingredient, created = Ingredient.objects.update_or_create(
            flavordb_id=entity_id,
            defaults={"category": category, "wikipedia_title": wikipedia_title},
        )

        assert isinstance(
            molecules := data.get("molecules"), Sequence
        ), f"Molecules property must be a list, got {type(molecules)}."
        for molecule in molecules:
            assert isinstance(
                molecule, Mapping
            ), f"Molecule items must be dictionaries, got {type(molecules)}."
            assert isinstance(
                molecule_pubchem_id := molecule.get("pubchem_id"), int
            ), f"PubChem IDs must be integers, got {type(molecule_pubchem_id)}"
            assert isinstance(
                # Note: the API misspells this as "fooddb_id" (with two d's).
                molecule_foodb_id := molecule.get("fooddb_id"),
                str,
            ), f"FooDB IDs must be strings, got {type(molecule_foodb_id)}"

            molecule, _ = Molecule.objects.get_or_create(
                pubchem_id=molecule_pubchem_id,
                defaults={"foodb_id": molecule_foodb_id},
            )
            assert molecule.foodb_id == molecule_foodb_id, (
                f"FooDB ID of existing molecule {molecule_pubchem_id} did not match: "
                f"{molecule.foodb_id!r} != {molecule_foodb_id}"
            )

            ingredient.molecule_entries.update_or_create(
                molecule=molecule,
                defaults={"flavordb_found": True},
            )

        assert isinstance(
            main_name := data.get("entity_alias_readable"), str
        ), f"Entity names property must be a string, got {type(main_name)}."
        assert isinstance(
            raw_aliases := data.get("entity_alias_synonyms"), str
        ), f"Entity names property must be a string, got {type(raw_aliases)}."
        # Note: don't use a set here because the order is actually important.
        all_names = [
            unicodedata.normalize("NFC", name.strip())
            for name in f"{main_name},{raw_aliases}".split(",")
        ]
        # Do a quick and dirty duplicate check. This should handle 99% of all entries
        # because sometimes the aliases contain the main name.
        try:
            if all_names[0] == all_names[1]:
                del all_names[0]
        except IndexError:
            pass
        for index, label in enumerate(all_names):
            if not label:
                continue
            ingredient.names.update_or_create(
                label=label,
                defaults={"priority": index},
            )

        return created

    def sync_flavordb(self) -> None:
        IngredientMolecule.objects.update(flavordb_found=False)

        session = requests.Session()
        for entity_id in range(1000):
            cache_key = f"flavordb_{entity_id}"
            response = caches["default"].get(cache_key, None)
            if response is None:
                response = session.get(
                    "https://cosylab.iiitd.edu.in/flavordb/entities_json",
                    params={"id": entity_id},
                    headers={"Accept": "application/json"},
                )
                caches["default"].set(cache_key, response, None)
            assert isinstance(response, requests.Response)

            if response.status_code == 404:
                logging.warning(f"[FlavorDB] Entity {entity_id}: entity not found.")
                continue

            try:
                response.raise_for_status()
                if self._handle_flavordb_entity(entity_id, response.json()):
                    logging.info(f"[FlavorDB] Entity {entity_id}: created new record.")
                else:
                    logging.debug(
                        f"[FlavorDB] Entity {entity_id}: updated existing record."
                    )
            except:
                logging.exception(
                    f"[FlavorDB] Entity {entity_id}: error while processing."
                )

    def sync_foodb_ingredients(
        self,
        foodb_path: str,
    ) -> dict[int, str]:
        unhandled_items = list[Mapping[str, Any]]()

        ingredient_names = (
            IngredientName.objects
            # This order_by() removes the default grouping because the names are
            # ordered.
            .order_by().annotate(
                mangled_label=functions.Replace(
                    functions.Lower(models.F("label")),
                    models.Value(" "),
                    models.Value(""),
                )
            )
        )

        # Get only those names that are actually unique or are the first in their
        # priority list, because some synonyms are present in FlavorDB with multiple
        # ingredients.
        mangled_name_list = list(
            ingredient_names.values_list("mangled_label")
            .annotate(
                count=models.Count("pk"),
                min_priority=models.Min("priority"),
            )
            .filter(models.Q(count=1) | models.Q(min_priority=0))
            .values_list("mangled_label", "min_priority")
        )
        known_mangled_names = {name for (name, _) in mangled_name_list}
        prioritized_mangled_names = {
            name for (name, min_priority) in mangled_name_list if min_priority == 0
        }

        ingredient_foodb_ids = dict[int, str]()

        class Done(Exception):
            pass

        with open(f"{foodb_path}/Food.json", "r") as food_file:
            for line_index, line in enumerate(food_file.readlines()):
                try:
                    line_data = json.loads(line)
                    assert isinstance(line_data, Mapping)
                    assert isinstance(foodb_internal_id := line_data.get("id"), int)
                    assert isinstance(foodb_id := line_data.get("public_id"), str)
                    Ingredient._meta.get_field("foodb_id").run_validators(foodb_id)
                    assert isinstance(name := line_data.get("name"), str)

                    ingredient_foodb_ids[foodb_internal_id] = foodb_id

                    lower_name = name.lower()
                    initial_mangled_name = re.sub(r"[^\w]", "", lower_name)
                    if initial_mangled_name.startswith("other"):
                        # We don't need things like "Other alcoholic beverage" or
                        # "Other bread" because they don't produce any information
                        # anyway.
                        continue
                    if "var." in lower_name:
                        # Same thing for variants, which exist for some foods
                        continue
                    if "ssp." in lower_name:
                        # ... and subspecies.
                        continue
                    if line_data.get("export_to_foodb", False) is not True:
                        # These are mostly generic entries that have the same name as
                        # their category.
                        continue
                    if "(" in lower_name:
                        # These names are a bit difficult to parse, so we just bail out
                        # at the moment.
                        continue

                    # If the initial name we got does not produce a match, there are a
                    # few other mappings we can try in order to get the names to match
                    # the format the FlavorDB uses.
                    mangled_name_candidates = [initial_mangled_name]
                    if initial_mangled_name.startswith("common"):
                        mangled_name_candidates.append(initial_mangled_name[6:])
                    if initial_mangled_name.startswith("garden"):
                        mangled_name_candidates.append(initial_mangled_name[6:])
                    if initial_mangled_name == "eggs":
                        mangled_name_candidates[0] = "egg"

                    for index, mangled_name in enumerate(mangled_name_candidates):
                        if mangled_name in known_mangled_names:
                            updated_count = Ingredient.objects.filter(
                                models.Exists(
                                    ingredient_names.order_by("priority")
                                    .filter(
                                        ingredient=models.OuterRef("pk"),
                                        mangled_label=mangled_name,
                                    )
                                    .filter(
                                        models.Q(priority=0)
                                        if mangled_name in prioritized_mangled_names
                                        else models.Q()
                                    )
                                ),
                                # For all the other name candidates we tried out, we
                                # don't want to overwrite any existing data if there
                                # was one. For example, we wouldn't want "Garden Onion"
                                # to take over the entry for "Onion" if the former came
                                # after the latter.
                                (
                                    models.Q(foodb_id__in=[foodb_id, ""])
                                    if index > 0
                                    else models.Q()
                                ),
                            ).update(foodb_id=foodb_id)
                            if updated_count > 0:
                                raise Done

                    unhandled_items.append(line_data)
                except Done:
                    pass
                except:
                    logging.exception(
                        f"[FooDB ingredients] line {line_index + 1}: error while "
                        f"processing."
                    )

                if line_index % 40 == 39:
                    logging.debug(
                        f"[FooDB ingredients] processed {line_index + 1} lines."
                    )

        logging.info(
            f"[FooDB ingredients] {len(unhandled_items)} entries were not matched and "
            f"will be processed individually."
        )

        for line_index, line_data in enumerate(unhandled_items):
            try:
                assert isinstance(foodb_id := line_data.get("public_id"), str)
                Ingredient._meta.get_field("foodb_id").run_validators(foodb_id)
                assert isinstance(name := line_data.get("name"), str)
                assert isinstance(group := line_data.get("food_group"), str)
                assert isinstance(subgroup := line_data.get("food_subgroup"), str)
                assert isinstance(
                    wikipedia_title := line_data.get("wikipedia_id", "") or "", str
                )

                try:
                    category = FOODB_GROUP_MAPPINGS[group, subgroup]
                except KeyError:
                    logging.warning(
                        f"[FooDB ingredients] could not map group: {group, subgroup}"
                    )
                    category = Ingredient.Category.UNCATEGORIZED

                ingredient, _ = Ingredient.objects.update_or_create(
                    foodb_id=foodb_id,
                    defaults={"category": category, "wikipedia_title": wikipedia_title},
                )
                ingredient.names.update_or_create(
                    label=unicodedata.normalize("NFC", name.strip()),
                    defaults={"priority": -1},
                )
            except:
                logging.exception(
                    f"[FooDB ingredients] unhandled line {line_index + 1}: error while "
                    f"processing."
                )

        return ingredient_foodb_ids

    @transaction.atomic
    def _handle_foodb_content_item(
        self,
        line_data: Any,
        molecule_foodb_ids: dict[int, str],
        molecule_cache: dict[int, Molecule],
        ingredient_foodb_ids: dict[int, str],
        ingredient_cache: dict[int, Ingredient],
    ) -> bool:
        assert isinstance(line_data, Mapping)

        if line_data.get("source_type") != "Compound":
            return False
        assert isinstance(foodb_internal_food_id := line_data.get("food_id"), int)
        try:
            ingredient = ingredient_cache[foodb_internal_food_id]
        except KeyError:
            try:
                ingredient = Ingredient.objects.get(
                    foodb_id=ingredient_foodb_ids[foodb_internal_food_id]
                )
                ingredient_cache[foodb_internal_food_id] = ingredient
            except (KeyError, Ingredient.DoesNotExist):
                return False

        assert isinstance(foodb_internal_molecule_id := line_data.get("source_id"), int)
        try:
            molecule = molecule_cache[foodb_internal_molecule_id]
        except KeyError:
            try:
                molecule, _ = Molecule.objects.get_or_create(
                    foodb_id=molecule_foodb_ids[foodb_internal_molecule_id]
                )
                molecule_cache[foodb_internal_molecule_id] = molecule
            except KeyError:
                return False

        try:
            content_amount = float(line_data["orig_content"])
        except TypeError:
            # Some records don't have this field.
            return False
        ingredient_molecule_entry, _ = IngredientMolecule.objects.get_or_create(
            ingredient=ingredient, molecule=molecule
        )
        ingredient_molecule_entry.foodb_content_sum = models.F(
            "foodb_content_sum"
        ) + models.Value(content_amount)
        ingredient_molecule_entry.foodb_content_sample_count = models.F(
            "foodb_content_sample_count"
        ) + models.Value(1)
        ingredient_molecule_entry.save()

        return True

    def sync_foodb_content(self, foodb_path: str, ingredient_foodb_ids: dict[int, str]):
        molecule_foodb_ids = dict[int, str]()

        with open(f"{foodb_path}/Compound.json", "r") as compound_file:
            for line_index, line in enumerate(compound_file.readlines()):
                try:
                    line_data = json.loads(line)
                    assert isinstance(line_data, Mapping)
                    assert isinstance(foodb_internal_id := line_data.get("id"), int)
                    assert isinstance(foodb_id := line_data.get("public_id"), str)
                    Molecule._meta.get_field("foodb_id").run_validators(foodb_id)
                    molecule_foodb_ids[foodb_internal_id] = foodb_id
                except:
                    logging.exception(
                        f"[FooDB compounds] line {line_index + 1}: error while "
                        f"processing."
                    )

                if line_index % 1000 == 999:
                    logging.debug(
                        f"[FooDB compounds] Processed {line_index + 1} lines."
                    )

        IngredientMolecule.objects.update(
            foodb_content_sum=0, foodb_content_sample_count=0
        )
        ingredient_cache = dict[int, Ingredient]()
        molecule_cache = dict[int, Molecule]()
        updated_count = 0

        with open(f"{foodb_path}/Content.json", "r") as content_file:
            for line_index, line in enumerate(content_file.readlines()):
                try:
                    line_data = json.loads(line)
                    if self._handle_foodb_content_item(
                        line_data,
                        molecule_foodb_ids,
                        molecule_cache,
                        ingredient_foodb_ids,
                        ingredient_cache,
                    ):
                        updated_count += 1
                except:
                    logging.exception(
                        f"[FooDB content] line {line_index + 1}: error while "
                        f"processing."
                    )

                if line_index % 1000 == 999:
                    logging.debug(f"[FooDB content] processed {line_index + 1} lines.")

        logging.debug(f"[FooDB content] updated {updated_count} entries.")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--foodb-path", nargs="?", type=str)

    def handle(self, *args: Any, **options: Any) -> None:
        assert isinstance(
            foodb_path := options.get("foodb_path", None), str
        ), "--foodb-path argument must be provided."
        if not os.path.isdir(foodb_path):
            raise ValueError(
                "The --foodb-path argument must point to the location where the FooDB "
                "data dump (in JSON format) is extracted."
            )
        if foodb_path.endswith("/"):
            foodb_path = foodb_path[:-1]

        # self.sync_flavordb()
        ingredient_foodb_ids = self.sync_foodb_ingredients(foodb_path)
        self.sync_foodb_content(foodb_path, ingredient_foodb_ids)
