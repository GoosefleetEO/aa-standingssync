from typing import Iterable, List, Set

from django.db import models, transaction
from django.db.models import Exists, OuterRef
from django.utils.timezone import now

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class EveContactQuerySet(models.QuerySet):
    def grouped_by_standing(self) -> dict:
        """Return alliance contacts grouped by their standing as dict."""
        contacts_by_standing = dict()
        for contact in self.all():
            if contact.standing not in contacts_by_standing:
                contacts_by_standing[contact.standing] = set()
            contacts_by_standing[contact.standing].add(contact)
        return contacts_by_standing


class EveContactManagerBase(models.Manager):
    pass


EveContactManager = EveContactManagerBase.from_queryset(EveContactQuerySet)


class EveWarQuerySet(models.QuerySet):
    def annotate_active_wars(self) -> models.QuerySet:
        from .models import EveWar

        return self.annotate(
            active=Exists(EveWar.objects.active_wars().filter(pk=OuterRef("pk")))
        )

    def active_wars(self) -> models.QuerySet:
        return self.filter(started__lt=now(), finished__gt=now()) | self.filter(
            started__lt=now(), finished__isnull=True
        )

    def finished_wars(self) -> models.QuerySet:
        return self.filter(finished__lte=now())


class EveWarManagerBase(models.Manager):
    def war_targets(self, alliance_id: int) -> List[models.Model]:
        """Return list of current war targets for given alliance as EveEntity objects
        or an empty list if there are None.
        """
        war_targets = list()
        active_wars = self.active_wars()
        # case 1 alliance is aggressor
        for war in active_wars:
            if war.aggressor_id == alliance_id:
                war_targets.append(war.defender)
                if war.allies:
                    war_targets += list(war.allies.all())

        # case 2 alliance is defender
        for war in active_wars:
            if war.defender_id == alliance_id:
                war_targets.append(war.aggressor)

        # case 3 alliance is ally
        for war in active_wars:
            if war.allies.filter(id=alliance_id).exists():
                war_targets.append(war.aggressor)

        return war_targets

    def update_or_create_from_esi(self, id: int):
        """Updates existing or creates new objects from ESI with given ID."""
        from .models import EveEntity

        logger.info("Retrieving war details for ID %s", id)
        war_info = esi.client.Wars.get_wars_war_id(war_id=id).results(ignore_cache=True)
        aggressor, _ = EveEntity.objects.get_or_create(
            id=self._extract_id_from_war_participant(war_info["aggressor"])
        )
        defender, _ = EveEntity.objects.get_or_create(
            id=self._extract_id_from_war_participant(war_info["defender"])
        )
        with transaction.atomic():
            war, _ = self.update_or_create(
                id=id,
                defaults={
                    "aggressor": aggressor,
                    "declared": war_info["declared"],
                    "defender": defender,
                    "is_mutual": war_info["mutual"],
                    "is_open_for_allies": war_info["open_for_allies"],
                    "retracted": war_info.get("retracted"),
                    "started": war_info.get("started"),
                    "finished": war_info.get("finished"),
                },
            )
            war.allies.clear()
            if war_info.get("allies"):
                for ally_info in war_info.get("allies"):
                    eve_entity, _ = EveEntity.objects.get_or_create(
                        id=self._extract_id_from_war_participant(ally_info)
                    )
                    war.allies.add(eve_entity)

    @staticmethod
    def _extract_id_from_war_participant(participant: dict) -> int:
        alliance_id = participant.get("alliance_id")
        corporation_id = participant.get("corporation_id")
        if not alliance_id and not corporation_id:
            raise ValueError(f"Invalid participant: {participant}")
        return alliance_id or corporation_id

    def unfinished_war_ids(self, war_ids: Iterable[int]) -> Set[int]:
        """Determine IDs from unfinished and new wars."""
        finished_war_ids = set(self.finished_wars().values_list("id", flat=True))
        war_ids = set(war_ids)
        return war_ids.difference(finished_war_ids)


EveWarManager = EveWarManagerBase.from_queryset(EveWarQuerySet)
