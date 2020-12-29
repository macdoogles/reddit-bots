from datetime import datetime, timedelta
from optparse import OptionParser
from pytz import timezone
from services import nba_data
from time import sleep

import dateutil.parser
import logging
import logging.config
import praw
import pytz
import re
import sys
import traceback

EASTERN_TIMEZONE = timezone('US/Eastern')
UTC = timezone('UTC')

TEAM_SUB_MAP = {
  '76ers': 'sixers',
  'Bucks': 'MkeBucks',
  'Bulls': 'chicagobulls',
  'Cavaliers': 'clevelandcavs',
  'Celtics': 'bostonceltics',
  'Clippers': 'LAClippers',
  'Grizzlies': 'memphisgrizzlies',
  'Hawks': 'AtlantaHawks',
  'Heat': 'heat',
  'Hornets': 'CharlotteHornets',
  'Jazz': 'UtahJazz',
  'Kings': 'kings',
  'Knicks': 'NYKnicks',
  'Lakers': 'lakers',
  'Magic': 'OrlandoMagic',
  'Mavericks': 'mavericks',
  'Nets': 'GoNets',
  'Nuggets': 'denvernuggets',
  'Pacers': 'pacers',
  'Pelicans': 'NOLAPelicans',
  'Pistons': 'DetroitPistons',
  'Raptors': 'torontoraptors',
  'Rockets': 'rockets',
  'Spurs': 'NBASpurs',
  'Suns': 'suns',
  'Thunder': 'thunder',
  'Timberwolves': 'timberwolves',
  'Trail Blazers': 'ripcity',
  'Warriors': 'warriors',
  'Wizards': 'washingtonwizards',
}

logging.config.fileConfig('logging.conf')
logger = logging.getLogger('sidebarbot')


def build_roster(year):
  current_year = nba_data.current_year()
  players = nba_data.players(year)
  roster = nba_data.roster('knicks')
  team_players = filter(lambda player: player['personId'] in roster, players)

  rows = []
  for player in team_players:
    name = f'{player["firstName"]} {player["lastName"]}'
    jersey = player['jersey']
    position = player['pos'].replace('-', '/') if player['pos'] else ''
    rows.append(f'{name}|{jersey}|{position}')
  rows.sort()

  rows.insert(0, ':--|:--:|:--:')
  rows.insert(0, 'Name|No.|Position')
  return '\n'.join(rows)


def build_schedule(teams, year):
  schedule = nba_data.schedule('knicks', year)

  logger.info('Building schedule text.')
  # FYI: We want to show to a show a total of 12 games: 
  #    most recent + 4 prior + 7 next.
  # Get the array index of the last game played.
  last_played_idx = schedule['league']['lastStandardGamePlayedIndex']

  # Get the next 7 games.
  end_idx = min(last_played_idx + 7, len(schedule['league']['standard']))

  # Show the previous 4 games or more if we're at the end of the season.
  start_idx = max(0, last_played_idx - (4 + (7 - (end_idx - last_played_idx - 1))))

  rows = ['Date|Team|Loc|Time/Outcome', ':--:|:--:|:--:|:--:']
  for i in range(start_idx, end_idx):
    game = schedule['league']['standard'][i]
    is_home_team = game['isHomeTeam']
    knicks_score = game['hTeam' if is_home_team else 'vTeam']
    opp_score = game['vTeam' if is_home_team else 'hTeam']
    opp_team_name = teams[opp_score['teamId']]['nickname']
    opp_team_sub = TEAM_SUB_MAP[opp_team_name]

    gametime = dateutil.parser \
        .parse(game['startTimeUTC']) \
        .astimezone(EASTERN_TIMEZONE)
    today = datetime.now(UTC).astimezone(EASTERN_TIMEZONE).date()
    if gametime.date() == today:
      date = 'Today'
    elif gametime.date() == today - timedelta(days=1):
      date = 'Yesterday'
    elif gametime.date() == today + timedelta(days=1):
      date = 'Tomorrow'
    else:
      date = gametime.strftime('%b %d')

    time = gametime.strftime('%I:%M %p').lstrip('0')
    time_or_score = (time if knicks_score['score'] == ''
        else winloss(knicks_score, opp_score))

    row = ('%s|[](/r/%s)|%s|%s' %
        (date, opp_team_sub, 
            'Home' if is_home_team else 'Away', time_or_score))
    rows.append(row)
  return '\n'.join(rows)


