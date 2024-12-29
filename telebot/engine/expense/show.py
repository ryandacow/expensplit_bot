from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.supabase.data_manager import connect_to_base, is_member, is_category
#expenses, balance, participants, admins, settlement_logs
#from telebot.engine.currency import base_currency

#List of Commands:
#show_balance, show_expenses, show_spending, show_categories

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
                f"   Beneficiaries: {beneficiaries_splits_text}\n\n"
            )

        await update.message.reply_text(print_expenses, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"Error while fetching expenses: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()



CATEGORY, INDIVIDUAL = range(2)

async def show_spending(update: Update, context: CallbackContext):
    context.user_data["bot_message"] = await update.message.reply_text("Which category is to be shown? Type 'all' to show all categories.")
    return CATEGORY

async def spending_category(update: Update, context: CallbackContext):
    group_id = update.message.chat_id
    category = update.message.text

    #Auto delete message
    bot_message = context.user_data.get("bot_message")
    await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    if category != "all" and not await is_category(group_id, category):
        await update.message.reply_text("No such category found. Use /add_category to create a new category.")
        return CATEGORY
    
    context.user_data["category"] = category
    context.user_data["bot_message"] = await update.message.reply_text("Which member is to be shown? Type 'all' to show all members.")
    return INDIVIDUAL

async def spending_individual(update: Update, context: CallbackContext):
    group_id = update.message.chat_id
    member = update.message.text

    #Auto delete message
    bot_message = context.user_data.get("bot_message")
    await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    if member != "all" and not is_member(group_id, member):
        await update.message.reply_text("No such member found. Use /add_member to add them in.")
        return INDIVIDUAL
    
    context.user_data["member"] = member
    return await spending_process(update, context)

async def spending_process(update: Update, context: CallbackContext):
    group_id = update.message.chat_id
    input_category = context.user_data["category"]
    member = context.user_data["member"].strip().lower()

    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        #If all categories and all members is given.
        if input_category == "all" and member == "all":
            cursor.execute("""
            SELECT username, SUM(split_amount) AS total_spent
            FROM expense_beneficiaries
            WHERE group_id = %s
            GROUP by username
            ORDER by total_spent DESC;
            """, (group_id, ))
            total_spending = cursor.fetchall()

            if not total_spending:
                await update.message.reply_text(f"No spending data found for this group.")
                return ConversationHandler.END

            spending_text = "*Group Spending Overview:*\n"
            for username, total_spent in total_spending:
                spending_text += f"{username}: {total_spent:.2f}\n"

            await update.message.reply_text(spending_text, parse_mode="Markdown")
    
        #If all categories and one member is given.
        elif input_category == "all" and member != "all":
            #Fetch spending_data by category
            cursor.execute("""
            SELECT COALESCE(e.category_name, 'Others') AS category, SUM(eb.split_amount) AS total_spent
            FROM expense_beneficiaries eb
            JOIN expenses e ON eb.expense_id = e.id
            WHERE eb.group_id = %s AND eb.username = %s
            GROUP BY e.category_name;
            """, (group_id, member))
            spending_data = cursor.fetchall()

            #Fetch total spending
            cursor.execute("""
            SELECT SUM(split_amount) AS total_spent
            FROM expense_beneficiaries
            WHERE group_id = %s AND username = %s;
            """, (group_id, member))
            total_spending = cursor.fetchone()[0] or 0.00

            if not spending_data:
                await update.message.reply_text(f"No spending data found for {member}.")
                return ConversationHandler.END

            message = f"*Spending Overview for {member}:*\n\n"
            message += f"*By Category:*\n"
            message += "\n".join(f"{category}: {total_spent:.2f}" for category, total_spent in spending_data)
            message += f"\n\nTotal Spending: {total_spending:.2f}"

            await update.message.reply_text(message,parse_mode="Markdown")
        
        #If one category and one member is given.
        elif input_category != "all" and member != "all":
            cursor.execute("""
            SELECT COALESCE(e.category_name, 'Others') AS category, SUM(eb.split_amount) AS total_spent
            FROM expense_beneficiaries eb
            JOIN expenses e ON eb.expense_id = e.id
            WHERE eb.group_id = %s AND eb.username = %s AND e.category_name ILIKE %s
            GROUP BY e.category_name;
            """, (group_id, member, input_category))
            spending_data = cursor.fetchone()
            
            if spending_data is None or spending_data[1] is None:
                await update.message.reply_text(
                    f"No spending data found for {member} in {input_category} category."
                )
                return ConversationHandler.END

            category_name, total_spent = spending_data
            await update.message.reply_text(
                f"*Spending Overview for {member} in '{category_name}':*\n"
                f"Total Spent: {total_spent:.2f}",
                parse_mode="Markdown"
            )

    except Exception as e:
        await update.message.reply_text(f"Error while fetching expenses: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()
    return ConversationHandler.END

async def show_spending_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("The action to show spending has been cancelled.")
    return ConversationHandler.END



#Lists all categories created.    
async def show_categories(update: Update, context: CallbackContext):
    """Show the list of categories created."""
    # Get the group_id from the chat_id
    group_id = update.message.chat_id

    try:
        # Connect to the database
        connection = connect_to_base()
        cursor = connection.cursor()

        # Retrieve the list of categories for the group
        cursor.execute("""
        SELECT category_name FROM categories WHERE group_id = %s;
        """, (group_id,))
        
        # Fetch all the results
        categories = cursor.fetchall()

        if not categories:
            await update.message.reply_text("There are no categories created yet.")
            return
        
        # Create a string of all members
        categories_list = "\n".join([category[0] for category in categories])  # Extracting the username from the tuple
        
        # Send the list of members
        await update.message.reply_text(f"Categories:\n{categories_list}")

    except Exception as e:
        await update.message.reply_text(f"Error retrieving categories: {e}")
    
    finally:
        if connection:
            connection.close()