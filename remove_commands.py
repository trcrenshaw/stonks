import os
from discord.ext import commands
from discord_slash import SlashCommand
from discord_slash.utils.manage_commands import remove_all_commands
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

logger.info('Test')
TOKEN = os.environ['TOKEN']


bot = commands.Bot(command_prefix='#')
slash = SlashCommand(bot, sync_commands=True)

guild_ids=[821841802796859403]

@bot.event
async def on_ready():
    print('Ready')


@slash.slash(name='ignore', guild_ids=guild_ids)
async def ignore(ctx, *args):
    await ctx.send(f'Removing Commands')

bot.run(TOKEN)
