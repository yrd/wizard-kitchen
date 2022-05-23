from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class IngredientQuerySet(models.QuerySet["Ingredient"]):
    def annotate_display_name(self) -> IngredientQuerySet:
        return self.annotate(
            display_name=IngredientName.objects.filter(
                ingredient=models.OuterRef("pk")
            ).values("label")[:1]
        )


IngredientManager = models.Manager.from_queryset(IngredientQuerySet)


class Ingredient(models.Model):
    """An ingredient.

    In FlavorDB, this is an entity.
    """

    class Category(models.TextChoices):
        UNCATEGORIZED = "uncategorized", _("Uncategorized")
        ADDITIVE = "additive", _("Additive")
        ANIMAL_PRODUCT = "animalproduct", _("Animal products")
        BAKERY = "bakery", _("Bakery")
        BEVERAGE = "beverage", _("Beverages")
        BEVERAGE_ALCOHOLIC = "beverage-alcoholic", _("Beverages – alcoholic")
        BEVERAGE_CAFFEINATED = "beverage-caffeinated", _("Beverages - caffeinated")
        CEARALCROP_CEREAL = "cerealcrop-cereal", _("Cereal")
        CEREALCROP_MAIZE = "cerealcrop-maize", _("Maize")
        DAIRY = "dairy", _("Dairy")
        DISH = "dish", _("Dishes")
        ESSENTIAL_OIL = "essentialoil", _("Essential oils")
        FISHSEAFOOD_FISH = "fishseafood-fish", _("Fish")
        FISHSEAFOOD_SEAFOOD = "fishseafood-seafood", _("Seafood")
        FLOWER = "flower", _("Flowers")
        FRUIT = "fruit", _("Fruit")
        FRUIT_BERRY = "fruit-berry", _("Berries")
        FRUIT_CITRUS = "fruit-citrus", _("Citrus")
        FRUIT_ESSENCE = "fruit-essence", _("Fruit essences")
        FUNGUS = "fungus", _("Fungi")
        HERB = "herb", _("Herbs")
        MEAT = "meat", _("Meat")
        NUTSEED_LEGUME = "nutseed-legume", _("Legumes")
        NUTSEED_NUT = "nutseed-nut", _("Nuts")
        NUTSEED_SEED = "nutseed-seed", _("Seeds")
        PLANT = "plant", _("Plants")
        PLANT_DERIVATIVE = "plantderivative", _("Plant derivatives")
        SPICE = "spice", _("Spices")
        VEGETABLE = "vegetable", _("Vegetables")
        VEGETABLE_CABBAGE = "vegetable-cabbage", _("Cabbage")
        VEGETABLE_FRUIT = "vegetable-fruit", _("Vegetable Fruit")
        VEGETABLE_GOURD = "vegetable-gourd", _("Gourds")
        VEGETABLE_ROOT = "vegetable-root", _("Root Vegetables")
        VEGETABLE_STEM = "vegetable-stem", _("Vegetable Stems")
        VEGETABLE_TUBER = "vegetable-tuber", _("Tuber Vegetables")

    category = models.CharField(
        max_length=30,
        # choices=Category.choices,
        default=Category.UNCATEGORIZED,
        verbose_name=_("category"),
    )

    flavordb_id = models.PositiveIntegerField(
        unique=True,
        verbose_name=_("FlavorDB ID"),
        help_text=_("ID of the corresponding entity in the FlavorDB database."),
    )

    objects = IngredientManager()

    class Meta:
        verbose_name = _("ingredient")
        verbose_name_plural = _("ingredients")

    @property
    def category_label(self) -> str:
        for key, label in self.Category.choices:
            if key == self.category:
                return label
        return self.category


class IngredientName(models.Model):
    """Display name of an :class:`Ingredient`.

    This is separate to the ingredient model in order to support synonyms and different
    locales.
    """

    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name="names",
        related_query_name="name",
        verbose_name=_("ingredient"),
    )
    label = models.CharField(max_length=100, verbose_name=_("label"))

    class Meta:
        verbose_name = _("ingredient name")
        verbose_name_plural = _("ingredient names")


class IngredientMolecule(models.Model):
    """Relation between a molecule and an ingredient.

    An entry of this model means that the molecule can be found in the ingredient.
    """

    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name="molecule_entries",
        related_query_name="molecule_entry",
        verbose_name=_("ingredient"),
    )
    molecule_pubchem_id = models.PositiveIntegerField(
        verbose_name=_("molecule PubChem ID"),
        help_text=_("ID of the molecule in the PubChem database."),
    )
