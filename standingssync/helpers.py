from eveuniverse.models import EveEntity


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
