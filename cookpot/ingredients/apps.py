from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IngredientsConfig(AppConfig):
    name = "cookpot.ingredients"
    verbose_name = _("ingredients")
