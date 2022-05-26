from __future__ import annotations

from django.core import validators
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
        # Some of these are presentational, which means no upstream data has this
        # value. They are just here so that we have translations for the parent
        # category.
        UNCATEGORIZED = "uncategorized", _("Uncategorized")
        ADDITIVE = "additive", _("Additive")
        ANIMAL_PRODUCT = "animalproduct", _("Animal products")
        BAKERY = "bakery", _("Bakery")
        BAKERY_CANDIES = "bakery-candies", _("Candies")
        BEVERAGE = "beverage", _("Beverages")
        BEVERAGE_ALCOHOLIC = "beverage-alcoholic", _("Alcohol")
        BEVERAGE_CAFFEINATED = "beverage-caffeinated", _("Caffeine")
        CEREALS = "cerealcrop", _("Cereals")
        CEREALS_CEREAL = "cerealcrop-cereal", _("Cereal")
        CEREALS_MAIZE = "cerealcrop-maize", _("Maize")
        DAIRY = "dairy", _("Dairy")
        DISH = "dish", _("Dishes")
        ESSENTIAL_OIL = "essentialoil", _("Essential oils")
        AQUATIC = "aquatic", _("Aquatic")  # Presentational
        AQUATIC_FISH = "aquatic-fish", _("Fish")
        AQUATIC_SEAFOOD = "aquatic-seafood", _("Seafood")
        AQUATIC_SEAWEED = "aquatic-seaweed", _("Seaweed")
        FLOWER = "flower", _("Flowers")
        FRUIT = "fruit", _("Fruit")
        FRUIT_BERRY = "fruit-berry", _("Berries")
        FRUIT_CITRUS = "fruit-citrus", _("Citrus")
        FRUIT_ESSENCE = "fruit-essence", _("Fruit essences")
        FUNGUS = "fungus", _("Fungi")
        HERB = "herb", _("Herbs")
        MEAT = "meat", _("Meat")
        NUTSEED = "nutseed", _("Nuts & seeds")  # Presentational
        NUTSEED_LEGUME = "nutseed-legume", _("Legumes")
        NUTSEED_NUT = "nutseed-nut", _("Nuts")
        NUTSEED_SEED = "nutseed-seed", _("Seeds")
        PLANT = "plant", _("Plants")
        PLANT_DERIVATIVE = "plant-derivative", _("Plant derivatives")
        SPICE = "spice", _("Spices")
        VEGETABLE = "vegetable", _("Vegetables")
        VEGETABLE_CABBAGE = "vegetable-cabbage", _("Cabbage")
        VEGETABLE_FRUIT = "vegetable-fruit", _("Vegetable Fruit")
        VEGETABLE_GOURD = "vegetable-gourd", _("Gourds")
        VEGETABLE_ROOT = "vegetable-root", _("Root Vegetables")
        VEGETABLE_STEM = "vegetable-stem", _("Vegetable Stems")
        VEGETABLE_TUBER = "vegetable-tuber", _("Tuber Vegetables")

        @classmethod
        def get_label(cls, category_key: str) -> str:
            for key, label in cls.choices:
                if key == category_key:
                    return label
            return category_key

    category = models.CharField(
        max_length=30,
        # choices=Category.choices,
        default=Category.UNCATEGORIZED,
        verbose_name=_("category"),
    )

    flavordb_id = models.PositiveIntegerField(
        null=True,
        verbose_name=_("FlavorDB ID"),
        help_text=_("ID of the corresponding entity in the FlavorDB database."),
    )

    foodb_id = models.CharField(
        blank=True,
        default="",
        max_length=9,
        validators=[
            validators.RegexValidator(
                r"FOOD\d{5}",
                message=_("FooDB identifiers must look like this: FOOD00648"),
                code="invalid-foodb-id",
            )
        ],
        verbose_name=_("FooDB ID"),
        help_text=_("Public identifier of the food item in the FooDB database."),
    )

    wikipedia_title = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("Wikipedia title"),
        help_text=_("Title of the corresponding article in the English Wikipedia."),
    )

    objects = IngredientManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["flavordb_id"],
                condition=models.Q(flavordb_id__isnull=False),
                name="flavordb_entity_ids_unique",
            ),
            models.UniqueConstraint(
                fields=["foodb_id"],
                condition=~models.Q(foodb_id=""),
                name="foodb_food_ids_unique",
            ),
        ]
        verbose_name = _("ingredient")
        verbose_name_plural = _("ingredients")

    @property
    def category_label(self) -> str:
        return self.Category.get_label(self.category)


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

    priority = models.SmallIntegerField(
        default=100,
        verbose_name=_("priority"),
        help_text=_("Items with lower values here will come first."),
    )

    label = models.CharField(
        max_length=100,
        verbose_name=_("label"),
    )

    class Meta:
        ordering = ["ingredient", "priority"]
        verbose_name = _("ingredient name")
        verbose_name_plural = _("ingredient names")


class Molecule(models.Model):
    """"""

    pubchem_id = models.PositiveIntegerField(
        null=True,
        default=None,
        verbose_name=_("PubChem ID"),
        help_text=_("ID of the molecule in the PubChem database."),
        # FlavorDB uses this as the primary key.
    )

    foodb_id = models.CharField(
        max_length=9,
        blank=True,
        default="",
        validators=[
            validators.RegexValidator(
                r"FDB\d{6}",
                message=_("FooDB identifiers must look like this: FDB123456"),
                code="invalid-foodb-id",
            )
        ],
        verbose_name=_("FooDB ID"),
        help_text=_("Public identifier in the FooDB database."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pubchem_id"],
                condition=models.Q(pubchem_id__isnull=False),
                name="pubchem_ids_unique",
            ),
            models.UniqueConstraint(
                fields=["foodb_id"],
                condition=~models.Q(foodb_id=""),
                name="foodb_molecule_ids_unique",
            ),
            models.CheckConstraint(
                check=models.Q(pubchem_id__isnull=False) | ~models.Q(foodb_id=""),
                name="molecule_has_identifier",
            ),
        ]
        verbose_name = _("molecule")
        verbose_name_plural = _("molecules")


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
    molecule = models.ForeignKey(
        Molecule,
        on_delete=models.CASCADE,
        related_name="ingredient_entries",
        related_query_name="ingredient_entry",
        verbose_name=_("molecule"),
    )

    flavordb_found = models.BooleanField(
        default=False,
        verbose_name=_("found in FlavorDB"),
        help_text=_(
            "If this is set, the molecule was found in the ingredient according to "
            "FlavorDB."
        ),
    )

    foodb_content_sum = models.FloatField(
        default=0.0,
        verbose_name=_("FooDB content sum"),
        help_text=_(
            "Sum of content values from FooDB. These indicate how much of the "
            "molecule was found (in mg / 100g)."
        ),
    )
    foodb_content_sample_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("FooDB sample size"),
        help_text=_(
            "Number of samples were summed up in the other FooDB parameter. This is "
            "used to calculate an average."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ingredient", "molecule"], name="ingredient_molecule_unique"
            )
        ]
        verbose_name = _("ingredient molecule containment")
        verbose_name_plural = _("ingredient molecule containments")
