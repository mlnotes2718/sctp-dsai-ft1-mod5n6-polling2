from flask import Flask, render_template, request, jsonify
import joblib
import groq
from groq import Groq
import os
import threading
import time
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    print("TELEGRAM_BOT_TOKEN environment variable is required")
    exit(1)

# Initialize Groq client (if needed)
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if GROQ_API_KEY:
    groq_client = groq.Client(api_key=GROQ_API_KEY)
    print("Groq client initialized")
else:
    groq_client = None
    print("GROQ_API_KEY not set, Groq client not initialized")

# Global variables for bot management
telegram_app = None
bot_thread = None
bot_running = False
bot_start_time = None
last_error = None
shutdown_event = threading.Event()  # Event to signal shutdown

###############################################################
### Function for Telegram bot polling
###############################################################
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name if update.effective_user else "User"
    welcome_text = f"🤖 Hello {user_name}! I'm running on Render with polling!\n\n" 
    if update.message:
        await update.message.reply_text(welcome_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message and update.message.text:
            text = update.message.text
            if groq_client:
                try:
                    groq_response = groq_client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[{"role": "user", "content": text}]
                    )
                    reply_content = groq_response.choices[0].message.content or "No response from Groq."
                    await update.message.reply_text(reply_content)
                except Exception as ge:
                    print(f"Error querying Groq: {ge}")
                    await update.message.reply_text("Error querying Groq service.")
        else:
            print("Received update without message or text.")
    except Exception as e:
        print(f"Error in message handler: {e}")
        if update.message:
            await update.message.reply_text("Sorry, I encountered an error processing your message.")

def setup_telegram_bot():
    """Initialize and configure the Telegram bot"""
    global telegram_app
    
    try:
        print("Setting up Telegram bot...")
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        
        telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Add handlers
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("Telegram bot setup complete")
        return telegram_app
        
    except Exception as e:
        print(f"Error setting up Telegram bot: {e}")
        return None

def run_telegram_bot():
    """Run the Telegram bot in a separate thread with polling"""
    global bot_running, bot_start_time, last_error
    
    def bot_worker():
        global bot_running, bot_start_time, last_error, telegram_app
        
        loop = None
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            print("Starting Telegram bot with polling...")
            bot_running = True
            bot_start_time = time.time()
            last_error = None
            
            if telegram_app is not None:
                # Start polling with proper error handling
                async def run_polling():
                    try:
                        await telegram_app.initialize() # type: ignore
                        await telegram_app.start() # type: ignore
                        await telegram_app.updater.start_polling( # type: ignore
                            drop_pending_updates=True
                        )
                        
                        # Keep running until shutdown is signaled
                        while not shutdown_event.is_set() and bot_running:
                            await asyncio.sleep(1)
                            
                    except Exception as e:
                        print(f"Error in polling: {e}")
                        raise
                    finally:
                        # Cleanup
                        print("Cleaning up telegram app...")
                        try:
                            if telegram_app and telegram_app.updater and telegram_app.updater.running:
                                await telegram_app.updater.stop()
                            if telegram_app and telegram_app.running:
                                await telegram_app.stop()
                            if telegram_app:
                                await telegram_app.shutdown()
                        except Exception as cleanup_error:
                            print(f"Error during cleanup: {cleanup_error}")
                
                # Run the polling
                loop.run_until_complete(run_polling())
            else:
                print("Telegram app is not initialized. Cannot run polling.")
                
        except Exception as e:
            print(f"Error in bot thread: {e}")
            last_error = str(e)
        finally:
            print("Bot thread finished")
            bot_running = False
            if loop and not loop.is_closed():
                try:
                    loop.close()
                except Exception as e:
                    print(f"Error closing event loop: {e}")
    
    # Start bot in background thread
    thread = threading.Thread(target=bot_worker, daemon=False, name="TelegramBotThread")
    thread.start()
    print(f"Bot thread started: {thread.name}")
    return thread

def stop_bot_gracefully():
    """Gracefully stop the bot and wait for thread to finish"""
    global bot_thread, telegram_app, bot_running, shutdown_event
    
    try:
        print("Initiating graceful bot shutdown...")
        
        # Signal shutdown
        shutdown_event.set()
        bot_running = False
        
        # Wait for thread to finish
        if bot_thread and bot_thread.is_alive():
            print("Waiting for bot thread to finish...")
            bot_thread.join(timeout=15)
            
            if bot_thread.is_alive():
                print("Bot thread did not stop gracefully within timeout")
                return False
            else:
                print("Bot thread stopped gracefully")
                return True
        
        print("Bot stopped successfully")
        return True
        
    except Exception as e:
        print(f"Error during graceful shutdown: {e}")
        return False

