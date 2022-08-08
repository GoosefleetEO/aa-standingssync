import datetime as dt
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils.timezone import now
from esi.errors import TokenExpiredError, TokenInvalidError
from esi.models import Token
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from allianceauth.tests.auth_utils import AuthUtils
from app_utils.esi_testing import BravadoOperationStub
from app_utils.testing import NoSocketsTestCase, create_user_from_evecharacter

from ..models import EveContact, EveWar, SyncedCharacter, SyncManager
from .factories import (
    EveContactFactory,
    EveContactWarTargetFactory,
    EveEntityAllianceFactory,
    EveWarFactory,
    SyncedCharacterFactory,
    SyncManagerFactory,
    UserMainSyncerFactory,
)
from .utils import (
    ALLIANCE_CONTACTS,
    EsiCharacterContactsStub,
    EsiContact,
    EsiContactLabel,
    LoadTestDataMixin,
)

MODELS_PATH = "standingssync.models"


class TestGetEffectiveStanding(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        user, _ = create_user_from_evecharacter(
            cls.character_1.character_id, permissions=["standingssync.add_syncmanager"]
        )
        cls.sync_manager = SyncManagerFactory(user=user)
        contacts = [
            {"contact_id": 1001, "contact_type": "character", "standing": -10},
            {"contact_id": 2001, "contact_type": "corporation", "standing": 10},
            {"contact_id": 3001, "contact_type": "alliance", "standing": 5},
        ]
        for contact in contacts:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )

    def test_char_with_character_standing(self):
        c1 = EveCharacter(
            character_id=1001,
            character_name="Char 1",
            corporation_id=201,
            corporation_name="Corporation 1",
            corporation_ticker="C1",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c1), -10)

    def test_char_with_corporation_standing(self):
        c2 = EveCharacter(
            character_id=1002,
            character_name="Char 2",
            corporation_id=2001,
            corporation_name="Corporation 1",
            corporation_ticker="C1",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c2), 10)

    def test_char_with_alliance_standing(self):
        c3 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
            alliance_id=3001,
            alliance_name="Alliance 1",
            alliance_ticker="A1",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c3), 5)

    def test_char_without_standing_and_has_alliance(self):
        c4 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
            alliance_id=3002,
            alliance_name="Alliance 2",
            alliance_ticker="A2",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c4), 0.0)

    def test_char_without_standing_and_without_alliance_1(self):
        c4 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
            alliance_id=None,
            alliance_name=None,
            alliance_ticker=None,
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c4), 0.0)

    def test_char_without_standing_and_without_alliance_2(self):
        c4 = EveCharacter(
            character_id=1003,
            character_name="Char 3",
            corporation_id=2003,
            corporation_name="Corporation 3",
            corporation_ticker="C2",
        )
        self.assertEqual(self.sync_manager.get_effective_standing(c4), 0.0)


