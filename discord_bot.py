from typing import List, Any, Optional
from discord.ext import commands, tasks
import discord
import yfinance as yf
from dataclasses import dataclass
from datetime import datetime
import pickle
import os
import boto3
import argparse
import logging
from discord_slash import SlashCommand, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

logging.basicConfig(level=logging.INFO)


@dataclass
class Alert:
    ticker: Any = None
    type: Any = None
    value: Any = None
    last_alert: Any = None


@dataclass
class Trade:
    ticker: str = ''
    amount: float = 0
    price: float = 0
    sell: bool = False

    @property
    def buy(self):
        return not self.sell

    @buy.setter
    def buy(self, value):
        self.sell = not value


@dataclass
class Holding:
    ticker: str = ''
    amount: float = 0
    cost_basis: float = 0


TOKEN = os.environ['TOKEN']
S3_BUCKET = os.environ['S3_BUCKET']
ACCESS_KEY_ID = os.environ['ACCESS_KEY_ID']
ACCESS_KEY = os.environ['ACCESS_KEY']

client = commands.Bot(command_prefix='#')
slash = SlashCommand(client, sync_commands=True)

alerts: List[Alert] = []
trades: List[Trade] = []

try:
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY_ID, aws_secret_access_key=ACCESS_KEY)
    s3.download_file(S3_BUCKET, 'Alerts.pkl', 'Alerts.pkl')
    with open('Alerts.pkl', 'rb') as f:
        alerts = pickle.load(f)
except:
    alerts: List[Alert] = []

try:
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY_ID, aws_secret_access_key=ACCESS_KEY)
    s3.download_file(S3_BUCKET, 'Trades.pkl', 'Trades.pkl')
    with open('Trades.pkl', 'rb') as f:
        trades = pickle.load(f)
except:
    trades: List[Trade] = []


@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')


def save_alerts():
    with open('Alerts.pkl', 'wb') as f:
        pickle.dump(alerts, f, pickle.HIGHEST_PROTOCOL)
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY_ID, aws_secret_access_key=ACCESS_KEY)
    s3.upload_file('Alerts.pkl', S3_BUCKET, 'Alerts.pkl')


def save_trades():
    with open('Trades.pkl', 'wb') as f:
        pickle.dump(trades, f, pickle.HIGHEST_PROTOCOL)
    s3 = boto3.client('s3', aws_access_key_id=ACCESS_KEY_ID, aws_secret_access_key=ACCESS_KEY)
    s3.upload_file('Trades.pkl', S3_BUCKET, 'Trades.pkl')


@commands.command(aliases=['AddAlert', 'addAlert'])
async def add_alert(ctx, *args):
    if len(args) != 2:
        await ctx.send(f'Check your syntax on that command')
        return
    ticker = args[0]
    alert_type = '%' if '%' in args[1] else '$' if '$' in args[1] else ''
    num = float(args[1].replace(alert_type, ''))

    alerts.append(Alert(ticker, alert_type, num, None))
    await ctx.send(f'Added alert for {ticker} with {num}{alert_type} change')
    save_alerts()


@commands.command(aliases=['RemoveAlert', 'removeAlert'])
async def remove_alert(ctx, *args):
    global alerts
    for arg in args:
        try:
            i = int(arg)
            if 0 < i < len(alerts):
                alerts.pop(i)
        except ValueError:
            alerts = [alert for alert in alerts if alert.ticker != arg]
    save_alerts()


@commands.command(aliases=['GetAlerts', 'getAlerts'])
async def get_alerts(ctx, *args):
    msg = ''
    for index, alert in enumerate(alerts):
        msg += f'{index}: {alert.ticker} - {alert.value}{alert.type}\r'
    msg = 'No active alerts' if msg == '' else msg
    await ctx.send(msg)


@commands.command(aliases=['ResetAlerts', 'resetAlerts'])
async def reset_alerts(ctx, *args):
    for alert in alerts:
        alert.last_alert = None
    await ctx.send(f'All Alerts Reset')


@tasks.loop(seconds=100)
async def check_stocks():
    print('Checking Stocks')
    channel = client.get_channel(821841802796859406)
    for alert in alerts:
        try:
            data = yf.download(alert.ticker, period='1d', interval='1m')
        except:
            continue

        close = data['Close']
        if close.index[-1].date() != datetime.now().date():
            alert.last_alert = None
            continue

        prev_value = alert.last_alert if alert.last_alert is not None else close[0]
        if alert.type == '%':
            change = round(100 * (close[-1] - prev_value) / prev_value, 2)
            if abs(change) > alert.value:
                em = discord.Embed()
                em.colour = 0x00ff00 if change > alert.value else 0xff0000
                em.description = f'[{alert.ticker}](https://finance.yahoo.com/quote/{alert.ticker}) changed by ' \
                                 f'{change}%  Price: ${round(close[-1], 2)}'
                await channel.send(embed=em)
                alert.last_alert = close[-1]
        elif alert.type == '$':
            change = round(close[-1] - prev_value, 2)
            if abs(change) > alert.value:
                em = discord.Embed()
                em.colour = 0x00ff00 if change > alert.value else 0xff0000
                em.description = f'[{alert.ticker}](https://finance.yahoo.com/quote/{alert.ticker}) changed by ' \
                                 f'${change} Price: ${round(close[-1], 2)}'
                await channel.send(embed=em)
                alert.last_alert = close[-1]
    save_alerts()


