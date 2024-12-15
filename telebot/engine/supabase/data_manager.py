from telegram import Update, InputFile
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
import psycopg2, os
import pandas as pd
from psycopg2 import sql
from telebot.engine.supabase.database import connect_to_base

#is_member, is_admin, is_expense, is_category, add_group, add_participant, remove_participant, export_expenses

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

        # If the participant is already an admin
        result = cursor.fetchone()
        cursor.close()
        
        return result is not None
    
    except psycopg2.Error as e:
        print(f"Error adding participant: {e}")
        return "An error occurred while adding the participant."
    finally:
        if connection:
            connection.close()

def add_group(group_id):
    #Insert group into groups table for tracking.
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        cursor.execute("""
        SELECT 1 FROM groups WHERE group_id = %s;
        """, (group_id,))

        result = cursor.fetchone()

        if result is not None:
            cursor.execute("""
            INSERT INTO groups (group_id)
            VALUES (%s)
            ON CONFLICT(group_id) DO NOTHING;  -- Avoid duplicates
            """, (group_id,))

        connection.commit()
        cursor.close()

    except Exception as e:
        print(f"Error adding group: {e}")
        return "An error occurred while adding the group."
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
        INSERT INTO balances (group_id, username, balance)
        VALUES (%s, %s, %s)
        ON CONFLICT (group_id, username) DO NOTHING;  -- Avoid duplicates
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

async def is_expense(group_id, expense):
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Check if the user is in the admin table
        cursor.execute("""
        SELECT 1 FROM expenses WHERE group_id = %s AND purpose = %s;
        """, (group_id, expense))

        # If the participant is already an admin
        result = cursor.fetchone()
        cursor.close()
        
        return result is not None
    
    except psycopg2.Error as e:
        print(f"Error checking expense: {e}")
        return "An error occurred while checking for expense."
    finally:
        if connection:
            connection.close()



async def is_category(group_id, category_name):
    try:
        # Establish database connection
        connection = connect_to_base()
        
        # Use a context manager for the cursor
        with connection.cursor() as cursor:
            # Query to check if category exists
            cursor.execute("""
            SELECT 1 FROM categories WHERE group_id = %s AND category_name ILIKE %s;
            """, (group_id, category_name.strip()))  # Ensure no extra spaces
            
            result = cursor.fetchone()
            return result is not None  # True if category exists, False otherwise

    except Exception as e:
        # Log the error for debugging purposes
        print(f"Error checking category: {e}")
        return False  # Default to False if an error occurs

    finally:
        # Ensure the connection is always closed
        if connection:
            connection.close()



async def export_expenses(update: Update, context: CallbackContext):
    group_id = update.message.chat_id
    if update.message.chat == "group":
        group_name = update.message.chat.title.strip(" ", "_") if update.message.chat.title else "exported"
    else:
        group_name = update.message.chat.username if update.message.chat.username else "exported"

    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        cursor.execute("""
        SELECT 
            e.id AS expense_id, 
            e.purpose,
            e.amount,
            e.currency,
            e.payer,
            eb.username,
            eb.split_amount
        FROM expenses e
        JOIN expense_beneficiaries eb ON e.id = eb.expense_id
        WHERE eb.group_id = %s;
        """, (group_id,))

        data = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]

        #Create a DataFrame
        df = pd.DataFrame(data, columns=columns)
        
        #Sequential numbers for expense_id
        df["expense_id"] = pd.factorize(df["expense_id"])[0] + 1

        #Reorder to have expense_id column first
        df = df[["expense_id"] + [col for col in columns if col != "expense_id"]]

        #Save as csv
        file_path = f"/tmp/{group_name}_expenses.csv"
        df.to_csv(file_path, index=False)

        #Return to user
        with open(file_path, "rb") as file:
            await update.message.reply_document(
                document=InputFile(file),
                filename=f"{group_name}_expenses.csv",
                caption="Here is the exported expense data for your group.",
                parse_mode="Markdown"
            )

        os.remove(file_path)

    except Exception as e:
        # Log and notify user of error
        print(f"Error exporting expenses: {e}")
        await update.message.reply_text("An error occurred while exporting expenses. Please try again.")

    finally:
        # Ensure the connection is always closed
        if connection:
            cursor.close()
            connection.close()


#expenses = [] #track expenses overall
#balance = {} #track balances of individuals
#participants = set() #track participants
#settlement_logs = [] #tracks when balances are settled
#admins = ["RyanDaCow"]