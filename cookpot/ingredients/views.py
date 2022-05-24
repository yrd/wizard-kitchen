import math
import re

from django.db import models
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
)
from django.shortcuts import render

from .models import Ingredient, IngredientMolecule


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
            # top again. Keep this in sync with the stylesheet.
            "missing_sections": range(10 - len(sections_with_labels) % 10),
        },
    )


def section_cards(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(permitted_methods=["GET"])
    if not (section := request.GET.get("section", "")):
        return HttpResponseBadRequest()
    assert isinstance(section, str)

    all_ingredients = list(
        Ingredient.objects.filter(category__startswith=section)
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
    if request.method != "POST":
        return HttpResponseNotAllowed(permitted_methods=["POST"])

    selected_ingredient_pks = list[int]()
    for key, value in request.POST.items():
        if (match := re.match("^ingredient(\d+)$", key)) and value:
            try:
                selected_ingredient_pks.append(int(match.group(1)))
            except ValueError:
                continue

    # Find all the molecules that are present in the selected ingredients.
    pubchem_ids = (
        IngredientMolecule.objects.filter(ingredient__pk__in=selected_ingredient_pks)
        .values("molecule_pubchem_id")
        .distinct()
    )

    result_ingredients = (
        Ingredient.objects.annotate(
            # Annotate each ingredient with the number of molecules shared with the selected
            # ingredients.
            shared_molecule_count=models.Subquery(
                IngredientMolecule.objects.filter(
                    ingredient=models.OuterRef("pk"),
                    molecule_pubchem_id__in=pubchem_ids,
                )
                .values("ingredient")
                .annotate(count=models.Count("pk"))
                .values("count")
            )
        )
        .filter(
            # Filter out the already selected ingredients.
            ~models.Q(pk__in=selected_ingredient_pks)
        )
        .annotate_display_name()
        .order_by("-shared_molecule_count")
    )

    return render(
        request, "pairing_results.html", {"ingredients": result_ingredients[:15]}
    )
