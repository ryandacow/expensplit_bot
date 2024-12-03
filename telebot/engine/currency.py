from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.data_manager import connect_to_base, is_member
import requests

API_URL = "https://v6.exchangerate-api.com/v6/df74fed3c85165b35fe0b792/latest/SGD"

#base_currency = {"currency": "SGD", "rate": 0.00}

async def show_currency(update: Update, context: CallbackContext):
    connection = connect_to_base()
    group_id = update.message.chat_id

    try:
        cursor = connection.cursor()

         # Query to get the base_currency for the group
        cursor.execute("""
        SELECT base_currency FROM currency WHERE group_id = %s;
        """, (group_id,))

        result = cursor.fetchone()

        if result:
            base_currency = result[0]
            await update.message.reply_text(f"Base Currency: {base_currency}")
        else:
            await update.message.reply_text("Base Currency: SGD. Use /set_currency to change to a different currency.")
    
    except Exception as e:
        print(f"Error checking currency: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
   


async def set_currency(update: Update, context: CallbackContext):
    if not context.args:
        await update.message.reply_text("Usage: /set_currency <currency code>")

    new_currency = context.args[0].upper()
    group_id = update.message.chat_id

    try:
        # Fetch rates from ExchangeRate-API
        response = requests.get(API_URL)
        response.raise_for_status()  # Raise error for bad responses (e.g., 404 or 500)
        data = response.json()
        
        # Check if the new currency is valid
        if new_currency in data['conversion_rates']:
            new_rate = data['conversion_rates'][new_currency]

            connection = connect_to_base()
            cursor = connection.cursor()

           # Update the currency table with the new base currency and rate
            cursor.execute("""
            INSERT INTO currency (group_id, base_currency, rate)
            VALUES (%s, %s, %s)
            ON CONFLICT(group_id) DO UPDATE
            SET base_currency = %s, rate = %s;
            """, (group_id, new_currency, new_rate, new_currency, new_rate))

            # Commit the changes
            connection.commit()

            # Send confirmation message
            await update.message.reply_text(
                f"Base currency has been set to {new_currency}. Current rate: 1 SGD = {new_rate} {new_currency}."
            )

             # Clean up resources
            cursor.close()
            connection.close()

        else:
            await update.message.reply_text(
                f"{new_currency} is not supported. Use /valid_currencies to see all supported currencies."
            )
    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"Failed to fetch currency rates: {e}")
    


async def valid_currencies(update: Update, context: CallbackContext):
    await update.message.reply_text(
        f"You can find the list of supported currencies here:\nhttps://www.exchangerate-api.com/docs/supported-currencies"
    )



async def convert_currency(update: Update, context: CallbackContext):
    group_id = update.message.chat_id  # Get the group ID from the chat

    try:
        # Connect to the database and fetch the current base_currency and rate
        connection = connect_to_base()
        cursor = connection.cursor()

        # Fetch the current base_currency and rate for the group
        cursor.execute("""
        SELECT base_currency, rate FROM currency WHERE group_id = %s;
        """, (group_id,))
        result = cursor.fetchone()

        if result is None:
            await update.message.reply_text("Currency settings for this group are not set. Use /set_currency to set a base currency.")
            return

        base_currency, rate = result

        if base_currency == "SGD":
            await update.message.reply_text(f"The base currency is already in SGD, no conversion needed.")
            return

        # If a specific user is mentioned, convert their balance
        if context.args:
            user = context.args[0].lower()

            if not is_member(group_id, user):
                await update.message.reply_text(f"{context.args[0]} is not a member in the group. Use /add_member to add them in.")
                return

            # Convert balance for this user
            cursor.execute("""
            SELECT balance FROM balances WHERE group_id = %s AND username = (SELECT username FROM participants WHERE group_id = %s AND username = %s);
            """, (group_id, group_id, user))
            balance = cursor.fetchone()

            if balance:
                updated_balance = balance[0] / rate
                cursor.execute("""
                UPDATE balances SET balance = %s WHERE group_id = %s AND username = (SELECT username FROM participants WHERE group_id = %s AND username = %s);
                """, (round(updated_balance, 2), group_id, group_id, user))

            await update.message.reply_text(f"{user}'s balance has been converted from {base_currency} to SGD.")

        else:
            # Convert balances for all users in the group
            cursor.execute("""
            SELECT username, balance FROM participants
            JOIN balances ON participants.user_id = balances.user_id
            WHERE participants.group_id = %s;
            """, (group_id,))
            participants_balances = cursor.fetchall()

            for username, balance in participants_balances:
                updated_balance = balance / rate
                cursor.execute("""
                UPDATE balances SET balance = %s WHERE group_id = %s AND username = (SELECT username FROM participants WHERE group_id = %s AND username = %s);
                """, (round(updated_balance, 2), group_id, group_id, username))

            await update.message.reply_text(f"All balances have been converted from {base_currency} to SGD.")

        # Update the currency table to set base_currency to SGD and rate to 1.0
        cursor.execute("""
        UPDATE currency SET base_currency = 'SGD', rate = 1.0 WHERE group_id = %s;
        """, (group_id,))

        # Commit the changes and close connection
        connection.commit()
        cursor.close()
        connection.close()

    except Exception as e:
        await update.message.reply_text(f"Error while converting currency: {e}")