import datetime as dt

import factory
import factory.fuzzy

from django.utils.timezone import now
from eveuniverse.models import EveEntity

from app_utils.testdata_factories import (
    EveAllianceInfoFactory,
    EveCharacterFactory,
    EveCorporationInfoFactory,
    UserMainFactory,
)

from ..models import EveContact, EveWar, SyncedCharacter, SyncManager


class EveEntityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EveEntity
        django_get_or_create = ("id", "name")

    category = EveEntity.CATEGORY_CHARACTER

    @factory.lazy_attribute
    def id(self):
        if self.category == EveEntity.CATEGORY_CHARACTER:
            obj = EveCharacterFactory()
            return obj.character_id
        if self.category == EveEntity.CATEGORY_CORPORATION:
            obj = EveCorporationInfoFactory()
            return obj.corporation_id
        if self.category == EveEntity.CATEGORY_ALLIANCE:
            obj = EveAllianceInfoFactory()
            return obj.alliance_id
        raise NotImplementedError(f"Unknown category: {self.category}")


class EveEntityCharacterFactory(EveEntityFactory):
    name = factory.Faker("name")
    category = EveEntity.CATEGORY_CHARACTER


class EveEntityCorporationFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_CORPORATION


class EveEntityAllianceFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_ALLIANCE


class EveWarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EveWar

    id = factory.Sequence(lambda n: 1 + n)
    aggressor = factory.SubFactory(EveEntityAllianceFactory)
    declared = factory.fuzzy.FuzzyDateTime(
        now() - dt.timedelta(days=3), end_dt=now() - dt.timedelta(days=2)
    )
    defender = factory.SubFactory(EveEntityAllianceFactory)
    is_mutual = False
    is_open_for_allies = True
    started = factory.LazyAttribute(lambda obj: obj.declared + dt.timedelta(hours=24))

    @factory.post_generation
    def allies(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for ally in extracted:
                self.allies.add(ally)


class ManagerUserMainFactory(UserMainFactory):
    main_character__scopes = ["esi-alliances.read_contacts.v1"]
    permissions__ = ["standingssync.add_syncmanager"]


class SyncManagerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SyncManager

    class Params:
        user = factory.SubFactory(ManagerUserMainFactory)

    @factory.lazy_attribute
    def alliance(self):
        return EveAllianceInfoFactory(
            alliance_id=self.user.profile.main_character.alliance_id
        )

    @factory.lazy_attribute
    def character_ownership(self):
        return self.user.profile.main_character.character_ownership


class SyncedCharacterFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SyncedCharacter

    manager = factory.SubFactory(SyncManagerFactory)

    @factory.lazy_attribute
    def character_ownership(self):
        main = UserMainFactory()
        return main.profile.main_character.character_ownership


class EveContactFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = EveContact

    manager = factory.SubFactory(SyncManagerFactory)
    eve_entity = factory.SubFactory(EveEntityFactory)
    standing = 5
    is_war_target = False


class EveContactWarTargetFactory(EveContactFactory):
    standing = -10
    is_war_target = True
