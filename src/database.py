import aiosqlite
import logging
import os
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(level=logging.INFO)

DB_PATH = "data/database.db"

# Проверяем, существует ли путь к БД
if not os.path.exists(DB_PATH):
    logging.warning(f"⚠️ Файл базы данных {DB_PATH} не найден!")

# Блок 1: Инициализация базы данных
async def init_db():
    """Создает таблицы в БД, если их нет."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            # Таблица users
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT,
                is_admin BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )""")
            
            # Таблица spots
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )""")
            
            # Таблица checkins
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                spot_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                active BOOLEAN NOT NULL DEFAULT 1,
                checkin_type INTEGER NOT NULL,
                duration_hours REAL,
                arrival_time TEXT,
                end_time TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (spot_id) REFERENCES spots(id)
            )""")
            
            # Таблица favorite_spots
            await cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorite_spots (
                user_id INTEGER NOT NULL,
                spot_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, spot_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (spot_id) REFERENCES spots(id)
            )""")
            
            await conn.commit()
            logging.info("✅ Таблицы успешно инициализированы.")
    except Exception as e:
        logging.error(f"❌ Ошибка при инициализации БД: {e}")

# Блок 2: Функции для работы с пользователями
async def add_or_update_user(user_id: int, first_name: str, last_name: str = None, username: str = None, is_admin: bool = False):
    """Добавляет нового пользователя или обновляет существующего."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, first_name, last_name, username, is_admin, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, first_name, last_name, username, is_admin, datetime.utcnow().isoformat()))
            await conn.commit()
            logging.info(f"✅ Пользователь {user_id} добавлен/обновлён")
    except Exception as e:
        logging.error(f"❌ Ошибка при добавлении пользователя: {e}")

async def get_user(user_id: int) -> dict:
    """Получает информацию о пользователе по user_id."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT user_id, first_name, last_name, username, is_admin FROM users WHERE user_id = ?", (user_id,))
            user = await cursor.fetchone()
            if user:
                return {
                    "user_id": user[0],
                    "first_name": user[1],
                    "last_name": user[2],
                    "username": user[3],
                    "is_admin": user[4]
                }
            return None
    except Exception as e:
        logging.error(f"❌ Ошибка при получении пользователя: {e}")
        return None

# Блок 3: Функции для работы со спотами
async def get_spots() -> list:
    """Получает список всех спотов."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT id, name, latitude, longitude FROM spots")
            spots = [{"id": row[0], "name": row[1], "lat": row[2], "lon": row[3]} for row in await cursor.fetchall()]
            logging.info(f"🔍 Найдено {len(spots)} спотов в базе.")
            return spots
    except Exception as e:
        logging.error(f"❌ Ошибка при получении списка спотов: {e}")
        return []

async def add_spot(name: str, lat: float, lon: float) -> int:
    """Добавляет новый спот в БД и возвращает его ID."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("INSERT INTO spots (name, latitude, longitude) VALUES (?, ?, ?)", (name, lat, lon))
            await conn.commit()
            spot_id = cursor.lastrowid
            logging.info(f"✅ Новый спот добавлен: ID={spot_id}, Name={name}, Lat={lat}, Lon={lon}")
            return spot_id
    except Exception as e:
        logging.error(f"❌ Ошибка при добавлении спота: {e}")
        return None

async def get_spot_by_id(spot_id: int) -> dict:
    """Получает информацию о споте по его ID."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT id, name, latitude, longitude FROM spots WHERE id = ?", (spot_id,))
            spot = await cursor.fetchone()
            if spot:
                return {"id": spot[0], "name": spot[1], "lat": spot[2], "lon": spot[3]}
            return None
    except Exception as e:
        logging.error(f"❌ Ошибка при получении спота: {e}")
        return None

async def update_spot_name(spot_id: int, new_name: str):
    """Обновляет название спота."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("UPDATE spots SET name = ? WHERE id = ?", (new_name, spot_id))
            await conn.commit()
            logging.info(f"✅ Название спота ID={spot_id} обновлено на '{new_name}'")
    except Exception as e:
        logging.error(f"❌ Ошибка при обновлении названия спота: {e}")

async def update_spot_location(spot_id: int, new_lat: float, new_lon: float):
    """Обновляет геопозицию спота."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("UPDATE spots SET latitude = ?, longitude = ? WHERE id = ?", (new_lat, new_lon, spot_id))
            await conn.commit()
            logging.info(f"✅ Геопозиция спота ID={spot_id} обновлена: Lat={new_lat}, Lon={new_lon}")
    except Exception as e:
        logging.error(f"❌ Ошибка при обновлении геопозиции спота: {e}")

