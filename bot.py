from quart import Quart, request
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, CallbackContext, ConversationHandler, filters, MessageHandler
from telebot.credentials import BOT_TOKEN
from telebot.engine.database import setup_database
import os
import requests
import asyncio
import httpx, logging

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


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up database for each unique group ID at the start of activation
setup_database()
application = None

# Initialize Quart app
app = Quart(__name__)

# Initialize Telegram Bot Application
async def init_application():
    global application
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Please provide a valid bot token.")

    application = Application.builder().token(BOT_TOKEN).build()
    await application.initialize()

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

    logger.info("Telegram Bot Application initialized successfully.")

# Ensure the webhook is set correctly
async def set_webhook():
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL is not set. Please provide a valid webhook URL.")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f'https://api.telegram.org/bot{BOT_TOKEN}/setWebhook',
            json={"url": WEBHOOK_URL},
        )
        if response.status_code == 200:
            logger.info("Webhook set successfully.")
        else:
            logger.error(f"Failed to set webhook: {response.status_code} - {response.text}")

# Handle incoming webhook requests
@app.route('/webhook', methods=['POST'])
async def webhook():
    """Handle incoming updates from Telegram."""
    if application is None or not application.is_initialized:
        logger.error("Application is not initialized. Unable to process the update.")
        return "Service Unavailable", 503

    try:
        update = Update.de_json(await request.get_json(), application.bot)
        await application.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return "Internal Server Error", 500

# Asynchronous entry point for setting webhook and running the app
async def main():
    await init_application()
    await set_webhook()
    await app.run_task(host="0.0.0.0", port=8443)

if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical error during application startup: {e}")