from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler, CallbackQueryHandler, Updater
from telebot.engine.data_manager import connect_to_base, is_member
import asyncio, threading
#insert_expense, balance, participants, admins, settlement_logs

PURPOSE, PAYER, AMOUNT, BENEFICIARIES, SPLIT = range(5)

async def add_expense(update: Update, context: CallbackContext):
    bot_message = await update.message.reply_text("What was the expense for?")
    await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    return PURPOSE

async def add_purpose(update: Update, context: CallbackContext):
    context.user_data["purpose"] = update.message.text
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)
    
    bot_message = await update.message.reply_text("Who paid?")
    await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    return PAYER

async def add_payer(update: Update, context: CallbackContext):
    payer = update.message.text.strip()
    group_id = update.message.chat_id

    if not is_member(group_id, payer):
        await update.message.reply_text(f"{payer} is not a member in the group.\nPlease try again or use /cancel to end command before adding them in with /add_member")
        return PAYER
    
    context.user_data["payer"] = payer
    await update.message.reply_text("How much was the expense (in amount)?")
    return AMOUNT

async def add_amount(update:Update, context: CallbackContext):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            await update.message.reply_text("Amount must be greater than 0. Please input a valid amount.")
            return AMOUNT
    
        context.user_data["amount"] = amount
        await update.message.reply_text("Please input beneficiaries (comma-separated). Type all to include all members.")
        return BENEFICIARIES
    
    except ValueError:
        await update.message.reply_text("Invalid amount. Please input a valid amount.")
        return AMOUNT
    
async def add_beneficiaries(update: Update, context: CallbackContext):
    beneficiaries_text = update.message.text.strip()
    group_id = update.message.chat_id
    connection = connect_to_base()
    cursor = connection.cursor()

    if beneficiaries_text.lower() == "all":
        # Get all participants in the group
        cursor.execute("""
        SELECT username FROM participants WHERE group_id = %s;
        """, (group_id,))
        beneficiaries = [row[0] for row in cursor.fetchall()]
        await update.message.reply_text("Amount will be split amongst all beneficiaries, including the payer.")

    else:
        # Validate beneficiaries
        beneficiaries = [b.strip() for b in beneficiaries_text.split(",")]
        cursor.execute("""
        SELECT username FROM participants WHERE group_id = %s;
        """, (group_id,))
        valid_users = {row[0] for row in cursor.fetchall()}
        invalid_beneficiaries = [b for b in beneficiaries if b not in valid_users]

        if invalid_beneficiaries:
                await update.message.reply_text(f"Invalid beneficiaries: {', '.join(invalid_beneficiaries)}")
                return BENEFICIARIES
        
    context.user_data["beneficiaries"] = beneficiaries

    #If only one beneficiary added, amount is simply allocated to them and skips the need to add_split.
    if len(context.user_data["beneficiaries"]) == 1:
        context.user_data["split_amounts"] = [context.user_data["amount"]]
        return await process_expense(update, context)

    await update.message.reply_text(
        f"Beneficiaries: {', '.join(beneficiaries)}\n\n"
        "Please input the amounts each beneficiary will receive in the SAME order as shown.\n\n"
        "Type 'equal' to distribute amounts equally."
    )
    return SPLIT

async def add_split(update: Update, context: CallbackContext):    
    #If amount is to be split equally.
    if context.args[0].lower() == "equal":
        split_amount = round(context.user_data["amount"] / context.user_data["beneficiaries"], 2)
        context.user_data["split_amounts"] = [split_amount] * len(context.user_data["beneficiaries"])
        return await process_expense(update, context)
    
    split_text = update.message.text.strip()
    split_amounts = split_text.split(",")
    
    try:
        split_amounts = [float(amount.strip()) for amount in split_amounts]

        if len(split_amounts) != len(context.user_data["beneficiaries"]):
            await update.message.reply_text("The number of amounts does not match the number of beneficiaries. Please input again.")
            return SPLIT

        if sum(split_amounts) != context.user_data["amount"]:
            await update.message.reply_text("Sum of amounts does not match amount paid. Please input again.")
            return SPLIT
        
        context.user_data["split_amounts"] = split_amounts
        return await process_expense(update, context)
    
    except ValueError:
        await update.message.reply_text("Invalid amount inputted. Please enter valid numbers to be split.")
        return SPLIT

