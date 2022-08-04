"""Utility functions and classes for tests"""

import copy
from enum import Enum

from eveuniverse.models import EveEntity

from allianceauth.eveonline.models import (
    EveAllianceInfo,
    EveCharacter,
    EveCorporationInfo,
)
from app_utils.esi_testing import BravadoOperationStub

ALLIANCE_CONTACTS = [
    {"contact_id": 1002, "contact_type": "character", "standing": 10.0},
    {"contact_id": 1004, "contact_type": "character", "standing": 10.0},
    {"contact_id": 1005, "contact_type": "character", "standing": -10.0},
    {"contact_id": 1012, "contact_type": "character", "standing": -10.0},
    {"contact_id": 1013, "contact_type": "character", "standing": -5.0},
    {"contact_id": 1014, "contact_type": "character", "standing": 0.0},
    {"contact_id": 1015, "contact_type": "character", "standing": 5.0},
    {"contact_id": 1016, "contact_type": "character", "standing": 10.0},
    {"contact_id": 3011, "contact_type": "alliance", "standing": -10.0},
    {"contact_id": 3012, "contact_type": "alliance", "standing": -5.0},
    {"contact_id": 3013, "contact_type": "alliance", "standing": 0.0},
    {"contact_id": 3014, "contact_type": "alliance", "standing": 5.0},
    {"contact_id": 3015, "contact_type": "alliance", "standing": 10.0},
    {"contact_id": 2011, "contact_type": "corporation", "standing": -10.0},
    {"contact_id": 2012, "contact_type": "corporation", "standing": -5.0},
    {"contact_id": 2014, "contact_type": "corporation", "standing": 0.0},
    {"contact_id": 2013, "contact_type": "corporation", "standing": 5.0},
    {"contact_id": 2015, "contact_type": "corporation", "standing": 10.0},
]


def load_eve_entities():
    auth_to_eve_entities()
    map_to_category = {
        "alliance": EveEntity.CATEGORY_ALLIANCE,
        "corporation": EveEntity.CATEGORY_CORPORATION,
        "character": EveEntity.CATEGORY_CHARACTER,
    }
    for info in ALLIANCE_CONTACTS:
        EveEntity.objects.get_or_create(
            id=info["contact_id"],
            defaults={
                "category": map_to_category[info["contact_type"]],
                "name": f"dummy_{info['contact_id']}",
            },
        )


class LoadTestDataMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.character_1 = EveCharacter.objects.create(
            character_id=1001,
            character_name="Bruce Wayne",
            corporation_id=2001,
            corporation_name="Wayne Technologies",
            alliance_id=3001,
            alliance_name="Wayne Enterprises",
        )
        cls.corporation_1 = EveCorporationInfo.objects.create(
            corporation_id=cls.character_1.corporation_id,
            corporation_name=cls.character_1.corporation_name,
            member_count=99,
        )
        cls.alliance_1 = EveAllianceInfo.objects.create(
            alliance_id=cls.character_1.alliance_id,
            alliance_name=cls.character_1.alliance_name,
            executor_corp_id=cls.corporation_1.corporation_id,
        )
        cls.character_2 = EveCharacter.objects.create(
            character_id=1002,
            character_name="Clark Kent",
            corporation_id=2001,
            corporation_name="Wayne Technologies",
            alliance_id=3001,
            alliance_name="Wayne Enterprises",
        )
        cls.character_3 = EveCharacter.objects.create(
            character_id=1003,
            character_name="Lex Luthor",
            corporation_id=2003,
            corporation_name="Lex Corp",
            alliance_id=3003,
            alliance_name="Lex Holding",
        )
        cls.corporation_3 = EveCorporationInfo.objects.create(
            corporation_id=cls.character_3.corporation_id,
            corporation_name=cls.character_3.corporation_name,
            member_count=666,
        )
        cls.alliance_3 = EveAllianceInfo.objects.create(
            alliance_id=cls.character_3.alliance_id,
            alliance_name=cls.character_3.alliance_name,
            executor_corp_id=cls.corporation_3.corporation_id,
        )
        cls.character_4 = EveCharacter.objects.create(
            character_id=1004,
            character_name="Kara Danvers",
            corporation_id=2004,
            corporation_name="CatCo",
        )
        cls.corporation_4 = EveCorporationInfo.objects.create(
            corporation_id=cls.character_4.corporation_id,
            corporation_name=cls.character_4.corporation_name,
            member_count=1234,
        )
        cls.character_5 = EveCharacter.objects.create(
            character_id=1005,
            character_name="Peter Parker",
            corporation_id=2005,
            corporation_name="Daily Bugle",
        )
        cls.corporation_5 = EveCorporationInfo.objects.create(
            corporation_id=cls.character_5.corporation_id,
            corporation_name=cls.character_5.corporation_name,
            member_count=1234,
        )
        cls.character_6 = EveCharacter.objects.create(
            character_id=1099,
            character_name="Joe Doe",
            corporation_id=2005,
            corporation_name="Daily Bugle",
        )
        load_eve_entities()