@commands.command(aliases=['CheckAlerts', 'checkAlerts'])
async def check_alerts(ctx, *args):
    await check_stocks()


@commands.command(aliases=['GetStock', 'getStock', 'GetPrice', 'getPrice'])
async def get_stock(ctx, *args):
    ticker = args[0]

    try:
        data = yf.download(ticker, period='1d', interval='1m')
        close = data['Close']

        em = discord.Embed(colour=0x0080c0,
                           description=f'[{ticker}](https://finance.yahoo.com/quote/{ticker}) is ${round(close[-1], 2)}')
        await ctx.send(embed=em)
    except:
        await ctx.send(f'Could not get data for {ticker}')


@commands.command(aliases=['Buy'])
async def buy(ctx, *args):
    if len(args) != 3:
        await ctx.send(f'Check your syntax on that command')
        return
    ticker = args[0]

    try:
        amount = float(f'{args[1]}'.replace('%', ''))
    except:
        await ctx.send(f'Check your syntax on that command')
        return

    try:
        price = float(f'{args[2]}'.replace('$', ''))
    except:
        await ctx.send(f'Check your syntax on that command')
        return

    trades.append(Trade(ticker=ticker, amount=amount, price=price, sell=False))
    await ctx.send(f'Added purchase of {amount} shares of {ticker} at ${price}')
    save_trades()


@commands.command(aliases=['Sell'])
async def sell(ctx, *args):
    if len(args) != 3:
        await ctx.send(f'Check your syntax on that command')
        return
    ticker = args[0]

    try:
        amount = float(f'{args[1]}'.replace('%', ''))
    except:
        await ctx.send(f'Check your syntax on that command')
        return

    try:
        price = float(f'{args[2]}'.replace('$', ''))
    except:
        await ctx.send(f'Check your syntax on that command')
        return

    trades.append(Trade(ticker=ticker, amount=amount, price=price, sell=True))
    await ctx.send(f'Added sale of {amount} shares of {ticker} at ${price}')
    save_trades()


def holdings(trades: List[Trade]) -> List[Holding]:
    tickers = set([trade.ticker for trade in trades])

    for ticker in tickers:
        ticker_trades = [trade for trade in trades if trade.ticker == ticker]

        amount = sum([t.amount for t in ticker_trades if not t.sell]) - sum(
            [t.amount for t in ticker_trades if not t.sell])


@commands.command(aliases=['Positions'])
async def positions(ctx, *args):
    tickers = set([trade.ticker for trade in trades])


@check_stocks.before_loop
async def before():
    await client.wait_until_ready()
    print("Finished waiting")


ticker_option = create_option(
    name="ticker",
    description="The stock ticker.",
    option_type=3,
    required=True
)
shares_option = create_option(
    name="shares",
    description="Shares Traded.",
    option_type=3,
    required=True
)
share_price_option = create_option(
    name="price_per_share",
    description="The Price paid per share",
    option_type=3,
    required=False
)
total_price_option = create_option(
    name="total_price",
    description="The Total Price paid",
    option_type=3,
    required=False
)

price_above_choice = create_choice(name='Above', value='Above')
price_below_choice = create_choice(name='Below', value='Below')

price_type_option = create_option(
    name="trigger_type",
    description="Alert when Ticker Price is Above or Below trigger price",
    option_type=3,
    required=True,
    choices=[price_above_choice, price_below_choice]
)

guild_ids = [821841802796859403]


@slash.slash(name='get_price',
             guild_ids=guild_ids,
             description='Gets the current price of the a stock',
             options=[ticker_option, shares_option, share_price_option, total_price_option]
             )
async def _get_price(ctx: SlashContext, ticker: str, shares: str, price_per_share: Optional[str] = None,
                     total_price: Optional[str] = None):
    embed = discord.Embed(title=f"Ticker: {ticker}\n"
                                f"Shares: {shares}\n"
                                f"$/share: {price_per_share}\n"
                                f"TotalPrice: {total_price}\n")
    await ctx.send(embeds=[embed])


@slash.subcommand(base='Add',
                  name='Price_Alert',
                  guild_ids=guild_ids,
                  description='Add Alert for ticker',
                  options=[ticker_option,
                           price_type_option,
                           share_price_option])
async def add_price_alert(ctx: SlashContext, ticker: str, trigger_type: str, price_per_share: Optional[str] = None):
    embed = discord.Embed(title=f"Ticker: {ticker}\n"
                                f"Above/Below: {trigger_type}\n"
                                f"$/share: {price_per_share}")

    await ctx.send(embeds=[embed])


check_stocks.start()

client.add_command(add_alert)
client.add_command(get_alerts)
client.add_command(get_stock)
client.add_command(reset_alerts)
client.add_command(remove_alert)

client.run(TOKEN)
