from typing import Any, Optional, cast

import django.forms.renderers
import django.forms.utils
import django.forms.widgets
from django import forms
from django.db import models
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
)
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from .models import Ingredient, IngredientName


def pairing_view(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(permitted_methods=["GET"])

    ingredient_library = list[list[Ingredient]]()

    for (category,) in (
        Ingredient.objects.values_list("category").distinct().order_by("category")
    ):
        ingredients = (
            Ingredient.objects.filter(category=category)
            .annotate(
                display_name=IngredientName.objects.filter(
                    ingredient=models.OuterRef("pk")
                ).values("label")[:1]
            )
            .order_by("display_name")
        )
        ingredient_library.append(list(ingredients))

    return render(
        request, "pairing_view.html", {"ingredient_library": ingredient_library}
    )
