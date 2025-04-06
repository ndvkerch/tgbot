import aiosqlite
import logging
import os
import pytz
from datetime import datetime, timedelta
from dateutil import parser
from aiogram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "data/database.db"

# Блок 1: Инициализация БД
async def init_db():
    """Инициализация структуры базы данных"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    is_admin BOOLEAN NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'UTC'
                );

                CREATE TABLE IF NOT EXISTS spots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    creator_id INTEGER NOT NULL
                );

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
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(spot_id) REFERENCES spots(id)
                );

                CREATE TABLE IF NOT EXISTS favorite_spots (
                    user_id INTEGER NOT NULL,
                    spot_id INTEGER NOT NULL,
                    PRIMARY KEY(user_id, spot_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(spot_id) REFERENCES spots(id)
                );
            ''')
            await conn.commit()
            logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {str(e)}")
        raise

# Блок 2: Работа с пользователями
async def add_or_update_user(
    user_id: int,
    first_name: str,
    last_name: str = None,
    username: str = None,
    is_admin: bool = False,
    timezone: str = "UTC"
) -> None:
    """Обновление данных пользователя с часовым поясом"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, first_name, last_name, username, is_admin, created_at, timezone)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                first_name,
                last_name,
                username,
                int(is_admin),
                datetime.utcnow().isoformat(),
                timezone
            ))
            await conn.commit()
            logger.info(f"Пользователь {user_id} обновлён")
    except Exception as e:
        logger.error(f"Ошибка обновления пользователя: {str(e)}")
        raise

async def get_user(user_id: int) -> dict:
    """Получение данных пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                SELECT user_id, first_name, last_name, username, is_admin, timezone
                FROM users WHERE user_id = ?
            ''', (user_id,))
            row = await cursor.fetchone()
            return {
                "user_id": row[0],
                "first_name": row[1],
                "last_name": row[2],
                "username": row[3],
                "is_admin": bool(row[4]),
                "timezone": row[5]
            } if row else None
    except Exception as e:
        logger.error(f"Ошибка получения пользователя: {str(e)}")
        return None

# Блок 3: Работа со спотами
async def get_spots() -> list:
    """Получение списка всех спотов"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                SELECT id, name, latitude, longitude FROM spots
            ''')
            return [{"id": row[0], "name": row[1], "lat": row[2], "lon": row[3]} 
                    for row in await cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения спотов: {str(e)}")
        return []

async def add_spot(name: str, lat: float, lon: float, creator_id: int) -> int:
    """Добавление нового спота"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                INSERT INTO spots (name, latitude, longitude, creator_id)
                VALUES (?, ?, ?, ?)
            ''', (name, lat, lon, creator_id))
            await conn.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка добавления спота: {str(e)}")
        raise

