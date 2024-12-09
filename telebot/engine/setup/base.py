from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler, CallbackQueryHandler
from telebot.engine.supabase.data_manager import connect_to_base, is_admin
import psycopg2
from telebot.engine.setup.members import MEMBER_CONFIRMATION

async def bot_start(update: Update, context: CallbackContext):
    print("Bot started.")

    group_id = update.message.chat_id
    connection = None

    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Begin transaction
        cursor.execute("BEGIN;")

        # Ensure the group exists in the 'groups' table
        cursor.execute("""
        INSERT INTO groups (group_id)
        VALUES (%s)
        ON CONFLICT(group_id) DO NOTHING;
        """, (group_id,))

        # Ensure 'RyanDaCow' is an admin
        cursor.execute("""
        INSERT INTO admins (group_id, username)
        VALUES (%s, %s)
        ON CONFLICT(group_id, username) DO NOTHING;
        """, (group_id, "RyanDaCow"))

        print(f"RyanDaCow ensured as admin for group {group_id}")

        # Ensure currency entry exists for the group
        cursor.execute("""
        INSERT INTO currency (group_id, base_currency, rate)
        VALUES (%s, 'SGD', 1.00)
        ON CONFLICT(group_id) DO NOTHING;
        """, (group_id,))

        # Commit all changes
        connection.commit()
        print("Database updates committed successfully.")

        keyboard = [
            [InlineKeyboardButton("Add Member", callback_data="add_member")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Hello! Welcome to ExpenSplit, a Bot for tracking expenses amongst a group of people!\n\n"
            "To begin, click the button below to add an individual in the tracker.\n\n"
            "Use /help to show a list of common commands.\n"
            "DISCLAIMERS: DO NOT USE /convert_currency until the end of the trip.\n"
            "Please give the bot up to one minute to respond as it takes time for the server to boot.\n\n"
            "Please enjoy using ExpenSplit! :D",
            reply_markup=reply_markup
        )

    except psycopg2.Error as e:
        if connection:
            connection.rollback()  # Rollback in case of error
        print(f"Error during bot initialization: {e}")
        await update.message.reply_text("An error occurred during initialization. Please try again.")
    finally:
        if connection:
            cursor.close()
            connection.close()


async def help(update: Update, context: CallbackContext): #convert to inline buttons eventually
    await update.message.reply_text(
        "Below are a list of common commands and how to use them!\n"
        "/start: Initialises the Bot. Activate once before utilising the bot\n\n"
        "/add_member <name>: Adds a member to be tracked\n"
        "/show_members: Shows all members being tracked\n\n"
        "/add_expense: Add an expense to be tracked\n"
        "/undo: Undoes the latest expense added\n"
        "/show_expenses: Shows expense log\n"
        "/show_balance: Shows balances of individual/all participant(s)\n"
        "/show_spending: Shows individual/group spending(s) \n"
        "/settle_all: Resets all balances after being settled\n\n"
        "/set_currency: Sets the currency expenses are recorded down in\n"
        "/convert_currency: Converts all expenses and balances to SGD\n"
        "/valid_currencies: Shows all currencies that can be set\n\n"
        "/cancel: Cancels ongoing command (add_expense, settle_all)"
    )
