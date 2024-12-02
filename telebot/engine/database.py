from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
import psycopg2
from psycopg2 import sql
import os
from supabase_py import create_client
from telebot.credentials import SUPABASE_API_KEY, SUPABASE_DB_HOST, SUPABASE_DB_NAME, SUPABASE_DB_PASSWORD, SUPABASE_DB_USER, SUPABASE_URL

# Assuming the connection details for Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)

def connect_to_base():
    try:
        connection = psycopg2.connect(
            dbname=SUPABASE_DB_NAME,    # Replace with your Supabase DB name
            user=SUPABASE_DB_USER,         # Replace with your Supabase username
            password=SUPABASE_DB_PASSWORD, # Replace with your Supabase password
            host=SUPABASE_DB_HOST,         # Replace with your Supabase host
            port=6543                 # Default PostgreSQL port
        )
        return connection
    except psycopg2.Error as e:
        print(f"Error connecting to the database: {e}")
        return None

def setup_database():
    """Set up the database tables."""
    connection = connect_to_base()

    try:
        cursor = connection.cursor()

        # Create groups table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id BIGINT PRIMARY KEY,
            group_name TEXT
        );
        """)

        # Create expenses table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(group_id),  -- Group the expense belongs to
            purpose TEXT,                                 -- Description of the expense
            payer_id BIGINT,                              -- ID of the payer
            amount NUMERIC,                               -- Total amount of the expense
            currency TEXT,                                -- Currency of the expense
            created_at TIMESTAMP DEFAULT NOW()            -- Timestamp when expense was created
        );
        """)

        # Create expense_beneficiaries table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expense_beneficiaries (
            id SERIAL PRIMARY KEY,
            expense_id INTEGER REFERENCES expenses(id) ON DELETE CASCADE,  -- Link to the expense
            beneficiary_id BIGINT,                                         -- User ID of the beneficiary
            split_amount NUMERIC                                           -- Amount each beneficiary owes
        );
        """)

        # Create balances table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            id SERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(group_id),  -- Group the balance belongs to
            username BIGINT,                               -- ID of the user
            balance NUMERIC DEFAULT 0,                   -- User's balance (negative means owed)
            UNIQUE(group_id, username)                    -- Ensure unique balance per user per group
        );
        """)

        # Create participants table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            id SERIAL PRIMARY KEY,
            group_id BIGINT,                               -- ID of the group
            username TEXT,                                 -- Participant's username
            UNIQUE(group_id, username)                     -- Ensure unique participants per group
        );
        """)

        # Create settlement_logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settlement_logs (
            id SERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(group_id),  -- Group the settlement belongs to
            user_id BIGINT,                               -- User ID of the person settling
            settled_at TIMESTAMP DEFAULT NOW(),           -- Timestamp of the settlement
            details TEXT                                  -- Details of the settlement
        );
        """)

        # Create admins table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(group_id),  -- Group the admin belongs to
            username BIGINT,    -- Username of the user (admin)
            UNIQUE (group_id, username)  -- Ensure unique admins per group
        );
        """)

        # Create currency table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS currency (
            group_id BIGINT PRIMARY KEY,        -- Link to the group
            base_currency TEXT DEFAULT 'SGD',   -- Default base currency is SGD
            rate NUMERIC DEFAULT 0.00           -- Default rate is 0.00
        );
        """)

        # Commit the changes
        connection.commit()
        print("Database setup completed successfully.")

        # Ensure RyanDaCow is added as an admin for each group
        cursor.execute("SELECT group_id FROM groups;")
        groups = cursor.fetchall()

        for group in groups:
            group_id = group[0]
            add_default_admin_for_group(group_id)  # Ensure admin is added for each group

    except psycopg2.Error as e:
        print(f"Error setting up database: {e}")

    finally:
        # Clean up resources
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def add_default_admin_for_group(group_id):
    """Ensure 'RyanDaCow' is added as an admin for the group."""
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Check if 'RyanDaCow' is already an admin
        cursor.execute("""
        SELECT 1 FROM admins WHERE group_id = %s AND username = %s;
        """, (group_id, "RyanDaCow"))

        # If 'RyanDaCow' is not an admin, insert them as an admin
        if cursor.fetchone() is None:
            cursor.execute("""
            INSERT INTO admins (group_id, username)
            VALUES (%s, %s)
            ON CONFLICT(group_id, username) DO NOTHING;  -- Avoid duplicates
            """, (group_id, "RyanDaCow"))

            # Commit changes
            connection.commit()
            print(f"RyanDaCow added as admin for group {group_id}")

        cursor.close()
    except psycopg2.Error as e:
        print(f"Error adding default admin: {e}")
    finally:
        if connection:
            connection.close()