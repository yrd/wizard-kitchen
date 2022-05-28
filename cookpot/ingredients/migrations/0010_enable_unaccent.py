from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ingredients", "0010_enable_trigram"),
    ]

    operations = [
        UnaccentExtension(),
    ]
