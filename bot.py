# bot.py
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters import Text
from aiogram.utils.callback_data import CallbackData
from aiogram import executor
from datetime import datetime, timedelta
from config import BOT_TOKEN, ADMINS, WEBHOOK_URL, REFERRAL_BONUS_PERCENT, MIN_WITHDRAW

# --- DATABASE SETUP ---
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

# Users
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 0,
    referred_by INTEGER
)""")

# Tasks
cursor.execute("""CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    reward REAL,
    assigned_user INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hold_until TIMESTAMP
)""")

# Submissions
cursor.execute("""CREATE TABLE IF NOT EXISTS submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task_id INTEGER,
    proof TEXT,
    status TEXT DEFAULT 'pending'
)""")

# Withdrawals
cursor.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    status TEXT DEFAULT 'pending'
)""")
conn.commit()

# --- BOT SETUP ---
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# --- CALLBACK DATA ---
menu_cb = CallbackData("menu", "action")

# --- USER MAIN MENU ---
def user_main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📞 Support", callback_data=menu_cb.new(action="support")),
        InlineKeyboardButton("💰 Wallet", callback_data=menu_cb.new(action="wallet")),
        InlineKeyboardButton("🗂 My Accounts", callback_data=menu_cb.new(action="accounts")),
        InlineKeyboardButton("📋 Tasks", callback_data=menu_cb.new(action="tasks")),
        InlineKeyboardButton("⚙️ Settings", callback_data=menu_cb.new(action="settings")),
        InlineKeyboardButton("👥 Referral", callback_data=menu_cb.new(action="referral"))
    )
    return kb

# --- HELPER FUNCTIONS ---
def add_task(text, reward, hours=4, hold_days=2):
    now = datetime.now()
    expires_at = now + timedelta(hours=hours)
    hold_until = now + timedelta(days=hold_days)
    cursor.execute(
        "INSERT INTO tasks(text,reward,expires_at,hold_until) VALUES(?,?,?,?)",
        (text, reward, expires_at, hold_until)
    )
    conn.commit()

def assign_task(user_id):
    now = datetime.now()
    cursor.execute(
        "SELECT id, text, reward, expires_at FROM tasks WHERE assigned_user IS NULL AND expires_at > ? LIMIT 1",
        (now,)
    )
    task = cursor.fetchone()
    if task:
        task_id, text, reward, expires_at = task
        cursor.execute("UPDATE tasks SET assigned_user=? WHERE id=?", (user_id, task_id))
        conn.commit()
        return task_id, text, reward
    return None, None, None

def complete_task(user_id, task_id):
    cursor.execute("UPDATE submissions SET status='approved' WHERE user_id=? AND task_id=?", (user_id, task_id))
    cursor.execute("SELECT reward FROM tasks WHERE id=?", (task_id,))
    reward = cursor.fetchone()[0]
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))
    conn.commit()

# --- START COMMAND ---
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    user_id = msg.from_user.id
    ref_id = None
    # Handle referral in /start?ref=ID
    if msg.get_args():
        try:
            ref_id = int(msg.get_args())
        except:
            ref_id = None
    cursor.execute("INSERT OR IGNORE INTO users(user_id, referred_by) VALUES(?,?)", (user_id, ref_id))
    conn.commit()
    await msg.answer("Welcome to Crypto Earning Bot 💸", reply_markup=user_main_menu())

# --- MENU HANDLERS ---
@dp.callback_query_handler(menu_cb.filter())
async def menu_handler(query: types.CallbackQuery, callback_data: dict):
    action = callback_data['action']
    user_id = query.from_user.id

    if action == "support":
        await query.message.answer("Send your message and it will be forwarded to admins.")
        @dp.message_handler(lambda m: True)
        async def forward_support(msg: types.Message):
            for admin_id in ADMINS:
                await bot.send_message(admin_id, f"📩 Support from {msg.from_user.id}:\n{msg.text}")
            await msg.reply("✅ Message sent to admin.")
            dp.message_handlers.unregister(forward_support)

    elif action == "wallet":
        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        balance = cursor.fetchone()[0]
        await query.message.answer(f"💰 Your balance: ${balance}\nMinimum withdraw: ${MIN_WITHDRAW}")

    elif action == "accounts":
        now = datetime.now()
        cursor.execute("SELECT task_id, text, hold_until FROM tasks WHERE assigned_user=? AND hold_until>?", (user_id, now))
        tasks = cursor.fetchall()
        if tasks:
            text = "🗂 Your accounts / tasks:\n\n"
            for t in tasks:
                text += f"Task ID: {t[0]} | {t[1]} | Hold until: {t[2]}\n"
            await query.message.answer(text)
        else:
            await query.message.answer("❌ No accounts/tasks currently.")

    elif action == "tasks":
        task_id, text_task, reward = assign_task(user_id)
        if task_id:
            await query.message.answer(f"📋 New Task:\n{text_task}\nReward: ${reward}\nSubmit proof by replying to this message.")
        else:
            await query.message.answer("❌ No tasks available currently.")

    elif action == "settings":
        await query.message.answer("⚙️ Settings:\n- Task hold/cooldown time\n- Notifications (coming soon)")

    elif action == "referral":
        link = f"https://t.me/YOUR_BOT_USERNAME?start={user_id}"
        cursor.execute("SELECT SUM(balance) FROM users WHERE referred_by=?", (user_id,))
        bonus = cursor.fetchone()[0] or 0
        await query.message.answer(f"👥 Your referral link:\n{link}\nTotal referral bonus earned: ${bonus}")

# --- WEBHOOK STARTUP ---
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

# --- EXECUTOR ---
if __name__ == "__main__":
    executor.start_webhook(
        dispatcher=dp,
        webhook_path="/YOUR_WEBHOOK_PATH",
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=8443
    )