def auth_to_eve_entities():
    """Creates EveEntity objects from existing Auth objects."""
    for obj in EveAllianceInfo.objects.all():
        EveEntity.objects.get_or_create(
            id=obj.alliance_id,
            defaults={
                "name": obj.alliance_name,
                "category": EveEntity.CATEGORY_ALLIANCE,
            },
        )
    for obj in EveCorporationInfo.objects.all():
        EveEntity.objects.get_or_create(
            id=obj.corporation_id,
            defaults={
                "name": obj.corporation_name,
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )
    for obj in EveCharacter.objects.all():
        EveEntity.objects.get_or_create(
            id=obj.character_id,
            defaults={
                "name": obj.character_name,
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )


class EsiContactStub:
    class ContactType(Enum):
        CHARACTER = "character"
        CORPORATION = "corporation"
        ALLIANCE = "alliance"

    def __init__(
        self,
        contact_id: int,
        contact_type: str,
        standing: float,
        label_ids: list = None,
    ) -> None:
        if contact_type not in self.ContactType:
            raise ValueError(f"Invalid contact_type: {contact_type}")

        self._contact_id = int(contact_id)
        self._contact_type = contact_type
        self.standing = float(standing)
        self.label_ids = list(label_ids) if label_ids else None

    def __repr__(self) -> str:
        return (
            "{}("
            "{}"
            ", {}.{}"
            ", standing={}"
            "{}"
            ")".format(
                type(self).__name__,
                self.contact_id,
                type(self).__name__,
                self.contact_type,
                self.standing,
                f", label_ids={self.label_ids}" if self.label_ids else "",
            )
        )

    def __key(self):
        return (
            self.contact_id,
            self.contact_type,
            self.standing,
            tuple(self.label_ids) if self.label_ids else None,
        )

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        if isinstance(other, type(self)):
            return self.__key() == other.__key()
        return NotImplemented

    @property
    def contact_id(self):
        return self._contact_id

    @property
    def contact_type(self):
        return self._contact_type

    def to_esi_dict(self) -> dict:
        return {
            "contact_id": self.contact_id,
            "contact_type": self.ContactType(self.contact_type),
            "standing": self.standing,
            "label_ids": self.label_ids,
        }


class EsiCharacterContactsStub:
    """Simulates the contacts for a character on ESI"""

    def __init__(self) -> None:
        self._contacts = dict()
        self._labels = dict()

    def setup_contacts(self, character_id: int, contacts: list):
        self._contacts[character_id] = dict()
        if character_id not in self._labels:
            self._labels[character_id] = dict()
        for contact in contacts:
            if contact.label_ids:
                for label_id in contact.label_ids:
                    if label_id not in self.labels(character_id).keys():
                        raise ValueError(f"Invalid label_id: {label_id}")
            self._contacts[character_id][contact.contact_id] = copy.deepcopy(contact)

    def setup_labels(self, character_id: int, labels: dict):
        self._labels[character_id] = dict(labels)

    def contacts(self, character_id: int) -> dict:
        return self._contacts[character_id].values()

    def labels(self, character_id: int) -> dict:
        return self._labels[character_id] if character_id in self._labels else dict()

    def esi_get_characters_character_id_contacts(self, character_id, token, page=None):
        contacts = [obj.to_esi_dict() for obj in self._contacts[character_id].values()]
        return BravadoOperationStub(contacts)

    def esi_get_characters_character_id_contacts_labels(
        self, character_id, token, page=None
    ):
        labels = [
            {"label_id": k, "label_name": v}
            for k, v in self._labels[character_id].items()
        ]
        return BravadoOperationStub(labels)

    def esi_post_characters_character_id_contacts(
        self, character_id, contact_ids, standing, token, label_ids=None
    ):
        self._check_label_ids_valid(character_id, label_ids)
        contact_type_map = {
            1: EsiContactStub.ContactType.CHARACTER,
            2: EsiContactStub.ContactType.CORPORATION,
            3: EsiContactStub.ContactType.ALLIANCE,
        }
        for contact_id in contact_ids:
            contact_type = contact_type_map[contact_id // 1000]
            self._contacts[character_id][contact_id] = EsiContactStub(
                contact_id=contact_id,
                contact_type=contact_type,
                standing=standing,
                label_ids=label_ids,
            )
        return BravadoOperationStub([])

    def esi_put_characters_character_id_contacts(
        self, character_id, contact_ids, standing, token, label_ids=None
    ):
        self._check_label_ids_valid(character_id, label_ids)
        for contact_id in contact_ids:
            self._contacts[character_id][contact_id].standing = standing
            if label_ids:
                if not self._contacts[character_id][contact_id].label_ids:
                    self._contacts[character_id][contact_id].label_ids = label_ids
                else:
                    self._contacts[character_id][contact_id].label_ids += label_ids
        return BravadoOperationStub([])

    def esi_delete_characters_character_id_contacts(
        self, character_id, contact_ids, token
    ):
        for contact_id in contact_ids:
            del self._contacts[character_id][contact_id]
        return BravadoOperationStub([])

    def _check_label_ids_valid(self, character_id, label_ids):
        if label_ids:
            for label_id in label_ids:
                if label_id not in self.labels(character_id).keys():
                    raise ValueError(f"Invalid label_id: {label_id}")
