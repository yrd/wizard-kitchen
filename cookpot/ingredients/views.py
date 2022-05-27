import math

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import models
from django.db.models import expressions, functions
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
)
from django.shortcuts import render

from .models import Ingredient, IngredientMolecule, Molecule


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
            .annotate(
                rank=SearchRank(SearchVector("name__label"), SearchQuery(search_query)),
            )
            .annotate_display_name()
            .filter(rank__gt=0)
            .order_by("-rank")
            .distinct()[:30]
        )
        # The results should all have the same category because we don't want
        # to group them.
        for ingredient in all_ingredients:
            ingredient.category = "Search"
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


def pairing_results(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(permitted_methods=["POST"])

    ingredients_parameter = request.GET.get("ingredients", "")
    if not isinstance(ingredients_parameter, str):
        return HttpResponseBadRequest()
    selected_ingredient_pks = list[int]()
    for value in ingredients_parameter.split(","):
        try:
            selected_ingredient_pks.append(int(value.strip()))
        except ValueError:
            return HttpResponseBadRequest()

    # For each ingredient-molecule entry, calculate a score, which is more or less how
    # much the molecule is present in that ingredient, but with respect to both sources.
    ingredient_molecules_with_score = IngredientMolecule.objects.annotate(
        score=models.Case(
            # Prefer data from FooDB, if it is available.
            models.When(
                models.Q(foodb_content_sample_count__gt=0),
                then=(
                    models.F("foodb_content_sum")
                    / models.F("foodb_content_sample_count")
                ),
            ),
            # Otherwise, check if FlavorDB has a record. Here, we don't really have
            # a way to calculate the score, so we give all FlavorDB records a fixed
            # value.
            models.When(models.Q(flavordb_found=True), then=models.Value(300)),
            # This case shouldn't actually every occur, because wo only create
            # IngredientMolecule objects when we have data.
            default=models.Value(0),
            output_field=models.FloatField(),
        )
    ).filter(score__gt=0)

    ##################
    # Matching score #
    ##################

    # Find those molecules that are present in all the provided ingredients.
    shared_molecules = Molecule.objects.filter(
        *[
            models.Exists(
                IngredientMolecule.objects.filter(
                    models.Q(foodb_content_sample_count__gt=0)
                    | models.Q(flavordb_found=True),
                    molecule=models.OuterRef("pk"),
                    ingredient=ingredient_pk,
                )
            )
            for ingredient_pk in selected_ingredient_pks
        ]
    )
    shared_ingredient_score = ingredient_molecules_with_score.filter(
        ingredient__in=selected_ingredient_pks, molecule__in=shared_molecules
    ).aggregate(value=models.Sum("score"))
    total_ingredient_score = ingredient_molecules_with_score.filter(
        ingredient__in=selected_ingredient_pks
    ).aggregate(value=models.Sum("score"))
    try:
        matching_score = (
            shared_ingredient_score.get("value", 0)
            / total_ingredient_score.get("value", 0)
        ) * 100
    except ZeroDivisionError:
        matching_score = 0

    #########################
    # Suggested ingredients #
    #########################

    # Group by molecule and sum up these scores for all the ingredients that were
    # selected. This gives us a list of molecules in our query.
    ranked_molecules = (
        ingredient_molecules_with_score.filter(ingredient__in=selected_ingredient_pks)
        # Group by molecule and calculate a total score for each molecule.
        .values("molecule")
        .annotate(total_score=models.Sum("score"))
        .values("molecule", "total_score")
    )

    # This is the final result query that finds other ingredients that could match.
    suggested_ingredients_base = (
        Ingredient.objects.filter_with_data()
        .annotate(
            weighted_score=models.Subquery(
                IngredientMolecule.objects.filter(
                    ingredient=models.OuterRef("pk"),
                )
                .annotate(
                    # Both ranked_molecules and max_score will be ingested using the
                    # WITH clause later on.
                    weighted_score=functions.Coalesce(
                        expressions.RawSQL(
                            # The "U0" below should actually be an OuterRef("molecule"),
                            # but Django doesn't seem to resolve those inside RawSQL
                            # statements.
                            """
                            SELECT total_score
                            FROM ranked_molecules
                            WHERE ranked_molecules.molecule_id = U0.molecule_id
                            """,
                            (),
                            output_field=models.FloatField(),
                        ),
                        models.Value(0.0),
                    )
                    / expressions.RawSQL(
                        "SELECT * FROM max_score", (), output_field=models.FloatField()
                    )
                )
                .values("ingredient")
                .annotate(total_weighted_score=models.Sum("weighted_score"))
                .values("total_weighted_score")
            )
        )
        .filter(
            # Filter out the already selected ingredients.
            ~models.Q(pk__in=selected_ingredient_pks)
        )
        .annotate_display_name()
        .order_by("-weighted_score")
    )

    (
        ranked_molecules_sql,
        ranked_molecules_params,
    ) = ranked_molecules.query.sql_with_params()
    (
        suggested_ingredients_base_sql,
        suggested_ingredients_base_params,
    ) = suggested_ingredients_base.query.sql_with_params()

    suggested_ingredients = Ingredient.objects.raw(
        f"""
        WITH
            ranked_molecules AS ({ranked_molecules_sql}),

            max_score AS (SELECT MAX(total_score) FROM ranked_molecules)

        {suggested_ingredients_base_sql}
        """,
        (*ranked_molecules_params, *suggested_ingredients_base_params),
    )

    return render(
        request,
        "data/pairing_results.html",
        {
            "matching_score": matching_score,
            "suggested_ingredients": suggested_ingredients[:15],
        },
    )
