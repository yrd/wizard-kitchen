import json
import logging
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

import requests
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.db.models import functions

from cookpot.ingredients.models import (
    Ingredient,
    IngredientMolecule,
    IngredientName,
    Molecule,
)

FLAVORDB_CATEGORY_MAPPINGS = {
    "cereal": "cerealcrop-cereal",
    "seed": "nutseed-seed",
    "Plant": "plant",
    "Vegetable": "vegetable",
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
        all_names = {
            unicodedata.normalize("NFC", name.strip())
            for name in f"{main_name},{raw_aliases}".split(",")
        }
        for index, label in enumerate(all_names):
            if not label:
                continue
            ingredient.names.update_or_create(
                label=label,
                defaults={"priority": index},
            )

        return created

    def sync_flavordb(self) -> None:
        session = requests.Session()
        for entity_id in range(1000):
            response = session.get(
                "https://cosylab.iiitd.edu.in/flavordb/entities_json",
                params={"id": entity_id},
                headers={"Accept": "application/json"},
            )
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

    def sync_foodb_ingredients(self) -> dict[int, str]:
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

        # Get only those names that are actually unique, because some synonyms are
        # present in FlavorDB with multiple ingredients.
        unique_mangled_names = {
            name
            for (name,) in (
                ingredient_names.values_list("mangled_label")
                .annotate(count=models.Count("pk"))
                .filter(count=1)
                .values_list("mangled_label")
            )
        }

        ingredient_foodb_ids = dict[int, str]()

        with open("/tmp/foodb_2020_04_07_json/Food.json", "r") as food_file:
            for line_index, line in enumerate(food_file.readlines()):
                try:
                    line_data = json.loads(line)
                    assert isinstance(line_data, Mapping)
                    assert isinstance(foodb_internal_id := line_data.get("id"), int)
                    assert isinstance(foodb_id := line_data.get("public_id"), str)
                    Ingredient._meta.get_field("foodb_id").run_validators(foodb_id)
                    assert isinstance(name := line_data.get("name"), str)

                    ingredient_foodb_ids[foodb_internal_id] = foodb_id

                    mangled_name = name.lower().replace(" ", "")
                    if mangled_name in unique_mangled_names:
                        updated_count = Ingredient.objects.filter(
                            models.Exists(
                                ingredient_names.filter(
                                    ingredient=models.OuterRef("pk"),
                                    mangled_label=mangled_name,
                                )
                            )
                        ).update(foodb_id=foodb_id)
                        if updated_count > 0:
                            continue

                    unhandled_items.append(line_data)
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
            f"[FooDB ingredients] {len(unhandled_items)} entries could not be matched "
            f"and will be skipped."
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

        content_amount = float(line_data["orig_content"])
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

    def sync_foodb_content(self, ingredient_foodb_ids: dict[int, str]):
        molecule_foodb_ids = dict[int, str]()

        with open("/tmp/foodb_2020_04_07_json/Compound.json", "r") as compound_file:
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

        with open("/tmp/foodb_2020_04_07_json/Content.json", "r") as content_file:
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

    def handle(self, *args: Any, **options: Any) -> None:
        # self.sync_flavordb()
        ingredient_foodb_ids = self.sync_foodb_ingredients()
        self.sync_foodb_content(ingredient_foodb_ids)
