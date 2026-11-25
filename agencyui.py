"""
AGENCYUI.PY — кнопочный интерфейс агентства (вместо длинных команд /hire, /train, /fire, /agent, /hq).

Вся игровая логика остаётся в agency.py и finance.py: кнопки вызывают те же команды, а их ответы
перехватываются и показываются прямо в экране, без лишних сообщений в чате.
Работает только в личке: агентура — закрытая информация.
"""
import logging
import time
from types import SimpleNamespace

from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
from telegram.constants import ParseMode

import agency
import database as db
import finance
from agency import HQ_ALIAS, HQ_TRACKS, MAX_LEVEL, MAX_SKILL, SKILLS, SKILL_ALIAS, parse_skills, usd
from style import hdr_agency
from textutils import esc
from tg import edit_html, safe_reply
from worldbank import ISO_RU

log = logging.getLogger(__name__)

_SKILL_KEY = {v: k for k, v in reversed(list(SKILL_ALIAS.items()))}      # навык -> любой его алиас для команды /train
_HQ_KEY = {v: k for k, v in reversed(list(HQ_ALIAS.items()))}


class _Cap:
    """Подставляет сообщение: команда «отвечает», а мы собираем её текст вместо отправки."""
    def __init__(self, msg):
        self.chat = msg.chat
        self.texts = []

    async def reply_text(self, text, **kw):
        self.texts.append(text)


async def _run(fn, q, args):
    """Запускает команду агентства от имени нажавшего и возвращает её ответ текстом."""
    cap = _Cap(q.message)
    upd = SimpleNamespace(effective_message=cap, effective_user=q.from_user, message=cap)
    await fn(upd, SimpleNamespace(args=list(args)))
    return "\n".join(cap.texts)


def _kb(*rows) -> M:
    return M([r for r in rows if r])


BACK = [B("◀️ Агентство", callback_data="ag:h")]


async def _agents(uid):
    planted = [a for a in await db.arun(db.list_agents, uid) if a["active"]]
    recruits = await db.arun(db.list_recruits, uid)
    return planted, recruits


async def home(q, note: str = ""):
    text = await _run(agency.agents_command, q, [])
    uid = q.from_user.id
    planted, recruits = await _agents(uid)
    rows = []
    for a in planted[:10]:
        asleep = " 😴" if (a.get("dormant_until") or 0) > time.time() else ""
        rows.append([B(f"A{a['id']} {a.get('name') or 'Агент'}{asleep} → {ISO_RU.get(a['target'], a['target'])}"[:60],
                       callback_data=f"ag:c:A{a['id']}")])
    for r in recruits[:6]:
        rows.append([B(f"R{r['id']} {r['name']} (резерв)"[:60], callback_data=f"ag:c:R{r['id']}")])
    rows.append([B("🧑‍💼 Нанять", callback_data="ag:r"), B("🏛 Штаб", callback_data="ag:q")])
    rows.append([B("🔄 Обновить", callback_data="ag:h"), B("🏠 Меню", callback_data="ui:home")])
    head = (f"{note}\n\n" if note else "")
    await edit_html(q, head + text[:3700], _kb(*rows))


async def _row(kind, rid):
    return await db.arun(db.get_agent if kind == "A" else db.get_recruit, rid)


async def card(q, kind, rid, note: str = ""):
    row = await _row(kind, rid)
    if not row or row.get("owner_id") != q.from_user.id:
        await home(q, "❌ Такого агента нет.")
        return
    sk = parse_skills(row.get("skills"))
    lines = [hdr_agency(f"{kind}{rid} · {row.get('name') or 'Агент'}"), ""]
    if kind == "A":
        asleep = (row.get("dormant_until") or 0) > time.time()
        lines.append(f"📍 {esc(ISO_RU.get(row['target'], row['target']))} · ранг <b>{row['rank']}/3</b>" + (" · 😴 на дне" if asleep else ""))
    else:
        lines.append("📦 В резерве (ещё не внедрён)")
    lines.append(f"🤝 Лояльность: <b>{row.get('loyalty') or 50}</b>")
    lines += ["", *(f"{SKILLS[k]}: <code>{'▰' * v}{'▱' * (MAX_SKILL - v)}</code> {v}/{MAX_SKILL}" for k, v in sk.items())]
    if row.get("bio"):
        lines += ["", f"<i>{esc(row['bio'])}</i>"]
    btn = [[B("🎓 Обучить", callback_data=f"ag:t:{kind}{rid}")]]
    if kind == "A":
        btn[0].append(B("😴 На дно", callback_data=f"ag:s:{kind}{rid}"))
        btn.append([B("⭐ Повысить", callback_data=f"ag:p:{kind}{rid}")])
    btn[-1].append(B("🚪 Уволить", callback_data=f"ag:f:{kind}{rid}"))
    await edit_html(q, (f"{note}\n\n" if note else "") + "\n".join(lines), _kb(*btn, BACK))


async def train_menu(q, kind, rid):
    row = await _row(kind, rid)
    if not row or row.get("owner_id") != q.from_user.id:
        await home(q, "❌ Такого агента нет.")
        return
    sk = parse_skills(row.get("skills"))
    hq = await db.arun(db.get_hq, q.from_user.id)
    rows = []
    for k, name in SKILLS.items():
        if sk[k] >= MAX_SKILL:
            continue
        cost = int(100_000 * 1.6 ** sk[k] * (1 - 0.1 * hq["academy"]) / 1000) * 1000
        rows.append([B(f"{name} {sk[k]}→{sk[k] + 1} · {usd(cost)}", callback_data=f"ag:td:{kind}{rid}:{k}")])
    await edit_html(q, hdr_agency("Чему учить?") + f"\n{esc(row.get('name') or 'Агент')} · 💰 {usd(await agency.clean_total(q.from_user.id))}",
                    _kb(*rows, [B("◀️ Назад", callback_data=f"ag:c:{kind}{rid}")]))


