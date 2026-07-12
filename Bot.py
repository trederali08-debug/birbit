#!/usr/bin/env python3
"""
Simple Telegram MMORPG-style bot (single-file).
Requirements:
    pip install python-telegram-bot
Run:
    8470547988:AAEjvGKFEUcEjdFwlUyQeJ5rXdVI9aw4708=your_token_here python bot.py
"""

import os
import logging
import random
import sqlite3
from typing import Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------- Config ----------
TOKEN = os.getenv("TELEGRAM_TOKEN") or "PUT_YOUR_TOKEN_HERE"
DB_PATH = "mmo_bot.db"
# ----------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory battle states: user_id -> battle dict
BATTLES: Dict[int, Dict[str, Any]] = {}


# ---------- Database helpers ----------
def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS players(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT,
        level INTEGER,
        xp INTEGER,
        gold INTEGER,
        hp INTEGER,
        max_hp INTEGER,
        atk INTEGER,
        defe INTEGER
    )
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS inventory(
        user_id INTEGER,
        item TEXT,
        qty INTEGER,
        PRIMARY KEY(user_id, item)
    )
    """
    )
    con.commit()
    con.close()


def get_player(user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT user_id, username, name, level, xp, gold, hp, max_hp, atk, defe FROM players WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    con.close()
    return row


def create_player(user_id: int, username: str, name: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    # Default starter stats
    level = 1
    xp = 0
    gold = 50
    max_hp = 30
    hp = max_hp
    atk = 5
    defe = 2
    cur.execute(
        "INSERT OR REPLACE INTO players(user_id, username, name, level, xp, gold, hp, max_hp, atk, defe) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user_id, username, name, level, xp, gold, hp, max_hp, atk, defe),
    )
    con.commit()
    con.close()


def update_player_stat(user_id: int, **kwargs):
    if not kwargs:
        return
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values())
    values.append(user_id)
    cur.execute(f"UPDATE players SET {fields} WHERE user_id = ?", values)
    con.commit()
    con.close()


def add_item(user_id: int, item: str, qty: int = 1):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT qty FROM inventory WHERE user_id = ? AND item = ?", (user_id, item))
    r = cur.fetchone()
    if r:
        cur.execute("UPDATE inventory SET qty = qty + ? WHERE user_id = ? AND item = ?", (qty, user_id, item))
    else:
        cur.execute("INSERT INTO inventory(user_id, item, qty) VALUES(?,?,?)", (user_id, item, qty))
    con.commit()
    con.close()


def get_inventory(user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT item, qty FROM inventory WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    con.close()
    return rows


# ---------- Game logic ----------
def xp_to_next(level: int) -> int:
    return 100 + (level - 1) * 50


def level_up_check(user_id: int, level: int, xp: int):
    next_xp = xp_to_next(level)
    leveled = False
    while xp >= next_xp:
        xp -= next_xp
        level += 1
        leveled = True
        # Reward: increase stats
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT max_hp, atk, defe FROM players WHERE user_id = ?", (user_id,))
        r = cur.fetchone()
        if r:
            max_hp, atk, defe = r
            max_hp += 5
            atk += 2
            defe += 1
            cur.execute("UPDATE players SET max_hp=?, atk=?, defe=? WHERE user_id=?", (max_hp, atk, defe, user_id))
            con.commit()
        con.close()
        next_xp = xp_to_next(level)
    update_player_stat(user_id, level=level, xp=xp)
    return leveled, level


def make_monster(player_level: int):
    # Monster scales with player level
    m_level = max(1, player_level + random.choice([-1, 0, 0, 1]))
    base = 10 + (m_level - 1) * 5
    hp = base + random.randint(0, 6)
    atk = 3 + m_level * 2 + random.randint(0, 2)
    defe = 1 + m_level + random.randint(0, 1)
    names = ["Goblin", "Wolf", "Bandit", "Skeleton", "Slime", "Orc"]
    name = random.choice(names)
    return {"name": name, "level": m_level, "hp": hp, "max_hp": hp, "atk": atk, "def": defe}


def calc_damage(attacker_atk: int, defender_def: int):
    raw = attacker_atk - defender_def // 2
    raw += random.randint(-2, 3)
    return max(1, raw)


# ---------- Command handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    row = get_player(user.id)
    if not row:
        display_name = user.full_name or user.username or f"user{user.id}"
        create_player(user.id, user.username or "", display_name)
        await update.message.reply_text(
            f"Xush kelibsiz, {display_name}!\nSiz yangi sarguzashtni boshladingiz. /help bilan buyruqlarni ko'ring."
        )
    else:
        await update.message.reply_text("Sizning profilingiz mavjud. /profile bilan ko'ring.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - o'yinchi yaratish\n"
        "/profile - stats\n"
        "/explore - atrofni o'rganish (random encounter)\n"
        "/inventory - inventar\n"
        "/shop - do'kon\n"
        "/help - yordam\n"
    )
    await update.message.reply_text(text)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    row = get_player(user.id)
    if not row:
        await update.message.reply_text("Profil topilmadi. /start bilan boshlang.")
        return
    _, username, name, level, xp, gold, hp, max_hp, atk, defe = row
    next_xp = xp_to_next(level)
    text = (
        f"{name} (lvl {level})\n"
        f"HP: {hp}/{max_hp}\n"
        f"ATK: {atk}  DEF: {defe}\n"
        f"XP: {xp}/{next_xp}\n"
        f"Gold: {gold}\n"
    )
    await update.message.reply_text(text)


async def explore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    row = get_player(user.id)
    if not row:
        await update.message.reply_text("Profil topilmadi. /start bilan boshlang.")
        return
    _, _, name, level, xp, gold, hp, max_hp, atk, defe = row

    # Random event
    r = random.random()
    if r < 0.35:
        # nothing happens
        await update.message.reply_text("Siz hududni o'rganasiz, ammo hech narsa topmaysiz.")
    elif r < 0.85:
        # monster
        monster = make_monster(level)
        BATTLES[user.id] = {
            "player": {"hp": hp, "max_hp": max_hp, "atk": atk, "def": defe},
            "monster": monster,
        }
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Attack ⚔️", callback_data="attack")],
                [InlineKeyboardButton("Run 🏃", callback_data="run")],
            ]
        )
        await update.message.reply_text(
            f"Sizga hujum! {monster['name']} (lvl {monster['level']}) paydo bo'ldi. HP: {monster['hp']}",
            reply_markup=kb,
        )
    else:
        # find gold or item
        if random.random() < 0.6:
            found = random.randint(5, 30)
            update_player_stat(user.id, gold=gold + found)
            await update.message.reply_text(f"Siz {found} oltin topdingiz!")
        else:
            item = random.choice(["Potion", "Antidote", "Gem"])
            add_item(user.id, item, 1)
            await update.message.reply_text(f"Siz {item} topdingiz!")


# ---------- CallbackQuery for battle / shop ----------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    data = query.data

    if data == "attack":
        if user_id not in BATTLES:
            await query.edit_message_text("Siz hozir jangda emassiz. /explore bilan jang boshlang.")
            return
        battle = BATTLES[user_id]
        player = battle["player"]
        monster = battle["monster"]

        # player's attack
        player_atk = player["atk"]
        monster_def = monster["def"]
        dmg = calc_damage(player_atk, monster_def)
        monster["hp"] -= dmg
        text = f"Siz {monster['name']} ga {dmg} zarba berdingiz. (Monster HP: {max(0, monster['hp'])}/{monster['max_hp']})\n"

        if monster["hp"] <= 0:
            # monster defeated
            reward_xp = 20 + monster["level"] * 10 + random.randint(0, 10)
            reward_gold = 10 + monster["level"] * 5 + random.randint(0, 10)
            # update player xp/gold in DB
            row = get_player(user_id)
            if row:
                _, _, _, level, xp, gold, hp_db, max_hp_db, atk_db, defe_db = row
                xp += reward_xp
                gold += reward_gold
                update_player_stat(user_id, xp=xp, gold=gold, hp=min(max_hp_db, player["hp"]))
                leveled, new_level = level_up_check(user_id, level, xp)
                msg = f"Siz {monster['name']} ni yutdingiz! XP +{reward_xp}, Gold +{reward_gold}."
                if leveled:
                    msg += f"\nTabriklar! Siz darajangizni oshirdingiz — yangi level: {new_level}."
                # possible drop
                if random.random() < 0.3:
                    item = random.choice(["Potion", "Gem"])
                    add_item(user_id, item, 1)
                    msg += f"\nSiz {item} topdingiz!"
                await query.edit_message_text(msg)
            else:
                await query.edit_message_text("Xato: profil topilmadi.")
            del BATTLES[user_id]
            return

        # monster attack back
        monster_atk = monster["atk"]
        player_def = player["def"]
        dmg2 = calc_damage(monster_atk, player_def)
        player["hp"] -= dmg2
        text += f"{monster['name']} sizga {dmg2} zarba berdi. (Sizning HP: {max(0, player['hp'])}/{player['max_hp']})"
        # update player's HP in DB
        row = get_player(user_id)
        if row:
            _, _, _, level, xp, gold, hp_db, max_hp_db, atk_db, defe_db = row
            update_player_stat(user_id, hp=max(0, player["hp"]))
        else:
            await query.edit_message_text("Xato: profil topilmadi.")
            del BATTLES[user_id]
            return

        if player["hp"] <= 0:
            # player died
            # penalty: lose some gold, restore to half HP
            penalty = min(gold, random.randint(5, 20))
            row = get_player(user_id)
            if row:
                _, _, _, level, xp, gold_db, hp_db, max_hp_db, atk_db, defe_db = row
                gold_db = max(0, gold_db - penalty)
                new_hp = max_hp_db // 2
                update_player_stat(user_id, gold=gold_db, hp=new_hp)
            await query.edit_message_text(f"Siz mag'lub bo'ldingiz va {penalty} oltinni yo'qotdingiz. Sizga yarim HP qaytarildi.")
            del BATTLES[user_id]
            return

        # still alive: show buttons again
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Attack ⚔️", callback_data="attack")],
                [InlineKeyboardButton("Run 🏃", callback_data="run")],
            ]
        )
        await query.edit_message_text(text, reply_markup=kb)

    elif data == "run":
        if user_id not in BATTLES:
            await query.edit_message_text("Siz hozir jangda emassiz.")
            return
        # chance to escape
        if random.random() < 0.55:
            del BATTLES[user_id]
            await query.edit_message_text("Siz muvaffaqiyatli qochdingiz!")
        else:
            # monster gets a free hit
            battle = BATTLES[user_id]
            monster = battle["monster"]
            player = battle["player"]
            dmg = calc_damage(monster["atk"], player["def"])
            player["hp"] -= dmg
            # update DB
            row = get_player(user_id)
            if row:
                _, _, _, level, xp, gold_db, hp_db, max_hp_db, atk_db, defe_db = row
                update_player_stat(user_id, hp=max(0, player["hp"]))
            if player["hp"] <= 0:
                # died while running
                penalty = min(gold_db, random.randint(5, 20))
                gold_db = max(0, gold_db - penalty)
                new_hp = max_hp_db // 2
                update_player_stat(user_id, gold=gold_db, hp=new_hp)
                del BATTLES[user_id]
                await query.edit_message_text(f"Siz qochmoqchi bo‘lganingizda o‘ltingiz: {penalty} oltin yo‘qotildi, yarim HP qaytarildi.")
            else:
                await query.edit_message_text(f"Qochish muvaffaqiyatsiz. {monster['name']} sizga {dmg} zarba berdi. (HP: {player['hp']}/{player['max_hp']})")
    elif data.startswith("shop_buy:"):
        parts = data.split(":")
        if len(parts) != 3:
            await query.edit_message_text("Noto'g'ri so'rov.")
            return
        item = parts[1]
        price = int(parts[2])
        row = get_player(user_id)
        if not row:
            await query.edit_message_text("Profil topilmadi.")
            return
        _, _, _, level, xp, gold_db, hp_db, max_hp_db, atk_db, defe_db = row
        if gold_db < price:
            await query.edit_message_text("Sizda yetarli oltin yo'q.")
            return
        # buy logic
        gold_db -= price
        add_item(user_id, item, 1)
        update_player_stat(user_id, gold=gold_db)
        await query.edit_message_text(f"Siz {item} sotib oldingiz. Qolgan oltin: {gold_db}.")
    else:
        await query.edit_message_text("Noma'lum tugma.")


# ---------- Shop & Inventory ----------
SHOP_ITEMS = [
    ("Potion", 20, "Restores 20 HP"),
    ("Antidote", 15, "Cures poison (placeholder)"),
    ("Sword", 150, "Increases ATK by 5 (equip not implemented)"),
]


async def shop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    row = get_player(user.id)
    if not row:
        await update.message.reply_text("Profil topilmadi. /start bilan boshlang.")
        return
    text_lines = ["Do'kon:"]
    kb_buttons = []
    for item, price, desc in SHOP_ITEMS:
        text_lines.append(f"{item} — {price} gold — {desc}")
        kb_buttons.append([InlineKeyboardButton(f"Buy {item} ({price}G)", callback_data=f"shop_buy:{item}:{price}")])
    kb = InlineKeyboardMarkup(kb_buttons)
    await update.message.reply_text("\n".join(text_lines), reply_markup=kb)


async def inventory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    inv = get_inventory(user.id)
    if not inv:
        await update.message.reply_text("Sizning inventaringiz bo'sh.")
        return
    lines = ["Sizning inventaringiz:"]
    for item, qty in inv:
        lines.append(f"{item} x{qty}")
    await update.message.reply_text("\n".join(lines))


# ---------- Main ----------
def main():
    init_db()
    if TOKEN == "PUT_YOUR_TOKEN_HERE":
        logger.error("Iltimos, TELEGRAM_TOKEN o'rnating (yoki tokenni bot.py ichiga joylang).")
        return
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("explore", explore))
    app.add_handler(CommandHandler("shop", shop_cmd))
    app.add_handler(CommandHandler("inventory", inventory_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