# Initialize the bot
def initialize_bot():
    """Initialize the bot on startup"""
    global bot_thread
    
    try:
        print("Initializing Telegram bot...")
        
        if setup_telegram_bot():
            bot_thread = run_telegram_bot()
            print("Bot initialization complete")
            
            # Give it a moment to start
            time.sleep(3)
            
            # Check if it started successfully
            if bot_thread and bot_thread.is_alive() and bot_running:
                print("✅ Bot started successfully!")
            else:
                print("❌ Bot failed to start properly")
        else:
            print("❌ Failed to setup bot")
            
    except Exception as e:
        print(f"❌ Error during bot initialization: {e}")
###############################################################


# Initialize Flask app
app = Flask(__name__)

@app.route("/",methods=["GET","POST"])
def index():
    return(render_template("index.html"))

@app.route("/main",methods=["GET","POST"])
def main():
    q = request.form.get("q")
    # db
    return(render_template("main.html"))

@app.route("/llama",methods=["GET","POST"])
def llama():
    return(render_template("llama.html"))

@app.route("/llama_reply",methods=["GET","POST"])
def llama_reply():
    q = request.form.get("q")
    # load model
    client = Groq()
    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "user",
                "content": q
            } # type: ignore
        ]
    )
    return(render_template("llama_reply.html",r=completion.choices[0].message.content))

@app.route("/deepseek",methods=["GET","POST"])
def deepseek():
    return(render_template("deepseek.html"))

@app.route("/deepseek_reply",methods=["GET","POST"])
def deepseek_reply():
    q = request.form.get("q")
    # load model
    client = Groq()
    completion_ds = client.chat.completions.create(
        model="deepseek-r1-distill-llama-70b",
        messages=[
            {
                "role": "user",
                "content": q
            } # type: ignore
        ]
    )
    return(render_template("deepseek_reply.html",r=completion_ds.choices[0].message.content))

@app.route("/dbs",methods=["GET","POST"])
def dbs():
    return(render_template("dbs.html"))

@app.route("/prediction",methods=["GET","POST"])
def prediction():
    q = float(request.form.get("q")) # type: ignore
    # load model
    model = joblib.load("dbs.jl")
    # make prediction
    pred = model.predict([[q]])
    return(render_template("prediction.html",r=pred))


###############################################################
### Telegram Flask routes
###############################################################
@app.route("/telegram_polling", methods=["GET", "POST"])
def telegram_polling():
    return render_template("telegram_polling.html", r="Telegram polling not started.")

@app.route('/start_polling', methods=['POST'])
def start_polling():
    """Start the bot via web interface"""
    global bot_thread, telegram_app, shutdown_event
    
    try:
        if bot_running:
            return render_template("telegram_polling.html", r="Bot is already polling")
        
        print("Starting bot via web interface...")
        
        # Reset shutdown event
        shutdown_event.clear()
        
        # Setup and start bot
        if setup_telegram_bot():
            bot_thread = run_telegram_bot()
            time.sleep(2)  # Give it time to start
            
            if bot_thread and bot_thread.is_alive():
                return render_template("telegram_polling.html", r="Bot started successfully")
            else:
                return render_template("telegram_polling.html", r="Bot failed to start")
        else:
            return render_template("telegram_polling.html", r="Failed to setup bot")

    except Exception as e:
        print(f"Error starting bot: {e}")
        return render_template("telegram_polling.html", r=f"Error: {e}")

@app.route('/stop_polling', methods=['POST'])
def stop_polling():
    """Stop the bot gracefully"""
    try:
        if not bot_running:
            print("Bot is not running")
            return render_template("telegram_polling.html", r="Bot is not running")
            
        success = stop_bot_gracefully()
        if success:
            return render_template("telegram_polling.html", r="Bot stopped successfully")
        else:
            return render_template("telegram_polling.html", r="Bot stop completed with warnings")
    except Exception as e:
        print(f"Error stopping bot: {e}")
        return render_template("telegram_polling.html", r=f"Error stopping bot: {e}")
###############################################################

if __name__ == "__main__":
    app.run()

