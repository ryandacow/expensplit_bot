from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
import psycopg2
from psycopg2 import sql
import os
from telebot.credentials import SUPABASE_API_KEY, SUPABASE_DB_HOST, SUPABASE_DB_NAME, SUPABASE_DB_PASSWORD, SUPABASE_DB_USER, SUPABASE_URL

#General Connection to SupabaseDB
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
    
    

#Creation of database tables for a new group
def setup_database():
    """Set up the database tables."""
    connection = connect_to_base()

    try:
        cursor = connection.cursor()

        # Create groups table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id BIGINT PRIMARY KEY,
            username TEXT
        );
        """)

        # Create expenses table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(group_id),               -- Group the expense belongs to
            purpose TEXT,                                              -- Description of the expense
            payer TEXT,                                                -- Username of the payer
            amount NUMERIC,                                            -- Total amount of the expense
            currency TEXT,                                             -- Currency of the expense
            category_name TEXT DEFAULT NULL REFERENCES categories(category_name),    -- Reference to the category
            created_at TIMESTAMP DEFAULT NOW()                                       -- Timestamp when expense was created
        );
        """)

        # Create expense_beneficiaries table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS expense_beneficiaries (
            id SERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(group_id),                   -- Group the beneficiary belongs to
            expense_id INTEGER REFERENCES expenses(id) ON DELETE CASCADE,  -- Link to the expense
            username TEXT,                                                 -- User ID of the beneficiary
            split_amount NUMERIC                                           -- Amount each beneficiary owes
        );
        """)

        # Create balances table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            id SERIAL PRIMARY KEY,
            group_id BIGINT REFERENCES groups(group_id),  -- Group the balance belongs to
            username TEXT,                               -- Username of member
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
            username TEXT,    -- Username of the user (admin)
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

        # Create categories table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            group_id BIGINT,                            -- ID of the group
            category_name TEXT,                         -- Name of the category
            UNIQUE(group_id, category_name),            -- Ensure unique categories per group
            PRIMARY KEY (group_id, category_name)       -- Composite primary key
        );
        """)

        # Commit the changes
        connection.commit()
        print("Database setup completed successfully.")

    except psycopg2.Error as e:
        print(f"Error setting up database: {e}")

    finally:
        # Clean up resources
        if cursor:
            cursor.close()
        if connection:
            connection.close()