async def update_spot_name(spot_id: int, new_name: str) -> None:
    """Обновление названия спота"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                UPDATE spots SET name = ? WHERE id = ?
            ''', (new_name, spot_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"Ошибка обновления спота: {str(e)}")
        raise

async def delete_spot(spot_id: int) -> None:
    """Удаление спота и связанных данных"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('DELETE FROM checkins WHERE spot_id = ?', (spot_id,))
            await conn.execute('DELETE FROM spots WHERE id = ?', (spot_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"Ошибка удаления спота: {str(e)}")
        raise

async def get_spot_by_id(spot_id: int) -> dict:
    """Возвращает данные спота по ID"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                SELECT id, name, latitude, longitude 
                FROM spots 
                WHERE id = ?
            ''', (spot_id,))
            row = await cursor.fetchone()
            return {
                "id": row[0],
                "name": row[1],
                "lat": row[2],
                "lon": row[3]
            } if row else None
    except Exception as e:
        logger.error(f"Ошибка получения спота: {str(e)}")
        return None

async def update_spot_location(spot_id: int, new_lat: float, new_lon: float) -> None:
    """Обновляет координаты спота"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                UPDATE spots 
                SET latitude = ?, longitude = ? 
                WHERE id = ?
            ''', (new_lat, new_lon, spot_id))
            await conn.commit()
            logger.info(f"Координаты спота {spot_id} обновлены")
    except Exception as e:
        logger.error(f"Ошибка обновления координат: {str(e)}")
        raise

# Блок 4: Работа с чекинами
async def checkin_user(
    user_id: int,
    spot_id: int,
    checkin_type: int,
    duration_hours: float = None,
    arrival_time: str = None,
    bot: Bot = None
) -> None:
    """Создание чекина с учётом часового пояса"""
    try:
        await deactivate_all_checkins(user_id)
        user = await get_user(user_id)
        tz = pytz.timezone(user['timezone'])
        
        timestamp = datetime.now(tz).astimezone(pytz.utc)
        end_time = None

        if checkin_type == 1 and duration_hours:
            end_time = (timestamp + timedelta(hours=duration_hours)).isoformat()
        elif checkin_type == 2 and arrival_time:
            local_dt = parser.parse(arrival_time).replace(tzinfo=tz)
            end_time = local_dt.astimezone(pytz.utc).isoformat()

        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                INSERT INTO checkins (
                    user_id, spot_id, timestamp, 
                    active, checkin_type, duration_hours, 
                    arrival_time, end_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                spot_id,
                timestamp.isoformat(),
                1,
                checkin_type,
                duration_hours,
                arrival_time,
                end_time
            ))
            await conn.commit()

        # Уведомления внутри блока try
        if bot:
            await notify_favorite_users(
                spot_id=spot_id,
                checkin_user_id=user_id,
                bot=bot,
                checkin_type=checkin_type,
                arrival_time=arrival_time
            )

    except Exception as e:  # Блок except закрывает try
        logger.error(f"Ошибка создания чекина: {str(e)}")
        raise

async def get_active_checkin(user_id: int) -> dict:
    """Получение активного чекина"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                SELECT id, spot_id, checkin_type, duration_hours, arrival_time, end_time
                FROM checkins 
                WHERE user_id = ? AND active = 1
            ''', (user_id,))
            row = await cursor.fetchone()
            return {
                "id": row[0],
                "spot_id": row[1],
                "checkin_type": row[2],
                "duration_hours": row[3],
                "arrival_time": row[4],
                "end_time": row[5]
            } if row else None
    except Exception as e:
        logger.error(f"Ошибка получения чекина: {str(e)}")
        return None

async def checkout_user(checkin_id: int) -> None:
    """Завершение чекина"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                UPDATE checkins SET active = 0 WHERE id = ?
            ''', (checkin_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"Ошибка завершения чекина: {str(e)}")
        raise

async def update_checkin_to_arrived(checkin_id: int, duration_hours: float) -> None:
    """Обновляет чек-ин при подтверждении прибытия"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            timestamp = datetime.utcnow()
            end_time = (timestamp + timedelta(hours=duration_hours)).isoformat()
            await conn.execute('''
                UPDATE checkins SET 
                    checkin_type = 1,
                    duration_hours = ?,
                    arrival_time = NULL,
                    end_time = ?
                WHERE id = ?
            ''', (duration_hours, end_time, checkin_id))
            await conn.commit()
            logger.info(f"Чек-ин {checkin_id} обновлён")
    except Exception as e:
        logger.error(f"Ошибка обновления: {str(e)}")
        raise

