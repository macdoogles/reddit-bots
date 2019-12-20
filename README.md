# /r/nyknicks bots

A reddit bot that manages the [/r/nyknicks](https://www.reddit.com/r/NYKnicks/)
sidebar.

## Prerequisites
* [Set up your python environment](https://cloud.google.com/python/setup)
* Use Python3 (virtualenv --python python3 env)
* A praw.ini file (not submitted) with the following contents:

        [nyknicks-sidebarbot]
        client_id=(from reddit.com/prefs/apps)
        client_secret=(from reddit.com/prefs/apps)
        password=(mod password)
        username=(mod username)

## Running locally:

    $ pip install --user --upgrade virtualenv
    $ cd your/project
    $ virtualenv --python python3 env
    $ source env/bin/activate
    $ pip install -r requirements.txt
    $ python sidebarbot.py
    $ deactivate  # to end virtualenv
