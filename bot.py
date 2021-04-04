import os
from discord.ext import commands
from discord_slash import SlashCommand
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.info('Test')
TOKEN = os.environ['TOKEN']

bot = commands.Bot(command_prefix='#')
slash = SlashCommand(bot, sync_commands=True)

bot.load_extension('cogs.Stocks')
bot.run(TOKEN)
