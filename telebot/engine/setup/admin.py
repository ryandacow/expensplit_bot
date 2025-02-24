from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler, CallbackQueryHandler
from telebot.engine.supabase.data_manager import connect_to_base, is_admin
import psycopg2
#expenses, balance, participants, admins, settlement_logs

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

DELETE_ALL_GIVE_PASSWORD, DELETE_ALL_CONFIRMATION = range(2)

async def delete_all_start(update: Update, context: CallbackContext):
    user = update.message.from_user.username
    group_id = update.message.chat_id

    if not is_admin(group_id, user):
        context.user_data["bot_message"] = await update.message.reply_text(
            f"{user} is not authorised to perform this action. Please input the password."
        )
        return DELETE_ALL_GIVE_PASSWORD
    
    context.user_data["bot_message"] =  await update.message.reply_text(
        "Are you sure you want to delete all data? This cannot be undone.\n"
        "Reply with 'yes' or 'no'."
    )

    return DELETE_ALL_CONFIRMATION

async def delete_all_password(update: Update, context: CallbackContext):
    password = update.message.text

    bot_message = context.user_data.get("bot_message")
    await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    if password == "123456":
        context.user_data["bot_message"] =  await update.message.reply_text(
            "Valid password.\n"
            "Are you sure you want to delete all data? This cannot be undone.\n"
            "Reply with 'yes' or 'no'."
        )
        return DELETE_ALL_CONFIRMATION
    
    else:
        await update.message.reply_text(
            "Invalid password. Ending data deletion."
        )
        return ConversationHandler.END

async def delete_all_confirm(update: Update, context: CallbackContext):
    group_id = update.message.chat_id
    confirmation = update.message.text

    bot_message = context.user_data.get("bot_message")
    await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    if confirmation == "yes":
        try:
            connection = connect_to_base()
            cursor = connection.cursor()

            # Begin a transaction
            cursor.execute("BEGIN;")
            
            # Delete from expense_beneficiaries (expenses related to the group)
            cursor.execute("""
            DELETE FROM expense_beneficiaries WHERE expense_id IN 
            (SELECT id FROM expenses WHERE group_id = %s);
            """, (group_id,))
            
            # Delete from expenses (expenses related to the group)
            cursor.execute("""
            DELETE FROM expenses WHERE group_id = %s;
            """, (group_id,))
            
            # Delete from participants (users related to the group)
            cursor.execute("""
            DELETE FROM participants WHERE group_id = %s;
            """, (group_id,))
            
            # Delete from balances (balance records related to the group)
            cursor.execute("""
            DELETE FROM balances WHERE group_id = %s;
            """, (group_id,))
            
            # Delete from admins (admins related to the group)
            cursor.execute("""
            DELETE FROM admins WHERE group_id = %s;
            """, (group_id,))
            
            # Optionally, delete from the currency table if you want to reset the base currency
            cursor.execute("""
            DELETE FROM currency WHERE group_id = %s;
            """, (group_id,))

            # Delete from categories table
            cursor.execute("""
            DELETE FROM categories WHERE group_id = %s;
            """, (group_id,))

            # Delete from groups (group_id and username)
            cursor.execute("""
            DELETE FROM groups WHERE group_id = %s;
            """, (group_id,))

            # Commit the transaction
            connection.commit()
            
            # Confirm the deletion to the user
            await update.effective_chat.send_message(f"All data for group {group_id} has been deleted and reset")
            
        except Exception as e:
            await update.message.reply_text(f"Error while deleting group data: {e}")
            connection.rollback()  # Rollback the transaction if an error occurs

        finally:
            cursor.close()
            connection.close()

    else:
        await update.message.reply_text("The action to delete all data has been cancelled.")

    return ConversationHandler.END

async def delete_all_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("The action to delete all data has been cancelled.")
    return ConversationHandler.END