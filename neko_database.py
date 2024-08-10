import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger('discord')


def create_connection(db_file):
    """Create a database connection to the SQLite database specified by db_file."""
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to database: {e}")
    return conn


def create_tables(conn):
    """Create necessary tables if they don't exist."""
    try:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS giveaways (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            end_time TEXT NOT NULL,
            winners INTEGER NOT NULL,
            image TEXT
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            giveaway_id TEXT,
            user_id INTEGER,
            FOREIGN KEY (giveaway_id) REFERENCES giveaways (id),
            PRIMARY KEY (giveaway_id, user_id)
        )
        ''')
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error creating tables: {e}")


def add_giveaway(conn, giveaway_id, title, channel_id, end_time, winners, image=None):
    """Add a new giveaway to the database."""
    try:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO giveaways (id, title, channel_id, end_time, winners, image)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (giveaway_id, title, channel_id, end_time.isoformat(), winners, image))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error adding giveaway: {e}")


def get_giveaway(conn, giveaway_id):
    """Retrieve a giveaway from the database."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM giveaways WHERE id = ?", (giveaway_id,))
        return cursor.fetchone()
    except sqlite3.Error as e:
        logger.error(f"Error getting giveaway: {e}")
        return None


def update_giveaway(conn, giveaway_id, title=None, channel_id=None, end_time=None, winners=None, image=None):
    """Update an existing giveaway in the database."""
    try:
        cursor = conn.cursor()
        updates = []
        values = []
        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if channel_id is not None:
            updates.append("channel_id = ?")
            values.append(channel_id)
        if end_time is not None:
            updates.append("end_time = ?")
            values.append(end_time.isoformat())
        if winners is not None:
            updates.append("winners = ?")
            values.append(winners)
        if image is not None:
            updates.append("image = ?")
            values.append(image)

        if updates:
            query = f"UPDATE giveaways SET {', '.join(updates)} WHERE id = ?"
            values.append(giveaway_id)
            cursor.execute(query, tuple(values))
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error updating giveaway: {e}")


def delete_giveaway(conn, giveaway_id):
    """Delete a giveaway from the database."""
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM giveaways WHERE id = ?", (giveaway_id,))
        cursor.execute("DELETE FROM participants WHERE giveaway_id = ?", (giveaway_id,))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error deleting giveaway: {e}")


def add_participant(conn, giveaway_id, user_id):
    """Add a participant to a giveaway."""
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO participants (giveaway_id, user_id) VALUES (?, ?)",
                       (giveaway_id, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error adding participant: {e}")


def remove_participant(conn, giveaway_id, user_id):
    """Remove a participant from a giveaway."""
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM participants WHERE giveaway_id = ? AND user_id = ?", (giveaway_id, user_id))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error removing participant: {e}")


def get_participants(conn, giveaway_id):
    """Get all participants for a giveaway."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM participants WHERE giveaway_id = ?", (giveaway_id,))
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Error getting participants: {e}")
        return []


def get_active_giveaways(conn):
    """Get all active giveaways (end time in the future)."""
    try:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute("SELECT * FROM giveaways WHERE end_time > ?", (now,))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting active giveaways: {e}")
        return []


def get_expired_giveaways(conn):
    """Get all expired giveaways (end time in the past)."""
    try:
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()
        cursor.execute("SELECT * FROM giveaways WHERE end_time <= ?", (now,))
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Error getting expired giveaways: {e}")
        return []


def close_connection(conn):
    """Close the database connection."""
    if conn:
        conn.close()