import logging
import os
import datetime
import hashlib
import json
from celery import shared_task
from esi.models import Token, TokenExpiredError
from esi.clients import esi_client_factory
from django.db import transaction
from .models import *


# add custom tag to logger with name of this app
class LoggerAdapter(logging.LoggerAdapter):
    def __init__(self, logger, prefix):
        super(LoggerAdapter, self).__init__(logger, {})
        self.prefix = prefix

    def process(self, msg, kwargs):
        return '[%s] %s' % (self.prefix, msg), kwargs

logger = logging.getLogger(__name__)
logger = LoggerAdapter(logger, __package__)


SWAGGER_SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'swagger.json')
"""
Swagger spec operations:

get_characters_character_id_contacts
delete_characters_character_id_contacts
post_characters_character_id_contacts
get_alliances_alliance_id_contacts
"""


def makeLoggerTag(tag: str):
    """creates a function to add logger tags"""
    return lambda text : '{}: {}'.format(tag, text)

def chunks(lst, size):
    """Yield successive size-sized chunks from lst."""
    for i in range(0, len(lst), size):
        yield lst[i: i + size]


@shared_task
def run_character_sync(sync_char_pk, force_sync = False):
    """syncs contacts for one character"""

    try:
        synced_character = SyncedCharacter.objects.get(pk=sync_char_pk)
    except SyncedCharacter.DoesNotExist:
        raise SyncedCharacter.DoesNotExist(
            "Requested character with pk {} does not exist".format(
                sync_char_pk
            )
        )
    addTag = makeLoggerTag(synced_character)
    
    # abort if owner does not have sufficient permissions
    if not synced_character.character.user.has_perm(
            'standingssync.add_syncedcharacter'
        ):
        logger.warn('Sync aborted due to insufficient user permissions')
        synced_character.last_error = SyncedCharacter.ERROR_INSUFFICIENT_PERMISSIONS
        synced_character.save()
        return

    # check if an update is needed
    if (not force_sync 
            and synced_character.manager.version_hash == synced_character.version_hash):
        logger.info(addTag(
            'contacts of this char are up-to-date, no sync required'
        ))
    else:        
        # get token
        try:
            token = Token.objects.filter(
                user=synced_character.character.user, 
                character_id=synced_character.character.character.character_id
            ).require_scopes(SyncedCharacter.get_esi_scopes()).require_valid().first()
        except TokenExpiredError:
            synced_character.last_error = SyncedCharacter.ERROR_TOKEN_INVALID
            synced_character.save()
            return
        
        if token is None:
            synced_character.last_error = SyncedCharacter.ERROR_UNKNOWN
            synced_character.save()
            raise RuntimeError('Can not find suitable token for alliance char')
        
        try:
            # fetching data from ESI
            logger.info(addTag('Updating contacts with new version'))            
            client = esi_client_factory(token=token, spec_file=SWAGGER_SPEC_PATH)
            
            # fetch current contacts
            contacts = client.Contacts.get_characters_character_id_contacts(
                character_id=synced_character.character.character.character_id
            ).result()

            # delete all current contacts via ESI
            max_items = 10
            contact_ids_chunks = chunks([x['contact_id'] for x in contacts], max_items)
            for contact_ids_chunk in contact_ids_chunks:
                response = client.Contacts.delete_characters_character_id_contacts(
                    character_id=synced_character.character.character.character_id,
                    contact_ids=contact_ids_chunk
                ).result()
            
            # write alliance contacts to ESI
            for contact in AllianceContact.objects.filter(
                manager=synced_character.manager
            ):
                response = client.Contacts.post_characters_character_id_contacts(
                    character_id=synced_character.character.character.character_id,
                    contact_ids=[contact.contact_id],
                    standing=contact.standing
                ).result()    

            # store updated version hash with character
            synced_character.version_hash = synced_character.manager.version_hash
            synced_character.last_sync = datetime.datetime.now(
                datetime.timezone.utc
            )
            synced_character.last_error = SyncedCharacter.ERROR_NONE
            synced_character.save()
        
        except Exception as ex:
            logger.error('An unhandled exception has occured: {}'.format(ex))
            synced_character.last_error = SyncedCharacter.ERROR_UNKNOWN
            synced_character.save()
            raise


@shared_task
def run_manager_sync(manager_pk, force_sync = False):
    """sync contacts and related characters for one manager"""

    try:
        sync_manager = SyncManager.objects.get(pk=manager_pk)
    except SyncManager.DoesNotExist:        
        raise SyncManager.DoesNotExist(
            'task called for non existing manager with pk {}'.format(manager_pk)
        )
    else:
        addTag = makeLoggerTag(sync_manager)

        current_version_hash = sync_manager.version_hash
        alliance_name = sync_manager.alliance.alliance_name

        if sync_manager.character is None:
            logger.error(addTag(
                'No character configured to sync alliance contacts. ' 
                + 'Sync aborted'
            ))
            return

        # abort if character does not have sufficient permissions
        if not sync_manager.character.user.has_perm(
                'standingssync.add_syncmanager'
            ):
            logger.error(addTag(
                'Character does not have sufficient permission to sync contacts'
            ))
            return

        # get token    
        try:
            token = Token.objects.filter(
                user=sync_manager.character.user, 
                character_id=sync_manager.character.character.character_id
            ).require_scopes(
                SyncManager.get_esi_scopes()
            ).require_valid().first()
        except TokenExpiredError:        
            logger.error(addTag(
                'Missing valid token to sync alliance contacts'
            ))
            return
        
        # fetching data from ESI
        logger.info(addTag('Fetching alliance contacts from ESI'))        
        client = esi_client_factory(token=token, spec_file=SWAGGER_SPEC_PATH)

        contacts = client.Contacts.get_alliances_alliance_id_contacts(
            alliance_id=sync_manager.character.character.alliance_id
        ).result()
        
        # calc MD5 hash on contacts    
        new_version_hash = hashlib.md5(
            json.dumps(contacts).encode('utf-8')
        ).hexdigest()

        if force_sync or new_version_hash != current_version_hash:
            logger.info(
                addTag('Storing alliance update with {:,} contacts'.format(
                    len(contacts)
                ))
            )
            with transaction.atomic():
                AllianceContact.objects.filter(manager=sync_manager).delete()
                for contact in contacts:
                    AllianceContact.objects.create(
                        manager=sync_manager,
                        contact_id=contact['contact_id'],
                        contact_type=contact['contact_type'],
                        standing=contact['standing']                        
                    )
                sync_manager.version_hash = new_version_hash
                sync_manager.last_sync = datetime.datetime.now(
                    datetime.timezone.utc
                )
                sync_manager.save()
        else:
            logger.info(addTag('Alliance contacts are unchanged.'))
        
        # dispatch tasks for characters that need syncing
        alts_need_syncing = SyncedCharacter.objects.filter(
                manager=sync_manager
            ).exclude(
            version_hash=new_version_hash
        )
        for character in alts_need_syncing:
            run_character_sync.delay(character.pk)


@shared_task
def run_sync_all():
    """syncs all managers and related characters if needed"""        
    for sync_manager in SyncManager.objects.all():
        run_manager_sync.delay(sync_manager.pk)