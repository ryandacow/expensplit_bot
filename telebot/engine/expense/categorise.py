from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ConversationHandler
from telebot.engine.supabase.data_manager import connect_to_base, is_member, is_expense, is_category
import psycopg2

#Create_category, Update_category, Show_categories

CATEGORY_CONFIRMATION = range(1)
CATEGORY, EXPENSE = range(2)

#Creates a new category
async def create_category(update: Update, context: CallbackContext):
    context.user_data["bot_message"] = await update.effective_chat.send_message("What is the name of the new category?")
    return CATEGORY_CONFIRMATION

async def name_category(update: Update, context: CallbackContext):
    category_name = update.message.text
    group_id = update.message.chat_id

    #Auto delete message
    bot_message = context.user_data.get("bot_message")
    if bot_message:
       await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    if await is_category(group_id, category_name):
        await update.effective_chat.send_message("This category already exists.")
        return ConversationHandler.END

    try:
        connection = connect_to_base()
        cursor = connection.cursor()

        # Insert new category if not found
        cursor.execute("""
        INSERT INTO categories (group_id, category_name)
        VALUES (%s, %s)
        ON CONFLICT(group_id, category_name) DO NOTHING;  -- Avoid duplicates
        """, (group_id, category_name))

        # Commit changes
        connection.commit()
        cursor.close()

    except Exception as e:
        print(f"Error adding category: {e}")
        return "An error occurred while adding the category."
    finally:
        if connection:
            connection.close()

    await update.effective_chat.send_message(f"{category_name} has been created.")

    return ConversationHandler.END

async def create_category_cancel(update: Update, context: CallbackContext):
    await update.effective_chat.send_message("The action to create category has been cancelled.")
    return ConversationHandler.END





#Adds an expense into a category
async def update_category(update: Update, context: CallbackContext):
    context.user_data["bot_message"] = await update.effective_chat.send_message("Which category is to be updated?")
    return CATEGORY

async def expense_category(update: Update, context: CallbackContext):
    #Auto delete message
    bot_message = context.user_data.get("bot_message")
    if bot_message:
       await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    group_id = update.message.chat_id
    category_name = update.message.text

    if not await is_category(group_id, category_name):
        await update.effective_chat.send_message("No such category found. Please try again.")
        return CATEGORY

    context.user_data["category"] = category_name
    context.user_data["bot_message"] = await update.effective_chat.send_message("Which expense is to be added?")
    return EXPENSE

async def expense_name(update: Update, context: CallbackContext):
    #Auto delete message
    bot_message = context.user_data.get("bot_message")
    if bot_message:
        await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    await context.bot.deleteMessage(chat_id=update.message.chat_id, message_id=update.message.message_id)

    group_id = update.message.chat_id
    expense_name = update.message.text

    if not await is_expense(group_id, expense_name):
        await update.message.reply_text("No such expense found. Please try again.")
        return EXPENSE
    
    context.user_data["expense"] = expense_name
    return await add_expense_into_category(update, context)

async def add_expense_into_category(update: Update, context: CallbackContext):
    bot_message = await update.effective_chat.send_message("Updating category...")

    # Retrieve necessary data from user_data
    group_id = update.message.chat_id
    category_name = context.user_data.get("category")
    expense_name = context.user_data.get("expense")

    try:
        # Database connection
        connection = connect_to_base()
        cursor = connection.cursor()

        # Update the expense with the new category
        cursor.execute("""
        UPDATE expenses
        SET category_name = %s
        WHERE group_id = %s AND purpose = %s;
        """, (category_name, group_id, expense_name))
        connection.commit()

        await update.effective_chat.send_message(
            f"Expense '{expense_name}' has been successfully updated with the category '{category_name}'."
        )

        if bot_message:
            await context.bot.deleteMessage(chat_id=bot_message.chat_id, message_id=bot_message.message_id)
    
    except Exception as e:
        await update.effective_chat.send_message(f"An error occurred while updating the category: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()

    return ConversationHandler.END

async def update_category_cancel(update: Update, context: CallbackContext):
    await update.effective_chat.send_message("The action to update category has been cancelled.")
    return ConversationHandler.END