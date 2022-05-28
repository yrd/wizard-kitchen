import math
from collections.abc import Sequence
from typing import Any

from django.contrib.postgres.search import TrigramSimilarity
from django.db import models
from django.db.models import expressions, functions
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
)
from django.shortcuts import render
from django.views import View

from .models import (
    Ingredient,
    IngredientName,
    IngredientQuerySet,
    Molecule,
    MoleculeOccurrence,
)


def index(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(permitted_methods=["GET"])

    sections = set[str]()
    for (category,) in (
        Ingredient.objects.values_list("category").distinct().order_by("category")
    ):
        sections.add(category.split("-")[0])

    sections_with_labels = [
        (key, Ingredient.Category.get_label(key)) for key in sorted(sections)
    ]

    return render(
        request,
        "index.html",
        {
            "sections": sections_with_labels,
            # This is the number of sections missing to fill the column. A spacer will
            # be rendered for each of these so that the category selectors begin at the
            # top again. Keep this in sync with the stylesheet. We add two to account
            # for the search bar.
            "missing_sections": range(10 - ((len(sections_with_labels) + 2) % 10)),
        },
    )


def section_cards(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(permitted_methods=["GET"])

    section = request.GET.get("section", "").strip()
    search_query = request.GET.get("query", "").strip()
    if (not section and not search_query) or (section and search_query):
        return HttpResponseBadRequest()
    assert isinstance(section, str)

    # When getting a single section, we want to group them by category. When searching,
    # we just want to return everything.
    if search_query:
        all_ingredients = list(
            Ingredient.objects.filter_with_data()
            .annotate_display_name()
            .filter(
                models.Exists(
                    IngredientName.objects.annotate(
                        rank=TrigramSimilarity("label", search_query)
                    ).filter(
                        models.Q(rank__gt=0.5)
                        | models.Q(label__unaccent__icontains=search_query),
                        ingredient=models.OuterRef("pk"),
                    )
                )
            )
            .order_by("display_name")
            .distinct()[:30]
        )

        if len(all_ingredients) == 0:
            return render(request, "data/empty_search_results.html")

        # The results should all have the same category because we don't want
        # to group them.
        for ingredient in all_ingredients:
            ingredient.category = "Results"
    else:
        all_ingredients = list(
            Ingredient.objects.filter_with_data()
            .filter(category__startswith=section)
            .annotate_display_name()
            .order_by("display_name")
        )

    categories = sorted({ingredient.category for ingredient in all_ingredients})

    library = list[tuple[str, str, list[Ingredient]]]()
    for category in categories:
        ingredients = [
            ingredient
            for ingredient in all_ingredients
            if ingredient.category == category
        ]

        # Try to make equally-sized groups.
        group_count = math.ceil(len(ingredients) / 17)
        group_size = math.ceil(len(ingredients) / group_count)
        group_number = 1
        while len(ingredients) > 0:
            category_label = Ingredient.Category.get_label(category) + (
                f" ({group_number})" if group_count > 1 else ""
            )
            library.append(
                (f"{category}-{group_number}", category_label, ingredients[:group_size])
            )
            ingredients = ingredients[group_size:]
            group_number += 1

    return render(request, "data/section_cards.html", {"library": library})


class PairingResultsView(View):
    @classmethod
    def calculate_matching_score(cls, ingredient_pks: Sequence[int]) -> int:
        # Find those molecules that are present in all the provided ingredients.
        shared_molecules = Molecule.objects.filter(
            *[
                models.Exists(
                    MoleculeOccurrence.objects.filter(
                        models.Q(foodb_content_sample_count__gt=0)
                        | models.Q(flavordb_found=True),
                        molecule=models.OuterRef("pk"),
                        ingredient=ingredient_pk,
                    )
                )
                for ingredient_pk in ingredient_pks
            ]
        )

        shared_ingredient_score = (
            MoleculeOccurrence.objects.with_score()
            .filter(ingredient__in=ingredient_pks, molecule__in=shared_molecules)
            .aggregate(value=models.Sum("score"))
        )
        total_ingredient_score = (
            MoleculeOccurrence.objects.with_score()
            .filter(ingredient__in=ingredient_pks)
            .aggregate(value=models.Sum("score"))
        )

        try:
            return (
                shared_ingredient_score.get("value", 0)
                / total_ingredient_score.get("value", 0)
            ) * 100
        except ZeroDivisionError:
            return 0

    @classmethod
    def calculate_suggested_ingredients(
        cls, ingredient_pks: Sequence[int], *, reverse: bool = False
    ) -> IngredientQuerySet:
        # Group by molecule and sum up these scores for all the ingredients that were
        # selected. This gives us a list of molecules in our query.
        scored_molecule_occurrences = MoleculeOccurrence.objects.with_score(
            filter_zero=False
        ).filter(ingredient__in=ingredient_pks)
        (
            scored_molecule_occurrences_sql,
            scored_molecule_occurrences_params,
        ) = scored_molecule_occurrences.query.sql_with_params()
        scored_molecules = expressions.RawSQL(
            f"""
            SELECT molecule_id, SUM(score) as total_score
            FROM ({scored_molecule_occurrences_sql}) scored_molecule_occurrences
            WHERE scored_molecule_occurrences.score > 0
            GROUP BY molecule_id
            """,
            scored_molecule_occurrences_params,
        )

        # This is the final result query that finds other ingredients that could match.
        base_queryset = (
            Ingredient.objects.filter_with_data()
            .annotate(
                weighted_score=models.Subquery(
                    MoleculeOccurrence.objects.filter(
                        ingredient=models.OuterRef("pk"),
                    )
                    .annotate(
                        # Both scored_molecules and max_score will be ingested using the
                        # WITH clause later on.
                        weighted_score=functions.Coalesce(
                            expressions.RawSQL(
                                # The "U0" below should actually be an OuterRef("molecule"),
                                # but Django doesn't seem to resolve those inside RawSQL
                                # statements.
                                """
                                SELECT total_score
                                FROM scored_molecules
                                WHERE scored_molecules.molecule_id = U0.molecule_id
                                """,
                                (),
                                output_field=models.FloatField(),
                            ),
                            models.Value(0.0),
                        )
                        / expressions.RawSQL(
                            "SELECT * FROM max_score",
                            (),
                            output_field=models.FloatField(),
                        )
                    )
                    .values("ingredient")
                    .annotate(total_weighted_score=models.Sum("weighted_score"))
                    .values("total_weighted_score")
                )
            )
            .filter(
                # Filter out the already selected ingredients.
                ~models.Q(pk__in=ingredient_pks)
            )
            .annotate_display_name()
            # By default, highest-ranking results are returned first.
            .order_by("-weighted_score" if not reverse else "weighted_score")
        )

        (
            base_queryset_sql,
            base_queryset_params,
        ) = base_queryset.query.sql_with_params()

        return Ingredient.objects.raw(
            f"""
            WITH
                scored_molecules AS ({scored_molecules.sql}),

                max_score AS (SELECT MAX(total_score) FROM scored_molecules)

            {base_queryset_sql}
            """,
            (*scored_molecules.params, *base_queryset_params),
        )

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        ingredients_parameter = request.GET.get("ingredients", "")
        if not isinstance(ingredients_parameter, str):
            return HttpResponseBadRequest()
        selected_ingredient_pks = list[int]()
        for value in ingredients_parameter.split(","):
            try:
                selected_ingredient_pks.append(int(value.strip()))
            except ValueError:
                return HttpResponseBadRequest()

        return render(
            request,
            "data/pairing_results.html",
            {
                "matching_score": self.calculate_matching_score(
                    selected_ingredient_pks
                ),
                "matching_ingredients": self.calculate_suggested_ingredients(
                    selected_ingredient_pks
                )[:15],
                "not_matching_ingredients": self.calculate_suggested_ingredients(
                    selected_ingredient_pks, reverse=True
                )[:6],
            },
        )
