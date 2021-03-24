import discord
from typing import List, Any
from discord.ext import commands, tasks
import discord
import yfinance as yf
from dataclasses import dataclass
from datetime import datetime
import pickle
import os


@dataclass
class Alert:
    ticker: Any = None
    type: Any = None
    value: Any = None
    last_alert: Any = None


TOKEN = os.environ['TOKEN']
client = commands.Bot(command_prefix='#')
alerts: List[Alert] = []
try:
    with open('Alerts.pkl', 'rb') as f:
        alerts = pickle.load(f)
except:
    alerts: List[Alert] = []

@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')


def save_alerts():
    with open('Alerts.pkl', 'wb') as f:
        pickle.dump(alerts, f, pickle.HIGHEST_PROTOCOL)


@commands.command()
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


@commands.command()
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


@commands.command()
async def get_alerts(ctx, *args):
    msg = ''
    for index, alert in enumerate(alerts):
        msg += f'{index}: {alert.ticker} - {alert.value}{alert.type}\r'
    msg = 'No active alerts' if msg == '' else msg
    await ctx.send(msg)


@commands.command()
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
            change = round(100*(close[-1] - prev_value)/prev_value, 2)
            if abs(change) > alert.value:
                embed = discord.Embed()
                embed.description = f'{alert.ticker} changed by {change}%  Price: ${round(close[-1], 2)}'
                await channel.send(embed=embed)
                alert.last_alert = close[-1]
        elif alert.type == '$':
            change = round(close[-1] - prev_value, 2)
            if abs(change) > alert.value:
                embed = discord.Embed()
                embed.description = f'{alert.ticker} changed by ${change}  Price: ${round(close[-1], 2)}'
                await channel.send(embed=embed)
                alert.last_alert = close[-1]
    save_alerts()


@commands.command()
async def get_stock(ctx, *args):
    ticker = args[0]
    em = discord.Embed(title="{ticker}",
                       colour=0x0080c0)
    em.add_field(name="Ticker", value="https://finance.yahoo.com/quote/{ticker}")
    await ctx.send(embed=em)


@check_stocks.before_loop
async def before():
    await client.wait_until_ready()
    print("Finished waiting")

check_stocks.start()

client.add_command(add_alert)
client.add_command(get_alerts)
client.add_command(get_stock)
client.add_command(reset_alerts)
client.add_command(remove_alert)

client.run(TOKEN)


