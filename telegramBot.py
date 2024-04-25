import logging, os
import nest_asyncio
import numpy as np
import pandas as pd
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
# Assuming you have a 'keys.py' file with your token
import keys

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


data_base_filename = 'db.xlsx'
df = pd.DataFrame
def load_dataframe():
    df = pd.read_excel(data_base_filename,header=1)
    df = df.iloc[: , 1:]
    df.columns = df.columns.astype(str)
    df.columns = [x[:20] for x in df.columns]
    return df
df = load_dataframe()
check_admin = False

mask_df = pd.read_excel('mask_db.xlsx',header=None)
mask_df.columns = ["id","region"]
#mask_df = df.columns.astype(str)

# Function to check if the user is the bot administrator
def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return user.id == keys.admin_id

async def upload_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if check_admin and not is_admin(update, context):
        await update.message.reply_text("У Вас недостаточно прав, обратитесь к администратору.")
        return

    await update.message.reply_text("Введите пароль:")
    context.user_data['waiting_for_password'] = True
    return

async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['waiting_for_file'] = False
    context.user_data['waiting_for_password'] = False
    await update.message.reply_text("Обнавление датабазы отменено.")

async def downloader(update, context):
    if context.user_data['waiting_for_password']:
        await update.message.reply_text("Before uploading please enter the password (Use /cancel_upload to cancel the upload if you want to): ")
        return

    if not context.user_data['waiting_for_file']:
        await update.message.reply_text("Please use /upload_excel command to upload files")
        return

    # Download file
    fileName = update.message.document.file_name
    new_file = await update.message.effective_attachment.get_file()
    await new_file.download_to_drive(fileName)
    os.replace(fileName, data_base_filename)

    context.user_data['waiting_for_file'] = False

    # Update the file
    df = load_dataframe()

    # Acknowledge file received
    await update.message.reply_text(f"{fileName} saved successfully")
    return


# Command handler for /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Справку о командах можно узнать с помощью /help \n\nВведите номер или название региона для получения информации о налоговом вычете')
    context.user_data['waiting_for_password'] = False
    context.user_data['waiting_for_file'] = False

# Command handler for /help
async def bothelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('TEST avaiable commands:\n /start \n /upload_excel \n /cancel_upload \n general message')

# Message handler for word input
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle changing data
    if context.user_data.get('waiting_for_password'):
        try:
            if update.message.text == str(keys.password):
                context.user_data['waiting_for_file'] = True
                context.user_data['waiting_for_password'] = False
                await update.message.reply_text("Password accepted. Please upload the Excel file.")
            else:
                await update.message.reply_text("Incorrect password. Access denied.")
                context.user_data['waiting_for_password'] = False
        except Exception as e:
            logging.error(f"Error in handle_password: {e}")
            context.user_data['waiting_for_password'] = False
        return

    if context.user_data['waiting_for_file']:
        await update.message.reply_text("Please upload the Excel file. Use /cancel_upload to cancel the upload")
        return


    # Handle data search
    index = '1000'
    if str(update.message.text).isdigit():
        if not mask_df.loc[mask_df["id"] == int(update.message.text)].empty:
            region = mask_df.loc[mask_df["id"] == int(update.message.text)]["region"].to_list()[0]
            if df.loc[df[df.columns[0]] == region].empty:
                print(region)
                await update.message.reply_text(f'Данный регион не найден в текущей базе данных')
                return
            else:
                index = str(df.loc[df[df.columns[0]] == region].index[0])
    elif not df.loc[df[df.columns[0]] == str(update.message.text)].empty:
        index = str(df.loc[df[df.columns[0]] ==  str(update.message.text)].index[0])


    if(index.isdigit() and int(index) < df.shape[0] and not(pd.isna(df[df.columns[0]][int(index)])) ):
        if(pd.isna(df[df.columns[1]][int(index)])):
            await update.message.reply_text(f'Для региона {df[df.columns[0]][int(index)]} отсутствует закон ИНВ. \nВы можете выбрать другой регион')
            return
        elif(str(df[df.columns[2]][int(index)])=="НЕТ"):
            await update.message.reply_text(f"Для региона {df[df.columns[0]][int(index)]} не предусмотрен ИНВ в соответствии с {df[df.columns[1]][int(index)]}. \nВы можете выбрать другой регион")
            return
        keyboard = [
        [InlineKeyboardButton(str(column_name), callback_data=f"{index}:{str(column_name)}")]
        for column_name in df.columns[1:] if not(pd.isna(df[column_name][int(index)]))]
        keyboard.append([InlineKeyboardButton("Выбрать другой регион",callback_data="back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'Ваш выбор {df[df.columns[0]][int(index)]}! Доступная информация:', reply_markup=reply_markup)
        return
    await update.message.reply_text('Введеные данные не распознаны попробуйте ещё раз')
    return


# Callback query handler for column selection
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "back":
      await query.edit_message_text(f"Введите номер или название региона")
      return
    index, column_name = query.data.split(':')
    keyboard = [
    [InlineKeyboardButton(str(column_name), callback_data=f"{index}:{str(column_name)}")]
    for column_name in df.columns[1:] if not(pd.isna(df[column_name][int(index)]))]
    keyboard.append([InlineKeyboardButton("Выбрать другой регион",callback_data="back")])
    keyboard.remove([InlineKeyboardButton(str(column_name), callback_data=f"{index}:{str(column_name)}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Ваш выбор {df[df.columns[0]][int(index)]}! По вопросу {column_name} имеются следующие данные: {df[column_name][int(index)]}", reply_markup=reply_markup)
    return

if __name__ == '__main__':
    application = ApplicationBuilder().token(keys.token).build()

    # Command handler for /start
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    # Command handler for /help
    help_handler = CommandHandler('help', bothelp)
    application.add_handler(help_handler)

    # Command handlers for /upload_excel & /cancel_upload
    upload_excel_handler = CommandHandler('upload_excel', upload_excel)
    application.add_handler(upload_excel_handler)

    cancel_upload_handler = CommandHandler('cancel_upload', cancel_upload)
    application.add_handler( cancel_upload_handler)

    # Message handler for word input
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.ATTACHMENT, handle_message)
    application.add_handler(message_handler)

    # Message handler for file attachment
    application.add_handler(MessageHandler(filters.ATTACHMENT, downloader))

    # Callback query handler for column selection
    button_handler = CallbackQueryHandler(handle_button)
    application.add_handler(button_handler)

    # Run the bot
    application.run_polling()
