from flask import Flask, request
from threading import Thread
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, CallbackContext, ConversationHandler, filters, MessageHandler
from telebot.credentials import BOT_TOKEN
from telebot.engine.database import setup_database
import os
import requests
import asyncio

from telebot.engine.admin import (
    bot_start, 
    add_admin,
    remove_admin,
    show_admins,
)

from telebot.engine.settle import(
    settle_all_start, 
    settle_all_confirm, 
    settle_all_cancel, 
    SETTLE_CONFIRMATION,
)

from telebot.engine.members import(
    add_member, 
    remove_member, 
    show_members,
    remove_all_cancel,
    remove_all_start,
    remove_all_confirm,
    REMOVE_CONFIRMATION
)

from telebot.engine.show import(
    show_expenses, 
    show_balance,
)

from telebot.engine.add import(
    add_expense,
    add_purpose,
    add_payer,
    add_amount,
    add_beneficiaries,
    add_split,
    add_expense_cancel,
    PURPOSE,
    PAYER,
    AMOUNT,
    BENEFICIARIES,
    SPLIT,
    undo
)

from telebot.engine.currency import(
    set_currency,
    valid_currencies,
    show_currency,
    convert_currency
)

#Initialise flask and application with my bot token.
app = Flask(__name__)
application = Application.builder().token(BOT_TOKEN).build()

#Set up database for each unique group ID at the start of activation.
setup_database()


# Register commands
application.add_handler(CommandHandler("start", bot_start))

application.add_handler(CommandHandler("add_member", add_member))
application.add_handler(CommandHandler("remove_member", remove_member))
application.add_handler(CommandHandler("show_members", show_members))

application.add_handler(CommandHandler("undo", undo))

application.add_handler(CommandHandler("show_balance", show_balance))
application.add_handler(CommandHandler("show_expenses", show_expenses))

application.add_handler(CommandHandler("add_admin", add_admin))
application.add_handler(CommandHandler("remove_admin", remove_admin))
application.add_handler(CommandHandler("show_admins", show_admins))

application.add_handler(CommandHandler("show_currency", show_currency))
application.add_handler(CommandHandler("set_currency", set_currency))
application.add_handler(CommandHandler("valid_currencies", valid_currencies))
application.add_handler(CommandHandler("convert_currency", convert_currency))

#/settle_all command
settle_all_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("settle_all", settle_all_start)],
    states={
        SETTLE_CONFIRMATION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settle_all_confirm),  # Only plain text (not commands)
        ],
    },
    fallbacks=[CommandHandler("cancel", settle_all_cancel)],
) 

application.add_handler(settle_all_conv_handler)

#remove_all_members command
remove_all_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("remove_all_members", remove_all_start)],
    states={
        REMOVE_CONFIRMATION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, remove_all_confirm),  # Only plain text (not commands)
        ],
    },
    fallbacks=[CommandHandler("cancel", remove_all_cancel)],
)

application.add_handler(remove_all_conv_handler)

#add_expense command
expense_conv_handler = ConversationHandler(
entry_points=[CommandHandler('add_expense', add_expense)],
states={
    PURPOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_purpose)],
    PAYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_payer)],
    AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_amount)],
    BENEFICIARIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beneficiaries)],
    SPLIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_split)],
},
fallbacks=[CommandHandler('cancel', add_expense_cancel)],  # Optional: Implement cancel command
) 

application.add_handler(expense_conv_handler)



@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming updates from Telegram."""
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)  # This should be awaited
        return "OK", 200
    return "Bad Request", 400


def set_webhook():
    """Set the Telegram bot webhook."""
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # This will come from Render’s environment variable
    response = requests.post(
        f'https://api.telegram.org/bot{os.environ.get("BOT_TOKEN")}/setWebhook',
        json={"url": WEBHOOK_URL}
    )
    if response.status_code == 200:
        print("Webhook set successfully.")
    else:
        print(f"Failed to set webhook: {response.status_code} - {response.text}")


if __name__ == "__main__":
    set_webhook()
    # Directly run the Flask application without asyncio
    app.run(host="0.0.0.0", port=8443)