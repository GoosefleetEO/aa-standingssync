from unittest.mock import patch

from django.test import override_settings
from eveuniverse.models import EveEntity

from app_utils.esi_testing import BravadoOperationStub
from app_utils.testing import NoSocketsTestCase

from ..tasks import run_manager_sync
from .factories import (
    EveEntityAllianceFactory,
    EveEntityCharacterFactory,
    EveWarFactory,
    SyncedCharacterFactory,
    SyncManagerFactory,
)
from .utils import (
    EsiCharacterContactsStub,
    EsiContact,
    EsiContactLabel,
    create_esi_contact,
)

MODELS_PATH = "standingssync.models"


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
@patch(MODELS_PATH + ".STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGETS")
@patch(MODELS_PATH + ".esi")
class TestIntegration(NoSocketsTestCase):
    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", False)
    def test_should_sync_manager_and_character_no_wt(self, mock_esi):
        # given
        manager = SyncManagerFactory()
        sync_character = SyncedCharacterFactory(manager=manager)
        character = EveEntityCharacterFactory(
            id=sync_character.character.character_id,
            name=sync_character.character.character_name,
        )
        some_alliance_contact = EveEntityCharacterFactory()
        alliance_contacts = [
            create_esi_contact(character),
            create_esi_contact(some_alliance_contact),
        ]
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub(alliance_contacts)
        )
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_esi_mock(mock_esi)
        # when
        run_manager_sync.delay(manager_pk=manager.pk)
        # then
        character_contacts = esi_character_contacts._contacts[
            sync_character.character.character_id
        ]
        self.assertEqual(character_contacts[some_alliance_contact.id].standing, 5)
        self.assertEqual(character_contacts[manager.alliance.alliance_id].standing, 10)
        self.assertNotIn(
            sync_character.character.character_id, character_contacts.keys()
        )

    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    def test_should_sync_manager_and_character_with_wt_as_defender(self, mock_esi):
        # given
        manager = SyncManagerFactory()
        alliance = EveEntity.objects.get(id=manager.alliance.alliance_id)
        war = EveWarFactory(defender=alliance)
        sync_character = SyncedCharacterFactory(manager=manager)
        character = EveEntityCharacterFactory(
            id=sync_character.character.character_id,
            name=sync_character.character.character_name,
        )
        some_alliance_contact = EveEntityCharacterFactory()
        alliance_contacts = [
            create_esi_contact(character),
            create_esi_contact(some_alliance_contact),
        ]
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub(alliance_contacts)
        )
        war_target_label = EsiContactLabel(1, "WAR TARGETS")
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_esi_mock(mock_esi)
        esi_character_contacts.setup_labels(character.id, [war_target_label])
        # when
        run_manager_sync.delay(manager_pk=manager.pk)
        # then
        result = set(
            esi_character_contacts.contacts(sync_character.character.character_id)
        )
        expected = {
            EsiContact.from_eve_entity(some_alliance_contact, standing=5),
            EsiContact(
                manager.alliance.alliance_id,
                EsiContact.ContactType.ALLIANCE,
                standing=10,
            ),
            EsiContact.from_eve_entity(
                war.aggressor, standing=-10, label_ids=[war_target_label.id]
            ),
        }
        self.assertSetEqual(result, expected)

    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", True)
    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    def test_should_sync_manager_and_character_with_wt_as_aggressor(self, mock_esi):
        # given
        manager = SyncManagerFactory()
        alliance = EveEntity.objects.get(id=manager.alliance.alliance_id)
        ally = EveEntityAllianceFactory()
        war = EveWarFactory(aggressor=alliance, allies=[ally])
        sync_character = SyncedCharacterFactory(manager=manager)
        character = EveEntityCharacterFactory(
            id=sync_character.character.character_id,
            name=sync_character.character.character_name,
        )
        some_alliance_contact = EveEntityCharacterFactory()
        some_character_contact = EveEntityCharacterFactory()
        alliance_contacts = [
            create_esi_contact(character),
            create_esi_contact(some_alliance_contact),
        ]
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub(alliance_contacts)
        )
        war_target_label = EsiContactLabel(1, "WAR TARGETS")
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_esi_mock(mock_esi)
        esi_character_contacts.setup_contacts(
            character.id,
            [
                EsiContact.from_eve_entity(ally, standing=5),
                EsiContact.from_eve_entity(some_character_contact, standing=10),
            ],
        )
        esi_character_contacts.setup_labels(character.id, [war_target_label])
        # when
        run_manager_sync.delay(manager_pk=manager.pk)
        # then
        result = set(
            esi_character_contacts.contacts(sync_character.character.character_id)
        )
        expected = {
            EsiContact.from_eve_entity(some_alliance_contact, standing=5),
            EsiContact(
                manager.alliance.alliance_id,
                EsiContact.ContactType.ALLIANCE,
                standing=10,
            ),
            EsiContact.from_eve_entity(
                war.defender, standing=-10, label_ids=[war_target_label.id]
            ),
            EsiContact.from_eve_entity(
                ally, standing=-10, label_ids=[war_target_label.id]
            ),
        }
        self.assertSetEqual(result, expected)

    @patch(MODELS_PATH + ".STANDINGSSYNC_REPLACE_CONTACTS", False)
    @patch(MODELS_PATH + ".STANDINGSSYNC_ADD_WAR_TARGETS", True)
    def test_should_sync_manager_and_character_with_wt_as_aggressor_2(self, mock_esi):
        # given
        manager = SyncManagerFactory()
        alliance = EveEntity.objects.get(id=manager.alliance.alliance_id)
        ally = EveEntityAllianceFactory()
        war = EveWarFactory(aggressor=alliance, allies=[ally])
        sync_character = SyncedCharacterFactory(manager=manager)
        character = EveEntityCharacterFactory(
            id=sync_character.character.character_id,
            name=sync_character.character.character_name,
        )
        some_alliance_contact = EveEntityCharacterFactory()
        some_character_contact = EveEntityCharacterFactory()
        alliance_contacts = [
            create_esi_contact(character),
            create_esi_contact(some_alliance_contact),
        ]
        mock_esi.client.Contacts.get_alliances_alliance_id_contacts.return_value = (
            BravadoOperationStub(alliance_contacts)
        )
        war_target_label = EsiContactLabel(1, "WAR TARGETS")
        esi_character_contacts = EsiCharacterContactsStub()
        esi_character_contacts.setup_esi_mock(mock_esi)
        esi_character_contacts.setup_contacts(
            character.id,
            [
                EsiContact.from_eve_entity(ally, standing=5),
                EsiContact.from_eve_entity(some_character_contact, standing=10),
            ],
        )
        esi_character_contacts.setup_labels(character.id, [war_target_label])
        # when
        run_manager_sync.delay(manager_pk=manager.pk)
        # then
        result = set(
            esi_character_contacts.contacts(sync_character.character.character_id)
        )
        expected = {
            EsiContact.from_eve_entity(
                war.defender, standing=-10, label_ids=[war_target_label.id]
            ),
            EsiContact.from_eve_entity(
                ally, standing=-10, label_ids=[war_target_label.id]
            ),
            EsiContact.from_eve_entity(some_character_contact, standing=10),
        }
        self.assertSetEqual(result, expected)
