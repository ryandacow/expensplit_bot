from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.data_manager import connect_to_base, is_member
#expenses, balance, participants, admins, settlement_logs
#from telebot.engine.currency import base_currency

async def show_balance(update: Update, context: CallbackContext):
    group_id = update.message.chat_id  # Get group ID

    try:
        # Connect to the database
        connection = connect_to_base()
        cursor = connection.cursor()

        # Fetch the base currency for the group
        cursor.execute("""
        SELECT base_currency FROM currency WHERE group_id = %s;
        """, (group_id,))
        base_currency = cursor.fetchone()
        currency = base_currency[0] if base_currency else "SGD"

        # Fetch all balances for the group
        cursor.execute("""
        SELECT participants.username, balances.balance 
        FROM balances 
        JOIN participants ON balances.username = participants.username
        WHERE balances.group_id = %s;
        """, (group_id,))
        balances = cursor.fetchall()

        if not balances:
            await update.message.reply_text("There are no participants in the group.")
            return

        print_balance = "*Current Balance:*\n"

        if len(context.args) < 1:
            # Show balances for all participants
            for username, balance in balances:
                status = "to be received" if balance < 0 else "to be paid" if balance > 0 else "settled"
                balance_text = f"{currency}{abs(balance):.2f}"
                print_balance += f"{username}: {balance_text} ({status})\n"
        else:
            # Show balance for a specific user
            user_name = context.args[0].lower()

            cursor.execute("""
            SELECT balances.balance 
            FROM balances 
            JOIN participants ON balances.username = participants.username
            WHERE participants.group_id = %s AND participants.username = %s;
            """, (group_id, user_name))
            user_balance = cursor.fetchone()

            if not user_balance:
                await update.message.reply_text(f"{user_name} is not a member of the group. Use /add_member to add them in!")
                return

            balance = user_balance[0]
            status = "to be received" if balance < 0 else "to be paid" if balance > 0 else "settled"
            balance_text = f"{currency}{abs(balance):.2f}"
            print_balance += f"{user_name}: {balance_text} ({status})\n"

        await update.message.reply_text(print_balance, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"Error while fetching balances: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()

async def show_expenses(update: Update, context: CallbackContext):
    group_id = update.message.chat_id  # Get group ID

    try:
        # Connect to the database
        connection = connect_to_base()
        cursor = connection.cursor()

        # Fetch expense history for the group
        cursor.execute("""
        SELECT e.purpose, e.payer, e.amount, e.currency, 
               json_agg(json_build_object('beneficiary', eb.username, 'amount', eb.split_amount)) AS beneficiaries 
        FROM expenses e
        JOIN expense_beneficiaries eb ON e.id = eb.expense_id
        WHERE e.group_id = %s
        GROUP BY e.id
        ORDER BY e.created_at DESC;
        """, (group_id,))
        expenses = cursor.fetchall()

        if not expenses:
            await update.message.reply_text("There are no expenses to show. Use /add_expense to add an expense to be tracked!")
            return

        print_expenses = "*Expense History:*\n"

        for i, expense in enumerate(expenses, start=1):
            beneficiaries = expense[4]  # JSON array of beneficiaries and amounts
            beneficiaries_text = ", ".join([f"{b['beneficiary']}: {expense[3]}{b['amount']:.2f}" for b in beneficiaries])

            print_expenses += (
                f"*{i}.* Purpose: {expense[0]}\n"
                f"   Payer: {expense[1]}\n"
                f"   Amount Paid: {expense[3]}{expense[2]:.2f}\n"
                f"   Beneficiaries:\n      {beneficiaries_text}\n\n"
            )

        await update.message.reply_text(print_expenses, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"Error while fetching expenses: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()