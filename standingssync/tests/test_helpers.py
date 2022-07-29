from app_utils.testing import NoSocketsTestCase

from ..helpers import to_esi_dict
from .factories import (
    EveEntityAllianceFactory,
    EveEntityCharacterFactory,
    EveEntityCorporationFactory,
)


class TestEveEntity(NoSocketsTestCase):
    def test_should_return_esi_dict_for_character(self):
        # given
        obj = EveEntityCharacterFactory()
        # when
        result = to_esi_dict(obj, 5.0)
        # then
        self.assertDictEqual(
            result, {"contact_id": obj.id, "contact_type": "character", "standing": 5.0}
        )

    def test_should_return_esi_dict_for_corporation(self):
        # given
        obj = EveEntityCorporationFactory()
        # when
        result = to_esi_dict(obj, 2.0)
        # then
        self.assertDictEqual(
            result,
            {"contact_id": obj.id, "contact_type": "corporation", "standing": 2.0},
        )

    def test_should_return_esi_dict_for_alliance(self):
        # given
        obj = EveEntityAllianceFactory()
        # when
        result = to_esi_dict(obj, -2.0)
        # then
        self.assertDictEqual(
            result, {"contact_id": obj.id, "contact_type": "alliance", "standing": -2.0}
        )
