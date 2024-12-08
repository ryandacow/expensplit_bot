from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.data_manager import connect_to_base, is_member
#expenses, balance, participants, admins, settlement_logs
#from telebot.engine.currency import base_currency
#List of Commands:
#show_balance, show_expenses, help, show_spending

async def show_balance(update: Update, context: CallbackContext):
    group_id = update.message.chat_id  # Get group ID

    try:
        # Connect to the database
        connection = connect_to_base()
        cursor = connection.cursor()

        # Fetch the base currency for the group
        cursor.execute("""
        SELECT base_currency 
        FROM currency 
        WHERE group_id = %s;
        """, (group_id,))
        base_currency = cursor.fetchone()
        currency = base_currency[0] if base_currency else "SGD"

        # Fetch all balances for the group
        cursor.execute("""
        SELECT p.username, b.balance 
        FROM balances b
        JOIN participants p ON b.group_id = p.group_id AND b.username = p.username
        WHERE b.group_id = %s;
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
                balance_text = f"{currency}{abs(balance):.2f}" if balance >= 0 else f"-{currency}{abs(balance):.2f}"
                print_balance += f"{username}: {balance_text} ({status})\n"
        else:
            # Show balance for a specific user
            user_name = context.args[0].lower()

            cursor.execute("""
            SELECT b.balance 
            FROM balances b
            JOIN participants p ON b.group_id = p.group_id AND b.username = p.username
            WHERE b.group_id = %s AND LOWER(p.username) = %s;
            """, (group_id, user_name))
            user_balance = cursor.fetchone()

            if not user_balance:
                await update.message.reply_text(f"{user_name} is not a member of the group. Use /add_member to add them in!")
                return

            balance = user_balance[0]
            status = "to be received" if balance < 0 else "to be paid" if balance > 0 else "settled"
            balance_text = f"{currency}{abs(balance):.2f}" if balance >= 0 else f"-{currency}{abs(balance):.2f}"
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
            beneficiaries_splits_text = ", ".join(
                [f"{b['beneficiary']} ({expense[3]}{b['amount']:.2f})" for b in beneficiaries]
            )

            print_expenses += (
                f"*{i}.* Purpose: {expense[0]}\n"
                f"   Payer: {expense[1]}\n"
                f"   Amount Paid: {expense[3]}{expense[2]:.2f}\n"
                f"   Beneficiaries: {beneficiaries_splits_text}\n"
            )

        await update.message.reply_text(print_expenses, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"Error while fetching expenses: {e}")
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



async def show_spending(update: Update, context: CallbackContext):
    group_id = update.message.chat_id

    #If username is given, show spending of that individual.
    if context.args:
        user_name = context.args[0].strip().lower()

        try:
            connection = connect_to_base()
            cursor = connection.cursor()

            cursor.execute("""
            SELECT username FROM participants WHERE group_id = %s AND username = %s;
            """, (group_id, user_name))
            if not cursor.fetchone():
                await update.message.reply_text(f"{user_name} is not a participant in this group. Use /add_member to add them!")
                return

            cursor.execute("""
            SELECT SUM(split_amount) as total_spent
            FROM expense_beneficiaries
            WHERE group_id = %s AND username = %s;
            """, (group_id, user_name))
            spending_data = cursor.fetchone()

            total_spent = spending_data[0] if spending_data[0] else 0.00
            await update.message.reply_text(
                f"*Spending Overview for {user_name}*:\n"
                f"Total Spent: {total_spent:.2f}",
                parse_mode="Markdown"
            )
        
        except Exception as e:
            await update.message.reply_text(f"Error while fetching expenses: {e}")
        finally:
            if connection:
                cursor.close()
                connection.close()

    if not context.args: 
        try:
            connection = connect_to_base()
            cursor = connection.cursor()

            cursor.execute("""
            SELECT username, SUM(split_amount) as total_spent
            FROM expense_beneficiaries
            WHERE group_id = %s
            GROUP by username
            ORDER by total_spent DESC;
            """, (group_id, ))
            total_spending = cursor.fetchall()

            if not total_spending:
                await update.message.reply_text(f"No spending data found for this group.")
                return

            spending_text = "*Group Spending Overview:*\n"
            for username, total_spent in total_spending:
                spending_text += f"{username}: {total_spent:.2f}\n"

            
            await update.message.reply_text(spending_text, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"Error while fetching expenses: {e}")
        finally:
            if connection:
                cursor.close()
                connection.close()