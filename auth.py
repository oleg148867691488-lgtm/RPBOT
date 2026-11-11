"""
AUTH.PY — права доступа.

Две роли:
- ВЛАДЕЛЕЦ (owner): ADMIN_ID / RP_OWNER_ID из окружения. Может всё, включая опасное:
  /clear_facts, /deltag, /addadmin, /deladmin.
- АДМИН (staff): владельцы + список bot_admins (добавляется через /addadmin или /savechat).
  Может: /menu, /stats, /tags, /facts, /find, /delfact, /export, /bulk, /year <год>,
  /savechat, /saveworld, писать #факты в любом месте, лимиты вердиктов выше.

Раньше админом бота становился ЛЮБОЙ админ ЛЮБОЙ группы, куда добавили бота, и мог стереть общую
базу. Теперь это невозможно. Проверки по @username тоже убраны (ник можно перехватить) — только ID.
"""

import json

import config as C
import database as db


def _bot_admin_ids() -> set:
    ids = set()
    for key in ("bot_admins", "saved_admin_ids"):  # saved_admin_ids — наследие старой версии
        raw = db.get_setting(key)
        if not raw:
            continue
        try:
            ids.update(int(x) for x in json.loads(raw))
        except (ValueError, TypeError):
            pass
    return ids


def is_owner(user_id: int) -> bool:
    return user_id in C.OWNER_IDS


def is_staff(user_id: int) -> bool:
    return user_id in C.OWNER_IDS or user_id in _bot_admin_ids()


def staff_list() -> list:
    return sorted(_bot_admin_ids() - set(C.OWNER_IDS))


# --- Следующие функции пишут в БД: вызывать через db.arun(...) ---

def _save(ids: set):
    db.set_setting("bot_admins", json.dumps(sorted(ids)))
    if db.get_setting("saved_admin_ids"):
        db.delete_setting("saved_admin_ids")  # перенесено в bot_admins


def add_bot_admins(new_ids) -> int:
    ids = _bot_admin_ids()
    before = len(ids)
    ids.update(int(i) for i in new_ids if int(i) not in C.OWNER_IDS)
    _save(ids)
    return len(ids) - before


def remove_bot_admin(user_id: int) -> bool:
    ids = _bot_admin_ids()
    if user_id not in ids:
        return False
    ids.discard(user_id)
    _save(ids)
    return True
