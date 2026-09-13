from backend.services import capital as cap

CFG = cap.PARTNER


def list_partners(conn) -> list[dict]:
    return cap.list_people(conn, CFG)


def get_partner(conn, partner_id: int) -> dict | None:
    return cap.get_person(conn, CFG, partner_id)


def create_partner(conn, data: dict) -> dict:
    return cap.create_person(conn, CFG, data)


def update_partner(conn, partner_id: int, data: dict) -> dict | None:
    return cap.update_person(conn, CFG, partner_id, data)


def delete_partner(conn, partner_id: int) -> None:
    return cap.delete_person(conn, CFG, partner_id)


def add_contribution(conn, partner_id: int, data: dict) -> dict:
    return cap.add_contribution(conn, CFG, partner_id, data)


def add_distribution(conn, partner_id: int, data: dict) -> dict:
    return cap.add_distribution(conn, CFG, partner_id, data)
