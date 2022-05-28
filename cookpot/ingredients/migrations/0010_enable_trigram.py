from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ingredients", "0009_auto_20220528_1054"),
    ]

    operations = [
        TrigramExtension(),
    ]
