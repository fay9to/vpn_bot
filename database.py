# database.py
import aiosqlite
from typing import Optional, Dict, Any, List
from datetime import datetime


class Database:

    # В database.py, в класс Database добавь:

    async def add_pending_payment_lolzteam(self, invoice_id: str, user_id: int,
                                           devices: int, tariff_days: int, amount: float):
        """Добавляет платёж LolzTeam в pending"""
        await self.conn.execute(
            """INSERT OR REPLACE INTO pending_payments 
               (invoice_id, user_id, devices, tariff_days, amount, payment_method) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (invoice_id, user_id, devices, tariff_days, amount, "lolzteam")
        )
        await self.conn.commit()

    async def get_pending_payment_by_lolzteam_id(self, invoice_id: str) -> Optional[Dict]:
        """Получает платёж LolzTeam по ID"""
        cursor = await self.conn.cursor()
        await cursor.execute(
            "SELECT * FROM pending_payments WHERE invoice_id = ? AND payment_method = 'lolzteam'",
            (invoice_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    def __init__(self):
        self.conn = None

    async def init_db(self):
        self.conn = await aiosqlite.connect('bot.db')
        self.conn.row_factory = aiosqlite.Row

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                balance REAL DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referred_by) REFERENCES users(id)
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                level INTEGER NOT NULL,
                bonus_earned REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(id),
                FOREIGN KEY (referred_id) REFERENCES users(id)
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                client_email TEXT UNIQUE NOT NULL,
                tariff_days INTEGER NOT NULL,
                device_limit INTEGER NOT NULL,
                expiry_time INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS gift_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                days INTEGER NOT NULL,
                devices INTEGER NOT NULL,
                created_by INTEGER NOT NULL,
                used_by INTEGER,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id),
                FOREIGN KEY (used_by) REFERENCES users(id)
            )
        ''')

        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_payments (
                invoice_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                devices INTEGER NOT NULL,
                tariff_days INTEGER NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        await self.conn.commit()

    async def create_user(self, telegram_id: int, username: str = None, referral_code: str = None,
                          referred_by: int = None) -> Optional[Dict]:
        cursor = await self.conn.cursor()
        try:
            await cursor.execute(
                "INSERT INTO users (telegram_id, username, referral_code, referred_by) VALUES (?, ?, ?, ?)",
                (telegram_id, username, referral_code, referred_by)
            )
            await self.conn.commit()
            return await self.get_user(telegram_id)
        except Exception as e:
            print(f"Error creating user: {e}")
            return None

    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        cursor = await self.conn.cursor()
        await cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        cursor = await self.conn.cursor()
        await cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_balance(self, user_id: int, amount: float, description: str = None,
                             tx_type: str = 'referral_bonus'):
        await self.conn.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (amount, user_id)
        )

        if description:
            await self.conn.execute(
                "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
                (user_id, amount, tx_type, description)
            )

        await self.conn.commit()

    async def get_transactions(self, user_id: int, limit: int = 10) -> List[Dict]:
        cursor = await self.conn.cursor()
        await cursor.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_referral_stats(self, user_id: int) -> Dict[str, Any]:
        cursor = await self.conn.cursor()

        await cursor.execute("""
            SELECT 
                level,
                COUNT(*) as count,
                COALESCE(SUM(bonus_earned), 0) as total_bonus
            FROM referrals 
            WHERE referrer_id = ? 
            GROUP BY level
        """, (user_id,))

        rows = await cursor.fetchall()
        stats = {
            'level_1': 0, 'level_2': 0, 'level_3': 0,
            'total_bonus': 0, 'total_earned': 0, 'total': 0
        }

        for row in rows:
            level, count, bonus = row['level'], row['count'], row['total_bonus']
            stats[f'level_{level}'] = count
            stats['total'] += count
            stats['total_bonus'] += bonus
            stats['total_earned'] += bonus

        return stats

    async def add_referral(self, referrer_id: int, referred_id: int, level: int, bonus: float = 0):
        await self.conn.execute(
            "INSERT INTO referrals (referrer_id, referred_id, level, bonus_earned) VALUES (?, ?, ?, ?)",
            (referrer_id, referred_id, level, bonus)
        )
        await self.conn.commit()

    async def add_subscription(self, user_id: int, client_email: str, tariff_days: int, device_limit: int,
                               expiry_time: int):
        await self.conn.execute(
            """INSERT OR REPLACE INTO subscriptions 
               (user_id, client_email, tariff_days, device_limit, expiry_time) 
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, client_email, tariff_days, device_limit, expiry_time)
        )
        await self.conn.commit()

    async def get_active_subscription(self, user_id: int) -> Optional[Dict]:
        cursor = await self.conn.cursor()
        await cursor.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? AND expiry_time > ? ORDER BY expiry_time DESC LIMIT 1",
            (user_id, int(datetime.now().timestamp() * 1000))
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_subscriptions(self, user_id: int) -> List[Dict]:
        cursor = await self.conn.cursor()
        await cursor.execute(
            "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def add_transaction(self, user_id: int, amount: float, type: str, description: str = None):
        await self.conn.execute(
            "INSERT INTO transactions (user_id, amount, type, description) VALUES (?, ?, ?, ?)",
            (user_id, amount, type, description)
        )
        await self.conn.commit()

    async def create_gift_code(self, code: str, days: int, devices: int, created_by: int):
        await self.conn.execute(
            "INSERT INTO gift_codes (code, days, devices, created_by) VALUES (?, ?, ?, ?)",
            (code, days, devices, created_by)
        )
        await self.conn.commit()

    async def get_gift_code(self, code: str) -> Optional[Dict]:
        cursor = await self.conn.cursor()
        await cursor.execute("SELECT * FROM gift_codes WHERE code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def use_gift_code(self, code: str, used_by: int) -> bool:
        cursor = await self.conn.cursor()
        await cursor.execute(
            "UPDATE gift_codes SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ? AND used_by IS NULL",
            (used_by, code)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    # Pending payments
    async def add_pending_payment(self, invoice_id: str, user_id: int, devices: int, tariff_days: int, amount: float):
        await self.conn.execute(
            "INSERT OR REPLACE INTO pending_payments (invoice_id, user_id, devices, tariff_days, amount) VALUES (?, ?, ?, ?, ?)",
            (str(invoice_id), user_id, devices, tariff_days, amount)
        )
        await self.conn.commit()

    async def get_pending_payment(self, invoice_id: str) -> Optional[Dict]:
        cursor = await self.conn.cursor()
        await cursor.execute("SELECT * FROM pending_payments WHERE invoice_id = ?", (str(invoice_id),))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_pending_payment(self, invoice_id: str):
        await self.conn.execute("DELETE FROM pending_payments WHERE invoice_id = ?", (str(invoice_id),))
        await self.conn.commit()


db = Database()