# Generated by Django 4.0.6 on 2022-07-29 17:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eveuniverse", "0007_evetype_description"),
        ("standingssync", "0004_remove_old_eve_entity"),
    ]

    operations = [
        migrations.CreateModel(
            name="EveWar",
            fields=[
                ("id", models.PositiveIntegerField(primary_key=True, serialize=False)),
                ("declared", models.DateTimeField()),
                (
                    "finished",
                    models.DateTimeField(db_index=True, default=None, null=True),
                ),
                ("is_mutual", models.BooleanField()),
                ("is_open_for_allies", models.BooleanField()),
                ("retracted", models.DateTimeField(default=None, null=True)),
                (
                    "started",
                    models.DateTimeField(db_index=True, default=None, null=True),
                ),
                (
                    "aggressor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "allies",
                    models.ManyToManyField(
                        related_name="+", to="eveuniverse.eveentity"
                    ),
                ),
                (
                    "defender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="EveContact",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("standing", models.FloatField()),
                ("is_war_target", models.BooleanField()),
                (
                    "eve_entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="eveuniverse.eveentity",
                    ),
                ),
                (
                    "manager",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contacts",
                        to="standingssync.syncmanager",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="evecontact",
            constraint=models.UniqueConstraint(
                fields=("manager", "eve_entity"), name="fk_eve_contact"
            ),
        ),
    ]