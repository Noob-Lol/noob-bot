import logging

from bot import TOKEN, bot

if __name__ == "__main__":
    bot.run(TOKEN, log_level=logging.WARNING, root_logger=True)
