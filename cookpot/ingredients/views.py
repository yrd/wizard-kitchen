import re

from django.db import models
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render

from .models import Ingredient, IngredientMolecule


def pairing_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(permitted_methods=["GET"])

    ingredient_library = list[list[Ingredient]]()

    for (category,) in (
        Ingredient.objects.values_list("category").distinct().order_by("category")
    ):
        ingredients = list(
            Ingredient.objects.filter(category=category)
            .annotate_display_name()
            .order_by("display_name")
        )
        while len(ingredients) > 0:
            ingredient_library.append(ingredients[:17])
            ingredients = ingredients[17:]

    return render(
        request,
        "pairing_view.html",
        {"ingredient_library": enumerate(ingredient_library)},
    )


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
