#!/usr/bin/env pipenv-shebang
import argparse
import datetime as dt
import os

from dotenv import load_dotenv

from model import init_db, GarminStat


def get_garmin_stats(db):
    data = []
    for row in db.query(GarminStat).all():
        row_dict = {'date': row.date, 'total_steps': row.total_steps, 'step_goal': row.step_goal,
                    'met_step_goal': (row.total_steps >= row.step_goal) and (row.step_goal != 0)}
        data.append(row_dict)
    return data


def print_ytd(data, end_date=None):
    goal_dict = {True: len([x for x in data if x['met_step_goal']]),
                 False: len([x for x in data if not x['met_step_goal']])}
    total_steps = int(sum([x['total_steps'] for x in data]))
    end_date = dt.date.fromisoformat(end_date) if end_date else dt.date.today() - dt.timedelta(days=1)

    current_data = [x for x in data if dt.date(end_date.year, 1, 1) <= x['date'] <= end_date]
    ytd_dict = {True: len([x for x in current_data if x['met_step_goal']]),
                False: len([x for x in current_data if not x['met_step_goal']])}
    ytd_steps = int(sum([x['total_steps'] for x in current_data]))
    
    print(f'{ytd_dict.get(True, 0):,} of {ytd_dict.get(True, 0) + ytd_dict.get(False, 0):,} '
          f'({ytd_dict.get(True, 0) / (ytd_dict.get(True, 0) + ytd_dict.get(False, 0)) * 100:.2f}%) this year')
    print(f'{goal_dict.get(True, 0):,} of {goal_dict.get(True, 0) + goal_dict.get(False, 0):,} '
          f'({goal_dict.get(True, 0) / (goal_dict.get(True, 0) + goal_dict.get(False, 0)) * 100:.2f}%) total lifetime')
    print(f'{goal_dict.get(True, 0) - ytd_dict.get(True, 0):,} of {len(data) - len(current_data):,} '
          f'({(goal_dict.get(True, 0) - ytd_dict.get(True, 0)) / (len(data) - len(current_data)) * 100:.2f}%) '
          f'year start\n')
    
    print(f'{ytd_steps:,} steps this year ({ytd_steps / len(current_data):,.0f} / day avg)')
    print(f'{total_steps:,} steps total ({total_steps / len(data):,.0f} / day avg)')
    print(f'{total_steps - ytd_steps:,} year start '
          f'({(total_steps - ytd_steps) / (len(data) - len(current_data)):,.0f} / day avg)\n')
    print(f'Data through {end_date.isoformat()}')
    
    year_goal = 5000000
    goal_pace = (year_goal / 365)*len(current_data)
    pace_diff = ytd_steps - goal_pace
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
