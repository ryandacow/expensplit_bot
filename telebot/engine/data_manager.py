from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
import psycopg2
from psycopg2 import sql
import os
from telebot.engine.database import connect_to_base

def is_member(group_id, username):
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Check if the user is already in the participants table
        cursor.execute("""
        SELECT 1 FROM participants WHERE group_id = %s AND username = %s;
        """, (group_id, username))

        # If the participant is already in the table
        result = cursor.fetchone()
        cursor.close()
        return result is not None
    
    except psycopg2.Error as e:
        print(f"Error checking participant status: {e}")
        return False
    finally:
        if connection:
            connection.close()

def is_admin(group_id, username):
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Check if the user is in the admin table
        cursor.execute("""
        SELECT 1 FROM admins WHERE group_id = %s AND username = %s;
        """, (group_id, username))

        # If the participant is already in the table
        result = cursor.fetchone()
        cursor.close()
        
        return result is not None
    
    except psycopg2.Error as e:
        print(f"Error adding participant: {e}")
        return "An error occurred while adding the participant."
    finally:
        if connection:
            connection.close()

def add_participant(group_id, username):
    """Insert a new participant into the participants table if not already a member."""
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Insert new participant if not found
        cursor.execute("""
        INSERT INTO participants (group_id, username)
        VALUES (%s, %s)
        ON CONFLICT(group_id, username) DO NOTHING;  -- Avoid duplicates
        """, (group_id, username))

        # Insert initial balance for the new participant
        cursor.execute("""
        INSERT INTO balances (group_id, user_id, balance)
        VALUES (%s, %s, %s)
        ON CONFLICT (group_id, user_id) DO NOTHING;  -- Avoid duplicates
        """, (group_id, username, 0.00))

        # Commit changes
        connection.commit()
        cursor.close()

    except Exception as e:
        print(f"Error adding participant: {e}")
        return "An error occurred while adding the participant."
    finally:
        if connection:
            connection.close()

def remove_participant(group_id, username):
    """Removes a new participant into the participants table if they are a member."""
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Remove participant if found
        cursor.execute("""
            DELETE FROM participants 
            WHERE group_id = %s AND username = %s;
        """, (group_id, username))

        # Commit changes
        connection.commit()
        cursor.close()

    except psycopg2.Error as e:
        print(f"Error adding participant: {e}")
        return "An error occurred while adding the participant."
    finally:
        if connection:
            connection.close()


#expenses = [] #track expenses overall
#balance = {} #track balances of individuals
#participants = set() #track participants
#settlement_logs = [] #tracks when balances are settled
#admins = ["RyanDaCow"]