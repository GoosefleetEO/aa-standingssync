from typing import List

from django.db import models
from django.db.models import Exists, OuterRef
from django.utils.timezone import now

from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag

from . import __title__
from .providers import esi

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class EveContactQuerySet(models.QuerySet):
    def grouped_by_standing(self) -> dict:
        """returns alliance contacts grouped by their standing as dict"""

        contacts_by_standing = dict()
        for contact in self.all():
            if contact.standing not in contacts_by_standing:
                contacts_by_standing[contact.standing] = set()
            contacts_by_standing[contact.standing].add(contact)

        return contacts_by_standing


class EveContactManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        return EveContactQuerySet(self.model, using=self._db)


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
        """returns list of current war targets for given alliance as EveEntity objects
        or an empty list if there are none
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

    def update_from_esi(self, id: int):
        from .models import EveEntity

        logger.info("Retrieving war details for ID %s", id)
        war_info = esi.client.Wars.get_wars_war_id(war_id=id).results()
        finished = war_info.get("finished")
        if finished and finished <= now():
            logger.info("Ignoring finished war with ID %s", id)
            return

        logger.info("Updating war details for ID %s", id)
        try:
            war = self.get(id=id)
        except self.model.DoesNotExist:
            aggressor, _ = EveEntity.objects.get_or_create(
                id=self._extract_id_from_war_participant(war_info.get("aggressor"))
            )
            defender, _ = EveEntity.objects.get_or_create(
                id=self._extract_id_from_war_participant(war_info.get("defender"))
            )
            war = self.create(
                id=id,
                aggressor=aggressor,
                declared=war_info.get("declared"),
                defender=defender,
                is_mutual=war_info.get("mutual"),
                is_open_for_allies=war_info.get("open_for_allies"),
                retracted=war_info.get("retracted"),
                started=war_info.get("started"),
                finished=war_info.get("finished"),
            )

        else:
            self.update(
                retracted=war_info.get("retracted"),
                started=war_info.get("started"),
                finished=war_info.get("finished"),
                is_mutual=war_info.get("mutual"),
                is_open_for_allies=war_info.get("open_for_allies"),
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


EveWarManager = EveWarManagerBase.from_queryset(EveWarQuerySet)
