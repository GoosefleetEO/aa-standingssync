from unittest.mock import patch

from django.test import TestCase, override_settings
from eveuniverse.models import EveEntity

from allianceauth.authentication.models import CharacterOwnership
from app_utils.testing import (
    NoSocketsTestCase,
    create_user_from_evecharacter,
    generate_invalid_pk,
)

from .. import tasks
from ..models import SyncedCharacter, SyncManager
from .factories import EveContactFactory, SyncedCharacterFactory, SyncManagerFactory
from .utils import ALLIANCE_CONTACTS, LoadTestDataMixin

MANAGERS_PATH = "standingssync.managers"
MODELS_PATH = "standingssync.models"
TASKS_PATH = "standingssync.tasks"


@patch(TASKS_PATH + ".run_manager_sync")
@patch(TASKS_PATH + ".update_all_wars")
class TestRunRegularSync(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # given
        cls.user_1, _ = create_user_from_evecharacter(cls.character_1.character_id)

    def test_should_start_all_tasks(self, mock_update_all_wars, mock_run_manager_sync):
        # given
        sync_manager = SyncManagerFactory(user=self.user_1, version_hash="new")
        with patch(TASKS_PATH + ".is_esi_online", lambda: True):
            # when
            tasks.run_regular_sync()
        # then
        self.assertTrue(mock_update_all_wars.apply_async.called)
        _, kwargs = mock_run_manager_sync.apply_async.call_args
        self.assertListEqual(kwargs["args"], [sync_manager.pk])

    def test_abort_when_esi_if_offline(
        self, mock_update_all_wars, mock_run_manager_sync
    ):
        # given
        with patch(TASKS_PATH + ".is_esi_online", lambda: False):
            # when
            tasks.run_regular_sync()
        # then
        self.assertFalse(mock_update_all_wars.apply_async.called)
        self.assertFalse(mock_run_manager_sync.apply_async.called)


class TestCharacterSync(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 1 user with 1 alt character
        cls.user_1, _ = create_user_from_evecharacter(cls.character_1.character_id)
        alt_ownership_2 = CharacterOwnership.objects.create(
            character=cls.character_2, owner_hash="x2", user=cls.user_1
        )
        alt_ownership_3 = CharacterOwnership.objects.create(
            character=cls.character_3, owner_hash="x3", user=cls.user_1
        )

        # sync manager with contacts
        cls.sync_manager = SyncManagerFactory(user=cls.user_1, version_hash="new")
        for contact in ALLIANCE_CONTACTS:
            EveContactFactory(
                manager=cls.sync_manager,
                eve_entity=EveEntity.objects.get(id=contact["contact_id"]),
                standing=contact["standing"],
            )

        # sync char
        cls.synced_character_2 = SyncedCharacterFactory(
            character_ownership=alt_ownership_2, manager=cls.sync_manager
        )
        cls.synced_character_3 = SyncedCharacterFactory(
            character_ownership=alt_ownership_3, manager=cls.sync_manager
        )

    def test_run_character_sync_wrong_pk(self):
        """calling for an non existing sync character should raise an exception"""
        with self.assertRaises(SyncedCharacter.DoesNotExist):
            tasks.run_character_sync(generate_invalid_pk(SyncedCharacter))

    @patch(TASKS_PATH + ".SyncedCharacter.update")
    def test_should_call_update(self, mock_update):
        # given
        mock_update.return_value = True
        # when
        result = tasks.run_character_sync(self.synced_character_2)
        # then
        self.assertTrue(result)
        self.assertTrue(mock_update.called)

    @patch(TASKS_PATH + ".SyncedCharacter.update")
    def test_should_raise_exception(self, mock_update):
        # given
        mock_update.side_effect = RuntimeError
        # when
        with self.assertRaises(RuntimeError):
            tasks.run_character_sync(self.synced_character_2)


@patch(TASKS_PATH + ".run_character_sync")
class TestManagerSync(LoadTestDataMixin, TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # create environment
        # 1 user has permission for manager sync
        cls.user_1, cls.main_ownership_1 = create_user_from_evecharacter(
            cls.character_1.character_id, permissions=["standingssync.add_syncmanager"]
        )

        # user 1 has no permission for manager sync and has 1 alt
        cls.user_2, cls.main_ownership_2 = create_user_from_evecharacter(
            cls.character_2.character_id
        )
        cls.alt_ownership_2 = CharacterOwnership.objects.create(
            character=cls.character_4, owner_hash="x4", user=cls.user_2
        )

    # run for non existing sync manager
    def test_run_sync_wrong_pk(self, mock_run_character_sync):
        with self.assertRaises(SyncManager.DoesNotExist):
            tasks.run_manager_sync(99999)

    @patch(MODELS_PATH + ".SyncManager.update_from_esi")
    def test_should_report_error_when_unexpected_exception_occurs(
        self, mock_update_from_esi, mock_run_character_sync
    ):
        # given
        mock_update_from_esi.side_effect = RuntimeError
        sync_manager = SyncManagerFactory(user=self.user_1)
        # when
        result = tasks.run_manager_sync(sync_manager.pk)
        # then
        sync_manager.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(sync_manager.last_error, SyncManager.Error.UNKNOWN)

    @patch(MODELS_PATH + ".SyncManager.update_from_esi")
    def test_should_normally_run_character_sync(
        self, mock_update_from_esi, mock_run_character_sync
    ):
        # given
        mock_update_from_esi.return_value = "abc"
        sync_manager = SyncManagerFactory(user=self.user_1)
        synced_character = SyncedCharacterFactory(
            character_ownership=self.alt_ownership_2, manager=sync_manager
        )
        # when
        result = tasks.run_manager_sync(sync_manager.pk)
        # then
        sync_manager.refresh_from_db()
        self.assertTrue(result)
        self.assertEqual(sync_manager.last_error, SyncManager.Error.NONE)
        _, kwargs = mock_run_character_sync.apply_async.call_args
        self.assertEqual(kwargs["kwargs"]["sync_char_pk"], synced_character.pk)
        self.assertFalse(kwargs["kwargs"]["force_sync"])


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class TestUpdateWars(LoadTestDataMixin, NoSocketsTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @patch(TASKS_PATH + ".update_war")
    @patch(TASKS_PATH + ".EveWar.objects.calc_relevant_war_ids")
    def test_should_start_tasks_for_each_war_id(
        self, mock_calc_relevant_war_ids, mock_update_war
    ):
        # given
        mock_calc_relevant_war_ids.return_value = [1, 2, 3]
        # when
        tasks.update_all_wars()
        # then
        result = {
            obj[1]["args"][0] for obj in mock_update_war.apply_async.call_args_list
        }
        self.assertSetEqual(result, {1, 2, 3})

    # @patch(TASKS_PATH + ".update_war")
    # @patch(TASKS_PATH + ".EveWar.objects.calc_relevant_war_ids")
    # def test_should_remove_older_finished_wars(
    #     self, mock_calc_relevant_war_ids, mock_update_war
    # ):
    #     # given
    #     mock_calc_relevant_war_ids.return_value = [2]
    #     EveWarFactory(id=1)
    #     EveWarFactory(id=2)
    #     # when
    #     tasks.update_all_wars()
    #     # then
    #     current_war_ids = set(EveWar.objects.values_list("id", flat=True))
    #     self.assertSetEqual(current_war_ids, {2})

    @patch(TASKS_PATH + ".EveWar.objects.update_or_create_from_esi")
    def test_should_update_war(self, mock_update_from_esi):
        # when
        tasks.update_war(42)
        # then
        args, _ = mock_update_from_esi.call_args
        self.assertEqual(args[0], 42)
