from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.data_manager import connect_to_base, is_admin
#expenses, balance, participants, admins, settlement_logs

SETTLE_CONFIRMATION = range(1)

async def settle_all_start(update: Update, context: CallbackContext):
    user = update.message.from_user.username
    group_id = update.message.chat_id

    if not is_admin(group_id, user):
        await update.message.reply_text(f"{user} is not authorised to perform this action. Get an admin to authorise you first.")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Are you sure you want to reset all balances to zero? Reply with 'yes' or 'no'."
    )

    return SETTLE_CONFIRMATION

async def settle_all_confirm(update: Update, context: CallbackContext):
    group_id = update.message.chat_id

    if update.message.text.lower() == "yes":
        try:
            # Connect to the database
            connection = connect_to_base()
            cursor = connection.cursor()

            # Update the balances for all participants in the group to 0
            cursor.execute("""
            UPDATE balances
            SET balance = 0
            WHERE group_id = %s;
            """, (group_id,))

            # Commit the changes
            connection.commit()
            cursor.close()
            
            await update.message.reply_text("All balances have been settled to zero.")
        
        except Exception as e:
            await update.message.reply_text(f"Error resetting balances: {e}")
        finally:
            if connection:
                connection.close()

    else:
        await update.message.reply_text("The action to reset all balances has been cancelled.")

    return ConversationHandler.END

async def settle_all_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("The action to reset all balances has been cancelled.")
    return ConversationHandler.END