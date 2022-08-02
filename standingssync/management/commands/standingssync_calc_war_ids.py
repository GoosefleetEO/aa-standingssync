from django.core.management.base import BaseCommand, CommandError
from django.db.models import Min

from ... import __title__, __version__
from ...models import EveWar
from ...providers import esi


class Command(BaseCommand):
    help = "Calculates the minimum and special war IDs."

    def handle(self, *args, **options):
        self.stdout.write(f"*** {__title__} v{__version__} - Calculate war IDs ***")

        if not EveWar.objects.exists():
            raise CommandError(
                "War database is empty. "
                "Please update wars from ESI before running this command."
            )

        war_ids = esi.client.Wars.get_wars().results()
        min_unfinished_war_id = EveWar.objects.filter(
            id__gte=min(war_ids), finished__isnull=True
        ).aggregate(Min("id"))["id__min"]
        special_unfinished_war_ids = list(
            EveWar.objects.filter(id__lt=min(war_ids), finished__isnull=True)
            .order_by("id")
            .values_list("id", flat=True)
        )
        self.stdout.write("Calculated new war ID values for settings are:")
        self.stdout.write(
            f"STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID = {min_unfinished_war_id}"
        )
        self.stdout.write(
            f"STANDINGSSYNC_SPECIAL_WAR_IDS = {special_unfinished_war_ids}"
        )