def build_standings(teams):
  standings = nba_data.conference_standings()
  logger.info('Building standings text.')
  division = standings['conference']['east']
  return print_standings(teams, division)


def build_tank_standings(teams):
  standings = nba_data.conference_standings()
  logger.info('Building tank standings text.')
  rows = standings['conference']['east']
  rows = rows + standings['conference']['west']
  rows = sorted(rows, key=lambda team: float(team['lossPct']), reverse=True)
  worst_wins = int(rows[0]['win'])
  worst_loss = int(rows[0]['loss'])
  for row in rows:
     gb = (abs(worst_wins - int(row['win'])) + abs(worst_loss - int(row['loss']))) / 2
     row['gamesBehind'] = ('%.1f' % gb).replace('.0', '')
  return print_standings(teams, rows[:10])


def print_standings(teams, standings):
  rows = [' | | |Record|GB', ':--:|:--:|:--|:--:|:--:']
  for i, d in enumerate(standings):
    team = teams[d['teamId']]['nickname']
    teamsub = TEAM_SUB_MAP[team]
    wins = d['win']
    loses = d['loss']
    games_behind = d['gamesBehind']
    games_behind = '-' if games_behind == '0' else games_behind
    row = ('%s|[](/r/%s)|%s|%s-%s|%s' %
        (i + 1, teamsub, team, wins, loses, games_behind))
    rows.append(row)
  return '\n'.join(rows)


def update_reddit_descr(descr, text, marker):
  start_marker = f'[](#Start{marker})'
  start = descr.index(start_marker)
  end_marker = f'[](#End{marker})'
  end = descr.index(end_marker) + len(end_marker)
  new_text = f'{start_marker}\n\n{text}\n\n{end_marker}'
  return descr.replace(descr[start:end], new_text)


def winloss(knicks_score, opp_score):
  kscore = int(knicks_score['score'])
  oscore = int(opp_score['score'])
  return ('W %s-%s' % (kscore, oscore) 
      if kscore > oscore else 'L %s-%s' % (oscore, kscore))


def execute(subreddit_name, tanking):
  current_year = nba_data.current_year()
  roster = build_roster(current_year)
  teams = nba_data.teams(current_year)
  schedule = build_schedule(teams, current_year)
  standings = build_tank_standings(teams) \
      if tanking else build_standings(teams)

  logger.info('Logging in to reddit.')
  reddit = praw.Reddit('nyknicks-sidebarbot', user_agent='python-praw')

  logger.info('Querying reddit settings.')
  subreddit = reddit.subreddit(subreddit_name)
  descr = subreddit.mod.settings()['description']
  updated_descr = update_reddit_descr(descr, schedule, 'Schedule')
  updated_descr = update_reddit_descr(updated_descr, standings, 'Standings')
  updated_descr = update_reddit_descr(updated_descr, roster, 'Roster')

  if updated_descr != descr:
    logger.info('Updating reddit settings.')
    subreddit.mod.update(description=updated_descr)
  else:
    logger.info('No changes.')

  logger.info('All done.')


if __name__ == "__main__":
  parser = OptionParser()
  parser.add_option(
      "-t", 
      "--tank_standings", 
      dest="tank",
      help="Print the race to be worst instead of best, if enabled.",
      metavar='yes|no')
  (options, args) = parser.parse_args()

  if len(args) != 1:
    logger.error(f'Invalid command line arguments: {args}')
    raise SystemExit(f'Usage: {sys.argv[0]} subreddit')

  subreddit_name = args[0]
  logger.info(f'Using subreddit: {subreddit_name}')

  yes = set(['yes', 'y', 'true'])
  tank_standings = True \
      if options.tank and options.tank.lower() in yes else False
  logger.info(f'Print tank standings: {tank_standings}')

  try:
    execute(subreddit_name, tank_standings)
  except:
    logger.error(traceback.format_exc())
