from typing import List, Any, Optional
from discord.ext import commands, tasks
import discord
import yfinance as yf
from dataclasses import dataclass
from datetime import datetime
import pickle
import os
import boto3
import logging
from discord_slash import SlashCommand, SlashContext, cog_ext
from discord_slash.utils.manage_commands import create_option, create_choice

logger = logging.getLogger(__name__)

GUILD_IDS = [821841802796859403]


@dataclass
class Alert:
    ticker: str = ''
    type: str = ''
    value: float = 0
    last_alert: datetime = None
    time_period: str = '1d'
    pre_post_data: bool = False


@dataclass
class Trade:
    ticker: str = ''
    shares: float = 0
    share_price: float = 0  # price per share
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


class Options:
    ticker = create_option(
        name="ticker",
        description="Stock Ticker Ex. AAPL",
        option_type=3,
        required=True
    )
    trigger_price = create_option(
        name="trigger_price",
        description="Alert Trigger Price",
        option_type=3,
        required=True
    )

    trigger_type = create_option(
        name="trigger_type",
        description="Alert when Ticker Price is Above or Below trigger price",
        option_type=3,
        required=True,
        choices=[
            create_choice(name='Above', value='Above'),
            create_choice(name='Below', value='Below')
        ]
    )

    change_type = create_option(
        name="change_type",
        description="Is alert based on percent change or dollar change",
        option_type=3,
        required=True,
        choices=[
            create_choice(name='Percent', value='%'),
            create_choice(name='Dollar', value='$')
        ]
    )

    change_value = create_option(
        name="change_value",
        description="Percent Change that will trigger an alert",
        option_type=3,
        required=True
    )

    time_period = create_option(
        name="time_period",
        description="Time Period to check for change",
        option_type=3,
        required=False,
        choices=[
            # create_choice(name='1 Minute', value='1m'),
            # create_choice(name='2 Minutes', value='2m'),
            # create_choice(name='5 Minutes', value='5m'),
            # create_choice(name='15 Minutes', value='15m'),
            # create_choice(name='30 Minutes', value='30m'),
            # create_choice(name='60 Minutes', value='60m'),
            # create_choice(name='90 Minutes', value='90m'),
            # create_choice(name='1 Hour', value='1h'),
            create_choice(name='1 Day', value='1d'),
            create_choice(name='5 Days', value='5d'),
            # create_choice(name='1 Week', value='1wk'),
            create_choice(name='1 Month', value='1mo'),
            create_choice(name='3 Months', value='3mo'),
            create_choice(name='6 Months', value='6mo'),
            create_choice(name='1 Year', value='1y'),
            create_choice(name='2 Years', value='2y'),
            create_choice(name='5 Years', value='5y'),
            create_choice(name='10 Years', value='10y'),
            create_choice(name='Year to Date', value='ytd'),
            create_choice(name='Max', value='max'),
        ]
    )

    prepost = create_option(
        name="pre_post_data",
        description="Include Pre/Post Market Data?",
        option_type=5,
        required=False,
    )

    index = create_option(
        name="index",
        description="Alert Index",
        option_type=4,
        required=True
    )

    shares = create_option(
        name="shares",
        description="Number of shares traded",
        option_type=3,
        required=True
    )

    share_price = create_option(
        name="share_price",
        description="Price per share",
        option_type=3,
        required=False
    )

    total_price = create_option(
        name="total_price",
        description="Total Price Paid",
        option_type=3,
        required=False
    )


