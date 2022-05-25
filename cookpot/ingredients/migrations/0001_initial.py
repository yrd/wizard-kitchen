# Generated by Django 3.2.9 on 2022-05-25 12:47

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Ingredient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(default='uncategorized', max_length=30, verbose_name='category')),
                ('flavordb_id', models.PositiveIntegerField(help_text='ID of the corresponding entity in the FlavorDB database.', unique=True, verbose_name='FlavorDB ID')),
                ('wikipedia_title', models.CharField(blank=True, default='', help_text='Title of the corresponding article in the English Wikipedia.', max_length=100, verbose_name='Wikipedia title')),
            ],
            options={
                'verbose_name': 'ingredient',
                'verbose_name_plural': 'ingredients',
            },
        ),
        migrations.CreateModel(
            name='Molecule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pubchem_id', models.PositiveIntegerField(help_text='ID of the molecule in the PubChem database.', verbose_name='PubChem ID')),
                ('foodb_id', models.CharField(help_text='Public identifier in the FooDB database.', max_length=9, validators=[django.core.validators.RegexValidator('FDB\\d{6}', code='invalid-foodb-id', message='FooDB identifiers must look like this: FDB123456')], verbose_name='FooDB ID')),
            ],
        ),
        migrations.CreateModel(
            name='IngredientName',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=100, verbose_name='label')),
                ('ingredient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='names', related_query_name='name', to='ingredients.ingredient', verbose_name='ingredient')),
            ],
            options={
                'verbose_name': 'ingredient name',
                'verbose_name_plural': 'ingredient names',
            },
        ),
        migrations.CreateModel(
            name='IngredientMolecule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('flavordb_found', models.BooleanField(default=False, help_text='If this is set, the molecule was found in the ingredient according to FlavorDB.', verbose_name='found in FlavorDB')),
                ('ingredient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='molecule_entries', related_query_name='molecule_entry', to='ingredients.ingredient', verbose_name='ingredient')),
                ('molecule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingredient_entries', related_query_name='ingredient_entry', to='ingredients.ingredient', verbose_name='molecule')),
            ],
        ),
    ]
