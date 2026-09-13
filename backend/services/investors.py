from backend.services import capital as cap

CFG = cap.INVESTOR


def list_investors(conn, project_ids: list[int] | None = None) -> list[dict]:
    return cap.list_people(conn, CFG, project_ids=project_ids)


def get_investor(conn, investor_id: int) -> dict | None:
    return cap.get_person(conn, CFG, investor_id)


def create_investor(conn, data: dict) -> dict:
    return cap.create_person(conn, CFG, data)


def update_investor(conn, investor_id: int, data: dict) -> dict | None:
    return cap.update_person(conn, CFG, investor_id, data)


def delete_investor(conn, investor_id: int) -> None:
    return cap.delete_person(conn, CFG, investor_id)


def add_contribution(conn, investor_id: int, data: dict) -> dict:
    return cap.add_contribution(conn, CFG, investor_id, data)


def add_distribution(conn, investor_id: int, data: dict) -> dict:
    return cap.add_distribution(conn, CFG, investor_id, data)