async def process_expense(update: Update, context: CallbackContext):
    """Process and record the expense in the database."""
    group_id = update.message.chat_id
    purpose = context.user_data["purpose"]
    payer = context.user_data["payer"]
    amount_paid = context.user_data["amount"]
    beneficiaries = context.user_data["beneficiaries"] #list
    split_amounts = context.user_data["split_amounts"] #list

    connection = connect_to_base()
    cursor = connection.cursor()

    try:
        # Insert expense into the 'expenses' table
        cursor.execute("""
        INSERT INTO expenses (group_id, purpose, payer, amount, currency)
        VALUES (%s, %s, %s, %s, (SELECT base_currency FROM currency WHERE group_id = %s))
        RETURNING id, currency;
        """, (group_id, purpose, payer, amount_paid, group_id))

        expense_data = cursor.fetchone()
        expense_id = expense_data[0]
        currency = expense_data[1]

        # Insert beneficiaries and update balances
        for beneficiary, split_amount in zip(beneficiaries, split_amounts):
            cursor.execute("""
            INSERT INTO expense_beneficiaries (expense_id, group_id, username, split_amount)
            VALUES (%s, %s, %s, %s);
            """, (expense_id, group_id, beneficiary, split_amount))

            # Deduct from payer
            cursor.execute("""
            UPDATE balances
            SET balance = balance - %s
            WHERE group_id = %s AND username = %s;
            """, (split_amount, group_id, payer))

            # Add to beneficiary
            cursor.execute("""
            UPDATE balances
            SET balance = balance + %s
            WHERE group_id = %s AND username = %s;
            """, (split_amount, group_id, beneficiary))

        connection.commit()

        # Provide confirmation
        beneficiaries_splits_text = ", ".join(
            [f"{beneficiary} ({currency}{split_amount})" for beneficiary, split_amount in zip(beneficiaries, split_amounts)]
        )
        await update.message.reply_text(
            f"Expense recorded!\n"
            f"Purpose: {purpose}\n"
            f"Amount: {currency}{amount_paid:.2f}\n"
            f"Payer: {payer}\n"
            f"Beneficiaries and Splits: {beneficiaries_splits_text}\n"
        )

    except Exception as e:
        await update.message.reply_text(f"Error recording the expense: {e}")
    finally:
        cursor.close()
        connection.close()

    return ConversationHandler.END

async def add_expense_cancel(update: Update, context: CallbackContext):
    """Cancel the add_expense conversation."""
    await update.message.reply_text("Expense adding has been cancelled.")
    return ConversationHandler.END

async def undo(update: Update, context: CallbackContext):
    group_id = update.message.chat_id
    connection = connect_to_base()
    cursor = connection.cursor()

    try:
        # Fetch the last expense for the group
        cursor.execute("""
        SELECT e.id, e.purpose, e.payer, e.amount, e.currency, json_agg(json_build_object('beneficiary', eb.username, 'amount', eb.split_amount)) AS beneficiaries
        FROM expenses e
        JOIN expense_beneficiaries eb ON e.id = eb.expense_id
        WHERE e.group_id = %s
        GROUP BY e.id
        ORDER BY e.created_at DESC
        LIMIT 1;
        """, (group_id,))

        last_expense = cursor.fetchone()

        if not last_expense:
            await update.message.reply_text("No expense to undo. Use /add_expense to add an expense to be tracked!")
            return

        # Extract data from the last expense
        expense_id, purpose, payer, amount_paid, currency, beneficiaries_data = last_expense
        beneficiaries = [item['beneficiary'] for item in beneficiaries_data]
        split_amounts = [item['amount'] for item in beneficiaries_data]

        # Reverse balances
        for beneficiary, split_amount in zip(beneficiaries, split_amounts):
            # Deduct from payer's balance
            cursor.execute("""
            UPDATE balances
            SET balance = balance + %s
            WHERE group_id = %s AND username = %s;
            """, (amount_paid, group_id, payer))

            # Subtract the beneficiary's split amount
            cursor.execute("""
            UPDATE balances
            SET balance = balance - %s
            WHERE group_id = %s AND username = %s;
            """, (split_amount, group_id, beneficiary))

        # Delete the last expense and associated beneficiaries
        cursor.execute("""
        DELETE FROM expense_beneficiaries WHERE expense_id = %s;
        """, (expense_id,))

        cursor.execute("""
        DELETE FROM expenses WHERE id = %s;
        """, (expense_id,))

        # Commit changes
        connection.commit()

        # Generate confirmation message
        beneficiaries_splits_text = ", ".join(
            [f"{beneficiary} ({currency}{split_amount})" for beneficiary, split_amount in zip(beneficiaries, split_amounts)]
        )
        await update.message.reply_text(
            f"Expense recorded!\n"
            f"Purpose: {purpose}\n"
            f"Amount: {currency}{amount_paid:.2f}\n"
            f"Payer: {payer}\n"
            f"Beneficiaries and Splits: {beneficiaries_splits_text}\n"
        )
    except Exception as e:
        connection.rollback()
        await update.message.reply_text(f"Failed to undo the last expense. Error: {e}")

    finally:
        cursor.close()
        connection.close()