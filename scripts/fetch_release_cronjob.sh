#!/bin/sh

# this script is intended to be run from a crontab owned by the
# www-data user on ArduPilot's autotest server

# CBS_REMOTES_RELOAD_TOKEN *must* be supplied as an environment
# variable in the crontab line, for example:

# 0 * * * * CBS_REMOTES_RELOAD_TOKEN=8d64ed06945 /home/custom/beta/CustomBuild/scripts/fetch_release_cronjob.sh

python3 /home/custom/beta/CustomBuild/scripts/fetch_releases.py \
	--out /home/custom/beta/base/configs/remotes.json \
	--appurl https://custom-beta.ardupilot.org/refresh_remotes \
	>> /home/beta/cron/fetch_releases_py.log 2>&1