class TestSyncManager(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 1 user has permission for manager sync
        cls.user_1, _ = create_user_from_evecharacter(
            cls.character_1.character_id, permissions=["standingssync.add_syncmanager"]
        )

        # user 1 has no permission for manager sync and has 1 alt
        cls.user_2, _ = create_user_from_evecharacter(cls.character_2.character_id)
        cls.alt_ownership = CharacterOwnership.objects.create(
            character=cls.character_4, owner_hash="x4", user=cls.user_2
        )

    def test_should_report_no_sync_error(self):
        # given
        sync_manager = SyncManagerFactory(user=self.user_1)
        sync_manager.set_sync_status(SyncManager.Error.NONE)
        # when/then
        self.assertTrue(sync_manager.is_sync_ok)

    def test_should_report_sync_error(self):
        # given
        sync_manager = SyncManagerFactory(user=self.user_1)
        for status in [
            SyncManager.Error.TOKEN_INVALID,
            SyncManager.Error.TOKEN_EXPIRED,
            SyncManager.Error.INSUFFICIENT_PERMISSIONS,
            SyncManager.Error.NO_CHARACTER,
            SyncManager.Error.ESI_UNAVAILABLE,
            SyncManager.Error.UNKNOWN,
        ]:
            with self.subTest(status=status):
                sync_manager.set_sync_status(status)
                # when/then
                self.assertFalse(sync_manager.is_sync_ok)

    def test_set_sync_status(self):
        # given
        sync_manager = SyncManagerFactory(user=self.user_1)
        sync_manager.last_error = SyncManager.Error.NONE
        sync_manager.last_sync = None
        # when
        sync_manager.set_sync_status(SyncManager.Error.TOKEN_INVALID)
        # then
        sync_manager.refresh_from_db()
        self.assertEqual(sync_manager.last_error, SyncManager.Error.TOKEN_INVALID)
        self.assertIsNotNone(sync_manager.last_sync)

    def test_should_abort_when_no_char(self):
        # given
        sync_manager = SyncManagerFactory(
            alliance=self.alliance_1, character_ownership=None
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertFalse(result)
        sync_manager.refresh_from_db()
        self.assertEqual(sync_manager.last_error, SyncManager.Error.NO_CHARACTER)

    def test_should_abort_when_insufficient_permission(self):
        # given
        sync_manager = SyncManagerFactory(user=self.user_2)
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertFalse(result)
        sync_manager.refresh_from_db()
        self.assertEqual(
            sync_manager.last_error, SyncManager.Error.INSUFFICIENT_PERMISSIONS
        )

    @patch(MODELS_PATH + ".Token")
    def test_should_report_error_when_character_has_no_token(self, mock_Token):
        # given
        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = (
            None
        )
        sync_manager = SyncManagerFactory(user=self.user_1)
        # when
        result = sync_manager.update_from_esi()
        # then
        sync_manager.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(sync_manager.last_error, SyncManager.Error.TOKEN_INVALID)

    @patch(MODELS_PATH + ".Token")
    def test_should_report_error_when_token_is_expired(self, mock_Token):
        # given
        mock_Token.objects.filter.side_effect = TokenExpiredError()
        sync_manager = SyncManagerFactory(user=self.user_1)
        SyncedCharacterFactory(
            character_ownership=self.alt_ownership, manager=sync_manager
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        sync_manager.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(sync_manager.last_error, SyncManager.Error.TOKEN_EXPIRED)

    @patch(MODELS_PATH + ".Token")
    def test_should_report_error_when_token_is_invalid(self, mock_Token):
        # given
        mock_Token.objects.filter.side_effect = TokenInvalidError()
        sync_manager = SyncManagerFactory(user=self.user_1)
        SyncedCharacterFactory(
            character_ownership=self.alt_ownership, manager=sync_manager
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        sync_manager.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(sync_manager.last_error, SyncManager.Error.TOKEN_INVALID)

    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_sync_contacts(self, mock_esi, mock_Token):
        # given
        sync_manager = SyncManagerFactory(user=self.user_1)
        SyncedCharacterFactory(
            character_ownership=self.alt_ownership, manager=sync_manager
        )
        with patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False):
            # when
            self._run_sync(sync_manager, mock_esi, mock_Token)
        # then (continued)
        contact = sync_manager.contacts.get(eve_entity_id=3015)
        self.assertEqual(contact.standing, 10.0)
        self.assertFalse(contact.is_war_target)

    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_sync_contacts_and_war_targets(self, mock_esi, mock_Token):
        # given
        sync_manager = SyncManagerFactory(user=self.user_1)
        SyncedCharacterFactory(
            character_ownership=self.alt_ownership, manager=sync_manager
        )
        EveWar.objects.create(
            id=8,
            aggressor=EveEntity.objects.get(id=3015),
            defender=EveEntity.objects.get(id=3001),
            declared=now() - dt.timedelta(days=3),
            started=now() - dt.timedelta(days=2),
            is_mutual=False,
            is_open_for_allies=False,
        )

        with patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True):
            # when
            self._run_sync(sync_manager, mock_esi, mock_Token)
        # then (continued)
        contact = sync_manager.contacts.get(eve_entity_id=3015)
        self.assertEqual(contact.standing, -10.0)
        self.assertTrue(contact.is_war_target)

    def _run_sync(self, sync_manager, mock_esi, mock_Token):
        def esi_get_alliances_alliance_id_contacts(*args, **kwargs):
            return BravadoOperationStub(ALLIANCE_CONTACTS)

        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.side_effect = (
            esi_get_alliances_alliance_id_contacts
        )
        mock_Token.objects.filter.return_value.require_scopes.return_value.require_valid.return_value.first.return_value = Mock(
            spec=Token
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertEqual(sync_manager.last_error, SyncManager.Error.NONE)
        expected_contact_ids = {x["contact_id"] for x in ALLIANCE_CONTACTS}
        expected_contact_ids.add(self.character_1.alliance_id)
        result_contact_ids = set(
            sync_manager.contacts.values_list("eve_entity_id", flat=True)
        )
        self.assertSetEqual(expected_contact_ids, result_contact_ids)
        return sync_manager


def fetch_war_targets():
    return set(
        EveContact.objects.filter(is_war_target=True).values_list(
            "eve_entity_id", flat=True
        )
    )


@patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
@patch(MODELS_PATH + ".esi")
class TestSyncManager2(NoSocketsTestCase):
    def test_should_add_war_target_contact_as_aggressor_1(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            aggressor=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(fetch_war_targets(), {war.defender.id})

    def test_should_add_war_target_contact_as_aggressor_2(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        ally = EveEntityAllianceFactory()
        war = EveWarFactory(
            aggressor=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            allies=[ally],
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(fetch_war_targets(), {war.defender.id, ally.id})

    def test_should_add_war_target_contact_as_defender(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(fetch_war_targets(), {war.aggressor.id})

    def test_should_add_war_target_contact_as_ally(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            allies=[EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)]
        )
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(fetch_war_targets(), {war.aggressor.id})

    def test_should_not_add_war_target_contact_from_unrelated_war(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        EveWarFactory()
        EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id)
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(fetch_war_targets(), set())

    def test_remove_outdated_war_target_contacts(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        sync_manager = SyncManagerFactory()
        war = EveWarFactory(
            defender=EveEntityAllianceFactory(id=sync_manager.alliance.alliance_id),
            finished=now(),
        )
        EveContactWarTargetFactory(manager=sync_manager, eve_entity=war.aggressor)
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)
        sync_manager.refresh_from_db()
        self.assertSetEqual(fetch_war_targets(), set())

    def test_do_nothing_when_contacts_are_unchanged(self, mock_esi):
        # given
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub([])
        )
        my_version_hash = SyncManager._calculate_version_hash({})
        sync_manager = SyncManagerFactory(version_hash=my_version_hash)
        # when
        result = sync_manager.update_from_esi()
        # then
        self.assertTrue(result)


@patch(MODELS_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGETS")
class TestSyncCharacter(LoadTestDataMixin, TestCase):
    CHARACTER_CONTACTS = [
        EsiContact(1014, EsiContact.ContactType.CHARACTER, standing=10.0),
        EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
        EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 1 user with 1 alt character
        cls.user_1, _ = create_user_from_evecharacter(cls.character_1.character_id)
        cls.alt_ownership_2 = CharacterOwnership.objects.create(
            character=cls.character_2, owner_hash="x2", user=cls.user_1
        )
        cls.alt_ownership_3 = CharacterOwnership.objects.create(
            character=cls.character_3, owner_hash="x3", user=cls.user_1
        )
        cls.sync_manager = SyncManagerFactory(user=cls.user_1, version_hash="new")
        # sync manager with contacts
        for contact in ALLIANCE_CONTACTS:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )
        # set to contacts as war targets
        cls.sync_manager.contacts.filter(eve_entity_id__in=[1014, 3013]).update(
            is_war_target=True, standing=-10.0
        )
        cls.alliance_contacts = [
            cls.eve_contact_2_esi_contact(obj)
            for obj in cls.sync_manager.contacts.all()
        ]

    @staticmethod
    def eve_contact_2_esi_contact(eve_contact):
        map_category_2_type = {
            EveEntity.CATEGORY_CHARACTER: EsiContact.ContactType.CHARACTER,
            EveEntity.CATEGORY_CORPORATION: EsiContact.ContactType.CORPORATION,
            EveEntity.CATEGORY_ALLIANCE: EsiContact.ContactType.ALLIANCE,
        }
        return EsiContact(
            contact_id=eve_contact.eve_entity_id,
            contact_type=map_category_2_type[eve_contact.eve_entity.category],
            standing=eve_contact.standing,
        )

    def setUp(self) -> None:
        self.maxDiff = None
        self.synced_character_2 = SyncedCharacterFactory(
            character_ownership=self.alt_ownership_2, manager=self.sync_manager
        )
        self.synced_character_3 = SyncedCharacterFactory(
            character_ownership=self.alt_ownership_3, manager=self.sync_manager
        )

    def test_should_report_no_sync_error(self):
        # given
        self.synced_character_2.set_sync_status(SyncManager.Error.NONE)
        # when/then
        self.assertTrue(self.synced_character_2.is_sync_ok)

    def test_should_report_sync_error(self):
        # given
        for status in [
            SyncedCharacter.Error.TOKEN_INVALID,
            SyncedCharacter.Error.TOKEN_EXPIRED,
            SyncedCharacter.Error.INSUFFICIENT_PERMISSIONS,
            SyncedCharacter.Error.ESI_UNAVAILABLE,
            SyncedCharacter.Error.UNKNOWN,
        ]:
            self.synced_character_2.set_sync_status(status)
            # when/then
            self.assertFalse(self.synced_character_2.is_sync_ok)

    def test_get_last_error_message_after_sync(self):
        self.synced_character_2.last_sync = now()
        self.synced_character_2.last_error = SyncedCharacter.Error.NONE
        expected = "OK"
        self.assertEqual(self.synced_character_2.get_status_message(), expected)

        self.synced_character_2.last_error = SyncedCharacter.Error.TOKEN_EXPIRED
        expected = "Expired token"
        self.assertEqual(self.synced_character_2.get_status_message(), expected)

    def test_get_last_error_message_no_sync(self):
        self.synced_character_2.last_sync = None
        self.synced_character_2.last_error = SyncedCharacter.Error.NONE
        expected = "Not synced yet"
        self.assertEqual(self.synced_character_2.get_status_message(), expected)

        self.synced_character_2.last_error = SyncedCharacter.Error.TOKEN_EXPIRED
        expected = "Expired token"
        self.assertEqual(self.synced_character_2.get_status_message(), expected)

    def test_set_sync_status(self):
        self.synced_character_2.last_error = SyncManager.Error.NONE
        self.synced_character_2.last_sync = None

        self.synced_character_2.set_sync_status(SyncManager.Error.TOKEN_INVALID)
        self.synced_character_2.refresh_from_db()

        self.assertEqual(
            self.synced_character_2.last_error, SyncManager.Error.TOKEN_INVALID
        )
        self.assertIsNotNone(self.synced_character_2.last_sync)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_do_nothing_if_no_update_needed(self, mock_esi, mock_Token):
        # given
        character_id = (
            self.synced_character_2.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        self.synced_character_2.version_hash = self.sync_manager.version_hash
        self.synced_character_2.save()
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertIsNone(self.synced_character_2.last_sync)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_replace_all_contacts_1(self, mock_esi, mock_Token):
        """run normal sync for a character which has blue standing"""
        # given
        character_id = (
            self.synced_character_2.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertEqual(self.synced_character_2.last_error, SyncedCharacter.Error.NONE)
        alliance_contacts_2 = {
            obj for obj in self.alliance_contacts if obj.contact_id != character_id
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(character_id)), alliance_contacts_2
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.0)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_replace_all_contacts_2(self, mock_esi, mock_Token):
        """run normal sync for a character which has no standing and allow neutrals"""
        # given
        character_id = (
            self.synced_character_3.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_3, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertEqual(self.synced_character_3.last_error, SyncedCharacter.Error.NONE)
        self.assertSetEqual(
            set(esi_character_contacts.contacts(character_id)),
            set(self.alliance_contacts),
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_replace_all_contacts_and_add_war_targets(
        self, mock_esi, mock_Token
    ):
        # given
        character_id = (
            self.synced_character_2.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_labels(
            character_id, [EsiContactLabel(1, "war targets")]
        )
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertEqual(self.synced_character_2.last_error, SyncedCharacter.Error.NONE)
        result = set(esi_character_contacts.contacts(character_id))
        expected = {
            EsiContact(
                1014,
                EsiContact.ContactType.CHARACTER,
                standing=-10.0,
                label_ids=[1],
            ),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(
                3013, EsiContact.ContactType.ALLIANCE, standing=-10.0, label_ids=[1]
            ),
            EsiContact(1016, EsiContact.ContactType.CHARACTER, standing=10.0),
            EsiContact(2013, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(2012, EsiContact.ContactType.CORPORATION, standing=-5.0),
            EsiContact(1005, EsiContact.ContactType.CHARACTER, standing=-10.0),
            EsiContact(1013, EsiContact.ContactType.CHARACTER, standing=-5.0),
            EsiContact(3014, EsiContact.ContactType.ALLIANCE, standing=5.0),
            EsiContact(2015, EsiContact.ContactType.CORPORATION, standing=10.0),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=-10.0),
            EsiContact(2014, EsiContact.ContactType.CORPORATION, standing=0.0),
            EsiContact(3015, EsiContact.ContactType.ALLIANCE, standing=10.0),
            EsiContact(1012, EsiContact.ContactType.CHARACTER, standing=-10.0),
            EsiContact(1015, EsiContact.ContactType.CHARACTER, standing=5.0),
            EsiContact(1004, EsiContact.ContactType.CHARACTER, standing=10.0),
            EsiContact(3012, EsiContact.ContactType.ALLIANCE, standing=-5.0),
        }
        self.assertSetEqual(result, expected)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_update_war_targets_only_1(self, mock_esi, mock_Token):
        # given
        character_id = (
            self.synced_character_2.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertEqual(self.synced_character_2.last_error, SyncedCharacter.Error.NONE)
        expected = {
            EsiContact(1014, EsiContact.ContactType.CHARACTER, standing=-10.0),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(3013, EsiContact.ContactType.ALLIANCE, standing=-10.0),
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(character_id)),
            expected,
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_update_war_targets_only_2(self, mock_esi, mock_Token):
        # given
        character_id = (
            self.synced_character_2.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        war_target_label = EsiContactLabel(99, "war targets")
        esi_character_contacts.setup_labels(
            character_id, [war_target_label, EsiContactLabel(1, "other")]
        )
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertEqual(self.synced_character_2.last_error, SyncedCharacter.Error.NONE)
        expected = {
            EsiContact(
                1014,
                EsiContact.ContactType.CHARACTER,
                standing=-10.0,
                label_ids=[war_target_label.id],
            ),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(
                3013,
                EsiContact.ContactType.ALLIANCE,
                standing=-10.0,
                label_ids=[war_target_label.id],
            ),
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(character_id)),
            expected,
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_remove_outdated_war_targets_with_label(self, mock_esi, mock_Token):
        # given
        character_id = self.synced_character_2.character.character_id
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_labels(
            character_id, [EsiContactLabel(1, "war targets")]
        )
        esi_character_contacts.setup_contacts(
            character_id,
            [
                EsiContact(
                    1011,
                    EsiContact.ContactType.CHARACTER,
                    standing=-10.0,
                    label_ids=[1],
                ),
                EsiContact(1014, EsiContact.ContactType.CHARACTER, standing=10.0),
                EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
                EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            ],
        )
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertEqual(self.synced_character_2.last_error, SyncedCharacter.Error.NONE)
        expected = {
            EsiContact(
                1014,
                EsiContact.ContactType.CHARACTER,
                standing=-10.0,
                label_ids=[1],
            ),
            EsiContact(2011, EsiContact.ContactType.CORPORATION, standing=5.0),
            EsiContact(3011, EsiContact.ContactType.ALLIANCE, standing=-10.0),
            EsiContact(
                3013, EsiContact.ContactType.ALLIANCE, standing=-10.0, label_ids=[1]
            ),
        }
        self.assertSetEqual(
            set(esi_character_contacts.contacts(character_id)),
            expected,
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_record_if_character_has_wt_label(self, mock_esi, mock_Token):
        # given
        character_id = (
            self.synced_character_2.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_labels(
            character_id, [EsiContactLabel(1, "war targets")]
        )
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertTrue(self.synced_character_2.has_war_targets_label)

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.01)
    @patch(MODELS_PATH + ".Token")
    @patch(MODELS_PATH + ".esi")
    def test_should_record_if_character_does_not_have_wt_label(
        self, mock_esi, mock_Token
    ):
        # given
        character_id = (
            self.synced_character_2.character_ownership.character.character_id
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_contacts(character_id, self.CHARACTER_CONTACTS)
        # when
        result = self._run_sync(
            mock_esi, mock_Token, self.synced_character_2, esi_character_contacts
        )
        # then
        self.assertTrue(result)
        self.assertFalse(self.synced_character_2.has_war_targets_label)

    @staticmethod
    def _run_sync(mock_esi, mock_Token, synced_character, esi_character_contacts):
        # given
        esi_character_contacts.setup_esi_mock(mock_esi)
        mock_Token.objects.filter = Mock()
        synced_character.character_ownership.user = (
            AuthUtils.add_permission_to_user_by_name(
                "standingssync.add_syncedcharacter",
                synced_character.character_ownership.user,
            )
        )
        # when
        result = synced_character.update()
        if result:
            synced_character.refresh_from_db()
        return result

    def test_should_deactivate_when_insufficient_permission(self):
        # when
        result = self.synced_character_2.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=self.synced_character_2.pk).exists()
        )

    @patch(MODELS_PATH + ".Token")
    def test_should_deactivate_when_no_token_found(self, mock_Token):
        # given
        mock_Token.objects.filter.return_value = Token.objects.none()
        self.synced_character_2.character_ownership.user = (
            AuthUtils.add_permission_to_user_by_name(
                "standingssync.add_syncedcharacter",
                self.synced_character_2.character_ownership.user,
            )
        )
        # when
        result = self.synced_character_2.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=self.synced_character_2.pk).exists()
        )

    @patch(MODELS_PATH + ".Token")
    def test_should_deactivate_when_token_is_invalid(self, mock_Token):
        # given
        mock_Token.objects.filter.side_effect = TokenInvalidError()
        self.synced_character_2.character_ownership.user = (
            AuthUtils.add_permission_to_user_by_name(
                "standingssync.add_syncedcharacter",
                self.synced_character_2.character_ownership.user,
            )
        )
        # when
        result = self.synced_character_2.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=self.synced_character_2.pk).exists()
        )

    @patch(MODELS_PATH + ".Token")
    def test_should_deactivate_when_token_is_expired(self, mock_Token):
        # given
        mock_Token.objects.filter.side_effect = TokenExpiredError()
        self.synced_character_2.character_ownership.user = (
            AuthUtils.add_permission_to_user_by_name(
                "standingssync.add_syncedcharacter",
                self.synced_character_2.character_ownership.user,
            )
        )
        # when
        result = self.synced_character_2.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=self.synced_character_2.pk).exists()
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_CHAR_MIN_STANDING", 0.1)
    @patch(MODELS_PATH + ".Token")
    def test_should_deactivate_when_character_has_no_standing(self, mock_Token):
        # given
        mock_Token.objects.filter.return_value = Mock()
        self.synced_character_2.character_ownership.user = (
            AuthUtils.add_permission_to_user_by_name(
                "standingssync.add_syncedcharacter",
                self.synced_character_2.character_ownership.user,
            )
        )
        contact = self.sync_manager.contacts.get(
            eve_entity_id=self.character_2.character_id
        )
        contact.standing = -10
        contact.save()
        # when
        result = self.synced_character_2.update()
        # then
        self.assertFalse(result)
        self.assertFalse(
            SyncedCharacter.objects.filter(pk=self.synced_character_2.pk).exists()
        )


class TestSyncCharacter2(NoSocketsTestCase):
    def test_should_not_sync_when_no_contacts(self):
        # given
        manager = SyncManagerFactory(version_hash="abc")
        character = SyncedCharacterFactory(manager=manager)
        # when
        result = character.update()
        # then
        self.assertTrue(result)

    def test_should_abort_sync_when_insufficient_permissions(self):
        # given
        manager = SyncManagerFactory(version_hash="abc")
        user = UserMainSyncerFactory(permissions__=[])
        character = SyncedCharacterFactory(manager=manager, user=user)
        # when
        result = character.update()
        # then
        self.assertFalse(result)


class TestEveWar(NoSocketsTestCase):
    def test_str(self):
        # given
        aggressor = EveEntityAllianceFactory(name="Alpha")
        defender = EveEntityAllianceFactory(name="Bravo")
        war = EveWarFactory(aggressor=aggressor, defender=defender)
        # when/then
        self.assertEqual(str(war), "Alpha vs. Bravo")
