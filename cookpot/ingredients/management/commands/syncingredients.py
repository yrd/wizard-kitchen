import logging
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cookpot.ingredients.models import Ingredient, IngredientMolecule, IngredientName


class Command(BaseCommand):
    help = "Fetch ingredient information from FlavorDB."

    @transaction.atomic
    def _handle_entity_data(self, entity_id: int, data: Any) -> bool:
        assert isinstance(data, Mapping), "Response was not a JSON object."

        assert isinstance(
            category := data.get("category"), str
        ), f"Category must be a string, got {type(category)}."
        # See if we have a remapping for the category. This is because some of the
        # categories are still present twice upstream.
        category = Ingredient.CATEGORY_MAPPINGS.get(category, category)
        if category not in Ingredient.Category.values:
            logging.warning(f"Entity {entity_id}: got unknown category {category}.")
            category = Ingredient.Category.UNCATEGORIZED

        ingredient, created = Ingredient.objects.update_or_create(
            defaults=dict(category=category), flavordb_id=entity_id
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
            ingredient.molecule_entries.get_or_create(
                molecule_pubchem_id=molecule_pubchem_id
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
        for label in all_names:
            if not label:
                continue
            ingredient.names.get_or_create(label=label)

        return created

    def handle(self, *args: Any, **options: Any) -> None:
        session = requests.Session()
        for entity_id in range(1000):
            response = session.get(
                "https://cosylab.iiitd.edu.in/flavordb/entities_json",
                params={"id": entity_id},
                headers={"Accept": "application/json"},
            )
            if response.status_code == 404:
                logging.warning(f"Entity {entity_id}: entity not found.")
                continue

            try:
                response.raise_for_status()
                if self._handle_entity_data(entity_id, response.json()):
                    logging.info(f"Entity {entity_id}: created new record.")
                else:
                    logging.info(f"Entity {entity_id}: updated existing record.")
            except:
                logging.exception(f"Entity {entity_id}: error while processing.")
