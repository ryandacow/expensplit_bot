from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.supabase.data_manager import add_participant, remove_participant, is_member, is_admin, connect_to_base
import logging
#expenses, balance, participants, admins, settlement_logs

REMOVE_CONFIRMATION = range(1)
MEMBER_CONFIRMATION = range(1)

async def add_member(update: Update, context: CallbackContext):
    if update.callback_query:  # Inline button case
        query = update.callback_query
        await query.answer()
        context.user_data["bot_message"] = await query.message.reply_text("Please input the new member's name:")
    else:
        context.user_data["bot_message"] = await update.effective_chat.send_message("Please input the new member's name.")
    
    return MEMBER_CONFIRMATION

async def specify_member(update: Update, context: CallbackContext):
    print(f"Received input: {update.message.text}")
    logging.info(f"Received input: {update.message.text}")
    new_member = update.message.text
    user = update.message.from_user.username
    group_id = update.message.chat_id

    #Auto delete message
    bot_message = context.user_data.get("bot_message")
    await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    if is_member(group_id, new_member):
        await update.effective_chat.send_message(f"{new_member} is already in the group.")
        return ConversationHandler.END

    # Add the member from the database
    try:
        add_participant(group_id, new_member)
        await update.effective_chat.send_message(f"{new_member} has been added to the group by {user}.")

    except Exception as e:
        await update.effective_chat.send_message(f"An error occurred while removing {new_member}: {str(e)}")

    return ConversationHandler.END

async def add_member_cancel(update: Update, context: CallbackContext):
    await update.effective_chat.send_message("The action to add member has been cancelled.")
    return ConversationHandler.END

async def remove_member(update: Update, context: CallbackContext):
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /remove_member <username>")
        return
    
    old_member = context.args[0]
    group_id = update.message.chat_id
    user = update.message.from_user.username

    if not is_member(group_id, old_member):
        await update.message.reply_text(f"{old_member} is not a member in the group.")
        return

    # Remove the member from the database
    try:
        remove_participant(group_id, old_member)
        await update.message.reply_text(f"{old_member} has been removed from the group by {user}.")

    except Exception as e:
        await update.message.reply_text(f"An error occurred while removing {old_member}: {str(e)}")

async def remove_all_start(update: Update, context: CallbackContext):
    group_id = update.message.chat_id
    user = update.message.from_user.username

    if not is_admin(group_id, user):
        await update.message.reply_text(f"{user} is not authorised to perform this action. Get an admin to authorise you first.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Are you sure you want to remove all members? Reply with 'yes' or 'no'."
    )

    return REMOVE_CONFIRMATION

async def remove_all_confirm(update: Update, context: CallbackContext):
    if update.message.text.lower() == "yes":
        group_id = update.message.chat_id
        
        try:
            # Connect to the database
            connection = connect_to_base()
            cursor = connection.cursor()

            # Remove all participants from the participants table
            cursor.execute("""
            DELETE FROM participants WHERE group_id = %s;
            """, (group_id,))
            
            # Remove all balances from the balances table
            cursor.execute("""
            DELETE FROM balances WHERE group_id = %s;
            """, (group_id,))

            # Commit the changes
            connection.commit()

            # Notify the user
            await update.message.reply_text("All members have been removed from the group.")

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    
        finally:
            if connection:
                connection.close()

    else:
        await update.message.reply_text("The action to remove all members has been cancelled.")

    return ConversationHandler.END

async def remove_all_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("The action to remove all balances has been cancelled.")
    return ConversationHandler.END



async def show_members(update: Update, context: CallbackContext):
    """Show the list of members in the group."""
    # Get the group_id from the chat_id
    group_id = update.message.chat_id

    try:
        # Connect to the database
        connection = connect_to_base()
        cursor = connection.cursor()

        # Retrieve the list of participants for the group
        cursor.execute("""
        SELECT username FROM participants WHERE group_id = %s;
        """, (group_id,))
        
        # Fetch all the results
        members = cursor.fetchall()

        if not members:
            await update.message.reply_text("There are no members in the group yet.")
            return
        
        # Create a string of all members
        member_list = "\n".join([member[0] for member in members])  # Extracting the username from the tuple
        
        # Send the list of members
        await update.message.reply_text(f"Members in the group:\n{member_list}")

    except Exception as e:
        await update.message.reply_text(f"Error retrieving members: {e}")
    
    finally:
        if connection:
            connection.close()