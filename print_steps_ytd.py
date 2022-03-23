#!/usr/bin/env pipenv-shebang
import argparse
import datetime as dt
import os

import pandas as pd
from dotenv import load_dotenv

from model import init_db


def get_garmin_stats(db):
    df = pd.read_sql_query('select date, day_of_week, total_steps, step_goal from garmin_stats;', db.bind)
    df['date'] = pd.to_datetime(df.date)
    df['met_step_goal'] = (df.total_steps >= df.step_goal) & (df.step_goal != 0)
    return df


def print_ytd(df, end_date=None):
    goal_dict = df.met_step_goal.value_counts().to_dict()
    total_steps = int(sum(df.total_steps))
    end_date = dt.date.fromisoformat(end_date) if end_date else dt.date.today() - dt.timedelta(days=1)

    current_year = df[(df.date >= pd.to_datetime(dt.date(end_date.year, 1, 1))) & (df.date <= pd.to_datetime(end_date))]
    ytd_dict = current_year.met_step_goal.value_counts().to_dict()
    ytd_steps = int(sum(current_year.total_steps))
    
    print(f'{ytd_dict.get(True, 0):,} of {ytd_dict.get(True, 0) + ytd_dict.get(False, 0):,} '
          f'({ytd_dict.get(True, 0) / (ytd_dict.get(True, 0) + ytd_dict.get(False, 0)) * 100:.2f}%) this year')
    print(f'{goal_dict.get(True, 0):,} of {goal_dict.get(True, 0) + goal_dict.get(False, 0):,} '
          f'({goal_dict.get(True, 0) / (goal_dict.get(True, 0) + goal_dict.get(False, 0)) * 100:.2f}%) total lifetime')
    print(f'{goal_dict.get(True, 0) - ytd_dict.get(True, 0):,} of {len(df) - len(current_year):,} '
          f'({(goal_dict.get(True, 0) - ytd_dict.get(True, 0)) / (len(df) - len(current_year)) * 100:.2f}%) '
          f'year start\n')
    
    print(f'{ytd_steps:,} steps this year ({ytd_steps / len(current_year):,.0f} / day avg)')
    print(f'{total_steps:,} steps total ({total_steps / len(df):,.0f} / day avg)')
    print(f'{total_steps - ytd_steps:,} year start '
          f'({(total_steps - ytd_steps) / (len(df) - len(current_year)):,.0f} / day avg)\n')
    print(f'Data through {end_date.isoformat()}')
    
    year_goal = 5000000
    goal_pace = (year_goal / 365)*len(current_year)
    pace_diff = current_year.total_steps.sum() - goal_pace
    print(f'\nPace for year\'s goal is {goal_pace:,.0f} ({"" if pace_diff < 0 else "+"}{pace_diff:,.0f})')
    print(f'Need {year_goal - ytd_steps:,} more steps this year (avg of '
          f'{int((year_goal - ytd_steps) / (365 - ytd_dict.get(True, 0) - ytd_dict.get(False, 0))):,} per day)')


if __name__ == '__main__':
    load_dotenv()
    if not os.getenv('GARMIN_DATABASE_PATH'):
        raise KeyError('Please make sure GARMIN_DATABASE_PATH is set in the environment variables')
    arg_parser = argparse.ArgumentParser(prog='print_ytd_stats', description='Pretty print my step stats ytd')
    arg_parser.add_argument('-e', '--end_date', default=None, help='End date for the stats')
    args = arg_parser.parse_args()

    session = init_db(os.getenv('GARMIN_DATABASE_PATH'))
    print_ytd(get_garmin_stats(session), args.end_date)
    session.close()
