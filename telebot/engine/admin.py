from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.data_manager import connect_to_base, is_admin
#expenses, balance, participants, admins, settlement_logs

async def bot_start(update: Update, context: CallbackContext):
    await update.message.reply_text("Hello! Welcome to ExpenSplit, a Bot for tracking expenses amongst a group of people!")

async def add_admin(update: Update, context: CallbackContext):
    user = update.message.from_user.username
    group_id = update.message.chat_id

    if not is_admin(group_id, user):
        await update.message.reply_text(f"{user} is not authorised to perform this action. Get an admin to authorise you first.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /add_admin <username>")
        return
    
    new_admin = context.args[0]
    
    if is_admin(group_id, new_admin):
        await update.message.reply_text(f"{new_admin} is already an admin.")
        return
    
    """Insert a new admin into the admins table if not already an admin."""
    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Insert new admin if not found
        cursor.execute("""
        INSERT INTO admins (group_id, username)
        VALUES (%s, %s)
        ON CONFLICT(group_id, username) DO NOTHING;  -- Avoid duplicates
        """, (group_id, new_admin))

        # Commit changes
        connection.commit()
        cursor.close()

    except Exception as e:
        print(f"Error adding participant: {e}")
        return "An error occurred while adding the participant."
    finally:
        if connection:
            connection.close()

    await update.message.reply_text(f"{new_admin} has been added as an admin by {user}.")
    

async def remove_admin(update: Update, context: CallbackContext):
    user = update.message.from_user.username
    group_id = update.message.chat_id

    if not is_admin(group_id, user):
        await update.message.reply_text(f"{user} is not authorised to perform this action. Get an admin to authorise you first.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /remove_admin <username>")
        return

    del_admin = context.args[0]

    if del_admin == "RyanDaCow":
        remove_power(group_id, user)
        await update.message.reply_text(f"{user} has been removed as admin.\nHaha nice try.")
        return

    if is_admin(group_id, del_admin):
        await update.message.reply_text(f"{del_admin} is already an admin.")
        return
    
    """Remove an admin from the admins table if they are an admin."""
    remove_power(group_id, del_admin)

    await update.message.reply_text(f"{del_admin} has been removed as admin by {user}.")

async def show_admins(update: Update, context: CallbackContext):
    """Show the list of admins in the group."""
    # Get the group_id from the chat_id
    group_id = update.message.chat_id

    try:
        # Connect to the database
        connection = connect_to_base()
        cursor = connection.cursor()

        # Retrieve the list of admins for the group
        cursor.execute("""
        SELECT username FROM admins WHERE group_id = %s;
        """, (group_id,))
        
        # Fetch all the results
        admins = cursor.fetchall()
        
        # Create a string of all admins
        admin_list = "\n".join([admin[0] for admin in admins])  # Extracting the username from the tuple
        
        # Send the list of admins
        await update.message.reply_text(f"Admins in the group:\n{admin_list}")

    except Exception as e:
        await update.message.reply_text(f"Error retrieving admins: {e}")
    
    finally:
        if connection:
            connection.close()

def remove_power(group_id, username):
    """Removes an admin into the admins table if they are a admin."""
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

    except Exception as e:
        print(f"Error removing admin: {e}")
        return "An error occurred while removing the admin."
    finally:
        if connection:
            connection.close()