async def hq_screen(q, note: str = ""):
    text = await _run(agency.hq_command, q, [])
    hq = await db.arun(db.get_hq, q.from_user.id)
    rows = []
    for k, (title, base, _eff) in HQ_TRACKS.items():
        if hq[k] >= MAX_LEVEL:
            continue
        rows.append([B(f"{title} ↑ {usd(int(base * 1.9 ** hq[k] / 1000) * 1000)}", callback_data=f"ag:qu:{k}")])
    await edit_html(q, (f"{note}\n\n" if note else "") + text[:3700], _kb(*rows, BACK))


async def hire_screen(q, note: str = ""):
    text = await _run(agency.hire_command, q, [])
    pool = await db.arun(db.get_candidates, q.from_user.id, time.time() - agency.POOL_TTL)
    rows = [[B(f"Нанять #{i} · {c['name']} · {usd(c['price'])}"[:60], callback_data=f"ag:rd:{i}")] for i, c in enumerate(pool, 1)]
    rows.append([B("🔄 Новые кандидаты · $50 000", callback_data="ag:rn")])
    await edit_html(q, (f"{note}\n\n" if note else "") + text[:3700], _kb(*rows, BACK))


async def callback(update, context):
    q = update.callback_query
    if q.message.chat.type != "private":
        await q.answer("🔒 Агентство открывается только в личке с ботом.", show_alert=True)
        return
    await q.answer()
    p = q.data.split(":")
    kind = p[1] if len(p) > 1 else "h"
    uid = q.from_user.id
    try:
        if kind == "h":
            await home(q)
        elif kind == "c":
            await card(q, p[2][0], int(p[2][1:]))
        elif kind == "t":
            await train_menu(q, p[2][0], int(p[2][1:]))
        elif kind == "td":                                              # обучить: навык выбран
            res = await _run(agency.train_command, q, [p[2], _SKILL_KEY[p[3]]])
            await card(q, p[2][0], int(p[2][1:]), res)
        elif kind == "s":                                               # на дно: выбор срока
            rows = [[B(f"{h} ч", callback_data=f"ag:sd:{p[2]}:{h}") for h in (6, 12, 24, 72)]]
            await edit_html(q, hdr_agency("На сколько залечь?") + "\nАгент не действует, но его и не ловят.",
                            _kb(*rows, [B("◀️ Назад", callback_data=f"ag:c:{p[2]}")]))
        elif kind == "sd":
            res = await _run(finance.agent_manage_command, q, ["sleep", p[2][1:], p[3]])
            await card(q, "A", int(p[2][1:]), res)
        elif kind == "p":                                               # повышение рискованное — просим подтвердить
            ag = await db.arun(db.get_agent, int(p[2][1:]))
            chance = int((0.5 - 0.1 * ag["rank"]) * 100) if ag and ag["rank"] < 3 else 0
            await edit_html(q, hdr_agency("Повысить в ранге?") + f"\nШанс успеха: <b>{chance}%</b>. При провале агент может быть выведен из строя (риск 30%).",
                            _kb([B("⭐ Рискнуть", callback_data=f"ag:pd:{p[2]}"), B("❌ Нет", callback_data=f"ag:c:{p[2]}")]))
        elif kind == "pd":
            res = await _run(finance.agent_manage_command, q, ["promote", p[2][1:]])
            await card(q, "A", int(p[2][1:]), res)
        elif kind == "f":                                               # увольнение — с подтверждением, кнопки в обратном порядке
            await edit_html(q, hdr_agency("Уволить агента?") + "\nЭто нельзя отменить.",
                            _kb([B("❌ Нет", callback_data=f"ag:c:{p[2]}"), B("🚪 Да, уволить", callback_data=f"ag:fd:{p[2]}")]))
        elif kind == "fd":
            res = await _run(agency.fire_command, q, [p[2]])
            await home(q, res)
        elif kind == "q":
            await hq_screen(q)
        elif kind == "qu":
            res = await _run(agency.hq_command, q, ["up", _HQ_KEY[p[2]]])
            await hq_screen(q, res.splitlines()[0] if res else "")
        elif kind == "r":
            await hire_screen(q)
        elif kind == "rd":
            res = await _run(agency.hire_command, q, [p[2]])
            await hire_screen(q, res.split("\n\n")[0] if res else "")
        elif kind == "rn":
            res = await _run(agency.hire_command, q, ["new"])
            await hire_screen(q, res.splitlines()[0] if res.startswith("❌") else "")
        else:
            await home(q)
    except Exception:
        log.exception("Ошибка меню агентства (uid=%s, data=%s)", uid, q.data)
        await edit_html(q, "❌ Что-то пошло не так. Попробуй ещё раз.", _kb(BACK))


async def agents_ui_command(update, context):
    """/agents и /agency: агентство с кнопками (в группе — подсказка перейти в личку)."""
    msg = update.effective_message
    if msg.chat.type != "private":
        await safe_reply(msg, "🔒 Это закрытая информация — только в <b>личке</b> с ботом.")
        return
    placeholder = await msg.reply_text("🕴 Открываю агентство…")
    async def _edit(text, parse_mode=None, reply_markup=None, **kw):
        return await placeholder.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)

    q = SimpleNamespace(message=placeholder, from_user=update.effective_user, data="ag:h", edit_message_text=_edit)
    await home(q)
