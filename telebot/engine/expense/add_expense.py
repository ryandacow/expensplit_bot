from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler, CallbackQueryHandler, Updater
from telebot.engine.supabase.data_manager import connect_to_base, is_member
import asyncio, threading
#insert_expense, balance, participants, admins, settlement_logs

PURPOSE, PAYER, AMOUNT, BENEFICIARIES, SPLIT = range(5)

async def add_expense(update: Update, context: CallbackContext):
    """Initiate the add_expense process."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data["bot_message"] = await query.message.reply_text("What was the expense for?")
    else:
        context.user_data["bot_message"] = await update.message.reply_text("What was the expense for?")
    return PURPOSE


async def delete_messages(context: CallbackContext, *messages):
    """Helper function to delete messages safely."""
    for msg in messages:
        try:
            if msg:
                await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
        except telegram.error.BadRequest:
            pass


async def add_purpose(update: Update, context: CallbackContext):
    """Capture purpose and prompt for payer."""
    context.user_data["purpose"] = update.message.text
    await delete_messages(context, context.user_data.get("bot_message"), update.message)
    context.user_data["bot_message"] = await update.message.reply_text("Who paid?")
    return PAYER


async def add_payer(update: Update, context: CallbackContext):
    """Validate and capture the payer."""
    payer = update.message.text.strip()
    group_id = update.message.chat_id
    await delete_messages(context, context.user_data.get("bot_message"), update.message)

    if not is_member(group_id, payer):
        context.user_data["bot_message"] = await update.message.reply_text(
            f"{payer} is not a member of the group. Please add them using /add_member or try again."
        )
        return PAYER

    context.user_data["payer"] = payer
    context.user_data["bot_message"] = await update.message.reply_text("How much was the expense (in amount)?")
    return AMOUNT


async def add_amount(update: Update, context: CallbackContext):
    """Validate and capture the expense amount."""
    amount = update.message.text.strip()
    await delete_messages(context, context.user_data.get("bot_message"), update.message)

    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be greater than 0.")

        context.user_data["amount"] = amount
        context.user_data["bot_message"] = await update.message.reply_text(
            "Please input beneficiaries (comma-separated). Type 'all' to include all group members."
        )
        return BENEFICIARIES

    except ValueError:
        context.user_data["bot_message"] = await update.message.reply_text("Invalid amount. Please input a valid number.")
        return AMOUNT


async def add_beneficiaries(update: Update, context: CallbackContext):
    """Validate beneficiaries and prompt for split amounts."""
    beneficiaries_text = update.message.text.strip()
    group_id = update.message.chat_id
    await delete_messages(context, context.user_data.get("bot_message"), update.message)

    connection = connect_to_base()
    cursor = connection.cursor()

    try:
        if beneficiaries_text.lower() == "all":
            cursor.execute("SELECT username FROM participants WHERE group_id = %s;", (group_id,))
            beneficiaries = [row[0] for row in cursor.fetchall()]
            context.user_data["all_beneficiary_message"] = await update.message.reply_text(
                "Amount will be split among all beneficiaries, including the payer."
            )
        else:
            beneficiaries = [b.strip() for b in beneficiaries_text.split(",")]
            cursor.execute("SELECT username FROM participants WHERE group_id = %s;", (group_id,))
            valid_users = {row[0] for row in cursor.fetchall()}
            invalid_beneficiaries = [b for b in beneficiaries if b not in valid_users]

            if invalid_beneficiaries:
                context.user_data["bot_message"] = await update.message.reply_text(
                    f"Invalid beneficiaries: {', '.join(invalid_beneficiaries)}. Please try again."
                )
                return BENEFICIARIES

        context.user_data["beneficiaries"] = beneficiaries

        if len(beneficiaries) == 1:
            context.user_data["split_amounts"] = [context.user_data["amount"]]
            return await process_expense(update, context)

        context.user_data["bot_message"] = await update.message.reply_text(
            f"Please input the amounts (comma-separated) each beneficiary will receive in the SAME order:\n"
            f"Beneficiaries: {', '.join(beneficiaries)}\nType 'equal' to split the amount equally."
        )
        return SPLIT

    finally:
        cursor.close()
        connection.close()


async def add_split(update: Update, context: CallbackContext):
    """Validate and capture split amounts."""
    await delete_messages(
        context,
        context.user_data.get("bot_message"),
        context.user_data.get("all_beneficiary_message"),
        update.message,
    )
    split_text = update.message.text.strip()

    try:
        if split_text.lower() == "equal":
            split_amount = round(context.user_data["amount"] / len(context.user_data["beneficiaries"]), 2)
            context.user_data["split_amounts"] = [split_amount] * len(context.user_data["beneficiaries"])
            return await process_expense(update, context)

        split_amounts = [float(amount.strip()) for amount in split_text.split(",")]

        if len(split_amounts) != len(context.user_data["beneficiaries"]):
            raise ValueError("Number of amounts does not match the number of beneficiaries.")

        if sum(split_amounts) != context.user_data["amount"]:
            raise ValueError("Sum of split amounts does not match the total expense amount.")

        context.user_data["split_amounts"] = split_amounts
        return await process_expense(update, context)

    except ValueError as e:
        context.user_data["bot_message"] = await update.message.reply_text(str(e))
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
            f"Beneficiaries and Splits: {beneficiaries_splits_text}\n\n"
            "Use /show_expenses or /show_balance to see expense log or balances respectively!"
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
            f"Last expense undone!\n"
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