async def get_checkins_for_user(user_id: int) -> list:
    """Получение всех чек-инов пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                SELECT id, spot_id, timestamp, checkin_type, duration_hours, arrival_time, end_time
                FROM checkins 
                WHERE user_id = ?
            ''', (user_id,))
            return [{
                "id": row[0],
                "spot_id": row[1],
                "timestamp": row[2],
                "checkin_type": row[3],
                "duration_hours": row[4],
                "arrival_time": row[5],
                "end_time": row[6]
            } for row in await cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения чек-инов пользователя: {str(e)}")
        return []

async def deactivate_all_checkins(user_id: int) -> None:
    """Деактивирует все активные чекины пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                UPDATE checkins 
                SET active = 0 
                WHERE user_id = ? AND active = 1
            ''', (user_id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"Ошибка деактивации чек-инов: {str(e)}")
        raise


# Блок 5: Избранные споты
async def add_favorite_spot(user_id: int, spot_id: int) -> None:
    """Добавление спота в избранное"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                INSERT OR IGNORE INTO favorite_spots (user_id, spot_id)
                VALUES (?, ?)
            ''', (user_id, spot_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"Ошибка добавления в избранное: {str(e)}")
        raise

async def get_favorite_spots(user_id: int) -> list:
    """Получение избранных спотов"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                SELECT spot_id FROM favorite_spots WHERE user_id = ?
            ''', (user_id,))
            return [row[0] for row in await cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка получения избранного: {str(e)}")
        return []

async def remove_favorite_spot(user_id: int, spot_id: int) -> None:
    """Удаление из избранного"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute('''
                DELETE FROM favorite_spots 
                WHERE user_id = ? AND spot_id = ?
            ''', (user_id, spot_id))
            await conn.commit()
    except Exception as e:
        logger.error(f"Ошибка удаления из избранного: {str(e)}")
        raise

async def notify_favorite_users(
    spot_id: int, 
    checkin_user_id: int, 
    bot: Bot,
    checkin_type: int,  # Добавляем тип чекина
    arrival_time: str = None  # Добавляем время прибытия
) -> None:
    """Отправляет уведомления в зависимости от типа чекина."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute('''
                SELECT user_id FROM favorite_spots WHERE spot_id = ?
            ''', (spot_id,))
            users = [row[0] for row in await cursor.fetchall()]

        checkin_user = await get_user(checkin_user_id)
        spot = await get_spot_by_id(spot_id)

        for user_id in users:
            if user_id == checkin_user_id:
                continue
            
            # Формируем текст уведомления
            if checkin_type == 1:
                text = f"🤙 Пользователь {checkin_user['first_name']} отметился на вашем избранном споте: {spot['name']}!"
            elif checkin_type == 2 and arrival_time:
                # Конвертируем время в локальный часовой пояс получателя
                user = await get_user(user_id)
                tz = pytz.timezone(user['timezone'])
                utc_time = datetime.fromisoformat(arrival_time)
                local_time = utc_time.astimezone(tz).strftime("%H:%M %d.%m.%Y")
                text = f"⏱ Пользователь {checkin_user['first_name']} планирует приехать на спот {spot['name']} в {local_time}!"
            else:
                continue

            try:
                await bot.send_message(chat_id=user_id, text=text)
                logger.info(f"Уведомление отправлено пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки: {e}")
    except Exception as e:
        logger.error(f"Ошибка в уведомлениях: {e}")

# Блок 6: Дополнительные функции
async def get_checkins_for_spot(spot_id: int) -> tuple:
    """Статистика по споту"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Активные чекины с именами пользователей
            cursor = await conn.execute('''
                SELECT u.first_name 
                FROM checkins c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.spot_id = ? 
                AND c.checkin_type = 1 
                AND c.active = 1
            ''', (spot_id,))
            active_users = [{"first_name": row[0]} for row in await cursor.fetchall()]

            # Планирующие прибытие
            cursor = await conn.execute('''
                SELECT u.first_name, c.arrival_time 
                FROM checkins c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.spot_id = ? 
                AND c.checkin_type = 2 
                AND c.active = 1
            ''', (spot_id,))
            arriving = [{"first_name": row[0], "arrival_time": row[1]} for row in await cursor.fetchall()]

            return len(active_users), active_users, arriving
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {str(e)}")
        return 0, [], []
    
# Инициализация базы данных (вызывается при старте бота)
# Вызов перенесён в bot.py, так как это асинхронная функция