from bravado.exception import HTTPError

from eveuniverse.models import EveEntity

from .providers import esi


def is_esi_online() -> bool:
    """Checks if the Eve servers are online. Returns True if there are, else False"""
    try:
        status = esi.client.Status.get_status().results()
        if status.get("vip"):
            return False

    except HTTPError:
        return False

    return True


def to_esi_dict(eve_entity: EveEntity, standing: float) -> dict:
    """Convert EveEntity to ESI contact dict."""
    return {
        "contact_id": eve_entity.id,
        "contact_type": eve_entity.category,
        "standing": standing,
    }


def extract_id_from_war_participant(participant: dict) -> int:
    alliance_id = participant.get("alliance_id")
    corporation_id = participant.get("corporation_id")
    if not alliance_id and not corporation_id:
        raise ValueError(f"Invalid participant: {participant}")
    return alliance_id or corporation_id