class Stocks(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.S3_BUCKET = os.environ['S3_BUCKET']
        self.ACCESS_KEY_ID = os.environ['ACCESS_KEY_ID']
        self.ACCESS_KEY = os.environ['ACCESS_KEY']

        self.intervals = {
            '1d': '1m',
            '5d': '1m',
            '1mo': '5m',
            '3mo': '1h',
            '6mo': '1h',
            '1y': '1d',
            '2y': '1d',
            '5y': '1d',
            '10y': '1d',
            'ytd': '1h',
            'max': '1d',
        }

        self.channels = {
            'general': self.bot.get_channel(821841802796859406),
        }


        self.alerts_file = 'Alerts.pkl'
        self.trades_file = 'Trades.pkl'
        self.alerts: List[Alert] = self.load(self.alerts_file)
        self.trades: List[Trade] = self.load(self.trades_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f'{self.bot.user} has connected to Discord!')
        logger.info(f'Starting Stock Loop task')
        self.check_stocks.start()

    @cog_ext.cog_subcommand(
        base='Add',
        name='Price_Alert',
        description='Price_Alert',
        guild_ids=GUILD_IDS,
        options=[Options.ticker,
                 Options.trigger_type,
                 Options.trigger_price,
                 Options.prepost]
    )
    async def add_price_alert(self, ctx: SlashContext,
                              ticker: str,
                              trigger_type: str,
                              trigger_price: str,
                              pre_post_data: bool = False):
        value = await self.to_float(trigger_price, ctx)
        if value is not None:
            self.alerts.append(Alert(ticker=ticker, type=trigger_type, value=value, pre_post_data=pre_post_data))
            await ctx.send(f'Price alert added for {ticker} prices {trigger_type} ${value}')
            logger.info(f'Price alert added for {ticker} prices {trigger_type} ${value}')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='Add',
        name='Change_Alert',
        description='Change_Alert',
        guild_ids=GUILD_IDS,
        options=[Options.ticker,
                 Options.change_type,
                 Options.change_value,
                 Options.time_period,
                 Options.prepost]
    )
    async def add_change_alert(self, ctx: SlashContext,
                               ticker: str,
                               change_type: str,
                               change_value: str,
                               time_period: str = '1d',
                               pre_post_data: bool = False):

        value = await self.to_float(change_value, ctx)
        if value is not None:
            self.alerts.append(Alert(ticker=ticker,
                                     type=change_type,
                                     value=value,
                                     time_period=time_period,
                                     pre_post_data=pre_post_data))
            val_text = f'${value}' if change_type == '$' else f'{value}%'
            await ctx.send(f'Change alert added for {ticker} {val_text} over {time_period}')
            logger.info(f'Change alert added for {ticker} {val_text} over {time_period}')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='Reset',
        name='All_Alerts',
        description='Reset All Alerts',
        guild_ids=GUILD_IDS,
        options=[]
    )
    async def reset_all_alerts(self, ctx: SlashContext):
        for alert in self.alerts:
            alert.last_alert = None
        await ctx.send(f'All alerts reset')
        logger.info(f'All alerts reset')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='Reset',
        name='Alerts_By_Ticker',
        description='Reset Ticker Alerts',
        guild_ids=GUILD_IDS,
        options=[Options.ticker]
    )
    async def reset_ticker_alerts(self, ctx: SlashContext, ticker: str):
        for alert in self.alerts:
            if alert.ticker == ticker:
                alert.last_alert = None
        await ctx.send(f'All {ticker} alerts reset')
        logger.info(f'All {ticker} alerts reset')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='Reset',
        name='Alerts_By_Index',
        description='Reset Alerts by index',
        guild_ids=GUILD_IDS,
        options=[Options.index]
    )
    async def reset_index_alerts(self, ctx: SlashContext, index: int):
        if 0 < index < len(self.alerts):
            self.alerts[index].last_alert = None
            await ctx.send(f'{self.alerts[index].ticker} alert reset')
            logger.info(f'{self.alerts[index].ticker} alert reset')
        else:
            await ctx.send(f'Index: {index} out of range')
            logger.error(f'Index: {index} out of range')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='Remove',
        name='All_Alerts',
        description='Reset All Alerts',
        guild_ids=GUILD_IDS,
        options=[]
    )
    async def remove_all_alerts(self, ctx: SlashContext):
        self.alerts = []
        await ctx.send(f'All alerts removed')
        logger.info(f'All alerts removed')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='Remove',
        name='Alerts_By_Ticker',
        description='Remove Ticker Alerts',
        guild_ids=GUILD_IDS,
        options=[Options.ticker]
    )
    async def remove_ticker_alerts(self, ctx: SlashContext, ticker: str):
        old_len = len(self.alerts)
        self.alerts = [alert for alert in self.alerts if alert.ticker != ticker]

        if old_len != len(self.alerts):
            await ctx.send(f'All {ticker} alerts removed')
            logger.info(f'All {ticker} alerts removed')
        else:
            await ctx.send(f'No alerts for {ticker} found')
            logger.warning(f'No alerts for {ticker} found')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='Remove',
        name='Alerts_By_Index',
        description='Remove Alerts by index',
        guild_ids=GUILD_IDS,
        options=[Options.index]
    )
    async def remove_index_alerts(self, ctx: SlashContext, index: int):
        if 0 < index < len(self.alerts):
            alert = self.alerts[index]
            self.alerts.pop(index)
            await ctx.send(f'Removed {alert.ticker} alert')
            logger.info(f'Removed {alert.ticker} alert')
        else:
            await ctx.send(f'Index: {index} out of range')
            logger.error(f'Index: {index} out of range')
        self.save(self.alerts, self.alerts_file)

    @cog_ext.cog_subcommand(
        base='List',
        name='Alerts',
        description='List all active alerts',
        guild_ids=GUILD_IDS,
        options=[]
    )
    async def list_alerts(self, ctx: SlashContext):
        msg = ''
        for index, alert in enumerate(self.alerts):
            msg += f'{index}: {alert.ticker} - {alert.value}{alert.type}\n'
        msg = 'No active alerts' if msg == '' else msg

        await ctx.send(msg)



    @cog_ext.cog_slash(
        name='Buy',
        description='Create Buy Trade',
        guild_ids=GUILD_IDS,
        options=[Options.ticker,
                 Options.shares,
                 Options.share_price,
                 Options.total_price]
    )
    async def buy(self, ctx: SlashContext, ticker: str, shares: str,
                   share_price: str = None, total_price: str = None):

        shares = await self.to_float(shares, ctx)
        share_price = await self.to_float(share_price, ctx)
        total_price = await self.to_float(total_price, ctx)

        if shares is not None:
            if share_price is None and total_price is not None:
                share_price = total_price / shares
            elif share_price is not None and total_price is None:
                total_price = shares * share_price
            elif share_price is None and total_price is None:
                await ctx.send(f'Error: Must have share_price or total_price')
                logger.error(f'Error: Must have share_price or total_price')
            else:
                await ctx.send(f'Error: Can\'t have both share_price and total_price')
                logger.error(f'Error: Can\'t have both share_price and total_price')
        else:
            return
        self.trades.append(Trade(ticker=ticker, share_price=share_price, shares=shares, sell=False))
        await ctx.send(f'Bought {shares} shares of  {ticker} at ${share_price} per share')
        logger.info(f'Bought {shares} shares of  {ticker} at ${share_price} per share')
        self.save(self.trades, self.trades_file)

    @cog_ext.cog_slash(
        name='Sell',
        description='Create Sell Trade',
        guild_ids=GUILD_IDS,
        options=[Options.ticker,
                 Options.shares,
                 Options.share_price,
                 Options.total_price]
    )
    async def sell(self, ctx: SlashContext, ticker: str, shares: str,
                   share_price: str = None, total_price: str = None):

        shares = await self.to_float(shares, ctx)
        share_price = await self.to_float(share_price, ctx)
        total_price = await self.to_float(total_price, ctx)

        if shares is not None:
            if share_price is None and total_price is not None:
                share_price = total_price / shares
            elif share_price is not None and total_price is None:
                total_price = shares * share_price
            elif share_price is None and total_price is None:
                await ctx.send(f'Error: Must have share_price or total_price')
                logger.error(f'Error: Must have share_price or total_price')
            else:
                await ctx.send(f'Error: Can\'t have both share_price and total_price')
                logger.error(f'Error: Can\'t have both share_price and total_price')
        else:
            return
        self.trades.append(Trade(ticker=ticker, share_price=share_price, shares=shares, sell=True))
        await ctx.send(f'Sold {shares} shares of  {ticker} at ${share_price} per share')
        logger.info(f'Sold {shares} shares of  {ticker} at ${share_price} per share')
        self.save(self.trades, self.trades_file)

    @tasks.loop(minutes=1)
    async def check_stocks(self):
        logger.info(f'Checking Stocks')
        channel = self.channels['general']
        for alert in self.alerts:
            try:
                data = yf.download(alert.ticker,
                                   period=alert.time_period,
                                   interval=self.intervals[alert.time_period],
                                   prepost=alert.pre_post_data)
            except:
                logger.error('Could not download data')
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
        self.save(self.alerts, self.alerts_file)

    @staticmethod
    async def to_float(s: Optional[str], ctx: SlashContext) -> Optional[float]:
        if s is None:
            return None
        try:
            return float(s.replace('$', '').replace('%', ''))
        except ValueError:
            await ctx.send(f'Error: Could not convert "{s}" to number')
            logger.error(f'Error: Could not convert "{s}" to number')
            return None

    def save(self, obj, file_name):
        try:
            logger.info(f'Saving {file_name} to s3')
            with open(file_name, 'wb') as f:
                pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)
            s3 = boto3.client('s3', aws_access_key_id=self.ACCESS_KEY_ID, aws_secret_access_key=self.ACCESS_KEY)
            s3.upload_file(file_name, self.S3_BUCKET, file_name)
        except:
            logger.error('Could not save file to s3')

    def load(self, file_name) -> Any:
        try:
            logger.info(f'Loading {file_name} from s3')
            s3 = boto3.client('s3', aws_access_key_id=self.ACCESS_KEY_ID, aws_secret_access_key=self.ACCESS_KEY)
            s3.download_file(self.S3_BUCKET, file_name, file_name)
            with open(file_name, 'rb') as f:
                return pickle.load(f)
        except:
            logger.error('Could not load file from s3')
            return []


def setup(bot):
    bot.add_cog(Stocks(bot))
