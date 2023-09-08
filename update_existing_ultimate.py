#!/usr/bin/env pipenv-shebang
import os

from dotenv import load_dotenv

from get_stats import update_activities
from model import init_db, Activity

if __name__ == '__main__':
    load_dotenv()

    db = init_db(os.getenv('GARMIN_DATABASE_PATH'))
    ultimate_acts = db.query(Activity).filter_by(activity_type_type_id='11').all()
    update_activities(ultimate_acts, 213, True)
    for ulti_act in ultimate_acts:
        ulti_act.activity_type_type_id = 213
        ulti_act.activity_type_type_key = 'ultimate_disc'
        ulti_act.activity_type_parent_type_id = 206
        db.add(ulti_act)
    db.commit()
    db.close()
    print('done')