async def delete_spot(spot_id: int):
    """Удаляет спот и связанные с ним чек-ины."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("DELETE FROM checkins WHERE spot_id = ?", (spot_id,))
            await cursor.execute("DELETE FROM spots WHERE id = ?", (spot_id,))
            await conn.commit()
            logging.info(f"✅ Спот ID={spot_id} удалён вместе с чек-инами")
    except Exception as e:
        logging.error(f"❌ Ошибка при удалении спота: {e}")

# Блок 4: Функции для работы с чек-инами
async def checkin_user(user_id: int, spot_id: int, checkin_type: int, bot=None, duration_hours: float = None, arrival_time: str = None):
    """Добавляет запись о чекине пользователя, разчекивает с других спотов и отправляет уведомления."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            # Проверяем, есть ли активный чек-ин
            await cursor.execute("SELECT id, spot_id FROM checkins WHERE user_id = ? AND active = 1", (user_id,))
            active_checkin = await cursor.fetchone()
            if active_checkin:
                # Разчекиваем пользователя с предыдущего спота
                await cursor.execute("UPDATE checkins SET active = 0 WHERE id = ?", (active_checkin[0],))
                logging.info(f"✅ Пользователь {user_id} разчекинен с предыдущего спота ID={active_checkin[1]}")

            # Вычисляем время окончания для автоматического разчекина
            timestamp = datetime.utcnow()
            end_time = None
            if checkin_type == 1 and duration_hours:
                end_time = (timestamp + timedelta(hours=duration_hours)).isoformat()
            elif checkin_type == 2 and arrival_time:
                arrival_dt = datetime.fromisoformat(arrival_time.replace("Z", "+00:00"))
                end_time = arrival_dt.isoformat()  # Пока не задаём длительность, ждём подтверждения

            # Добавляем новый чек-ин
            await cursor.execute("""
                INSERT INTO checkins (user_id, spot_id, timestamp, active, checkin_type, duration_hours, arrival_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, spot_id, timestamp.isoformat(), 1, checkin_type, duration_hours, arrival_time, end_time))
            await conn.commit()
            logging.info(f"✅ Чекин пользователя {user_id} на споте {spot_id} (type={checkin_type}, end_time={end_time})")

            # Отправляем уведомления пользователям, у которых спот в избранном
            if bot and checkin_type == 1:  # Уведомляем только при фактическом чек-ине (не планировании)
                await cursor.execute("""
                    SELECT user_id FROM favorite_spots WHERE spot_id = ? AND user_id != ?
                """, (spot_id, user_id))
                users_to_notify = await cursor.fetchall()
                spot = await get_spot_by_id(spot_id)
                user = await get_user(user_id)
                if spot and user:
                    for row in users_to_notify:
                        notify_user_id = row[0]
                        try:
                            await bot.send_message(
                                chat_id=notify_user_id,
                                text=f"🏄‍♂️ {user['first_name']} зачекинился на споте '{spot['name']}'!"
                            )
                            logging.info(f"✅ Уведомление отправлено пользователю {notify_user_id}")
                        except Exception as e:
                            logging.error(f"❌ Ошибка при отправке уведомления пользователю {notify_user_id}: {e}")
    except Exception as e:
        logging.error(f"❌ Ошибка при чекине пользователя: {e}")

async def get_active_checkin(user_id: int) -> dict:
    """Получает активный чек-ин пользователя."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("""
                SELECT id, spot_id, checkin_type, duration_hours, arrival_time, end_time
                FROM checkins
                WHERE user_id = ? AND active = 1
            """, (user_id,))
            checkin = await cursor.fetchone()
            if checkin:
                return {
                    "id": checkin[0],
                    "spot_id": checkin[1],
                    "checkin_type": checkin[2],
                    "duration_hours": checkin[3],
                    "arrival_time": checkin[4],
                    "end_time": checkin[5]
                }
            return None
    except Exception as e:
        logging.error(f"❌ Ошибка при получении активного чек-ина: {e}")
        return None

async def get_checkins_for_user(user_id: int) -> list:
    """Получает все чек-ины пользователя (активные и завершённые)."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("""
                SELECT id, spot_id, checkin_type, duration_hours, timestamp, active
                FROM checkins
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, (user_id,))
            checkins = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "spot_id": row[1],
                    "checkin_type": row[2],
                    "duration_hours": row[3],
                    "timestamp": row[4],
                    "active": row[5]
                }
                for row in checkins
            ]
    except Exception as e:
        logging.error(f"❌ Ошибка при получении чек-инов пользователя {user_id}: {e}")
        return []

async def checkout_user(checkin_id: int):
    """Разчекивает пользователя."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("UPDATE checkins SET active = 0 WHERE id = ?", (checkin_id,))
            await conn.commit()
            logging.info(f"✅ Пользователь разчекинен (checkin_id={checkin_id})")
    except Exception as e:
        logging.error(f"❌ Ошибка при разчекине: {e}")

async def update_checkin_to_arrived(checkin_id: int, duration_hours: float):
    """Обновляет чек-ин типа 2 (планирует приехать) в тип 1 (уже на месте)."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            timestamp = datetime.utcnow()
            end_time = (timestamp + timedelta(hours=duration_hours)).isoformat()
            await cursor.execute("""
                UPDATE checkins
                SET checkin_type = 1, duration_hours = ?, arrival_time = NULL, end_time = ?
                WHERE id = ?
            """, (duration_hours, end_time, checkin_id))
            await conn.commit()
            logging.info(f"✅ Чек-ин ID={checkin_id} обновлён: пользователь подтвердил прибытие")
    except Exception as e:
        logging.error(f"❌ Ошибка при обновлении чек-ина: {e}")

async def get_checkins_for_spot(spot_id: int) -> tuple[int, list[dict], list[dict]]:
    """Получает количество людей на месте и информацию о тех, кто планирует приехать."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            # Люди на месте (checkin_type=1, active=1)
            await cursor.execute("""
                SELECT u.first_name, u.username 
                FROM checkins c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.spot_id = ? AND c.checkin_type = 1 AND c.active = 1
            """, (spot_id,))
            on_spot_users = [{"first_name": row[0], "username": row[1]} for row in await cursor.fetchall()]
            on_spot_count = len(on_spot_users)

            # Люди, планирующие приехать (checkin_type=2, active=1)
            await cursor.execute("""
                SELECT u.first_name, u.username, c.arrival_time 
                FROM checkins c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.spot_id = ? AND c.checkin_type = 2 AND c.active = 1
            """, (spot_id,))
            arriving_users = [
                {"first_name": row[0], "username": row[1], "arrival_time": datetime.fromisoformat(row[2].replace("Z", "+00:00")).strftime("%H:%M")}
                for row in await cursor.fetchall()
            ]
            return on_spot_count, on_spot_users, arriving_users
    except Exception as e:
        logging.error(f"❌ Ошибка при получении чек-инов для спота {spot_id}: {e}")
        return 0, [], []

# Блок 5: Функции для работы с избранными спотами
async def add_favorite_spot(user_id: int, spot_id: int):
    """Добавляет спот в избранное пользователя."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("INSERT INTO favorite_spots (user_id, spot_id) VALUES (?, ?)", (user_id, spot_id))
            await conn.commit()
            logging.info(f"✅ Пользователь {user_id} добавил спот ID {spot_id} в избранное")
    except Exception as e:
        logging.error(f"❌ Ошибка при добавлении спота в избранное: {e}")

async def remove_favorite_spot(user_id: int, spot_id: int):
    """Удаляет спот из избранного пользователя."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("DELETE FROM favorite_spots WHERE user_id = ? AND spot_id = ?", (user_id, spot_id))
            await conn.commit()
            logging.info(f"✅ Пользователь {user_id} удалил спот ID {spot_id} из избранного")
    except Exception as e:
        logging.error(f"❌ Ошибка при удалении спота из избранного: {e}")

async def get_favorite_spots(user_id: int) -> list:
    """Получает список избранных спотов пользователя."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.cursor()
            await cursor.execute("SELECT spot_id FROM favorite_spots WHERE user_id = ?", (user_id,))
            spots = await cursor.fetchall()
            return [{"spot_id": row[0]} for row in spots]
    except Exception as e:
        logging.error(f"❌ Ошибка при получении избранных спотов: {e}")
        return []

# Инициализация базы данных (вызывается при старте бота)
# Вызов перенесён в bot.py, так как это асинхронная функция